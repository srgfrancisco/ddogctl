# ddogctl

**A modern CLI for the Datadog API. Like Dogshell, but better.**

## Features

- Rich terminal output with tables, colors, and progress bars
- APM trace search and service listing
- Log querying with trace correlation
- Database monitoring (DBM) for slow queries and execution plans
- Investigation workflows that correlate across monitors, traces, logs, and hosts
- Retry logic with exponential backoff
- Region shortcuts (`us`, `eu`, `us3`, `us5`, `ap1`, `gov`)

## ddogctl vs Dogshell

| Feature | ddogctl | Dogshell |
|---|---|---|
| Rich terminal output | Yes | No |
| APM traces | Yes | No |
| Log search + correlation | Yes | No |
| Database monitoring | Yes | No |
| Investigation workflows | Yes | No |
| Retry with backoff | Yes | No |
| Active maintenance | Yes | Deprecated |

## Installation

```bash
pip install ddogctl
```

Or with pipx:

```bash
pipx install ddogctl
```

Or with uv:

```bash
uv pip install ddogctl
```

## Configuration

Set the required environment variables:

```bash
export DD_API_KEY="your-api-key"
export DD_APP_KEY="your-app-key"
export DD_SITE="us"  # optional, defaults to datadoghq.com
```

### Personal Access Tokens

ddogctl also accepts a Datadog [Personal Access Token](https://docs.datadoghq.com/account_management/personal-access-tokens/) (PAT).
A PAT is scoped to your user and expires, so you don't need an API key for most commands:

```bash
export DD_PAT="ddpat_..."
# or save it in a profile
ddogctl config init --auth pat
ddogctl config set-profile work --pat ddpat_... --site eu
```

A `ddpat_` value in `DD_APP_KEY` is detected as a PAT too. Commands that send data to Datadog
(`event post`, `service-check post`) still need `DD_API_KEY` alongside the PAT.

### Region Shortcuts

| Shortcut | Site |
|---|---|
| `us` | `datadoghq.com` |
| `eu` | `datadoghq.eu` |
| `us3` | `us3.datadoghq.com` |
| `us5` | `us5.datadoghq.com` |
| `ap1` | `ap1.datadoghq.com` |
| `gov` | `ddog-gov.com` |

## Quick Start

```bash
# Monitors
ddogctl monitor list --state Alert
ddogctl monitor get 12345

# Metrics
ddogctl metric query "avg:system.cpu.user{env:prod}" --from 1h
ddogctl metric search "cpu"

# Events
ddogctl event list --from 1d --priority normal
ddogctl event post "Deployment" "v2.1.0 deployed to prod"

# Hosts
ddogctl host list --filter "env:prod"
ddogctl host info web-prod-01

# APM
ddogctl apm services
ddogctl apm traces my-service --from 1h
ddogctl apm spans search "service:worker @job.name:SyncJob" --field @messaging.destination
ddogctl apm spans search "service:mysql @duration:>1s" --format json   # full span: parent_id, tags, custom attrs
ddogctl apm trace 5501770330737245996                                  # span tree + root span

# Logs
ddogctl logs search "status:error" --service my-api --from 30m
ddogctl logs tail "env:prod" --follow

# Database Monitoring
ddogctl dbm slow-queries --service postgres-prod --from 1h
ddogctl dbm explain "SELECT * FROM users WHERE id = 1"

# Investigation Workflows
ddogctl investigate service my-api --from 1h
ddogctl investigate host web-prod-01 --from 30m
```

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for setup instructions and development guidelines.

## License

[MIT](./LICENSE)
