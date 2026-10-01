"""Database monitoring commands.

Datadog has no dedicated DBM API. Following Datadog's guide "Building applications with
the Database Monitoring API":
- `hosts` and `queries` read the Agent's per-query metrics (mysql.queries.*,
  postgresql.queries.*) through the v2 scalar metrics API, ranked server-side.
- `samples` and `explain` read dbm_type:activity / dbm_type:plan records from the
  databasequery index, which requires an unscoped application key.
"""

import click
import json
import sys
from datadog_api_client.exceptions import ApiException
from datadog_api_client.v2.model.formula_limit import FormulaLimit
from datadog_api_client.v2.model.metrics_aggregator import MetricsAggregator
from datadog_api_client.v2.model.metrics_data_source import MetricsDataSource
from datadog_api_client.v2.model.metrics_scalar_query import MetricsScalarQuery
from datadog_api_client.v2.model.query_formula import QueryFormula
from datadog_api_client.v2.model.query_sort_order import QuerySortOrder
from datadog_api_client.v2.model.scalar_formula_query_request import ScalarFormulaQueryRequest
from datadog_api_client.v2.model.scalar_formula_request import ScalarFormulaRequest
from datadog_api_client.v2.model.scalar_formula_request_attributes import (
    ScalarFormulaRequestAttributes,
)
from datadog_api_client.v2.model.scalar_formula_request_queries import (
    ScalarFormulaRequestQueries,
)
from datadog_api_client.v2.model.scalar_formula_request_type import ScalarFormulaRequestType
from rich.console import Console
from rich.markup import escape
from rich.table import Table
from ddogctl.client import get_datadog_client
from ddogctl.utils.error import handle_api_error
from ddogctl.utils.exit_codes import AUTH_ERROR, NOT_FOUND, VALIDATION_ERROR
from ddogctl.utils.output import emit_error, set_output_format
from ddogctl.utils.time import parse_time_range

console = Console()

NS_PER_MS = 1_000_000

# Per-query metric name suffix for each field we expose.
METRICS = {
    "calls": "count",
    "total_time": "time",
    "lock_time": "lock_time",
    "rows_examined": "rows_examined",
    "rows": "rows",
}

# The Agent tags MySQL query metrics with `schema` and Postgres ones with `db`.
ENGINES = {
    "mysql": {
        "prefix": "mysql.queries",
        "db_tag": "schema",
        "extra": ["lock_time", "rows_examined"],
    },
    "postgres": {"prefix": "postgresql.queries", "db_tag": "db", "extra": ["rows"]},
}

SORT_FORMULAS = {
    "calls": "calls",
    "total_time": "total_time",
    "avg_latency": "total_time / calls",
    "lock_time": "lock_time",
    "rows_examined": "rows_examined",
    "rows": "rows",
}

# Bucket the scalar API returns for series beyond the formula limit.
OTHER_GROUP = "_other"


def _ms(ns):
    return round(ns / NS_PER_MS, 2) if ns is not None else None


def _count(value):
    return round(value) if value is not None else 0


def _ratio(value):
    return round(value, 2) if value is not None else None


def _scope(tags):
    return "{" + ",".join(tags) + "}" if tags else "{*}"


def _query_scalar(client, queries, formulas, sort_formula, limit, from_ts, to_ts):
    """Run a scalar metrics query and return one dict per group, ranked by sort_formula.

    queries maps query names to metric queries; formulas reference those names. Each
    returned row maps group-by tag names and formula strings to their values.
    """
    body = ScalarFormulaQueryRequest(
        data=ScalarFormulaRequest(
            type=ScalarFormulaRequestType.SCALAR_REQUEST,
            attributes=ScalarFormulaRequestAttributes(
                _from=from_ts * 1000,
                to=to_ts * 1000,
                queries=ScalarFormulaRequestQueries(
                    [
                        MetricsScalarQuery(
                            name=name,
                            data_source=MetricsDataSource.METRICS,
                            query=query,
                            aggregator=MetricsAggregator.SUM,
                        )
                        for name, query in queries.items()
                    ]
                ),
                formulas=[
                    (
                        # Ask for one extra row so a trailing "_other" bucket
                        # doesn't cost a real row.
                        QueryFormula(
                            formula=f,
                            limit=FormulaLimit(count=limit + 1, order=QuerySortOrder.DESC),
                        )
                        if f == sort_formula
                        else QueryFormula(formula=f)
                    )
                    for f in formulas
                ],
            ),
        )
    )
    response = client.dbm.query_scalar(body)

    columns = response.data.attributes.columns
    groups = {c.name: c.values for c in columns if str(c.type) == "group"}
    numbers = {c.name: c.values for c in columns if str(c.type) == "number"}
    size = min((len(v) for v in numbers.values()), default=0)

    rows = []
    for i in range(size):
        row = {name: ",".join(values[i]) for name, values in groups.items()}
        if OTHER_GROUP in row.values():
            continue
        row.update({name: values[i] for name, values in numbers.items()})
        rows.append(row)
    return rows[:limit]


