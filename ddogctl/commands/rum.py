"""RUM (Real User Monitoring) commands."""

import click
import json
from rich.console import Console
from rich.table import Table
from ddogctl.client import get_datadog_client
from ddogctl.utils.error import handle_api_error
from ddogctl.utils.time import parse_time_range, to_utc_iso

console = Console()

EVENT_TYPE_COLORS = {
    "error": "red",
    "action": "yellow",
    "view": "cyan",
    "resource": "dim",
    "long_task": "magenta",
}


def _format_rum_event(event):
    """Extract fields from a RUM event."""
    attrs = event.attributes
    return {
        "id": event.id,
        "type": getattr(attrs, "type", getattr(event, "type", "unknown")),
        "timestamp": str(attrs.timestamp) if hasattr(attrs, "timestamp") else None,
        "attributes": attrs.attributes if hasattr(attrs, "attributes") else {},
        "tags": attrs.tags if hasattr(attrs, "tags") else [],
    }


@click.group()
def rum():
    """RUM (Real User Monitoring) commands."""
    pass


@rum.command(name="events")
@click.option("--query", default="*", help="RUM event query (default: *)")
@click.option("--from", "from_time", default="1h", help="Start time (e.g., 1h, 24h, 7d)")
@click.option("--to", "to_time", default="now", help="End time")
@click.option("--limit", default=50, type=int, help="Max events to return (max: 1000)")
@click.option("--format", type=click.Choice(["json", "table"]), default="table")
@handle_api_error
def list_events(query, from_time, to_time, limit, format):
    """Search RUM events.

    Rate limit: 300 requests/hour for RUM API.
    """
    client = get_datadog_client()

    # Parse time range
    from_ts, to_ts = parse_time_range(from_time, to_time)
    from_str = to_utc_iso(from_ts)
    to_str = to_utc_iso(to_ts)

    with console.status("[cyan]Searching RUM events...[/cyan]"):
        response = client.rum.list_rum_events(
            filter_query=query,
            filter_from=from_str,
            filter_to=to_str,
            page_limit=limit,
        )

    events = response.data if response.data else []

    if format == "json":
        output = [_format_rum_event(event) for event in events]
        print(json.dumps(output, indent=2, default=str))
    else:
        table = Table(title="RUM Events")
        table.add_column("Time", style="dim", width=20)
        table.add_column("Type", width=12)
        table.add_column("ID", style="cyan", width=18)
        table.add_column("Details", style="white")

        for event in events:
            attrs = event.attributes
            time_str = str(attrs.timestamp) if hasattr(attrs, "timestamp") else "N/A"
            if hasattr(attrs, "timestamp") and hasattr(attrs.timestamp, "strftime"):
                time_str = attrs.timestamp.strftime("%Y-%m-%d %H:%M:%S")

            event_type = getattr(attrs, "type", getattr(event, "type", "unknown"))
            color = EVENT_TYPE_COLORS.get(str(event_type), "white")
            type_styled = f"[{color}]{event_type}[/{color}]"

            event_attrs = attrs.attributes if hasattr(attrs, "attributes") else {}
            details = str(event_attrs)[:60] if event_attrs else ""

            table.add_row(
                time_str,
                type_styled,
                str(event.id)[:16] + ".." if len(str(event.id)) > 16 else str(event.id),
                details,
            )

        console.print(table)
        console.print(f"\n[dim]Total events: {len(events)}[/dim]")


@rum.command(name="analytics")
@click.option("--query", default="*", help="RUM event query (default: *)")
@click.option(
    "--metric",
    default="count",
    type=click.Choice(["count", "p99", "avg"]),
    help="Metric (count, p99, avg)",
)
@click.option("--group-by", help="Group by field (e.g., @type, @view.url, @geo.country)")
@click.option("--from", "from_time", default="1h", help="Start time (e.g., 1h, 24h, 7d)")
@click.option("--to", "to_time", default="now", help="End time")
@click.option("--format", type=click.Choice(["json", "table"]), default="table")
@handle_api_error
def analytics(query, metric, group_by, from_time, to_time, format):
    """RUM analytics and aggregations.

    Compute metrics (count, p99, avg) across RUM events, optionally grouped by dimensions.
    """
    client = get_datadog_client()

    # Parse time range
    from_ts, to_ts = parse_time_range(from_time, to_time)
    from_str = to_utc_iso(from_ts)
    to_str = to_utc_iso(to_ts)

    # Build filter
    filter_dict = {"query": query, "from": from_str, "to": to_str}

    # Configure compute
    if metric == "count":
        compute_dict = {"aggregation": "count"}
    elif metric == "p99":
        compute_dict = {"aggregation": "pc99", "metric": "@view.time_spent"}
    elif metric == "avg":
        compute_dict = {"aggregation": "avg", "metric": "@view.time_spent"}
    else:
        compute_dict = {"aggregation": "count"}

    # Configure group-by
    group_by_list = [{"facet": group_by}] if group_by else []

    # Build request body
    body = {
        "filter": filter_dict,
        "compute": [compute_dict],
        "group_by": group_by_list,
    }

    with console.status("[cyan]Computing RUM analytics...[/cyan]"):
        response = client.rum.aggregate_rum_events(body=body)

    buckets = response.data.buckets if response.data else []

    if format == "json":
        output = []
        for bucket in buckets:
            result = bucket.by.copy() if bucket.by else {}
            if bucket.computes:
                value = list(bucket.computes.values())[0]
                # Convert duration from ns to ms for time metrics
                if metric in ["p99", "avg"]:
                    result[metric] = round(value / 1_000_000, 2)
                else:
                    result[metric] = value
            output.append(result)
        print(json.dumps(output, indent=2))
    else:
        title = f"RUM Analytics ({metric})"
        if group_by:
            title += f" by {group_by}"

        table = Table(title=title)
        if group_by:
            table.add_column(group_by.replace("@", ""), style="cyan")

        metric_label = metric.upper()
        if metric in ["p99", "avg"]:
            metric_label += " (ms)"
        table.add_column(metric_label, justify="right", style="yellow")

        for bucket in buckets:
            row = []
            if bucket.by and group_by:
                row.append(str(bucket.by.get(group_by, "N/A")))

            if bucket.computes:
                value = list(bucket.computes.values())[0]
                if metric in ["p99", "avg"]:
                    value = value / 1_000_000
                row.append(f"{value:.2f}")

            table.add_row(*row)

        console.print(table)
        console.print(f"\n[dim]Total groups: {len(buckets)}[/dim]")
