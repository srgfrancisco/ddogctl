# ddogctl

**A modern CLI for the Datadog API. Like Dogshell, but better.**

## Features

- Rich terminal output with tables, colors, and progress bars
- APM trace search and service listing
- Log querying with trace correlation
- Database monitoring (DBM) for top queries, query samples, and explain plans
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

### Database Monitoring access

`dbm hosts` and `dbm queries` read the Agent's per-query metrics (`mysql.queries.*`,
`postgresql.queries.*`), so any credentials that can query metrics work, PATs included.
`dbm samples` and `dbm explain` read query samples and explain plans through the endpoint in
Datadog's [DBM API guide](https://docs.datadoghq.com/database_monitoring/guide/build_apps_with_dbm_api/),
which requires `DD_API_KEY` plus an **unscoped** application key. PATs and scoped keys may be
rejected with a 403.

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

# Database Monitoring (MySQL, Postgres)
ddogctl dbm hosts --from 24h
ddogctl dbm queries --host db-prod-01 --sort-by avg_latency --from 4h
ddogctl dbm queries --engine mysql --database shop --sort-by lock_time
ddogctl dbm samples 558c51ab1be9812b --limit 20    # needs an unscoped app key
ddogctl dbm explain 558c51ab1be9812b              # needs an unscoped app key

# Investigation Workflows
ddogctl investigate service my-api --from 1h
ddogctl investigate host web-prod-01 --from 30m
```

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for setup instructions and development guidelines.

## License

[MIT](./LICENSE)
