"""Logs commands."""

import click
import json
import time
from rich.console import Console
from rich.table import Table
from ddogctl.client import get_datadog_client
from ddogctl.utils.error import handle_api_error
from ddogctl.utils.time import parse_time_range, to_utc_iso

console = Console()

STATUS_COLORS = {
    "error": "red",
    "warn": "yellow",
    "warning": "yellow",
    "info": "cyan",
    "debug": "dim",
    "ok": "green",
}


def _format_log_entry(log):
    """Extract fields from a log entry."""
    attrs = log.attributes
    nested = getattr(attrs, "attributes", None) or {}
    if hasattr(nested, "to_dict"):
        nested = nested.to_dict()
    elif not isinstance(nested, dict):
        nested = {}
    return {
        "message": getattr(attrs, "message", getattr(attrs, "log", "N/A")),
        "service": getattr(attrs, "service", "N/A"),
        "status": getattr(attrs, "status", "unknown"),
        "timestamp": str(getattr(attrs, "timestamp", "")),
        "attributes": nested,
    }


def _render_logs_table(logs_data, title="Logs"):
    """Render logs as a Rich table with color-coded status."""
    table = Table(title=title)
    table.add_column("Time", style="dim", width=20)
    table.add_column("Status", width=8)
    table.add_column("Service", style="cyan", width=20)
    table.add_column("Message", style="white")

    for log in logs_data:
        attrs = log.attributes
        timestamp = getattr(attrs, "timestamp", None)
        time_str = str(timestamp) if timestamp else "N/A"
        if timestamp and hasattr(timestamp, "strftime"):
            time_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")

        status = getattr(attrs, "status", "unknown")
        color = STATUS_COLORS.get(status, "white")
        status_styled = f"[{color}]{status}[/{color}]"

        message = getattr(attrs, "message", getattr(attrs, "log", "N/A"))
        service = getattr(attrs, "service", "N/A")

        table.add_row(
            time_str,
            status_styled,
            service,
            message,
        )

    return table


@click.group()
def logs():
    """Log querying and analytics."""
    pass


@logs.command(name="search")
@click.argument("query")
@click.option("--from", "from_time", default="1h", help="Start time (e.g., 1h, 24h, 7d)")
@click.option("--to", "to_time", default="now", help="End time")
@click.option("--service", help="Filter by service name")
@click.option("--status", help="Filter by log status (error, warn, info, debug)")
@click.option("--limit", default=50, type=int, help="Max logs to return (max: 1000)")
@click.option("--format", type=click.Choice(["json", "table"]), default="table")
@handle_api_error
def search_logs(query, from_time, to_time, service, status, limit, format):
    """Search logs with a query.

    Rate limit: 300 requests/hour for logs API.
    """
    client = get_datadog_client()

    # Parse time range
    from_ts, to_ts = parse_time_range(from_time, to_time)
    from_str = to_utc_iso(from_ts)
    to_str = to_utc_iso(to_ts)

    # Build query with optional filters
    full_query = query
    if service:
        full_query = f"{full_query} service:{service}"
    if status:
        full_query = f"{full_query} status:{status}"

    body = {
        "filter": {
            "query": full_query,
            "from": from_str,
            "to": to_str,
        },
        "page": {
            "limit": limit,
        },
        "sort": "-timestamp",
    }

    with console.status("[cyan]Searching logs...[/cyan]"):
        response = client.logs.list_logs(body=body)

    log_entries = response.data if response.data else []

    if format == "json":
        output = [_format_log_entry(log) for log in log_entries]
        print(json.dumps(output, indent=2))
    else:
        table = _render_logs_table(log_entries, title="Log Search Results")
        console.print(table)
        console.print(f"\n[dim]Total logs: {len(log_entries)}[/dim]")


