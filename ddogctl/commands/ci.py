"""CI Visibility commands."""

import click
import json
from rich.console import Console
from rich.table import Table
from ddogctl.client import get_datadog_client
from ddogctl.utils.error import handle_api_error
from ddogctl.utils.time import parse_time_range, to_utc_datetime

console = Console()

STATUS_COLORS = {
    "success": "green",
    "error": "red",
    "failed": "red",
    "canceled": "yellow",
    "skipped": "dim",
    "running": "cyan",
    "blocked": "yellow",
    "pass": "green",
    "fail": "red",
}


def _extract_event_fields(event):
    """Extract common fields from a CI event."""
    attrs = event.attributes
    # attributes is a dict-like object; use getattr for safety
    result = {
        "id": event.id,
        "type": getattr(event, "type", None),
    }
    # Flatten known attribute fields
    if hasattr(attrs, "attributes"):
        inner = attrs.attributes
        if isinstance(inner, dict):
            result.update(inner)
        elif hasattr(inner, "to_dict"):
            result.update(inner.to_dict())
    return result


@click.group()
def ci():
    """CI Visibility commands (pipelines and tests)."""
    pass


@ci.command(name="pipelines")
@click.option("--query", default="*", help="Search query for pipeline events")
@click.option("--from", "from_time", default="1h", help="Start time (e.g., 1h, 24h, 7d)")
@click.option("--to", "to_time", default="now", help="End time")
@click.option("--limit", default=50, type=int, help="Max events to return (max: 1000)")
@click.option("--format", type=click.Choice(["json", "table"]), default="table")
@handle_api_error
def pipelines(query, from_time, to_time, limit, format):
    """Search CI pipeline events.

    Query pipeline execution events from CI Visibility.
    """
    client = get_datadog_client()

    from_ts, to_ts = parse_time_range(from_time, to_time)
    from_dt = to_utc_datetime(from_ts)
    to_dt = to_utc_datetime(to_ts)

    with console.status("[cyan]Searching CI pipeline events...[/cyan]"):
        response = client.ci_pipelines.list_ci_app_pipeline_events(
            filter_query=query,
            filter_from=from_dt,
            filter_to=to_dt,
            page_limit=limit,
        )

    events = response.data if response.data else []

    if format == "json":
        output = [_extract_event_fields(e) for e in events]
        print(json.dumps(output, indent=2, default=str))
    else:
        table = Table(title="CI Pipeline Events")
        table.add_column("ID", style="cyan", width=20)
        table.add_column("Pipeline", style="white", min_width=20)
        table.add_column("Status", width=10)
        table.add_column("Duration", justify="right", style="yellow", width=12)
        table.add_column("Branch", style="dim", width=20)

        for event in events:
            fields = _extract_event_fields(event)
            pipeline_name = str(fields.get("name", fields.get("pipeline_name", "N/A")))
            status = str(fields.get("status", "N/A"))
            color = STATUS_COLORS.get(status.lower(), "white")
            status_styled = f"[{color}]{status}[/{color}]"

            # Duration may be in nanoseconds
            duration_raw = fields.get("duration", None)
            if duration_raw is not None:
                duration_ms = duration_raw / 1_000_000
                if duration_ms >= 1000:
                    duration_str = f"{duration_ms / 1000:.1f}s"
                else:
                    duration_str = f"{duration_ms:.0f}ms"
            else:
                duration_str = "N/A"

            branch = str(
                fields.get("git", {}).get("branch", "")
                if isinstance(fields.get("git"), dict)
                else fields.get("branch", "N/A")
            )

            event_id = str(event.id or "N/A")
            if len(event_id) > 18:
                event_id = event_id[:16] + ".."

            table.add_row(event_id, pipeline_name, status_styled, duration_str, branch)

        console.print(table)
        console.print(f"\n[dim]Total pipeline events: {len(events)}[/dim]")


