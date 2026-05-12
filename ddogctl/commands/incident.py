"""Incident management commands."""

import click
import json
from rich.console import Console
from rich.table import Table
from ddogctl.client import get_datadog_client
from ddogctl.utils.error import handle_api_error
from ddogctl.utils.confirm import confirm_action

console = Console()

SEVERITY_CHOICES = ["SEV-1", "SEV-2", "SEV-3", "SEV-4", "SEV-5"]
STATUS_CHOICES = ["active", "stable", "resolved"]


@click.group()
def incident():
    """Incident management commands."""
    pass


@incident.command(name="list")
@click.option(
    "--format", type=click.Choice(["json", "table"]), default="table", help="Output format"
)
@handle_api_error
def list_incidents(format):
    """List all incidents."""
    client = get_datadog_client()

    with console.status("[cyan]Fetching incidents...[/cyan]"):
        response = client.incidents.list_incidents()

    incidents = response.data if response.data else []

    if format == "json":
        output = []
        for inc in incidents:
            attrs = inc.attributes
            output.append(
                {
                    "id": inc.id,
                    "title": getattr(attrs, "title", ""),
                    "severity": getattr(attrs, "severity", ""),
                    "status": getattr(attrs, "state", ""),
                    "created": str(getattr(attrs, "created", "")),
                    "modified": str(getattr(attrs, "modified", "")),
                }
            )
        print(json.dumps(output, indent=2))
    else:
        table = Table(title="Incidents")
        table.add_column("ID", style="cyan", width=20)
        table.add_column("Title", style="white", min_width=30)
        table.add_column("Severity", style="yellow", width=10)
        table.add_column("Status", style="bold", width=12)
        table.add_column("Created", style="dim", width=20)

        for inc in incidents:
            attrs = inc.attributes
            status_str = str(getattr(attrs, "state", ""))
            severity_str = str(getattr(attrs, "severity", ""))
            status_color = {
                "active": "red",
                "stable": "yellow",
                "resolved": "green",
            }.get(status_str, "white")

            table.add_row(
                str(inc.id),
                str(getattr(attrs, "title", "")),
                severity_str,
                f"[{status_color}]{status_str}[/{status_color}]",
                str(getattr(attrs, "created", "")),
            )

        console.print(table)
        console.print(f"\n[dim]Total incidents: {len(incidents)}[/dim]")


@incident.command(name="get")
@click.argument("incident_id")
@click.option(
    "--format", type=click.Choice(["json", "table"]), default="table", help="Output format"
)
@handle_api_error
def get_incident(incident_id, format):
    """Get incident details."""
    client = get_datadog_client()

    with console.status(f"[cyan]Fetching incident {incident_id}...[/cyan]"):
        response = client.incidents.get_incident(incident_id=incident_id)

    inc = response.data
    attrs = inc.attributes

    if format == "json":
        output = {
            "id": inc.id,
            "title": getattr(attrs, "title", ""),
            "severity": getattr(attrs, "severity", ""),
            "status": getattr(attrs, "state", ""),
            "created": str(getattr(attrs, "created", "")),
            "modified": str(getattr(attrs, "modified", "")),
        }
        print(json.dumps(output, indent=2))
    else:
        console.print(f"\n[bold cyan]Incident {inc.id}[/bold cyan]")
        console.print(f"[bold]Title:[/bold] {getattr(attrs, 'title', '')}")

        severity_str = str(getattr(attrs, "severity", ""))
        console.print(f"[bold]Severity:[/bold] [yellow]{severity_str}[/yellow]")

        status_str = str(getattr(attrs, "state", ""))
        status_color = {
            "active": "red",
            "stable": "yellow",
            "resolved": "green",
        }.get(status_str, "white")
        console.print(f"[bold]Status:[/bold] [{status_color}]{status_str}[/{status_color}]")

        console.print(f"[bold]Created:[/bold] {getattr(attrs, 'created', '')}")
        console.print(f"[bold]Modified:[/bold] {getattr(attrs, 'modified', '')}")