def _engines(engine):
    return list(ENGINES) if engine in (None, "all") else [engine]


@click.group()
def dbm():
    """Database monitoring commands (MySQL and Postgres)."""
    pass


@dbm.command(name="hosts")
@click.option(
    "--engine",
    type=click.Choice(["all", *ENGINES]),
    default="all",
    help="Database engine",
)
@click.option("--env", default=None, help="Filter by environment")
@click.option("--from", "from_time", default="1h", help="Start time (e.g., 1h, 24h, 7d)")
@click.option("--to", "to_time", default="now", help="End time")
@click.option("--limit", default=100, type=int, help="Max hosts per engine")
@click.option("--format", type=click.Choice(["json", "table"]), default="table")
@handle_api_error
def list_hosts(engine, env, from_time, to_time, limit, format):
    """List database hosts reporting DBM query metrics.

    Hosts are ranked by query executions over the time range.
    """
    client = get_datadog_client()
    from_ts, to_ts = parse_time_range(from_time, to_time)
    scope = _scope([f"env:{env}"] if env else [])

    hosts = []
    with console.status("[cyan]Fetching database hosts...[/cyan]"):
        for name in _engines(engine):
            prefix = ENGINES[name]["prefix"]
            queries = {
                "calls": f"sum:{prefix}.count{scope} by {{host}}",
                "total_time": f"sum:{prefix}.time{scope} by {{host}}",
            }
            formulas = ["calls", "total_time", SORT_FORMULAS["avg_latency"]]
            rows = _query_scalar(client, queries, formulas, "calls", limit, from_ts, to_ts)
            for row in rows:
                hosts.append(
                    {
                        "host": row.get("host"),
                        "engine": name,
                        "calls": _count(row.get("calls")),
                        "total_time_ms": _ms(row.get("total_time")),
                        "avg_latency_ms": _ms(row.get(SORT_FORMULAS["avg_latency"])),
                    }
                )

    hosts.sort(key=lambda h: h["calls"], reverse=True)

    if format == "json":
        print(json.dumps(hosts, indent=2))
        return

    if not hosts:
        console.print(
            "[yellow]No hosts are reporting DBM query metrics in this time range.[/yellow]"
        )
        return

    table = Table(title="Database Hosts")
    table.add_column("Host", style="cyan")
    table.add_column("Engine", style="white")
    table.add_column("Calls", justify="right", style="yellow")
    table.add_column("Total Time (ms)", justify="right", style="yellow")
    table.add_column("Avg Latency (ms)", justify="right", style="yellow")

    for h in hosts:
        table.add_row(
            escape(str(h["host"])),
            h["engine"],
            f"{h['calls']:,}",
            _fmt(h["total_time_ms"]),
            _fmt(h["avg_latency_ms"]),
        )

    console.print(table)
    console.print(f"\n[dim]Total hosts: {len(hosts)}[/dim]")


def _fmt(value):
    return "-" if value is None else f"{value:,.2f}"


def _query_row(row, engine):
    out = {
        "query_signature": row.get("query_signature"),
        "query": row.get("query"),
        "engine": engine,
        "calls": _count(row.get("calls")),
        "total_time_ms": _ms(row.get("total_time")),
        "avg_latency_ms": _ms(row.get(SORT_FORMULAS["avg_latency"])),
    }
    if engine == "mysql":
        out["lock_time_ms"] = _ms(row.get("lock_time"))
        out["rows_examined"] = _count(row.get("rows_examined"))
        out["avg_rows_examined"] = _ratio(row.get("rows_examined / calls"))
    else:
        out["rows"] = _count(row.get("rows"))
        out["avg_rows"] = _ratio(row.get("rows / calls"))
    return out


