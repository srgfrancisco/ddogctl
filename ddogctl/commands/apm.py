"""APM (Application Performance Monitoring) commands."""

import click
import json
import sys
from datetime import datetime
from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.tree import Tree
from ddogctl.client import get_datadog_client
from ddogctl.utils.error import handle_api_error
from ddogctl.utils.exit_codes import NOT_FOUND
from ddogctl.utils.time import parse_time_range, to_utc_iso
from ddogctl.utils.spans import (
    aggregate_spans,
    get_span_field,
    search_spans,
    span_duration_ms,
    span_to_dict,
)

console = Console()


@click.group()
def apm():
    """APM (Application Performance Monitoring) commands."""
    pass


@apm.command(name="services")
@click.option("--format", type=click.Choice(["json", "table"]), default="table")
@handle_api_error
def list_services(format):
    """List all APM services."""
    client = get_datadog_client()

    with console.status("[cyan]Fetching APM services...[/cyan]"):
        response = client.service_definitions.list_service_definitions(page_size=100)

    services = []
    for item in response.data or []:
        schema = item.attributes.schema
        services.append(
            {
                "name": schema.dd_service,
                "team": getattr(schema, "team", ""),
                "type": getattr(schema, "type", ""),
                "languages": getattr(schema, "languages", []),
            }
        )

    if format == "json":
        print(json.dumps(services, indent=2))
    else:
        table = Table(title="APM Services")
        table.add_column("Service", style="cyan")
        table.add_column("Team", style="white")
        table.add_column("Type", style="dim")
        table.add_column("Languages", style="yellow")
        for svc in sorted(services, key=lambda s: s["name"]):
            table.add_row(
                svc["name"],
                svc["team"],
                svc["type"],
                ", ".join(svc["languages"]) if svc["languages"] else "",
            )
        console.print(table)
        console.print(f"\n[dim]Total services: {len(services)}[/dim]")


@apm.command(name="traces")
@click.argument("service")
@click.option("--from", "from_time", default="1h", help="Start time (e.g., 1h, 24h, 7d)")
@click.option("--to", "to_time", default="now", help="End time")
@click.option("--limit", default=50, type=int, help="Max traces (max: 1000)")
@click.option("--filter", "extra_filter", help="Additional filter query")
@click.option("--format", type=click.Choice(["json", "table"]), default="table")
@handle_api_error
def search_traces(service, from_time, to_time, limit, extra_filter, format):
    """Search traces for a service.

    Rate limit: 300 requests/hour for spans API.
    """
    client = get_datadog_client()

    # Parse time range
    from_ts, to_ts = parse_time_range(from_time, to_time)
    from_str = to_utc_iso(from_ts)
    to_str = to_utc_iso(to_ts)

    # Build query
    query = f"service:{service}"
    if extra_filter:
        query = f"{query} {extra_filter}"

    with console.status(f"[cyan]Searching traces for {service}...[/cyan]"):
        response = client.spans.list_spans_get(
            filter_query=query, filter_from=from_str, filter_to=to_str, page_limit=limit
        )

    spans = response.data if response.data else []

    if format == "json":
        output = []
        for span in spans:
            attrs = span.attributes
            duration_ms = span_duration_ms(span)

            output.append(
                {
                    "trace_id": attrs.trace_id,
                    "span_id": attrs.span_id,
                    "service": attrs.service,
                    "resource": attrs.resource_name,
                    "duration_ms": round(duration_ms, 2),
                    "timestamp": (
                        attrs.start_timestamp.isoformat() if attrs.start_timestamp else None
                    ),
                }
            )
        print(json.dumps(output, indent=2))
    else:
        table = Table(title=f"Traces for {service}")
        table.add_column("Trace ID", style="cyan", width=18)
        table.add_column("Resource", style="white", min_width=30)
        table.add_column("Duration (ms)", justify="right", style="yellow", width=15)
        table.add_column("Time", style="dim", width=12)

        for span in spans:
            attrs = span.attributes
            duration_ms = span_duration_ms(span)
            time_str = (
                attrs.start_timestamp.strftime("%H:%M:%S") if attrs.start_timestamp else "N/A"
            )

            table.add_row(
                attrs.trace_id[:16] + "..", attrs.resource_name[:45], f"{duration_ms:.2f}", time_str
            )

        console.print(table)
        console.print(f"\n[dim]Total traces: {len(spans)}[/dim]")


