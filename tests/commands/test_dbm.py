"""Tests for DBM (Database Monitoring) commands.

Datadog has no dedicated DBM REST API in the SDK. Per Datadog's guide "Building
applications with the Database Monitoring API":
- query metrics come from the v2 scalar metrics API (mysql.queries.*, postgresql.queries.*)
- query samples / explain plans come from the logs-analytics list endpoint on app.<site>

Scalar responses are built from real datadog_api_client models so column shapes match
what the API returns (group columns hold lists of tag values, number columns floats).
"""

import json
from unittest.mock import patch

from rich.console import Console

from datadog_api_client.exceptions import ForbiddenException
from datadog_api_client.v2.model.data_scalar_column import DataScalarColumn
from datadog_api_client.v2.model.group_scalar_column import GroupScalarColumn
from datadog_api_client.v2.model.scalar_column_type_group import ScalarColumnTypeGroup
from datadog_api_client.v2.model.scalar_column_type_number import ScalarColumnTypeNumber
from datadog_api_client.v2.model.scalar_formula_query_response import (
    ScalarFormulaQueryResponse,
)
from datadog_api_client.v2.model.scalar_formula_response_atrributes import (
    ScalarFormulaResponseAtrributes,
)
from datadog_api_client.v2.model.scalar_formula_response_type import ScalarFormulaResponseType
from datadog_api_client.v2.model.scalar_response import ScalarResponse

from ddogctl.commands.dbm import dbm

NS_PER_MS = 1_000_000


def scalar_response(groups, numbers):
    """Build a ScalarFormulaQueryResponse.

    groups: {tag_name: [value, ...]}; numbers: {formula: [value, ...]} (aligned by index).
    """
    columns = [
        GroupScalarColumn(name=name, type=ScalarColumnTypeGroup.GROUP, values=[[v] for v in values])
        for name, values in groups.items()
    ]
    columns += [
        DataScalarColumn(name=name, type=ScalarColumnTypeNumber.NUMBER, values=values)
        for name, values in numbers.items()
    ]
    return ScalarFormulaQueryResponse(
        data=ScalarResponse(
            type=ScalarFormulaResponseType.SCALAR_RESPONSE,
            attributes=ScalarFormulaResponseAtrributes(columns=columns),
        )
    )


def empty_response():
    """What the API returns when no series match: no group column, empty number column."""
    return scalar_response({}, {"calls": []})


def sent_request(mock_client, call_index=0):
    """Return (queries by name, formulas) from the Nth scalar request sent."""
    body = mock_client.dbm.query_scalar.call_args_list[call_index].args[0]
    attrs = body.data.attributes
    queries = {q.name: q.query for q in attrs.queries.value}
    return queries, attrs.formulas


def invoke(runner, mock_client, args):
    # A wide console keeps table cells on one line so assertions can match them.
    with (
        patch("ddogctl.commands.dbm.get_datadog_client", return_value=mock_client),
        patch("ddogctl.commands.dbm.console", Console(width=200)),
    ):
        return runner.invoke(dbm, args)


# ---- hosts ----


