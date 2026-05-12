"""APM (Application Performance Monitoring) commands."""

import click
import json
from rich.console import Console
from rich.table import Table
from ddogctl.client import get_datadog_client
from ddogctl.utils.error import handle_api_error
from ddogctl.utils.time import parse_time_range, to_utc_iso
from ddogctl.utils.spans import aggregate_spans

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
            duration_ms = (attrs.duration / 1_000_000) if hasattr(attrs, "duration") else 0

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
            duration_ms = (attrs.duration / 1_000_000) if hasattr(attrs, "duration") else 0
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