@ci.command(name="tests")
@click.option("--query", default="*", help="Search query for test events")
@click.option("--from", "from_time", default="1h", help="Start time (e.g., 1h, 24h, 7d)")
@click.option("--to", "to_time", default="now", help="End time")
@click.option("--limit", default=50, type=int, help="Max events to return (max: 1000)")
@click.option("--format", type=click.Choice(["json", "table"]), default="table")
@handle_api_error
def tests(query, from_time, to_time, limit, format):
    """Search CI test events.

    Query test execution events from CI Visibility.
    """
    client = get_datadog_client()

    from_ts, to_ts = parse_time_range(from_time, to_time)
    from_dt = to_utc_datetime(from_ts)
    to_dt = to_utc_datetime(to_ts)

    with console.status("[cyan]Searching CI test events...[/cyan]"):
        response = client.ci_tests.list_ci_app_test_events(
            filter_query=query,
            filter_from=from_dt,
            filter_to=to_dt,
            page_limit=limit,
        )

    events = response.data if response.data else []

    if format == "json":
        output = [_extract_event_fields(e) for e in events]
        print(json.dumps(output, indent=2, default=str))
    else:
        table = Table(title="CI Test Events")
        table.add_column("ID", style="cyan", width=20)
        table.add_column("Test Name", style="white", min_width=25)
        table.add_column("Suite", style="dim", width=20)
        table.add_column("Status", width=10)
        table.add_column("Duration", justify="right", style="yellow", width=12)

        for event in events:
            fields = _extract_event_fields(event)
            test_name = str(fields.get("name", fields.get("test_name", "N/A")))
            suite = str(fields.get("suite", fields.get("test_suite", "N/A")))
            status = str(fields.get("status", "N/A"))
            color = STATUS_COLORS.get(status.lower(), "white")
            status_styled = f"[{color}]{status}[/{color}]"

            duration_raw = fields.get("duration", None)
            if duration_raw is not None:
                duration_ms = duration_raw / 1_000_000
                if duration_ms >= 1000:
                    duration_str = f"{duration_ms / 1000:.1f}s"
                else:
                    duration_str = f"{duration_ms:.0f}ms"
            else:
                duration_str = "N/A"

            event_id = str(event.id or "N/A")
            if len(event_id) > 18:
                event_id = event_id[:16] + ".."

            table.add_row(event_id, test_name, suite, status_styled, duration_str)

        console.print(table)
        console.print(f"\n[dim]Total test events: {len(events)}[/dim]")


@ci.command(name="pipeline-details")
@click.argument("pipeline_id")
@click.option("--format", type=click.Choice(["json", "table"]), default="table")
@handle_api_error
def pipeline_details(pipeline_id, format):
    """Get details for a specific CI pipeline run.

    Searches for pipeline events matching the given pipeline ID.
    """
    client = get_datadog_client()

    with console.status(f"[cyan]Fetching pipeline {pipeline_id}...[/cyan]"):
        response = client.ci_pipelines.list_ci_app_pipeline_events(
            filter_query=f"@ci.pipeline.id:{pipeline_id}",
            page_limit=100,
        )

    events = response.data if response.data else []

    if not events:
        console.print(f"[yellow]No events found for pipeline {pipeline_id}.[/yellow]")
        return

    if format == "json":
        output = [_extract_event_fields(e) for e in events]
        print(json.dumps(output, indent=2, default=str))
    else:
        table = Table(title=f"Pipeline Details: {pipeline_id}")
        table.add_column("ID", style="cyan", width=20)
        table.add_column("Name", style="white", min_width=20)
        table.add_column("Status", width=10)
        table.add_column("Duration", justify="right", style="yellow", width=12)
        table.add_column("Level", style="dim", width=10)

        for event in events:
            fields = _extract_event_fields(event)
            name = str(fields.get("name", fields.get("pipeline_name", "N/A")))
            status = str(fields.get("status", "N/A"))
            color = STATUS_COLORS.get(status.lower(), "white")
            status_styled = f"[{color}]{status}[/{color}]"

            duration_raw = fields.get("duration", None)
            if duration_raw is not None:
                duration_ms = duration_raw / 1_000_000
                if duration_ms >= 1000:
                    duration_str = f"{duration_ms / 1000:.1f}s"
                else:
                    duration_str = f"{duration_ms:.0f}ms"
            else:
                duration_str = "N/A"

            level = str(fields.get("level", fields.get("pipeline_level", "N/A")))

            event_id = str(event.id or "N/A")
            if len(event_id) > 18:
                event_id = event_id[:16] + ".."

            table.add_row(event_id, name, status_styled, duration_str, level)

        console.print(table)
        console.print(f"\n[dim]Total events: {len(events)}[/dim]")
