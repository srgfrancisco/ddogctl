# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ddogctl is a modern CLI for the Datadog API. Like Dogshell, but better. Rich terminal output, 22 command groups, retry logic, structured JSON output, stdin piping, and investigation workflows. Requires Python 3.10+.

## Commands

```bash
# Setup
curl -LsSf https://astral.sh/uv/install.sh | sh  # Install uv if needed
uv sync --all-extras                          # --all-extras required for dev tools

# Run tests
uv run pytest tests/ -v
uv run pytest tests/commands/test_apm.py -v          # single module
uv run pytest tests/commands/test_apm.py::test_name   # single test
uv run pytest tests/ --cov=ddogctl --cov-report=html  # coverage
uv run pytest tests/ -m "not integration"             # skip integration tests

# Code quality
uv run black ddogctl/ tests/                          # format (line-length: 100)
uv run ruff check ddogctl/ tests/                     # lint (line-length: 100)
uv run mypy ddogctl/                                  # type check

# Run CLI
export DD_API_KEY=... DD_APP_KEY=...
uv run ddogctl monitor list --state Alert
uv run ddogctl apm services
uv run ddogctl logs search "status:error" --service my-api
uv run ddogctl dbm queries --sort-by avg_latency
uv run ddogctl investigate latency my-service --threshold 500
uv run ddogctl monitor list --state Alert --watch 10   # refresh every 10s
```

## Architecture

**Entry point**: `ddogctl.cli:main` — a Click group (`AliasGroup`) that registers command subgroups.

**Command groups** (`ddogctl/commands/`): Each file defines a Click group with subcommands. Commands call `get_datadog_client()` to get an API client, then use Rich for output formatting. All commands support `--format json|table`.
- **Defensive attribute access**: Use `getattr(obj, "attr", default)` for optional attributes (pattern in rum.py, incident.py, user.py). API responses vary by source (e.g., AWS Firelens logs).

```
ddogctl monitor      {list, get, create, update, delete, mute, unmute, validate, mute-all, unmute-all}
ddogctl metric       {query, search, metadata}
ddogctl event        {list, get, post}
ddogctl host         {list, get, totals}
ddogctl apm          {services, traces, analytics}
ddogctl logs         {search, tail, query, trace}
ddogctl dbm          {hosts, queries, explain, samples}
ddogctl investigate  {latency, errors, throughput, compare}
ddogctl dashboard    {list, get, create, update, delete, export, clone}
ddogctl slo          {list, get, create, update, delete, history, export}
ddogctl downtime     {list, get, create, update, delete, cancel-by-scope}
ddogctl tag          {list, add, replace, detach}
ddogctl service-check {post}
ddogctl synthetics   {list, get, results, trigger}
ddogctl incident     {list, get, create, update, delete}
ddogctl notebook     {list, get, create, delete}
ddogctl user         {list, get, invite, disable}
ddogctl usage        {summary, hosts, logs, top-avg-metrics}
ddogctl rum          {events, analytics}
ddogctl ci           {pipelines, tests, pipeline-details}
ddogctl config       {init, set-profile, use-profile, list-profiles, get}
ddogctl apply        -f <file> [--dry-run] [--recursive]
ddogctl diff         -f <file>
ddogctl completion   {bash, zsh, fish}
```

**Aliases**: `mon`=monitor, `dash`=dashboard, `dt`=downtime, `sc`=service-check, `inv`=investigate

**Key modules**:
- `ddogctl/client.py` — `DatadogClient` wraps `datadog_api_client` SDK. V1 APIs: monitors, metrics, events, hosts, tags, service_checks, downtimes, slos, dashboards, usage, synthetics, notebooks. V2 APIs: logs, spans, service_definitions, incidents, users, rum, ci_pipelines, ci_tests. Use `get_datadog_client()` to instantiate.
- `ddogctl/config.py` — `DatadogConfig` (Pydantic BaseSettings) loads from env vars (`DD_API_KEY`, `DD_APP_KEY`, `DD_SITE`) or `~/.ddogctl/config.json` profiles. Supports region shortcuts (us, eu, us3, us5, ap1, gov). Precedence: CLI `--profile` flag > env var > active profile > defaults.
- `ddogctl/utils/error.py` — `@handle_api_error` decorator with retry logic (exponential backoff on 429/5xx, immediate exit on 401/403). Emits structured JSON errors when `--format json`.
- `ddogctl/utils/exit_codes.py` — Semantic exit codes: 0=success, 1=general, 2=auth, 3=not found, 4=validation, 5=rate limited, 6=server error.
- `ddogctl/utils/time.py` — `parse_time_range()` handles relative (1h, 24h, 7d) and ISO datetime formats, returns Unix timestamps.
- `ddogctl/utils/confirm.py` — `--confirm` flag utility for destructive operations.
- `ddogctl/utils/file_input.py` — `-f`/`--file` JSON input parsing.
- `ddogctl/utils/export.py` — JSON export to file.
- `ddogctl/utils/stdin.py` — `--from-stdin` flag for composable piping.
- `ddogctl/utils/watch.py` — `--watch` mode with Rich Live display.
- `ddogctl/utils/output.py` — Structured error output helpers.
- `ddogctl/utils/tags.py` — Tag parsing and display formatting.
- `ddogctl/utils/spans.py` — `aggregate_spans()` wrapper for spans API aggregation.

