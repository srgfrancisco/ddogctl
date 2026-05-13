"""Check for newer ddogctl releases on PyPI."""

import json
import sys
from importlib.metadata import PackageNotFoundError, version as _pkg_version

import click
import requests
from packaging.version import InvalidVersion, Version
from rich.console import Console

PYPI_URL = "https://pypi.org/pypi/ddogctl/json"
REQUEST_TIMEOUT = 5

console = Console()


def _current_version() -> str:
    """Return the installed ddogctl version, or "0.0.0" if not installed."""
    try:
        return _pkg_version("ddogctl")
    except PackageNotFoundError:
        return "0.0.0"


def _detect_upgrade_command(executable: str | None = None) -> str:
    """Suggest the right upgrade command based on the running interpreter path."""
    exe = executable if executable is not None else sys.executable
    exe_lower = exe.lower()
    if "pipx" in exe_lower:
        return "pipx upgrade ddogctl"
    if "/uv/tools/" in exe_lower or "\\uv\\tools\\" in exe_lower:
        return "uv tool upgrade ddogctl"
    return f"{exe} -m pip install --upgrade ddogctl"


@click.command(name="update")
@click.option("--format", "output_format", type=click.Choice(["json", "text"]), default="text")
def update(output_format: str) -> None:
    """Check PyPI for a newer ddogctl release.

    Read-only: prints the upgrade command but does not install anything.
    """
    current = _current_version()
    upgrade_cmd = _detect_upgrade_command()

    try:
        response = requests.get(PYPI_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        latest = response.json()["info"]["version"]
    except requests.RequestException as exc:
        message = f"Could not reach PyPI: {exc}"
        if output_format == "json":
            click.echo(json.dumps({"error": message, "current": current}))
        else:
            console.print(f"[red]{message}[/red]")
        raise SystemExit(1)

    try:
        update_available = Version(latest) > Version(current)
        local_ahead = Version(current) > Version(latest)
    except InvalidVersion:
        update_available = latest != current
        local_ahead = False

    if output_format == "json":
        click.echo(
            json.dumps(
                {
                    "current": current,
                    "latest": latest,
                    "update_available": update_available,
                    "upgrade_command": upgrade_cmd,
                }
            )
        )
        return

    if update_available:
        console.print(f"[yellow]Update available:[/yellow] {current} -> [green]{latest}[/green]")
        console.print(f"Run: [cyan]{upgrade_cmd}[/cyan]")
    elif local_ahead:
        console.print(f"[cyan]Local version {current} is ahead of PyPI ({latest}).[/cyan]")
    else:
        console.print(f"[green]ddogctl {current} is up to date.[/green]")
