"""Metric query commands."""

import click
import json
from datetime import datetime, timedelta, timezone
from rich.console import Console
from rich.table import Table
from ddogctl.client import get_datadog_client
from ddogctl.utils.error import handle_api_error
from ddogctl.utils.time import parse_time_range

console = Console()


@click.group()
def metric():
    """Metric query commands."""
    pass


@metric.command(name="query")
@click.argument("query")
@click.option("--from", "from_time", default="1h", help="Start time (e.g., 1h, 24h, 7d)")
@click.option("--to", "to_time", default="now", help="End time")
@click.option(
    "--format", type=click.Choice(["json", "table", "csv"]), default="table", help="Output format"
)
@handle_api_error
def query_metric(query, from_time, to_time, format):
    """Query metrics."""
    client = get_datadog_client()

    from_ts, to_ts = parse_time_range(from_time, to_time)

    with console.status(f"[cyan]Querying metric: {query}...[/cyan]"):
        result = client.metrics.query_metrics(_from=from_ts, to=to_ts, query=query)

    if format == "json":
        print(json.dumps(result.to_dict(), indent=2, default=str))
    elif format == "csv":
        # CSV output for scripting
        if result.series:
            for series in result.series:
                metric_name = series.get("metric", "unknown")
                for point in series.get("pointlist", []):
                    timestamp, value = point.value
                    print(f"{timestamp},{metric_name},{value}")
    else:
        # Table format
        if not result.series:
            console.print("[yellow]No data found for query[/yellow]")
            return

        for series in result.series:
            table = Table(title=f"Metric: {series.get('metric', 'unknown')}")
            table.add_column("Timestamp", style="cyan")
            table.add_column("Value", style="green", justify="right")

            # Show last 20 points
            points = series.get("pointlist", [])[-20:]
            for point in points:
                timestamp, value = point.value
                from datetime import datetime

                dt = datetime.fromtimestamp(timestamp / 1000)
                table.add_row(dt.strftime("%Y-%m-%d %H:%M:%S"), f"{value:.2f}")

            console.print(table)
            console.print(f"[dim]Total points: {len(series.get('pointlist', []))}[/dim]\n")


@metric.command(name="search")
@click.argument("query")
@click.option("--limit", default=50, help="Maximum results to show")
@handle_api_error
def search_metrics(query, limit):
    """Search available metrics."""
    client = get_datadog_client()

    with console.status(f"[cyan]Searching metrics: {query}...[/cyan]"):
        from_ts = int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())
        results = client.metrics.list_active_metrics(_from=from_ts)

    if results.metrics:
        results.metrics = [m for m in results.metrics if query.lower() in m.lower()]

    if not results.metrics:
        console.print("[yellow]No metrics found[/yellow]")
        return

    console.print(f"\n[bold]Found {len(results.metrics)} metrics:[/bold]")
    for metric in results.metrics[:limit]:
        console.print(f"  • {metric}")

    if len(results.metrics) > limit:
        console.print(f"\n[dim]... and {len(results.metrics) - limit} more[/dim]")


@metric.command(name="metadata")
@click.argument("metric_name")
@handle_api_error
def get_metric_metadata(metric_name):
    """Get metric metadata."""
    client = get_datadog_client()

    with console.status(f"[cyan]Fetching metadata for {metric_name}...[/cyan]"):
        metadata = client.metrics.get_metric_metadata(metric_name=metric_name)

    console.print(f"\n[bold cyan]Metric: {metric_name}[/bold cyan]")
    if hasattr(metadata, "description") and metadata.description:
        console.print(f"[bold]Description:[/bold] {metadata.description}")
    if hasattr(metadata, "type") and metadata.type:
        console.print(f"[bold]Type:[/bold] {metadata.type}")
    if hasattr(metadata, "unit") and metadata.unit:
        console.print(f"[bold]Unit:[/bold] {metadata.unit}")
    if hasattr(metadata, "per_unit") and metadata.per_unit:
        console.print(f"[bold]Per Unit:[/bold] {metadata.per_unit}")