@apm.command(name="analytics")
@click.argument("service")
@click.option("--from", "from_time", default="1h", help="Start time (e.g., 1h, 24h, 7d)")
@click.option("--to", "to_time", default="now", help="End time")
@click.option("--metric", default="count", help="Metric (count, p99, avg, sum)")
@click.option("--group-by", help="Group by field (e.g., resource_name, @http.status_code)")
@click.option("--format", type=click.Choice(["json", "table"]), default="table")
@handle_api_error
def analytics(service, from_time, to_time, metric, group_by, format):
    """APM analytics and aggregations.

    Compute metrics (count, p99, avg, sum) across traces, optionally grouped by dimensions.
    """
    client = get_datadog_client()

    # Parse time range
    from_ts, to_ts = parse_time_range(from_time, to_time)
    from_str = to_utc_iso(from_ts)
    to_str = to_utc_iso(to_ts)

    # Build filter (as dict)
    filter_dict = {"query": f"service:{service}", "from": from_str, "to": to_str}

    # Configure compute (as dict)
    if metric == "count":
        compute_dict = {"aggregation": "count"}
    elif metric == "p99":
        compute_dict = {"aggregation": "pc99", "metric": "@duration"}
    elif metric == "avg":
        compute_dict = {"aggregation": "avg", "metric": "@duration"}
    elif metric == "sum":
        compute_dict = {"aggregation": "sum", "metric": "@duration"}
    else:
        compute_dict = {"aggregation": "count"}

    # Configure group-by (as list of dicts)
    group_by_list = [{"facet": group_by}] if group_by else []

    with console.status(f"[cyan]Computing analytics for {service}...[/cyan]"):
        response = aggregate_spans(client, filter_dict, [compute_dict], group_by_list)

    buckets = response.data.buckets if response.data else []

    if format == "json":
        output = []
        for bucket in buckets:
            result = bucket.by.copy() if bucket.by else {}
            # Extract metric value
            if bucket.computes:
                value = list(bucket.computes.values())[0]
                # Convert duration from ns to ms
                if metric in ["p99", "avg", "sum"]:
                    result[metric] = round(value / 1_000_000, 2)
                else:
                    result[metric] = value
            output.append(result)
        print(json.dumps(output, indent=2))
    else:
        title = f"Analytics for {service} ({metric})"
        if group_by:
            title += f" by {group_by}"

        table = Table(title=title)
        if group_by:
            table.add_column(group_by.replace("@", ""), style="cyan")

        metric_label = metric.upper()
        if metric in ["p99", "avg", "sum"]:
            metric_label += " (ms)"
        table.add_column(metric_label, justify="right", style="yellow")

        for bucket in buckets:
            row = []
            if bucket.by and group_by:
                row.append(str(bucket.by.get(group_by, "N/A")))

            if bucket.computes:
                value = list(bucket.computes.values())[0]
                if metric in ["p99", "avg", "sum"]:
                    value = value / 1_000_000
                row.append(f"{value:.2f}")

            table.add_row(*row)

        console.print(table)
        console.print(f"\n[dim]Total groups: {len(buckets)}[/dim]")


@apm.group()
def spans():
    """Search individual APM spans."""
    pass


@spans.command(name="search")
@click.argument("query")
@click.option("--from", "from_time", default="1h", help="Start time (e.g., 1h, 24h, 7d)")
@click.option("--to", "to_time", default="now", help="End time")
@click.option("--limit", default=50, type=int, help="Max spans; paginates past 1000")
@click.option(
    "--sort",
    type=click.Choice(["-timestamp", "timestamp"]),
    default="-timestamp",
    help="Sort order (the API only sorts by timestamp)",
)
@click.option(
    "--field",
    "fields",
    multiple=True,
    help="Extra column: @path for custom attributes (e.g. @messaging.destination) "
    "or a top-level attribute (e.g. trace_id). Repeatable.",
)
@click.option("--format", type=click.Choice(["json", "table"]), default="table")
@handle_api_error
def search_spans_cmd(query, from_time, to_time, limit, sort, fields, format):
    """Search spans with any span query.

    QUERY uses Datadog span search syntax, e.g. 'service:worker @job.name:SyncJob'
    or 'service:mysql @duration:>1s'. JSON output includes every span attribute
    (parent_id, tags, custom attributes) plus duration_ms.

    Rate limit: 300 requests/hour for spans API.
    """
    client = get_datadog_client()
    from_ts, to_ts = parse_time_range(from_time, to_time)

    with console.status("[cyan]Searching spans...[/cyan]"):
        results, truncated = search_spans(
            client, query, to_utc_iso(from_ts), to_utc_iso(to_ts), limit, sort
        )

    span_dicts = [span_to_dict(s) for s in results]

    if format == "json":
        if fields:
            for d in span_dicts:
                d["fields"] = {f: get_span_field(d, f) for f in fields}
        print(json.dumps(span_dicts, indent=2, default=str))
        return

    if not span_dicts:
        console.print(f"[yellow]No spans found for query: {escape(query)}[/yellow]")
        return

    table = Table(title=f"Spans: {escape(query)}")
    table.add_column("Time", style="dim", no_wrap=True)
    table.add_column("Service", style="cyan")
    table.add_column("Resource", style="white", max_width=50)
    table.add_column("Duration (ms)", justify="right", style="yellow")
    for f in fields:
        table.add_column(escape(f), style="green")

    for d in span_dicts:
        row = [
            (d.get("start_timestamp") or "")[11:23],
            d.get("service", ""),
            escape(str(d.get("resource_name", ""))),
            f"{d['duration_ms']:.2f}",
        ]
        for f in fields:
            value = get_span_field(d, f)
            row.append("" if value is None else escape(str(value)))
        table.add_row(*row)

    console.print(table)
    console.print(f"\n[dim]Total spans: {len(span_dicts)}[/dim]")
    if truncated:
        console.print("[dim]More spans match; raise --limit to fetch them.[/dim]")


