"""Tests for `apm spans search` and `apm trace`.

These use real datadog_api_client models instead of Mocks so that field names
(e.g. duration living under `custom.duration`) match what the API returns.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from datadog_api_client.v2.model.span import Span
from datadog_api_client.v2.model.spans_attributes import SpansAttributes
from datadog_api_client.v2.model.spans_list_response import SpansListResponse
from datadog_api_client.v2.model.spans_list_response_metadata import SpansListResponseMetadata
from datadog_api_client.v2.model.spans_response_metadata_page import SpansResponseMetadataPage

BASE = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)


def make_span(
    span_id,
    parent_id="0",
    trace_id="trace-1",
    service="web",
    resource="GET /",
    operation="rack.request",
    start_offset_ms=0,
    duration_ms=100,
    custom_extra=None,
):
    start = BASE + timedelta(milliseconds=start_offset_ms)
    custom = {"duration": duration_ms * 1_000_000}
    if custom_extra:
        custom.update(custom_extra)
    attrs = SpansAttributes(
        span_id=span_id,
        parent_id=parent_id,
        trace_id=trace_id,
        service=service,
        resource_name=resource,
        start_timestamp=start,
        end_timestamp=start + timedelta(milliseconds=duration_ms),
        custom=custom,
        tags=["env:prod"],
        operation_name=operation,
    )
    return Span(id=span_id, type="spans", attributes=attrs)


def make_response(spans, next_cursor=None):
    if next_cursor:
        meta = SpansListResponseMetadata(page=SpansResponseMetadataPage(after=next_cursor))
        return SpansListResponse(data=spans, meta=meta)
    return SpansListResponse(data=spans)


def invoke(runner, mock_client, args):
    from ddogctl.commands.apm import apm

    with patch("ddogctl.commands.apm.get_datadog_client", return_value=mock_client):
        return runner.invoke(apm, args)


# --- apm spans search -------------------------------------------------------


def test_spans_search_passes_query_verbatim(mock_client, runner):
    """Query is not forced to a service; it goes to the API as typed."""
    mock_client.spans.list_spans_get.return_value = make_response([make_span("1")])

    result = invoke(runner, mock_client, ["spans", "search", "@job.name:SyncJob", "--limit", "10"])

    assert result.exit_code == 0, result.output
    kwargs = mock_client.spans.list_spans_get.call_args.kwargs
    assert kwargs["filter_query"] == "@job.name:SyncJob"
    assert kwargs["page_limit"] == 10
    assert str(kwargs["sort"]) == "-timestamp"


def test_spans_search_json_includes_full_span(mock_client, runner):
    """JSON output keeps parent_id, custom attributes, tags and a real duration."""
    span = make_span(
        "1",
        parent_id="42",
        duration_ms=250,
        custom_extra={"messaging": {"destination": "critical"}},
    )
    mock_client.spans.list_spans_get.return_value = make_response([span])

    result = invoke(runner, mock_client, ["spans", "search", "*", "--format", "json"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert len(data) == 1
    out = data[0]
    assert out["span_id"] == "1"
    assert out["parent_id"] == "42"
    assert out["operation_name"] == "rack.request"
    assert out["duration_ms"] == 250.0
    assert out["custom"]["messaging"]["destination"] == "critical"
    assert out["tags"] == ["env:prod"]
    assert out["start_timestamp"] == BASE.isoformat()


def test_spans_search_table_shows_duration(mock_client, runner):
    mock_client.spans.list_spans_get.return_value = make_response(
        [make_span("1", resource="SELECT users", duration_ms=1234.5)]
    )

    result = invoke(runner, mock_client, ["spans", "search", "service:db"])

    assert result.exit_code == 0, result.output
    assert "SELECT users" in result.output
    assert "1234.50" in result.output
    assert "Total spans: 1" in result.output


def test_spans_search_field_columns(mock_client, runner):
    """--field adds columns from custom attributes (@path) or top-level attributes."""
    spans = [
        make_span("1", resource="SyncJob", custom_extra={"messaging": {"destination": "critical"}}),
        make_span("2", resource="MailJob", custom_extra={"messaging": {"destination": "mailers"}}),
        make_span("3", resource="OtherJob"),
    ]
    mock_client.spans.list_spans_get.return_value = make_response(spans)

    result = invoke(
        runner,
        mock_client,
        ["spans", "search", "*", "--field", "@messaging.destination", "--field", "trace_id"],
    )

    assert result.exit_code == 0, result.output
    assert "critical" in result.output
    assert "mailers" in result.output
    assert "trace-1" in result.output


def test_spans_search_field_in_json(mock_client, runner):
    """--field values are added under `fields` in JSON output."""
    span = make_span("1", custom_extra={"messaging": {"destination": "critical"}})
    mock_client.spans.list_spans_get.return_value = make_response([span])

    result = invoke(
        runner,
        mock_client,
        ["spans", "search", "*", "--field", "@messaging.destination", "--format", "json"],
    )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data[0]["fields"] == {"@messaging.destination": "critical"}


def test_spans_search_paginates_until_limit(mock_client, runner):
    mock_client.spans.list_spans_get.side_effect = [
        make_response([make_span("1"), make_span("2")], next_cursor="c1"),
        make_response([make_span("3"), make_span("4")], next_cursor="c2"),
    ]

    result = invoke(
        runner, mock_client, ["spans", "search", "*", "--limit", "3", "--format", "json"]
    )

    assert result.exit_code == 0, result.output
    assert [s["span_id"] for s in json.loads(result.output)] == ["1", "2", "3"]
    calls = mock_client.spans.list_spans_get.call_args_list
    assert len(calls) == 2
    assert "page_cursor" not in calls[0].kwargs
    assert calls[1].kwargs["page_cursor"] == "c1"
    assert calls[1].kwargs["page_limit"] == 1


def test_spans_search_stops_without_cursor(mock_client, runner):
    mock_client.spans.list_spans_get.return_value = make_response([make_span("1")])

    result = invoke(runner, mock_client, ["spans", "search", "*", "--limit", "500"])

    assert result.exit_code == 0, result.output
    assert mock_client.spans.list_spans_get.call_count == 1


def test_spans_search_page_size_capped_at_api_max(mock_client, runner):
    mock_client.spans.list_spans_get.return_value = make_response([make_span("1")])

    invoke(runner, mock_client, ["spans", "search", "*", "--limit", "5000"])

    assert mock_client.spans.list_spans_get.call_args.kwargs["page_limit"] == 1000


def test_spans_search_sort_ascending(mock_client, runner):
    mock_client.spans.list_spans_get.return_value = make_response([])

    result = invoke(runner, mock_client, ["spans", "search", "*", "--sort", "timestamp"])

    assert result.exit_code == 0, result.output
    assert str(mock_client.spans.list_spans_get.call_args.kwargs["sort"]) == "timestamp"


def test_spans_search_empty(mock_client, runner):
    mock_client.spans.list_spans_get.return_value = make_response([])

    result = invoke(runner, mock_client, ["spans", "search", "service:nothing"])

    assert result.exit_code == 0, result.output
    assert "No spans found" in result.output


def test_spans_search_duration_falls_back_to_timestamps(mock_client, runner):
    """Without custom.duration, duration comes from end - start."""
    attrs = SpansAttributes(
        span_id="1",
        trace_id="t",
        service="web",
        resource_name="r",
        start_timestamp=BASE,
        end_timestamp=BASE + timedelta(milliseconds=75),
    )
    mock_client.spans.list_spans_get.return_value = make_response([Span(id="1", attributes=attrs)])

    result = invoke(runner, mock_client, ["spans", "search", "*", "--format", "json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)[0]["duration_ms"] == 75.0


# --- apm trace --------------------------------------------------------------


def trace_spans():
    """A partially indexed trace: the top span's parent was not indexed."""
    return [
        make_span("10", parent_id="999", service="api", resource="POST /graphql", duration_ms=400),
        make_span(
            "11",
            parent_id="10",
            service="api",
            resource="resolver",
            start_offset_ms=5,
            duration_ms=300,
        ),
        make_span(
            "12",
            parent_id="11",
            service="mysql",
            resource="SELECT * FROM orders",
            operation="mysql2.query",
            start_offset_ms=10,
            duration_ms=250,
        ),
    ]