@logs.command(name="tail")
@click.argument("query")
@click.option("--lines", default=50, type=int, help="Number of log lines to show")
@click.option("--service", help="Filter by service name")
@click.option("--follow", is_flag=True, default=False, help="Stream new logs continuously")
@click.option("--format", type=click.Choice(["json", "table"]), default="table")
@handle_api_error
def tail_logs(query, lines, service, follow, format):
    """Tail recent logs (last 15 minutes).

    Shows the most recent log entries matching your query.
    Use --follow to stream new logs continuously.
    """
    client = get_datadog_client()

    # Build query with optional filters
    full_query = query
    if service:
        full_query = f"{full_query} service:{service}"

    def fetch_logs():
        """Fetch recent logs from the API."""
        from_ts, to_ts = parse_time_range("15m", "now")
        from_str = to_utc_iso(from_ts)
        to_str = to_utc_iso(to_ts)

        body = {
            "filter": {
                "query": full_query,
                "from": from_str,
                "to": to_str,
            },
            "page": {
                "limit": lines,
            },
            "sort": "-timestamp",
        }

        response = client.logs.list_logs(body=body)
        return response.data if response.data else []

    if follow:
        seen_ids = set()
        MAX_SEEN_IDS = 10000
        try:
            while True:
                try:
                    log_entries = fetch_logs()
                except Exception as err:
                    console.print(f"[red]Error fetching logs: {err}[/red]")
                    time.sleep(5)
                    continue

                # Filter to only new logs
                new_logs = [log for log in log_entries if log.id not in seen_ids]
                for log in log_entries:
                    seen_ids.add(log.id)

                # Prevent unbounded memory growth
                if len(seen_ids) > MAX_SEEN_IDS:
                    seen_ids = set(list(seen_ids)[-MAX_SEEN_IDS // 2 :])

                if new_logs:
                    if format == "json":
                        for log in new_logs:
                            print(json.dumps(_format_log_entry(log)))
                    else:
                        for log in new_logs:
                            attrs = log.attributes
                            timestamp = getattr(attrs, "timestamp", None)
                            time_str = str(timestamp) if timestamp else "N/A"
                            if timestamp and hasattr(timestamp, "strftime"):
                                time_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")

                            status = str(getattr(attrs, "status", "unknown"))
                            color = STATUS_COLORS.get(status, "white")
                            # Escape Rich markup in untrusted content
                            service = getattr(attrs, "service", "N/A")
                            message = getattr(attrs, "message", getattr(attrs, "log", "N/A"))
                            safe_service = str(service).replace("[", "\\[")
                            safe_message = str(message).replace("[", "\\[")
                            console.print(
                                f"[dim]{time_str}[/dim] "
                                f"[{color}]{status}[/{color}] "
                                f"[cyan]{safe_service}[/cyan] "
                                f"{safe_message}"
                            )

                time.sleep(5)
        except KeyboardInterrupt:
            console.print("\n[dim]Follow stopped[/dim]")
    else:
        with console.status("[cyan]Tailing logs...[/cyan]"):
            log_entries = fetch_logs()

        if not log_entries:
            console.print("[yellow]No logs found in the last 15 minutes.[/yellow]")
            return

        if format == "json":
            output = [_format_log_entry(log) for log in log_entries]
            print(json.dumps(output, indent=2))
        else:
            table = _render_logs_table(log_entries, title="Recent Logs (last 15m)")
            console.print(table)
            console.print(f"\n[dim]Total logs: {len(log_entries)}[/dim]")


@logs.command(name="query")
@click.option("--query", default="*", help="Log query (default: *)")
@click.option("--from", "from_time", default="1h", help="Start time (e.g., 1h, 24h, 7d)")
@click.option("--to", "to_time", default="now", help="End time")
@click.option("--group-by", help="Group by field (e.g., service, status, @http.method)")
@click.option("--metric", default="count", help="Metric (count)")
@click.option("--format", type=click.Choice(["json", "table"]), default="table")
@handle_api_error
def query_logs(query, from_time, to_time, group_by, metric, format):
    """Log analytics and aggregations.

    Compute metrics across logs, optionally grouped by dimensions.
    """
    client = get_datadog_client()

    # Parse time range
    from_ts, to_ts = parse_time_range(from_time, to_time)
    from_str = to_utc_iso(from_ts)
    to_str = to_utc_iso(to_ts)

    # Build filter
    filter_dict = {
        "query": query,
        "from": from_str,
        "to": to_str,
    }

    # Configure compute
    if metric == "count":
        compute_dict = {"aggregation": "count"}
    else:
        compute_dict = {"aggregation": "count"}

    # Configure group-by
    group_by_list = [{"facet": group_by}] if group_by else []

    # Build request
    request_dict = {
        "filter": filter_dict,
        "compute": [compute_dict],
        "group_by": group_by_list,
    }

    with console.status("[cyan]Computing log analytics...[/cyan]"):
        response = client.logs.aggregate_logs(body=request_dict)

    buckets = response.data.buckets if response.data else []

    if format == "json":
        output = []
        for bucket in buckets:
            result = bucket.by.copy() if bucket.by else {}
            if bucket.computes:
                value = list(bucket.computes.values())[0]
                result[metric] = value
            output.append(result)
        print(json.dumps(output, indent=2))
    else:
        title = f"Log Analytics ({metric})"
        if group_by:
            title += f" by {group_by}"

        table = Table(title=title)
        if group_by:
            table.add_column(group_by, style="cyan")

        metric_label = metric.upper()
        table.add_column(metric_label, justify="right", style="yellow")

        for bucket in buckets:
            row = []
            if bucket.by and group_by:
                row.append(str(bucket.by.get(group_by, "N/A")))

            if bucket.computes:
                value = list(bucket.computes.values())[0]
                row.append(f"{value:.2f}")

            table.add_row(*row)

        console.print(table)
        console.print(f"\n[dim]Total groups: {len(buckets)}[/dim]")


@logs.command(name="trace")
@click.argument("trace_id")
@click.option("--format", type=click.Choice(["json", "table"]), default="table")
@handle_api_error
def trace_logs(trace_id, format):
    """Find logs associated with a trace ID.

    Searches for logs with the given trace ID.
    """
    client = get_datadog_client()

    body = {
        "filter": {
            "query": f"@trace_id:{trace_id}",
        },
        "page": {
            "limit": 1000,
        },
        "sort": "-timestamp",
    }

    with console.status(f"[cyan]Searching logs for trace {trace_id}...[/cyan]"):
        response = client.logs.list_logs(body=body)

    log_entries = response.data if response.data else []

    if not log_entries:
        console.print(f"[yellow]No logs found for trace {trace_id}.[/yellow]")
        return

    if format == "json":
        output = [_format_log_entry(log) for log in log_entries]
        print(json.dumps(output, indent=2))
    else:
        table = _render_logs_table(log_entries, title=f"Logs for trace {trace_id}")
        console.print(table)
        console.print(f"\n[dim]Total logs: {len(log_entries)}[/dim]")
