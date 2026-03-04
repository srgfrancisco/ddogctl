"""Event query commands."""

import click
import json
from rich.console import Console
from rich.table import Table
from ddogctl.client import get_datadog_client
from ddogctl.utils.error import handle_api_error
from ddogctl.utils.time import parse_time_range

console = Console()


@click.group()
def event():
    """Event query commands."""
    pass


@event.command(name="list")
@click.option("--from", "from_time", default="24h", help="Start time (e.g., 1h, 24h, 7d)")
@click.option("--to", "to_time", default="now", help="End time")
@click.option("--sources", help="Event sources (comma-separated, e.g., alert,deploy)")
@click.option("--priority", type=click.Choice(["normal", "low"]), help="Event priority")
@click.option("--tags", help="Filter by tags (comma-separated)")
@click.option(
    "--format", type=click.Choice(["json", "table"]), default="table", help="Output format"
)
@handle_api_error
def list_events(from_time, to_time, sources, priority, tags, format):
    """List events."""
    client = get_datadog_client()

    from_ts, to_ts = parse_time_range(from_time, to_time)

    with console.status("[cyan]Fetching events...[/cyan]"):
        # Build kwargs only with provided parameters
        kwargs = {"start": from_ts, "end": to_ts}
        if sources:
            kwargs["sources"] = sources
        if priority:
            kwargs["priority"] = priority
        if tags:
            kwargs["tags"] = tags

        result = client.events.list_events(**kwargs)

    if not result.events:
        console.print("[yellow]No events found[/yellow]")
        return

    if format == "table":
        table = Table(title=f"Events (last {from_time})", show_lines=False)
        table.add_column("Time", style="cyan", width=20)
        table.add_column("Title", style="white", min_width=30)
        table.add_column("Source", style="dim", width=15)
        table.add_column("Priority", style="yellow", width=10)

        for evt in result.events:
            from datetime import datetime

            dt = datetime.fromtimestamp(evt.date_happened)
            title = evt.title[:60] if evt.title else ""

            # Convert enum to string
            priority_str = str(getattr(evt, "priority", "")) if hasattr(evt, "priority") else ""
            source_str = str(evt.source) if evt.source else ""

            table.add_row(dt.strftime("%Y-%m-%d %H:%M:%S"), title, source_str, priority_str)

        console.print(table)
        console.print(f"\n[dim]Total events: {len(result.events)}[/dim]")

    elif format == "json":
        print(json.dumps(result.to_dict(), indent=2, default=str))


@event.command(name="get")
@click.argument("event_id", type=int)
@handle_api_error
def get_event(event_id):
    """Get event details."""
    client = get_datadog_client()

    with console.status(f"[cyan]Fetching event {event_id}...[/cyan]"):
        evt = client.events.get_event(event_id=event_id)

    console.print(f"\n[bold cyan]Event #{evt.event.id}[/bold cyan]")
    console.print(f"[bold]Title:[/bold] {evt.event.title}")

    if hasattr(evt.event, "text") and evt.event.text:
        console.print(f"[bold]Text:[/bold]\n{evt.event.text}")

    from datetime import datetime

    dt = datetime.fromtimestamp(evt.event.date_happened)
    console.print(f"[bold]Date:[/bold] {dt.strftime('%Y-%m-%d %H:%M:%S')}")

    if hasattr(evt.event, "priority") and evt.event.priority:
        console.print(f"[bold]Priority:[/bold] {evt.event.priority}")

    if hasattr(evt.event, "tags") and evt.event.tags:
        console.print(f"[bold]Tags:[/bold] {', '.join(evt.event.tags)}")


@event.command(name="post")
@click.argument("title")
@click.option("--text", help="Event text/body")
@click.option("--tags", help="Event tags (comma-separated)")
@click.option("--priority", type=click.Choice(["normal", "low"]), default="normal")
@handle_api_error
def post_event(title, text, tags, priority):
    """Post an event."""
    client = get_datadog_client()

    from datadog_api_client.v1.model.event_create_request import EventCreateRequest

    tag_list = tags.split(",") if tags else None

    event_req = EventCreateRequest(
        title=title, text=text or title, tags=tag_list, priority=priority
    )

    with console.status("[cyan]Posting event...[/cyan]"):
        result = client.events.create_event(body=event_req)

    console.print(f"[green]✓ Event posted: {result.event.id}[/green]")
    console.print(f"[bold]Title:[/bold] {result.event.title}")
    if result.event.url:
        console.print(f"[bold]URL:[/bold] {result.event.url}")