def test_hosts_queries_dbm_metrics_by_host(mock_client, runner):
    mock_client.dbm.query_scalar.side_effect = [
        scalar_response(
            {"host": ["db-1", "db-2"]},
            {
                "calls": [1000.0, 10.0],
                "total_time": [2000 * NS_PER_MS, 50 * NS_PER_MS],
                "total_time / calls": [2 * NS_PER_MS, 5 * NS_PER_MS],
            },
        ),
        empty_response(),
    ]

    result = invoke(runner, mock_client, ["hosts", "--format", "json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == [
        {
            "host": "db-1",
            "engine": "mysql",
            "calls": 1000,
            "total_time_ms": 2000.0,
            "avg_latency_ms": 2.0,
        },
        {
            "host": "db-2",
            "engine": "mysql",
            "calls": 10,
            "total_time_ms": 50.0,
            "avg_latency_ms": 5.0,
        },
    ]
    mysql_queries, _ = sent_request(mock_client, 0)
    pg_queries, _ = sent_request(mock_client, 1)
    assert mysql_queries["calls"] == "sum:mysql.queries.count{*} by {host}.as_count()"
    assert mysql_queries["total_time"] == "sum:mysql.queries.time{*} by {host}.as_count()"
    assert pg_queries["calls"] == "sum:postgresql.queries.count{*} by {host}.as_count()"


def test_hosts_merges_engines_sorted_by_calls(mock_client, runner):
    mock_client.dbm.query_scalar.side_effect = [
        scalar_response(
            {"host": ["mysql-1"]},
            {"calls": [5.0], "total_time": [5.0], "total_time / calls": [1.0]},
        ),
        scalar_response(
            {"host": ["pg-1"]},
            {"calls": [50.0], "total_time": [5.0], "total_time / calls": [0.1]},
        ),
    ]

    result = invoke(runner, mock_client, ["hosts", "--format", "json"])

    assert result.exit_code == 0, result.output
    hosts = json.loads(result.output)
    assert [(h["host"], h["engine"]) for h in hosts] == [("pg-1", "postgres"), ("mysql-1", "mysql")]


def test_hosts_env_and_engine_filters(mock_client, runner):
    mock_client.dbm.query_scalar.return_value = empty_response()

    result = invoke(runner, mock_client, ["hosts", "--env", "prod", "--engine", "postgres"])

    assert result.exit_code == 0, result.output
    assert mock_client.dbm.query_scalar.call_count == 1
    queries, _ = sent_request(mock_client)
    assert queries["calls"] == "sum:postgresql.queries.count{env:prod} by {host}.as_count()"


def test_hosts_sends_time_range_in_ms_and_ranks_server_side(mock_client, runner):
    mock_client.dbm.query_scalar.return_value = empty_response()

    with patch("ddogctl.commands.dbm.parse_time_range", return_value=(1000, 4600)):
        result = invoke(runner, mock_client, ["hosts", "--engine", "mysql", "--limit", "7"])

    assert result.exit_code == 0, result.output
    attrs = mock_client.dbm.query_scalar.call_args.args[0].data.attributes
    assert (attrs._from, attrs.to) == (1_000_000, 4_600_000)
    limited = [f for f in attrs.formulas if "limit" in f]
    assert [f.formula for f in limited] == ["calls"]
    # One extra row so a trailing "_other" bucket doesn't cost a real row.
    assert limited[0].limit.count == 8
    assert str(limited[0].limit.order) == "desc"


def test_hosts_table_empty(mock_client, runner):
    mock_client.dbm.query_scalar.return_value = empty_response()

    result = invoke(runner, mock_client, ["hosts"])

    assert result.exit_code == 0, result.output
    assert "No hosts are reporting DBM query metrics" in result.output


def test_hosts_table_output(mock_client, runner):
    mock_client.dbm.query_scalar.side_effect = [
        scalar_response(
            {"host": ["db-prod-01"]},
            {
                "calls": [42.0],
                "total_time": [84 * NS_PER_MS],
                "total_time / calls": [2 * NS_PER_MS],
            },
        ),
        empty_response(),
    ]

    result = invoke(runner, mock_client, ["hosts"])

    assert result.exit_code == 0, result.output
    assert "db-prod-01" in result.output
    assert "mysql" in result.output
    assert "Total hosts: 1" in result.output


# ---- queries ----


def mysql_queries_response():
    return scalar_response(
        {
            "query_signature": ["sig-a", "sig-b", "_other"],
            "query": ["SELECT * FROM users WHERE id = ?", "UPDATE orders SET x = ?", "_other"],
        },
        {
            "calls": [100.0, 4.0, 9999.0],
            "total_time": [500 * NS_PER_MS, 400 * NS_PER_MS, 1.0],
            "total_time / calls": [5 * NS_PER_MS, 100 * NS_PER_MS, 1.0],
            "lock_time": [10 * NS_PER_MS, 0.0, 1.0],
            "rows_examined": [1000.0, 8.0, 1.0],
            "rows_examined / calls": [10.0, 2.0, 1.0],
        },
    )


def test_queries_json_output_mysql(mock_client, runner):
    mock_client.dbm.query_scalar.return_value = mysql_queries_response()

    result = invoke(runner, mock_client, ["queries", "--engine", "mysql", "--format", "json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == [
        {
            "query_signature": "sig-a",
            "query": "SELECT * FROM users WHERE id = ?",
            "engine": "mysql",
            "calls": 100,
            "total_time_ms": 500.0,
            "avg_latency_ms": 5.0,
            "lock_time_ms": 10.0,
            "rows_examined": 1000,
            "avg_rows_examined": 10.0,
        },
        {
            "query_signature": "sig-b",
            "query": "UPDATE orders SET x = ?",
            "engine": "mysql",
            "calls": 4,
            "total_time_ms": 400.0,
            "avg_latency_ms": 100.0,
            "lock_time_ms": 0.0,
            "rows_examined": 8,
            "avg_rows_examined": 2.0,
        },
    ]


def test_every_metric_query_uses_as_count(mock_client, runner):
    """mysql.queries.* / postgresql.queries.* are count metrics. Without .as_count(), a
    broad scalar query interpolates sparse series: a signature with 429 calls came back
    as ~1027, and differed between runs."""
    mock_client.dbm.query_scalar.return_value = empty_response()
    commands = [["hosts", "--engine", engine] for engine in ("mysql", "postgres")]
    commands += [["queries", "--engine", "mysql", "--sort-by", "lock_time"]]
    commands += [["queries", "--engine", "postgres", "--sort-by", "rows"]]

    sent = []
    for args in commands:
        mock_client.dbm.query_scalar.reset_mock()
        result = invoke(runner, mock_client, args)
        assert result.exit_code == 0, result.output
        queries, _ = sent_request(mock_client)
        sent.extend(queries.values())

    metrics = {q.split("{")[0].removeprefix("sum:") for q in sent}
    assert metrics == {
        "mysql.queries.count",
        "mysql.queries.time",
        "mysql.queries.lock_time",
        "mysql.queries.rows_examined",
        "postgresql.queries.count",
        "postgresql.queries.time",
        "postgresql.queries.rows",
    }
    assert all(q.endswith(".as_count()") for q in sent), sent


def test_queries_builds_metric_queries_grouped_by_signature(mock_client, runner):
    mock_client.dbm.query_scalar.return_value = mysql_queries_response()

    result = invoke(runner, mock_client, ["queries", "--engine", "mysql", "--format", "json"])

    assert result.exit_code == 0, result.output
    queries, _ = sent_request(mock_client)
    assert queries == {
        "calls": "sum:mysql.queries.count{*} by {query_signature,query}.as_count()",
        "total_time": "sum:mysql.queries.time{*} by {query_signature,query}.as_count()",
        "lock_time": "sum:mysql.queries.lock_time{*} by {query_signature,query}.as_count()",
        "rows_examined": "sum:mysql.queries.rows_examined{*} by {query_signature,query}.as_count()",
    }


def test_queries_filters_map_to_tags(mock_client, runner):
    mock_client.dbm.query_scalar.return_value = empty_response()

    args = ["queries", "--engine", "mysql", "--host", "db-1", "--database", "shop"]
    args += ["--service", "api", "--env", "prod", "--tag", "team:core"]
    result = invoke(runner, mock_client, args)

    assert result.exit_code == 0, result.output
    queries, _ = sent_request(mock_client)
    scope = "{host:db-1,schema:shop,service:api,env:prod,team:core}"
    assert (
        queries["calls"]
        == f"sum:mysql.queries.count{scope} by {{query_signature,query}}.as_count()"
    )


def test_queries_postgres_uses_db_tag_and_rows_metric(mock_client, runner):
    mock_client.dbm.query_scalar.return_value = empty_response()

    args = ["queries", "--engine", "postgres", "--database", "shop", "--sort-by", "rows"]
    result = invoke(runner, mock_client, args)

    assert result.exit_code == 0, result.output
    queries, formulas = sent_request(mock_client)
    assert queries == {
        "calls": "sum:postgresql.queries.count{db:shop} by {query_signature,query}.as_count()",
        "total_time": "sum:postgresql.queries.time{db:shop} by {query_signature,query}.as_count()",
        "rows": "sum:postgresql.queries.rows{db:shop} by {query_signature,query}.as_count()",
    }
    assert [f.formula for f in formulas if "limit" in f] == ["rows"]


def test_queries_postgres_json_output(mock_client, runner):
    mock_client.dbm.query_scalar.return_value = scalar_response(
        {"query_signature": ["sig-p"], "query": ["SELECT 1"]},
        {
            "calls": [10.0],
            "total_time": [20 * NS_PER_MS],
            "total_time / calls": [2 * NS_PER_MS],
            "rows": [30.0],
            "rows / calls": [3.0],
        },
    )

    result = invoke(runner, mock_client, ["queries", "--engine", "postgres", "--format", "json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == [
        {
            "query_signature": "sig-p",
            "query": "SELECT 1",
            "engine": "postgres",
            "calls": 10,
            "total_time_ms": 20.0,
            "avg_latency_ms": 2.0,
            "rows": 30,
            "avg_rows": 3.0,
        }
    ]


def test_queries_sort_by_maps_to_limited_formula(mock_client, runner):
    expected = {
        "calls": "calls",
        "total_time": "total_time",
        "avg_latency": "total_time / calls",
        "lock_time": "lock_time",
        "rows_examined": "rows_examined",
    }
    for sort_by, formula in expected.items():
        mock_client.dbm.query_scalar.reset_mock()
        mock_client.dbm.query_scalar.return_value = empty_response()

        args = ["queries", "--engine", "mysql", "--sort-by", sort_by, "--limit", "5"]
        result = invoke(runner, mock_client, args)

        assert result.exit_code == 0, result.output
        _, formulas = sent_request(mock_client)
        limited = [f for f in formulas if "limit" in f]
        assert [f.formula for f in limited] == [formula], sort_by
        assert limited[0].limit.count == 6


def test_queries_default_sort_is_total_time(mock_client, runner):
    mock_client.dbm.query_scalar.return_value = empty_response()

    result = invoke(runner, mock_client, ["queries", "--engine", "mysql"])

    assert result.exit_code == 0, result.output
    _, formulas = sent_request(mock_client)
    assert [f.formula for f in formulas if "limit" in f] == ["total_time"]


def test_queries_trims_to_limit_after_dropping_other(mock_client, runner):
    mock_client.dbm.query_scalar.return_value = mysql_queries_response()

    args = ["queries", "--engine", "mysql", "--limit", "1", "--format", "json"]
    result = invoke(runner, mock_client, args)

    assert result.exit_code == 0, result.output
    assert [q["query_signature"] for q in json.loads(result.output)] == ["sig-a"]


def test_queries_sort_by_unsupported_for_engine(mock_client, runner):
    args = ["queries", "--engine", "postgres", "--sort-by", "lock_time"]
    result = invoke(runner, mock_client, args)

    assert result.exit_code == 4
    assert "lock_time" in result.output
    mock_client.dbm.query_scalar.assert_not_called()


def test_queries_auto_engine_falls_back_to_postgres(mock_client, runner):
    pg = scalar_response(
        {"query_signature": ["sig-p"], "query": ["SELECT 1"]},
        {
            "calls": [1.0],
            "total_time": [1.0],
            "total_time / calls": [1.0],
            "rows": [1.0],
            "rows / calls": [1.0],
        },
    )
    mock_client.dbm.query_scalar.side_effect = [empty_response(), pg]

    result = invoke(runner, mock_client, ["queries", "--format", "json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)[0]["engine"] == "postgres"
    assert mock_client.dbm.query_scalar.call_count == 2


def test_queries_auto_engine_stops_at_first_engine_with_data(mock_client, runner):
    mock_client.dbm.query_scalar.return_value = mysql_queries_response()

    result = invoke(runner, mock_client, ["queries", "--format", "json"])

    assert result.exit_code == 0, result.output
    assert mock_client.dbm.query_scalar.call_count == 1


def test_queries_auto_engine_skips_engines_without_sort_metric(mock_client, runner):
    mock_client.dbm.query_scalar.return_value = empty_response()

    result = invoke(runner, mock_client, ["queries", "--sort-by", "rows"])

    assert result.exit_code == 0, result.output
    assert mock_client.dbm.query_scalar.call_count == 1
    queries, _ = sent_request(mock_client)
    assert queries["calls"].startswith("sum:postgresql.queries.count")


def test_queries_table_output(mock_client, runner):
    mock_client.dbm.query_scalar.return_value = mysql_queries_response()

    result = invoke(runner, mock_client, ["queries", "--engine", "mysql"])

    assert result.exit_code == 0, result.output
    assert "sig-a" in result.output
    assert "SELECT * FROM users" in result.output
    assert "Lock" in result.output
    assert "Exam/call" in result.output
    assert "Total queries: 2" in result.output


def test_queries_table_keeps_numbers_visible_at_80_columns(mock_client, runner):
    """Only the Query column may shrink in a default-width terminal; signatures and numbers
    (at production magnitudes) must stay whole."""
    mock_client.dbm.query_scalar.return_value = scalar_response(
        {
            "query_signature": ["a448e2e9bcae4067"],
            "query": ["SELECT " + "a_long_column_name, " * 20],
        },
        {
            "calls": [8_379_427.0],
            "total_time": [1_028_268_000 * NS_PER_MS],
            "total_time / calls": [0.12 * NS_PER_MS],
            "lock_time": [12_696.3 * NS_PER_MS],
            "rows_examined": [8_379_427.0],
            "rows_examined / calls": [1.0],
        },
    )

    with (
        patch("ddogctl.commands.dbm.get_datadog_client", return_value=mock_client),
        patch("ddogctl.commands.dbm.console", Console(width=80)),
    ):
        result = runner.invoke(dbm, ["queries", "--engine", "mysql"])

    assert result.exit_code == 0, result.output
    for value in ("a448e2e9bcae4067", "8.38M", "285.6h", "0.12ms", "12.7s", "1.00"):
        assert value in result.output, value
    assert max(len(line) for line in result.output.splitlines()) <= 80


def test_format_duration_and_count():
    from ddogctl.commands.dbm import _count_text, _duration_text

    assert _duration_text(None) == "-"
    assert _duration_text(0.12) == "0.12ms"
    assert _duration_text(999.994) == "999.99ms"
    assert _duration_text(11_556.29) == "11.6s"
    assert _duration_text(1_026_000) == "17.1m"
    assert _duration_text(1_028_268_000) == "285.6h"
    assert _count_text(429) == "429"
    assert _count_text(9_999) == "9,999"
    assert _count_text(65_090) == "65.1k"
    assert _count_text(8_379_427) == "8.38M"
    assert _count_text(2_500_000_000) == "2.50B"


def test_queries_table_empty(mock_client, runner):
    mock_client.dbm.query_scalar.return_value = empty_response()

    result = invoke(runner, mock_client, ["queries"])

    assert result.exit_code == 0, result.output
    assert "No DBM query metrics found" in result.output


def test_queries_handles_null_values(mock_client, runner):
    mock_client.dbm.query_scalar.return_value = scalar_response(
        {"query_signature": ["sig-a"], "query": ["SELECT 1"]},
        {
            "calls": [None],
            "total_time": [5 * NS_PER_MS],
            "total_time / calls": [None],
            "lock_time": [None],
            "rows_examined": [None],
            "rows_examined / calls": [None],
        },
    )

    args = ["queries", "--engine", "mysql", "--format", "json"]
    result = invoke(runner, mock_client, args)

    assert result.exit_code == 0, result.output
    row = json.loads(result.output)[0]
    assert row["calls"] == 0
    assert row["avg_latency_ms"] is None
    assert row["total_time_ms"] == 5.0


def test_queries_rejects_unknown_sort_by(mock_client, runner):
    result = invoke(runner, mock_client, ["queries", "--sort-by", "bogus"])

    assert result.exit_code != 0
    mock_client.dbm.query_scalar.assert_not_called()


# ---- samples ----


def sample_event(statement="SELECT * FROM users WHERE id = ?", signature="sig-a"):
    return {
        "event": {
            "timestamp": "2026-10-01T12:00:00.000Z",
            "host": "db-1",
            "custom": {
                "db": {
                    "statement": statement,
                    "query_signature": signature,
                    "wait_event": "ClientRead",
                    "wait_event_type": "Client",
                    "rows": 3,
                }
            },
        }
    }


def test_samples_searches_activity_by_signature(mock_client, runner):
    mock_client.dbm.search_events.return_value = [sample_event()]

    with patch("ddogctl.commands.dbm.parse_time_range", return_value=(1000, 4600)):
        args = ["samples", "sig-a", "--host", "db-1", "--limit", "5", "--format", "json"]
        result = invoke(runner, mock_client, args)

    assert result.exit_code == 0, result.output
    mock_client.dbm.search_events.assert_called_once_with(
        "dbm_type:activity @db.query_signature:sig-a host:db-1",
        from_ms=1_000_000,
        to_ms=4_600_000,
        limit=5,
    )
    assert json.loads(result.output) == [sample_event()["event"]]


def test_samples_without_signature_lists_recent_activity(mock_client, runner):
    mock_client.dbm.search_events.return_value = []

    args = ["samples", "--service", "api", "--env", "prod"]
    result = invoke(runner, mock_client, args)

    assert result.exit_code == 0, result.output
    query = mock_client.dbm.search_events.call_args.args[0]
    assert query == "dbm_type:activity service:api env:prod"
    assert "No query samples found" in result.output


def test_samples_table_output(mock_client, runner):
    mock_client.dbm.search_events.return_value = [sample_event()]

    result = invoke(runner, mock_client, ["samples", "sig-a"])

    assert result.exit_code == 0, result.output
    assert "db-1" in result.output
    assert "ClientRead" in result.output
    assert "SELECT * FROM users" in result.output
    assert "Total samples: 1" in result.output


def test_samples_forbidden_explains_key_requirement(mock_client, runner):
    mock_client.dbm.search_events.side_effect = ForbiddenException(status=403, reason="Forbidden")
    mock_client.dbm.app_url = "https://app.datadoghq.com"

    result = invoke(runner, mock_client, ["samples", "sig-a"])

    assert result.exit_code == 2
    assert "unscoped application key" in result.output
    assert "https://app.datadoghq.com/databases/samples" in result.output


def test_samples_forbidden_json_error(mock_client, runner):
    mock_client.dbm.search_events.side_effect = ForbiddenException(status=403, reason="Forbidden")
    mock_client.dbm.app_url = "https://app.datadoghq.eu"

    result = invoke(runner, mock_client, ["samples", "sig-a", "--format", "json"])

    assert result.exit_code == 2
    error = json.loads(result.stderr)
    assert error["code"] == "PERMISSION_DENIED"
    assert "https://app.datadoghq.eu/databases/samples" in error["hint"]


# ---- explain ----


def plan_event(definition='{"Plan": {"Node Type": "Seq Scan", "Relation Name": "users"}}'):
    return {
        "event": {
            "timestamp": "2026-10-01T12:00:00.000Z",
            "host": "db-1",
            "custom": {
                "db": {
                    "statement": "SELECT * FROM users",
                    "query_signature": "sig-a",
                    "plan": {"definition": definition, "cost": 42.5, "signature": "plan-1"},
                }
            },
        }
    }


def test_explain_searches_plans_by_signature(mock_client, runner):
    mock_client.dbm.search_events.return_value = [plan_event()]

    with patch("ddogctl.commands.dbm.parse_time_range", return_value=(1000, 4600)):
        result = invoke(runner, mock_client, ["explain", "sig-a", "--format", "json"])

    assert result.exit_code == 0, result.output
    mock_client.dbm.search_events.assert_called_once_with(
        "dbm_type:plan @db.query_signature:sig-a",
        from_ms=1_000_000,
        to_ms=4_600_000,
        limit=1,
    )
    assert json.loads(result.output) == [
        {
            "timestamp": "2026-10-01T12:00:00.000Z",
            "host": "db-1",
            "query_signature": "sig-a",
            "statement": "SELECT * FROM users",
            "plan_signature": "plan-1",
            "cost": 42.5,
            "plan": {"Plan": {"Node Type": "Seq Scan", "Relation Name": "users"}},
        }
    ]


def test_explain_defaults_to_24h_window(mock_client, runner):
    mock_client.dbm.search_events.return_value = [plan_event()]

    with patch("ddogctl.commands.dbm.parse_time_range", return_value=(0, 1)) as ptr:
        result = invoke(runner, mock_client, ["explain", "sig-a"])

    assert result.exit_code == 0, result.output
    ptr.assert_called_once_with("24h", "now")


def test_explain_text_output(mock_client, runner):
    mock_client.dbm.search_events.return_value = [plan_event()]

    result = invoke(runner, mock_client, ["explain", "sig-a"])

    assert result.exit_code == 0, result.output
    assert "SELECT * FROM users" in result.output
    assert "42.5" in result.output
    assert '"Node Type": "Seq Scan"' in result.output


def test_explain_keeps_non_json_plan_as_text(mock_client, runner):
    mock_client.dbm.search_events.return_value = [plan_event(definition="-> Table scan on users")]

    result = invoke(runner, mock_client, ["explain", "sig-a", "--format", "json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)[0]["plan"] == "-> Table scan on users"


def test_explain_not_found(mock_client, runner):
    mock_client.dbm.search_events.return_value = []

    result = invoke(runner, mock_client, ["explain", "sig-missing"])

    assert result.exit_code == 3
    assert "No explain plans found for sig-missing" in result.output


def test_explain_forbidden_explains_key_requirement(mock_client, runner):
    mock_client.dbm.search_events.side_effect = ForbiddenException(status=403, reason="Forbidden")
    mock_client.dbm.app_url = "https://app.datadoghq.com"

    result = invoke(runner, mock_client, ["explain", "sig-a"])

    assert result.exit_code == 2
    assert "unscoped application key" in result.output