## Testing Patterns

Tests use `unittest.mock` with Click's `CliRunner`. Key fixtures from `tests/conftest.py`:
- `mock_client` — Mock with all API attributes (`.monitors`, `.hosts`, `.metrics`, `.events`, `.spans`, `.logs`, `.dbm`, `.service_definitions`, `.service_checks`, `.downtimes`, `.slos`, `.dashboards`, `.incidents`, `.users`, `.usage`, `.synthetics`, `.rum`, `.ci_pipelines`, `.ci_tests`, `.notebooks`)
- `runner` — `CliRunner()` instance
- Factory functions: `create_mock_monitor()`, `create_mock_host()`, `create_mock_span()`, `create_mock_log()`, `create_mock_dbm_host()`, `create_mock_dbm_query()`, `create_mock_dbm_sample()`, `create_mock_service_list()`, `create_mock_rum_event()`

Standard test pattern: patch `get_datadog_client` to return `mock_client`, invoke command via `runner`, assert on output and exit code.
- **Mock attribute limiting**: Use `Mock(spec_set=["attr1", "attr2"])` to limit attributes. `del mock.attr` doesn't work—Mock returns new Mock for any attribute access.

## Development Workflow

- **Worktrees**: Always create a Git worktree for every new feature, fix, or change. Use the `./.worktrees` folder. Use `git gtr` instead of plain `git worktree` commands.
- **Pull requests**: Every change lands via PR — no direct commits to `main`. Open a PR from the worktree branch, get it reviewed, then merge.
- **Branch protection**: Cannot push directly to `main`—branch protection rules require all changes via PRs.
- **Commits**: Follow conventional commit format.
- **CI**: Tests run on Python 3.10-3.13 + `claude-review` AI code review. Never merge without all CI checks passing.

## Development Methodology

Strict TDD (RED-GREEN-REFACTOR). Coverage target >90%. Reference implementation: `ddogctl/commands/apm.py`.

## Gotchas

- `uv sync` without `--all-extras` will miss dev dependencies (black, ruff, mypy, pytest).
- When parallel PRs modify `cli.py`, `client.py`, and `conftest.py` (shared files), merge sequentially and rebase each subsequent PR.
- `git gtr` may not be available everywhere — falls back to `git worktree` commands.
- The `claude-review` CI check can take 5-17 minutes. Wait for it before merging.
- Worktrees: run `uv sync --all-extras` after creation; use `--force` to remove (uv untracked files); use `gh pr merge --squash` without `--delete-branch` if worktree still references branch.
- `git remote prune origin` cleans stale remote tracking refs after branch deletion.

## Releasing

Fully automated via `python-semantic-release`. On every merge to `main`:
1. CI tests run (Python 3.10-3.13)
2. Commits since last tag are analyzed for conventional commit prefixes
3. If `feat`/`fix`/`perf`/breaking changes found: version is bumped in `pyproject.toml`, tagged, published to PyPI, and a GitHub Release is created
4. If only `chore`/`docs`/`ci`/`refactor` commits: no release

Version lives in `pyproject.toml` only. `cli.py` reads it at runtime via `importlib.metadata`.

To force a major bump: use `feat!:` prefix or include `BREAKING CHANGE:` in commit body.

- **Setup requirements**: `RELEASE_TOKEN` (fine-grained PAT with Contents: Read & Write) in repo secrets, PyPI trusted publisher configured for workflow `release.yml`