@dbm.command(name="queries")
@click.option(
    "--engine",
    type=click.Choice(list(ENGINES)),
    default=None,
    help="Database engine (default: first of mysql, postgres with data)",
)
@click.option("--from", "from_time", default="1h", help="Start time (e.g., 1h, 24h, 7d)")
@click.option("--to", "to_time", default="now", help="End time")
@click.option("--host", default=None, help="Filter by database host")
@click.option("--database", default=None, help="Filter by database (MySQL schema / Postgres db)")
@click.option("--service", default=None, help="Filter by service tag on the DBM check")
@click.option("--env", default=None, help="Filter by environment")
@click.option("--tag", "tags", multiple=True, help="Extra tag filter (repeatable), e.g. team:core")
@click.option(
    "--sort-by",
    "sort_by",
    type=click.Choice(list(SORT_FORMULAS)),
    default="total_time",
    help="Rank by field; lock_time/rows_examined are MySQL-only, rows is Postgres-only",
)
@click.option("--limit", default=20, type=int, help="Max queries to return")
@click.option("--format", type=click.Choice(["json", "table"]), default="table")
@handle_api_error
def list_queries(
    engine, from_time, to_time, host, database, service, env, tags, sort_by, limit, format
):
    """List top normalized queries from DBM query metrics.

    Times come from mysql.queries.* / postgresql.queries.* and are summed over the
    time range. Use the QUERY_SIGNATURE with `dbm samples` and `dbm explain`.
    """
    candidates = [e for e in _engines(engine) if sort_by in _sort_keys(e)]
    if not candidates:
        set_output_format(format)
        emit_error(
            "VALIDATION_ERROR",
            400,
            f"--sort-by {sort_by} is not available for {engine}",
            f"Choose one of: {', '.join(_sort_keys(engine))}",
        )
        sys.exit(VALIDATION_ERROR)

    client = get_datadog_client()
    from_ts, to_ts = parse_time_range(from_time, to_time)

    results, used_engine = [], candidates[0]
    with console.status("[cyan]Fetching database queries...[/cyan]"):
        for name in candidates:
            spec = ENGINES[name]
            filters = []
            if host:
                filters.append(f"host:{host}")
            if database:
                filters.append(f"{spec['db_tag']}:{database}")
            if service:
                filters.append(f"service:{service}")
            if env:
                filters.append(f"env:{env}")
            filters.extend(tags)
            scope = _scope(filters)

            queries = {
                f: f"sum:{spec['prefix']}.{METRICS[f]}{scope} by {{query_signature,query}}"
                for f in ["calls", "total_time", *spec["extra"]]
            }
            formulas = ["calls", "total_time", SORT_FORMULAS["avg_latency"]]
            for extra in spec["extra"]:
                formulas += [extra, f"{extra} / calls"]
            rows = _query_scalar(
                client, queries, formulas, SORT_FORMULAS[sort_by], limit, from_ts, to_ts
            )
            if rows:
                results, used_engine = [_query_row(r, name) for r in rows], name
                break

    if format == "json":
        print(json.dumps(results, indent=2))
        return

    if not results:
        console.print("[yellow]No DBM query metrics found in this time range.[/yellow]")
        return

    table = Table(title=f"Top Queries ({used_engine}, by {sort_by})")
    table.add_column("Signature", style="cyan", no_wrap=True)
    table.add_column("Query", style="white", max_width=60, no_wrap=True, overflow="ellipsis")
    table.add_column("Calls", justify="right", style="yellow")
    table.add_column("Total (ms)", justify="right", style="yellow")
    table.add_column("Avg (ms)", justify="right", style="yellow")
    if used_engine == "mysql":
        table.add_column("Lock (ms)", justify="right", style="yellow")
        table.add_column("Rows exam./call", justify="right", style="yellow")
    else:
        table.add_column("Rows/call", justify="right", style="yellow")

    for q in results:
        cells = [
            escape(str(q["query_signature"])),
            escape(str(q["query"])),
            f"{q['calls']:,}",
            _fmt(q["total_time_ms"]),
            _fmt(q["avg_latency_ms"]),
        ]
        if used_engine == "mysql":
            cells += [_fmt(q["lock_time_ms"]), _fmt(q["avg_rows_examined"])]
        else:
            cells.append(_fmt(q["avg_rows"]))
        table.add_row(*cells)

    console.print(table)
    console.print(f"\n[dim]Total queries: {len(results)}[/dim]")


def _sort_keys(engine):
    """The --sort-by values an engine's metrics support."""
    return ["calls", "total_time", "avg_latency", *ENGINES[engine]["extra"]]


def _search_dbm_events(client, query, from_time, to_time, limit, format):
    """Search DBM samples/plans, turning a 403 into a hint about the key it needs."""
    from_ts, to_ts = parse_time_range(from_time, to_time)
    try:
        return client.dbm.search_events(
            query, from_ms=from_ts * 1000, to_ms=to_ts * 1000, limit=limit
        )
    except ApiException as e:
        if e.status != 403:
            raise
        set_output_format(format)
        emit_error(
            "PERMISSION_DENIED",
            403,
            "Datadog denied access to DBM query samples and explain plans.",
            "This endpoint needs DD_API_KEY plus an unscoped application key for a user "
            "with Database Monitoring access; Personal Access Tokens and scoped keys may "
            f"be rejected. In the UI: {client.dbm.app_url}/databases/samples",
        )
        sys.exit(AUTH_ERROR)


def _db(event):
    return event.get("custom", {}).get("db", {})