@incident.command(name="create")
@click.option("--title", required=True, help="Incident title")
@click.option(
    "--severity",
    type=click.Choice(SEVERITY_CHOICES),
    required=True,
    help="Incident severity",
)
@click.option(
    "--format", type=click.Choice(["json", "table"]), default="table", help="Output format"
)
@handle_api_error
def create_incident(title, severity, format):
    """Create a new incident."""
    from datadog_api_client.v2.model.incident_create_request import IncidentCreateRequest
    from datadog_api_client.v2.model.incident_create_data import IncidentCreateData
    from datadog_api_client.v2.model.incident_create_attributes import IncidentCreateAttributes

    client = get_datadog_client()

    body = IncidentCreateRequest(
        data=IncidentCreateData(
            type="incidents",
            attributes=IncidentCreateAttributes(
                title=title,
                customer_impacted=False,
                fields={"severity": {"type": "dropdown", "value": severity}},
            ),
        )
    )

    with console.status("[cyan]Creating incident...[/cyan]"):
        response = client.incidents.create_incident(body=body)

    inc = response.data
    attrs = inc.attributes

    if format == "json":
        output = {
            "id": inc.id,
            "title": getattr(attrs, "title", ""),
            "severity": severity,
            "status": getattr(attrs, "state", ""),
        }
        print(json.dumps(output, indent=2))
    else:
        console.print(f"[green]Incident {inc.id} created[/green]")
        console.print(f"[bold]Title:[/bold] {getattr(attrs, 'title', '')}")
        console.print(f"[bold]Severity:[/bold] {severity}")


@incident.command(name="update")
@click.argument("incident_id")
@click.option("--title", default=None, help="New incident title")
@click.option("--status", default=None, type=click.Choice(STATUS_CHOICES), help="Incident status")
@click.option(
    "--severity", default=None, type=click.Choice(SEVERITY_CHOICES), help="Incident severity"
)
@click.option(
    "--format", type=click.Choice(["json", "table"]), default="table", help="Output format"
)
@handle_api_error
def update_incident(incident_id, title, status, severity, format):
    """Update an existing incident."""
    from datadog_api_client.v2.model.incident_update_request import IncidentUpdateRequest
    from datadog_api_client.v2.model.incident_update_data import IncidentUpdateData
    from datadog_api_client.v2.model.incident_update_attributes import IncidentUpdateAttributes

    if not any([title, status, severity]):
        raise click.UsageError("No update fields specified. Use --title, --status, or --severity.")

    client = get_datadog_client()

    attrs_kwargs = {}
    if title is not None:
        attrs_kwargs["title"] = title

    fields = {}
    if severity is not None:
        fields["severity"] = {"type": "dropdown", "value": severity}
    if status is not None:
        fields["state"] = {"type": "dropdown", "value": status}
    if fields:
        attrs_kwargs["fields"] = fields

    body = IncidentUpdateRequest(
        data=IncidentUpdateData(
            id=incident_id,
            type="incidents",
            attributes=IncidentUpdateAttributes(**attrs_kwargs),
        )
    )

    with console.status(f"[cyan]Updating incident {incident_id}...[/cyan]"):
        response = client.incidents.update_incident(incident_id=incident_id, body=body)

    inc = response.data
    attrs = inc.attributes

    if format == "json":
        output = {
            "id": inc.id,
            "title": getattr(attrs, "title", ""),
            "status": getattr(attrs, "state", ""),
        }
        print(json.dumps(output, indent=2))
    else:
        console.print(f"[green]Incident {incident_id} updated[/green]")
        console.print(f"[bold]Title:[/bold] {getattr(attrs, 'title', '')}")


@incident.command(name="delete")
@click.argument("incident_id")
@click.option("--confirm", "confirmed", is_flag=True, help="Skip confirmation prompt")
@handle_api_error
def delete_incident(incident_id, confirmed):
    """Delete an incident."""
    if not confirm_action(f"Delete incident {incident_id}?", confirmed):
        console.print("[yellow]Aborted[/yellow]")
        return

    client = get_datadog_client()

    with console.status(f"[cyan]Deleting incident {incident_id}...[/cyan]"):
        client.incidents.delete_incident(incident_id=incident_id)

    console.print(f"[green]Incident {incident_id} deleted[/green]")
