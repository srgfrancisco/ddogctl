"""Main CLI entry point for Datadog CLI."""

import click
from rich.console import Console

console = Console()

# Command aliases: short name -> full command name
ALIASES = {
    "mon": "monitor",
    "dash": "dashboard",
    "dt": "downtime",
    "sc": "service-check",
    "inv": "investigate",
}


class AliasGroup(click.Group):
    """Click Group subclass that supports command aliases."""

    def get_command(self, ctx, cmd_name):
        rv = click.Group.get_command(self, ctx, cmd_name)
        if rv is not None:
            return rv
        # Check aliases
        if cmd_name in ALIASES:
            return click.Group.get_command(self, ctx, ALIASES[cmd_name])
        return None

    def resolve_command(self, ctx, args):
        # Always resolve alias to the full command name
        cmd_name = args[0] if args else None
        if cmd_name in ALIASES:
            args = [ALIASES[cmd_name]] + args[1:]
        return super().resolve_command(ctx, args)


@click.group(cls=AliasGroup)
@click.version_option(version="2.0.3")
@click.option(
    "--profile",
    default=None,
    envvar="DDOGCTL_PROFILE",
    help="Configuration profile to use (from ~/.ddogctl/config.json).",
)
@click.pass_context
def main(ctx, profile):
    """A modern CLI for the Datadog API. Like Dogshell, but better.

    Query monitors, metrics, events, hosts, APM traces, logs, and more
    from your terminal with rich output and smart defaults.

    Configuration:
        DD_API_KEY - Datadog API key (required)
        DD_APP_KEY - Datadog Application key (required)
        DD_SITE - Datadog site (default: datadoghq.com)

    Examples:
        ddogctl monitor list --state Alert
        ddogctl apm traces my-service --from 1h
        ddogctl logs search "status:error" --service my-api
    """
    ctx.ensure_object(dict)
    ctx.obj["profile"] = profile


# Import and register all command groups
# ruff: noqa: E402
from ddogctl.commands.monitor import monitor
from ddogctl.commands.metric import metric
from ddogctl.commands.event import event
from ddogctl.commands.host import host
from ddogctl.commands.apm import apm
from ddogctl.commands.logs import logs
from ddogctl.commands.dbm import dbm
from ddogctl.commands.investigate import investigate
from ddogctl.commands.service_check import service_check
from ddogctl.commands.tag import tag
from ddogctl.commands.downtime import downtime
from ddogctl.commands.slo import slo
from ddogctl.commands.dashboard import dashboard
from ddogctl.commands.synthetics import synthetics
from ddogctl.commands.rum import rum
from ddogctl.commands.notebook import notebook
from ddogctl.commands.completion import completion
from ddogctl.commands.apply import apply_cmd, diff_cmd
from ddogctl.commands.config import config
from ddogctl.commands.incident import incident
from ddogctl.commands.user import user
from ddogctl.commands.usage import usage
from ddogctl.commands.ci import ci

main.add_command(monitor)
main.add_command(metric)
main.add_command(event)
main.add_command(host)
main.add_command(apm)
main.add_command(logs)
main.add_command(dbm)
main.add_command(investigate)
main.add_command(service_check)
main.add_command(tag)
main.add_command(downtime)
main.add_command(slo)
main.add_command(dashboard)
main.add_command(synthetics)
main.add_command(rum)
main.add_command(notebook)
main.add_command(completion)
main.add_command(apply_cmd)
main.add_command(diff_cmd)
main.add_command(config)
main.add_command(incident)
main.add_command(user)
main.add_command(usage)
main.add_command(ci)


if __name__ == "__main__":
    main()