@dbm.command(name="samples")
@click.argument("query_signature", required=False)
@click.option("--from", "from_time", default="1h", help="Start time (e.g., 1h, 24h, 7d)")
@click.option("--to", "to_time", default="now", help="End time")
@click.option("--host", default=None, help="Filter by database host")
@click.option("--service", default=None, help="Filter by service")
@click.option("--env", default=None, help="Filter by environment")
@click.option("--limit", default=10, type=click.IntRange(1, 1000), help="Max samples (1-1000)")
@click.option("--format", type=click.Choice(["json", "table"]), default="table")
@handle_api_error
def list_samples(query_signature, from_time, to_time, host, service, env, limit, format):
    """List query samples (point-in-time snapshots of running queries).

    QUERY_SIGNATURE (from `dbm queries`) narrows to one query; omit it to see recent
    activity. Requires an unscoped application key.
    """
    client = get_datadog_client()

    parts = ["dbm_type:activity"]
    if query_signature:
        parts.append(f"@db.query_signature:{query_signature}")
    if host:
        parts.append(f"host:{host}")
    if service:
        parts.append(f"service:{service}")
    if env:
        parts.append(f"env:{env}")

    with console.status("[cyan]Fetching query samples...[/cyan]"):
        records = _search_dbm_events(client, " ".join(parts), from_time, to_time, limit, format)
    events = [r.get("event", {}) for r in records]

    if format == "json":
        print(json.dumps(events, indent=2, default=str))
        return

    if not events:
        console.print("[yellow]No query samples found in this time range.[/yellow]")
        return

    table = Table(title="Query Samples")
    table.add_column("Time", style="cyan", no_wrap=True)
    table.add_column("Host", style="white")
    table.add_column("Rows", justify="right", style="yellow")
    table.add_column("Wait Event", style="magenta")
    table.add_column("Statement", style="white", max_width=60, no_wrap=True, overflow="ellipsis")

    for event in events:
        db = _db(event)
        wait = "/".join(str(w) for w in (db.get("wait_event_type"), db.get("wait_event")) if w)
        table.add_row(
            escape(str(event.get("timestamp", ""))),
            escape(str(event.get("host", ""))),
            "" if db.get("rows") is None else str(db.get("rows")),
            escape(wait),
            escape(str(db.get("statement", ""))),
        )

    console.print(table)
    console.print(f"\n[dim]Total samples: {len(events)}[/dim]")


def _plan_row(event):
    db = _db(event)
    plan = db.get("plan", {})
    definition = plan.get("definition")
    if isinstance(definition, str):
        try:
            definition = json.loads(definition)
        except ValueError:
            pass  # MySQL text plans aren't JSON; keep as text.
    return {
        "timestamp": event.get("timestamp"),
        "host": event.get("host"),
        "query_signature": db.get("query_signature"),
        "statement": db.get("statement"),
        "plan_signature": plan.get("signature"),
        "cost": plan.get("cost"),
        "plan": definition,
    }


@dbm.command(name="explain")
@click.argument("query_signature")
@click.option("--from", "from_time", default="24h", help="Start time (e.g., 1h, 24h, 7d)")
@click.option("--to", "to_time", default="now", help="End time")
@click.option(
    "--limit", default=1, type=click.IntRange(1, 1000), help="Max plans, most recent first"
)
@click.option("--format", type=click.Choice(["json", "text"]), default="text")
@handle_api_error
def explain_query(query_signature, from_time, to_time, limit, format):
    """Show explain plans the Agent collected for a query.

    QUERY_SIGNATURE comes from `dbm queries`. Requires an unscoped application key.
    """
    client = get_datadog_client()

    query = f"dbm_type:plan @db.query_signature:{query_signature}"
    with console.status(f"[cyan]Fetching explain plans for {query_signature}...[/cyan]"):
        records = _search_dbm_events(client, query, from_time, to_time, limit, format)
    plans = [_plan_row(r.get("event", {})) for r in records]

    if not plans:
        console.print(
            f"[yellow]No explain plans found for {escape(query_signature)} "
            f"between {from_time} and {to_time}. Try a wider --from.[/yellow]"
        )
        sys.exit(NOT_FOUND)

    if format == "json":
        print(json.dumps(plans, indent=2, default=str))
        return

    for p in plans:
        console.print(f"\n[bold cyan]Explain plan for {escape(query_signature)}[/bold cyan]")
        console.print(
            f"[dim]Time: {escape(str(p['timestamp']))}  Host: {escape(str(p['host']))}[/dim]"
        )
        console.print(
            f"[dim]Plan signature: {escape(str(p['plan_signature']))}  Cost: {p['cost']}[/dim]"
        )
        console.print(f"\n{escape(str(p['statement']))}\n")
        plan = p["plan"]
        text = plan if isinstance(plan, str) else json.dumps(plan, indent=2)
        console.print(escape(str(text)), highlight=False)
