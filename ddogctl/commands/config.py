"""Configuration and profile management commands."""

import json
import os
import sys

import click
from rich.console import Console
from rich.table import Table

console = Console()

REGION_SHORTCUTS = {
    "us": "datadoghq.com",
    "eu": "datadoghq.eu",
    "us3": "us3.datadoghq.com",
    "us5": "us5.datadoghq.com",
    "ap1": "ap1.datadoghq.com",
    "gov": "ddog-gov.com",
}


def get_config_dir() -> str:
    """Return the path to the config directory (~/.ddogctl)."""
    return os.path.join(os.path.expanduser("~"), ".ddogctl")


def get_config_path() -> str:
    """Return the path to the config file (~/.ddogctl/config.json)."""
    return os.path.join(get_config_dir(), "config.json")


def expand_site(site: str) -> str:
    """Expand a region shortcut to a full site domain."""
    return REGION_SHORTCUTS.get(site.lower(), site)


def mask_key(key: str) -> str:
    """Mask an API key, showing only the last 4 characters."""
    if len(key) <= 4:
        return "****"
    return "****" + key[-4:]


def load_config_data() -> dict:
    """Load config data from the config file.

    Returns:
        Config data dict, or empty dict if file doesn't exist or is corrupt.
    """
    config_path = get_config_path()
    if not os.path.exists(config_path):
        return {}
    try:
        with open(config_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        console.print(f"[red]Failed to load config file: {e}[/red]")
        sys.exit(1)


def save_config_data(data: dict) -> None:
    """Save config data to the config file, creating directory if needed."""
    config_dir = get_config_dir()
    os.makedirs(config_dir, mode=0o700, exist_ok=True)
    config_path = get_config_path()
    with open(config_path, "w") as f:
        json.dump(data, f, indent=2)
    os.chmod(config_path, 0o600)


@click.group()
def config():
    """Configuration and profile management."""
    pass


def build_profile(
    site: str, api_key: str | None = None, app_key: str | None = None, pat: str | None = None
) -> dict:
    """Build a profile dict, omitting credentials that weren't provided."""
    profile = {"pat": pat, "api_key": api_key, "app_key": app_key}
    return {**{k: v for k, v in profile.items() if v}, "site": site}


@config.command(name="init")
@click.option(
    "--auth",
    type=click.Choice(["keys", "pat"]),
    default="keys",
    show_default=True,
    help="Authenticate with an API+App key pair or a Personal Access Token",
)
def init_config(auth):
    """Interactive setup wizard to create a profile.

    Prompts for credentials, site, and profile name, then saves
    to ~/.ddogctl/config.json.
    """
    console.print("[cyan]Datadog CLI Configuration Wizard[/cyan]\n")

    pat = api_key = app_key = None
    if auth == "pat":
        pat = click.prompt("Personal Access Token", hide_input=True)
    else:
        api_key = click.prompt("API Key", hide_input=True)
        app_key = click.prompt("App Key", hide_input=True)
    site = click.prompt("Site (us, eu, us3, us5, ap1, gov, or full domain)", default="us")
    profile_name = click.prompt("Profile name", default="default")

    site = expand_site(site)

    # Load existing config or create new
    data = load_config_data()
    if not data:
        data = {"active_profile": "", "profiles": {}}

    data["profiles"][profile_name] = build_profile(site, api_key, app_key, pat)

    # Set as active if no active profile
    if not data["active_profile"]:
        data["active_profile"] = profile_name

    save_config_data(data)

    console.print(f"\n[green]Profile '{profile_name}' saved successfully![/green]")
    console.print(f"[dim]Config file: {get_config_path()}[/dim]")


@config.command(name="set-profile")
@click.argument("name")
@click.option("--api-key", help="Datadog API key")
@click.option("--app-key", help="Datadog Application key")
@click.option("--pat", help="Datadog Personal Access Token (replaces --app-key)")
@click.option("--site", default="us", help="Datadog site (us, eu, us3, us5, ap1, gov, or domain)")
def set_profile(name, api_key, app_key, pat, site):
    """Create or update a profile.

    Requires --pat, or both --api-key and --app-key.

    Example:
        ddogctl config set-profile prod --api-key xxx --app-key yyy --site us
        ddogctl config set-profile work --pat ddpat_xxx --site eu
    """
    if not pat and not (api_key and app_key):
        raise click.UsageError("Provide --pat, or both --api-key and --app-key")

    site = expand_site(site)

    data = load_config_data()
    if not data:
        data = {"active_profile": "", "profiles": {}}

    data["profiles"][name] = build_profile(site, api_key, app_key, pat)

    # Set as active if it's the first profile or no active profile
    if not data["active_profile"]:
        data["active_profile"] = name

    save_config_data(data)

    console.print(f"[green]Profile '{name}' saved.[/green]")


@config.command(name="use-profile")
@click.argument("name")
def use_profile(name):
    """Set the active profile.

    Example:
        ddogctl config use-profile staging
    """
    data = load_config_data()

    if not data:
        console.print("[red]No config file found. Run 'ddogctl config init' first.[/red]")
        sys.exit(1)

    if name not in data.get("profiles", {}):
        console.print(
            f"[red]Profile '{name}' not found. "
            f"Available profiles: {', '.join(data.get('profiles', {}).keys())}[/red]"
        )
        sys.exit(1)

    data["active_profile"] = name
    save_config_data(data)

    console.print(f"[green]Active profile set to '{name}'.[/green]")


@config.command(name="list-profiles")
def list_profiles():
    """List all configured profiles."""
    data = load_config_data()

    if not data or not data.get("profiles"):
        console.print(
            "[yellow]No profiles configured. Run 'ddogctl config init' to set up.[/yellow]"
        )
        return

    active = data.get("active_profile", "")

    table = Table(title="Profiles")
    table.add_column("", width=3)
    table.add_column("Name", style="cyan")
    table.add_column("API Key", style="dim")
    table.add_column("App Key", style="dim")
    table.add_column("PAT", style="dim")
    table.add_column("Site", style="white")

    for name, profile in sorted(data["profiles"].items()):
        marker = "*" if name == active else ""
        table.add_row(
            marker,
            name,
            mask_key(profile.get("api_key", "")),
            mask_key(profile.get("app_key", "")),
            mask_key(profile["pat"]) if profile.get("pat") else "",
            profile.get("site", ""),
        )

    console.print(table)
    console.print(f"\n[dim]Active profile: {active}[/dim]")


@config.command(name="get")
@click.argument("key")
def get_value(key):
    """Show the current value for a configuration key.

    Valid keys: active_profile, api_key, app_key, pat, site

    Example:
        ddogctl config get site
        ddogctl config get active_profile
    """
    valid_keys = {"active_profile", "api_key", "app_key", "pat", "site"}

    if key not in valid_keys:
        console.print(
            f"[red]Unknown key '{key}'. Valid keys: {', '.join(sorted(valid_keys))}[/red]"
        )
        sys.exit(1)

    data = load_config_data()

    if not data:
        console.print("[red]No config file found. Run 'ddogctl config init' first.[/red]")
        sys.exit(1)

    if key == "active_profile":
        console.print(data.get("active_profile", ""))
        return

    active = data.get("active_profile", "")
    profiles = data.get("profiles", {})

    if active not in profiles:
        console.print("[red]No active profile set. Run 'ddogctl config use-profile <name>'.[/red]")
        sys.exit(1)

    profile = profiles[active]
    value = profile.get(key, "")

    # Mask sensitive keys
    if key in ("api_key", "app_key", "pat"):
        value = mask_key(value)

    console.print(value)