def test_trace_queries_by_trace_id(mock_client, runner):
    mock_client.spans.list_spans_get.return_value = make_response(trace_spans())

    result = invoke(runner, mock_client, ["trace", "abc123"])

    assert result.exit_code == 0, result.output
    kwargs = mock_client.spans.list_spans_get.call_args.kwargs
    assert kwargs["filter_query"] == "trace_id:abc123"
    assert str(kwargs["sort"]) == "timestamp"


def test_trace_json_identifies_root(mock_client, runner):
    mock_client.spans.list_spans_get.return_value = make_response(trace_spans())

    result = invoke(runner, mock_client, ["trace", "trace-1", "--format", "json"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["trace_id"] == "trace-1"
    assert data["span_count"] == 3
    assert data["root_span_ids"] == ["10"]
    assert data["duration_ms"] == 400.0
    by_id = {s["span_id"]: s for s in data["spans"]}
    assert by_id["10"]["depth"] == 0
    assert by_id["10"]["parent_indexed"] is False
    assert by_id["12"]["depth"] == 2
    assert by_id["12"]["parent_indexed"] is True


def test_trace_true_root_parent_zero(mock_client, runner):
    spans = [make_span("1", parent_id="0"), make_span("2", parent_id="1", start_offset_ms=1)]
    mock_client.spans.list_spans_get.return_value = make_response(spans)

    result = invoke(runner, mock_client, ["trace", "trace-1", "--format", "json"])

    data = json.loads(result.output)
    assert data["root_span_ids"] == ["1"]
    assert data["spans"][0]["parent_indexed"] is None


def test_trace_table_renders_tree(mock_client, runner):
    mock_client.spans.list_spans_get.return_value = make_response(trace_spans())

    result = invoke(runner, mock_client, ["trace", "trace-1"])

    assert result.exit_code == 0, result.output
    out = result.output
    assert "POST /graphql" in out
    assert "SELECT * FROM orders" in out
    assert "250.00 ms" in out
    assert "parent 999 not indexed" in out
    assert "3 spans" in out
    # Child appears after its parent in the tree
    assert out.index("POST /graphql") < out.index("resolver") < out.index("SELECT * FROM orders")


def test_trace_fetches_all_pages(mock_client, runner):
    spans = trace_spans()
    mock_client.spans.list_spans_get.side_effect = [
        make_response(spans[:2], next_cursor="c1"),
        make_response(spans[2:]),
    ]

    result = invoke(runner, mock_client, ["trace", "trace-1", "--format", "json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["span_count"] == 3
    assert mock_client.spans.list_spans_get.call_count == 2


def test_trace_warns_when_truncated(mock_client, runner):
    mock_client.spans.list_spans_get.return_value = make_response(trace_spans(), next_cursor="c1")

    result = invoke(runner, mock_client, ["trace", "trace-1", "--limit", "3"])

    assert result.exit_code == 0, result.output
    assert "--limit" in result.output


def test_trace_not_found(mock_client, runner):
    mock_client.spans.list_spans_get.return_value = make_response([])

    result = invoke(runner, mock_client, ["trace", "missing"])

    assert result.exit_code == 3
    assert "No spans found for trace missing" in result.output


# --- apm traces regression --------------------------------------------------


def test_traces_reads_duration_from_custom(mock_client, runner):
    """Real SDK spans have no `duration` attribute; it lives in custom.duration."""
    mock_client.spans.list_spans_get.return_value = make_response([make_span("1", duration_ms=321)])

    result = invoke(runner, mock_client, ["traces", "web", "--format", "json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)[0]["duration_ms"] == 321.0