@apm.command(name="trace")
@click.argument("trace_id")
@click.option("--from", "from_time", default="24h", help="Start time (e.g., 1h, 24h, 7d)")
@click.option("--to", "to_time", default="now", help="End time")
@click.option("--limit", default=1000, type=int, help="Max spans to fetch")
@click.option("--format", type=click.Choice(["json", "table"]), default="table")
@handle_api_error
def trace(trace_id, from_time, to_time, limit, format):
    """Show every indexed span of a trace as a tree, with its root span.

    Only indexed spans are returned. When a span's parent was not indexed, it is
    shown as a top-level span and marked "parent not indexed".

    Rate limit: 300 requests/hour for spans API.
    """
    client = get_datadog_client()
    from_ts, to_ts = parse_time_range(from_time, to_time)

    with console.status(f"[cyan]Fetching trace {trace_id}...[/cyan]"):
        results, truncated = search_spans(
            client,
            f"trace_id:{trace_id}",
            to_utc_iso(from_ts),
            to_utc_iso(to_ts),
            limit,
            sort="timestamp",
        )

    if not results:
        console.print(
            f"[yellow]No spans found for trace {escape(trace_id)} "
            f"between {from_time} and {to_time}. Try a wider --from.[/yellow]"
        )
        sys.exit(NOT_FOUND)

    span_dicts = [span_to_dict(s) for s in results]
    span_ids = {d.get("span_id") for d in span_dicts}
    children: dict = {}
    roots = []
    for d in span_dicts:
        parent = d.get("parent_id")
        if not parent or parent == "0":
            d["parent_indexed"] = None
            roots.append(d)
        elif parent in span_ids:
            d["parent_indexed"] = True
            children.setdefault(parent, []).append(d)
        else:
            d["parent_indexed"] = False
            roots.append(d)

    def assign_depth(node, depth):
        node["depth"] = depth
        for child in children.get(node.get("span_id"), []):
            assign_depth(child, depth + 1)

    for root in roots:
        assign_depth(root, 0)

    starts = [d["start_timestamp"] for d in span_dicts if d.get("start_timestamp")]
    ends = [d["end_timestamp"] for d in span_dicts if d.get("end_timestamp")]
    total_ms = max(span_dicts, key=lambda d: d["duration_ms"])["duration_ms"]
    if starts and ends:
        span_total = datetime.fromisoformat(max(ends)) - datetime.fromisoformat(min(starts))
        total_ms = round(span_total.total_seconds() * 1000, 2)

    if format == "json":
        output = {
            "trace_id": trace_id,
            "span_count": len(span_dicts),
            "duration_ms": total_ms,
            "truncated": truncated,
            "root_span_ids": [r.get("span_id") for r in roots],
            "spans": span_dicts,
        }
        print(json.dumps(output, indent=2, default=str))
        return

    def label(d):
        text = (
            f"[cyan]{escape(str(d.get('service', '')))}[/cyan] "
            f"[dim]{escape(str(d.get('operation_name', '')))}[/dim] "
            f"{escape(str(d.get('resource_name', ''))[:80])} "
            f"[yellow]{d['duration_ms']:.2f} ms[/yellow]"
        )
        if d["parent_indexed"] is False:
            text += f" [dim](parent {escape(str(d.get('parent_id')))} not indexed)[/dim]"
        return text

    def add_children(branch, node):
        for child in children.get(node.get("span_id"), []):
            add_children(branch.add(label(child)), child)

    tree = Tree(f"[bold]Trace {escape(trace_id)}[/bold]")
    for root in roots:
        add_children(tree.add(f"[bold]{label(root)}[/bold]"), root)

    console.print(tree)
    console.print(
        f"\n[dim]{len(span_dicts)} spans · {total_ms:.2f} ms · {len(roots)} root(s)[/dim]"
    )
    if truncated:
        console.print(f"[yellow]Trace has more than {limit} spans; raise --limit.[/yellow]")
