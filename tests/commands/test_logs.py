"""Tests for Logs commands."""

import json
import os
import re
import time
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from tests.conftest import create_mock_log

# Search command tests


def test_logs_search_basic_query(mock_client, runner):
    """Test basic log search returns correct count."""
    from ddogctl.commands.logs import logs

    now = datetime.now()
    mock_logs = [
        create_mock_log("Request received", "web-api", "info", now),
        create_mock_log("Request completed", "web-api", "info", now),
    ]
    mock_response = Mock(data=mock_logs, meta=Mock(page=Mock(after=None)))
    mock_client.logs.list_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["search", "*", "--format", "json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert len(output) == 2


def test_logs_search_table_format(mock_client, runner):
    """Test search displays table with correct headers and content."""
    from ddogctl.commands.logs import logs

    now = datetime.now()
    mock_logs = [
        create_mock_log("Connection error", "web-api", "error", now),
    ]
    mock_response = Mock(data=mock_logs, meta=Mock(page=Mock(after=None)))
    mock_client.logs.list_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["search", "*"])

        assert result.exit_code == 0
        assert "Time" in result.output
        assert "Status" in result.output
        assert "Service" in result.output
        assert "Message" in result.output
        assert "Connection error" in result.output
        assert "web-api" in result.output


def test_logs_search_json_format(mock_client, runner):
    """Test search JSON output has expected fields."""
    from ddogctl.commands.logs import logs

    now = datetime.now()
    mock_logs = [
        create_mock_log("Test message", "my-service", "info", now),
    ]
    mock_response = Mock(data=mock_logs, meta=Mock(page=Mock(after=None)))
    mock_client.logs.list_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["search", "*", "--format", "json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert len(output) == 1
        assert output[0]["message"] == "Test message"
        assert output[0]["service"] == "my-service"
        assert output[0]["status"] == "info"
        assert "timestamp" in output[0]


def test_logs_search_json_includes_nested_attributes(mock_client, runner):
    """Test search JSON output includes nested attributes from log payload."""
    from ddogctl.commands.logs import logs

    now = datetime.now()
    nested_attrs = {
        "jobName": "data-sync",
        "queueName": "EVENTS_PROCESS_BATCH",
        "event": "failed",
        "failedReason": "Connection timeout",
        "stacktrace": ["Error: Connection timeout", "  at Worker.process"],
        "attemptsMade": 3,
        "userId": "usr-123",
    }
    mock_logs = [
        create_mock_log(
            "Background job event", "task-worker", "error", now, attributes=nested_attrs
        ),
    ]
    mock_response = Mock(data=mock_logs, meta=Mock(page=Mock(after=None)))
    mock_client.logs.list_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["search", "*", "--format", "json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert len(output) == 1
        log_entry = output[0]
        assert log_entry["message"] == "Background job event"
        assert log_entry["attributes"]["jobName"] == "data-sync"
        assert log_entry["attributes"]["queueName"] == "EVENTS_PROCESS_BATCH"
        assert log_entry["attributes"]["event"] == "failed"
        assert log_entry["attributes"]["failedReason"] == "Connection timeout"
        assert log_entry["attributes"]["attemptsMade"] == 3


def test_logs_search_json_empty_attributes(mock_client, runner):
    """Test search JSON output handles logs with no nested attributes."""
    from ddogctl.commands.logs import logs

    now = datetime.now()
    mock_logs = [
        create_mock_log("Simple log", "web-api", "info", now),
    ]
    mock_response = Mock(data=mock_logs, meta=Mock(page=Mock(after=None)))
    mock_client.logs.list_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["search", "*", "--format", "json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output[0]["attributes"] == {}


def test_logs_trace_json_includes_nested_attributes(mock_client, runner):
    """Test trace JSON output includes nested attributes."""
    from ddogctl.commands.logs import logs

    now = datetime.now()
    nested_attrs = {"http.method": "GET", "http.status_code": 500, "trace_id": "abc123"}
    mock_logs = [
        create_mock_log(
            "Request failed", "web-api", "error", now, attributes=nested_attrs, trace_id="abc123"
        ),
    ]
    mock_response = Mock(data=mock_logs, meta=Mock(page=Mock(after=None)))
    mock_client.logs.list_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["trace", "abc123", "--format", "json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output[0]["attributes"]["http.method"] == "GET"
        assert output[0]["attributes"]["http.status_code"] == 500


def test_logs_search_with_time_range(mock_client, runner):
    """Test search with --from 24h is accepted."""
    from ddogctl.commands.logs import logs

    mock_response = Mock(data=[], meta=Mock(page=Mock(after=None)))
    mock_client.logs.list_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["search", "*", "--from", "24h"])

        assert result.exit_code == 0
        mock_client.logs.list_logs.assert_called_once()


def test_logs_search_with_service_filter(mock_client, runner):
    """Test search with --service adds service to query."""
    from ddogctl.commands.logs import logs

    mock_response = Mock(data=[], meta=Mock(page=Mock(after=None)))
    mock_client.logs.list_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["search", "*", "--service", "web-api"])

        assert result.exit_code == 0
        call_kwargs = mock_client.logs.list_logs.call_args.kwargs
        body = call_kwargs["body"]
        assert "service:web-api" in body["filter"]["query"]


def test_logs_search_with_status_filter(mock_client, runner):
    """Test search with --status adds status to query."""
    from ddogctl.commands.logs import logs

    mock_response = Mock(data=[], meta=Mock(page=Mock(after=None)))
    mock_client.logs.list_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["search", "*", "--status", "error"])

        assert result.exit_code == 0
        call_kwargs = mock_client.logs.list_logs.call_args.kwargs
        body = call_kwargs["body"]
        assert "status:error" in body["filter"]["query"]


def test_logs_search_empty_results(mock_client, runner):
    """Test search with no results shows total 0."""
    from ddogctl.commands.logs import logs

    mock_response = Mock(data=[], meta=Mock(page=Mock(after=None)))
    mock_client.logs.list_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["search", "nonexistent"])

        assert result.exit_code == 0
        assert "Total logs: 0" in result.output


def test_logs_search_with_limit(mock_client, runner):
    """Test search respects --limit parameter."""
    from ddogctl.commands.logs import logs

    mock_response = Mock(data=[], meta=Mock(page=Mock(after=None)))
    mock_client.logs.list_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["search", "*", "--limit", "10"])

        assert result.exit_code == 0
        call_kwargs = mock_client.logs.list_logs.call_args.kwargs
        body = call_kwargs["body"]
        assert body["page"]["limit"] == 10


# Tail command tests


def test_logs_tail_basic(mock_client, runner):
    """Test tail returns recent logs."""
    from ddogctl.commands.logs import logs

    now = datetime.now()
    mock_logs = [
        create_mock_log("Recent log entry", "web-api", "info", now),
    ]
    mock_response = Mock(data=mock_logs, meta=Mock(page=Mock(after=None)))
    mock_client.logs.list_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["tail", "*", "--format", "json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert len(output) == 1
        assert output[0]["message"] == "Recent log entry"


def test_logs_tail_with_lines(mock_client, runner):
    """Test tail respects --lines parameter."""
    from ddogctl.commands.logs import logs

    mock_response = Mock(data=[], meta=Mock(page=Mock(after=None)))
    mock_client.logs.list_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["tail", "*", "--lines", "25"])

        assert result.exit_code == 0
        call_kwargs = mock_client.logs.list_logs.call_args.kwargs
        body = call_kwargs["body"]
        assert body["page"]["limit"] == 25


def test_logs_tail_with_service_filter(mock_client, runner):
    """Test tail with --service filter works."""
    from ddogctl.commands.logs import logs

    mock_response = Mock(data=[], meta=Mock(page=Mock(after=None)))
    mock_client.logs.list_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["tail", "*", "--service", "web-api"])

        assert result.exit_code == 0
        call_kwargs = mock_client.logs.list_logs.call_args.kwargs
        body = call_kwargs["body"]
        assert "service:web-api" in body["filter"]["query"]


def test_logs_tail_color_coded(mock_client, runner):
    """Test tail output contains log messages."""
    from ddogctl.commands.logs import logs

    now = datetime.now()
    mock_logs = [
        create_mock_log("Error occurred", "web-api", "error", now),
        create_mock_log("Warning issued", "web-api", "warn", now),
        create_mock_log("Info message", "web-api", "info", now),
    ]
    mock_response = Mock(data=mock_logs, meta=Mock(page=Mock(after=None)))
    mock_client.logs.list_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["tail", "*"])

        assert result.exit_code == 0
        assert "Error occurred" in result.output
        assert "Warning issued" in result.output
        assert "Info message" in result.output


def test_logs_tail_empty(mock_client, runner):
    """Test tail shows 'No logs found' when empty."""
    from ddogctl.commands.logs import logs

    mock_response = Mock(data=[], meta=Mock(page=Mock(after=None)))
    mock_client.logs.list_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["tail", "*"])

        assert result.exit_code == 0
        assert "No logs found" in result.output


# Query command tests


def test_logs_query_count_by_service(mock_client, runner):
    """Test log query with count aggregation grouped by service."""
    from ddogctl.commands.logs import logs

    class MockBucket:
        def __init__(self, service, count):
            self.by = {"service": service}
            self.computes = {"c0": count}

    mock_buckets = [
        MockBucket("web-api", 1500),
        MockBucket("worker", 800),
    ]
    mock_response = Mock(data=Mock(buckets=mock_buckets))
    mock_client.logs.aggregate_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(
            logs,
            [
                "query",
                "--query",
                "*",
                "--metric",
                "count",
                "--group-by",
                "service",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert len(output) == 2
        assert output[0]["service"] == "web-api"
        assert output[0]["count"] == 1500
        assert output[1]["service"] == "worker"
        assert output[1]["count"] == 800


def test_logs_query_count_by_status(mock_client, runner):
    """Test log query grouped by status."""
    from ddogctl.commands.logs import logs

    class MockBucket:
        def __init__(self, status, count):
            self.by = {"status": status}
            self.computes = {"c0": count}

    mock_buckets = [
        MockBucket("error", 250),
        MockBucket("info", 5000),
    ]
    mock_response = Mock(data=Mock(buckets=mock_buckets))
    mock_client.logs.aggregate_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(
            logs,
            [
                "query",
                "--query",
                "*",
                "--metric",
                "count",
                "--group-by",
                "status",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert len(output) == 2
        assert output[0]["status"] == "error"
        assert output[0]["count"] == 250


def test_logs_query_json_format(mock_client, runner):
    """Test log query JSON output is valid."""
    from ddogctl.commands.logs import logs

    class MockBucket:
        def __init__(self, service, count):
            self.by = {"service": service}
            self.computes = {"c0": count}

    mock_buckets = [MockBucket("web-api", 100)]
    mock_response = Mock(data=Mock(buckets=mock_buckets))
    mock_client.logs.aggregate_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(
            logs, ["query", "--metric", "count", "--group-by", "service", "--format", "json"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert isinstance(output, list)
        assert len(output) == 1


def test_logs_query_table_format(mock_client, runner):
    """Test log query table has correct columns."""
    from ddogctl.commands.logs import logs

    class MockBucket:
        def __init__(self, service, count):
            self.by = {"service": service}
            self.computes = {"c0": count}

    mock_buckets = [
        MockBucket("web-api", 1000),
        MockBucket("worker", 500),
    ]
    mock_response = Mock(data=Mock(buckets=mock_buckets))
    mock_client.logs.aggregate_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["query", "--metric", "count", "--group-by", "service"])

        assert result.exit_code == 0
        assert "Log Analytics" in result.output
        assert "service" in result.output
        assert "COUNT" in result.output
        assert "web-api" in result.output
        assert "1000" in result.output
        assert "Total groups: 2" in result.output


def test_logs_query_without_groupby(mock_client, runner):
    """Test log query without group-by returns single aggregate."""
    from ddogctl.commands.logs import logs

    class MockBucket:
        def __init__(self, count):
            self.by = {}
            self.computes = {"c0": count}

    mock_buckets = [MockBucket(9876)]
    mock_response = Mock(data=Mock(buckets=mock_buckets))
    mock_client.logs.aggregate_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["query", "--metric", "count", "--format", "json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert len(output) == 1
        assert output[0]["count"] == 9876


def test_logs_query_empty_results(mock_client, runner):
    """Test log query with no results shows total 0."""
    from ddogctl.commands.logs import logs

    mock_response = Mock(data=Mock(buckets=[]))
    mock_client.logs.aggregate_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["query", "--metric", "count"])

        assert result.exit_code == 0
        assert "Total groups: 0" in result.output


# Trace command tests


def test_logs_trace_basic(mock_client, runner):
    """Test finding logs for a trace ID."""
    from ddogctl.commands.logs import logs

    now = datetime.now()
    mock_logs = [
        create_mock_log("Request started", "web-api", "info", now, trace_id="abc123"),
        create_mock_log("Request finished", "web-api", "info", now, trace_id="abc123"),
    ]
    mock_response = Mock(data=mock_logs, meta=Mock(page=Mock(after=None)))
    mock_client.logs.list_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["trace", "abc123", "--format", "json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert len(output) == 2


def test_logs_trace_json_format(mock_client, runner):
    """Test trace logs JSON output."""
    from ddogctl.commands.logs import logs

    now = datetime.now()
    mock_logs = [
        create_mock_log("Trace log", "web-api", "info", now, trace_id="trace-xyz"),
    ]
    mock_response = Mock(data=mock_logs, meta=Mock(page=Mock(after=None)))
    mock_client.logs.list_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["trace", "trace-xyz", "--format", "json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert len(output) == 1
        assert output[0]["message"] == "Trace log"
        assert output[0]["service"] == "web-api"


def test_logs_trace_table_format(mock_client, runner):
    """Test trace logs table output includes trace ID in title."""
    from ddogctl.commands.logs import logs

    now = datetime.now()
    mock_logs = [
        create_mock_log("Trace entry", "web-api", "info", now, trace_id="trace-456"),
    ]
    mock_response = Mock(data=mock_logs, meta=Mock(page=Mock(after=None)))
    mock_client.logs.list_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["trace", "trace-456"])

        assert result.exit_code == 0
        assert "trace-456" in result.output
        assert "Trace entry" in result.output


def test_logs_trace_not_found(mock_client, runner):
    """Test trace with no matching logs shows 'No logs found'."""
    from ddogctl.commands.logs import logs

    mock_response = Mock(data=[], meta=Mock(page=Mock(after=None)))
    mock_client.logs.list_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["trace", "nonexistent-trace"])

        assert result.exit_code == 0
        assert "No logs found" in result.output


# ============================================================================
# Tail --follow Tests
# ============================================================================


def test_logs_tail_follow_flag_accepted(mock_client, runner):
    """Test that --follow flag is accepted by the tail command."""
    from ddogctl.commands.logs import logs

    now = datetime.now()
    mock_logs = [
        create_mock_log("Log entry", "web-api", "info", now),
    ]
    mock_response = Mock(data=mock_logs, meta=Mock(page=Mock(after=None)))
    mock_client.logs.list_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        with patch("ddogctl.commands.logs.time.sleep", side_effect=KeyboardInterrupt):
            result = runner.invoke(logs, ["tail", "*", "--follow"])

            # Should not fail with unrecognized option
            assert result.exit_code == 0


def test_logs_tail_follow_polls_repeatedly(mock_client, runner):
    """Test that --follow polls the API in a loop."""
    from ddogctl.commands.logs import logs

    now = datetime.now()
    mock_logs = [
        create_mock_log("Log entry 1", "web-api", "info", now),
    ]

    call_count = 0

    def sleep_side_effect(interval):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise KeyboardInterrupt

    mock_response = Mock(data=mock_logs, meta=Mock(page=Mock(after=None)))
    mock_client.logs.list_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        with patch("ddogctl.commands.logs.time.sleep", side_effect=sleep_side_effect):
            result = runner.invoke(logs, ["tail", "*", "--follow"])

            assert result.exit_code == 0
            # Should have called list_logs multiple times (initial + follow polls)
            assert mock_client.logs.list_logs.call_count >= 2


def test_logs_tail_follow_shows_new_logs(mock_client, runner):
    """Test that --follow displays new log entries as they arrive."""
    from ddogctl.commands.logs import logs

    now = datetime.now()
    first_logs = [
        create_mock_log("First log", "web-api", "info", now),
    ]
    second_logs = [
        create_mock_log("Second log", "web-api", "error", now),
    ]

    responses = iter(
        [
            Mock(data=first_logs, meta=Mock(page=Mock(after="cursor1"))),
            Mock(data=second_logs, meta=Mock(page=Mock(after=None))),
        ]
    )
    mock_client.logs.list_logs.side_effect = lambda **kwargs: next(responses)

    call_count = 0

    def sleep_side_effect(interval):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise KeyboardInterrupt

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        with patch("ddogctl.commands.logs.time.sleep", side_effect=sleep_side_effect):
            result = runner.invoke(logs, ["tail", "*", "--follow"])

            assert result.exit_code == 0
            assert "First log" in result.output
            assert "Second log" in result.output


def test_logs_tail_follow_handles_empty_polls(mock_client, runner):
    """Test that --follow handles polls that return no new logs."""
    from ddogctl.commands.logs import logs

    now = datetime.now()
    initial_logs = [
        create_mock_log("Initial log", "web-api", "info", now),
    ]

    responses = iter(
        [
            Mock(data=initial_logs, meta=Mock(page=Mock(after=None))),
            Mock(data=[], meta=Mock(page=Mock(after=None))),
        ]
    )
    mock_client.logs.list_logs.side_effect = lambda **kwargs: next(responses)

    call_count = 0

    def sleep_side_effect(interval):
        nonlocal call_count
        call_count += 1
        if call_count >= 1:
            raise KeyboardInterrupt

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        with patch("ddogctl.commands.logs.time.sleep", side_effect=sleep_side_effect):
            result = runner.invoke(logs, ["tail", "*", "--follow"])

            assert result.exit_code == 0
            assert "Initial log" in result.output


def test_logs_tail_without_follow_runs_normally(mock_client, runner):
    """Test that without --follow, tail command runs once and exits."""
    from ddogctl.commands.logs import logs

    now = datetime.now()
    mock_logs = [
        create_mock_log("Normal tail log", "web-api", "info", now),
    ]
    mock_response = Mock(data=mock_logs, meta=Mock(page=Mock(after=None)))
    mock_client.logs.list_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["tail", "*", "--format", "json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert len(output) == 1
        assert output[0]["message"] == "Normal tail log"
        # list_logs should be called exactly once
        mock_client.logs.list_logs.assert_called_once()


def test_logs_tail_follow_clean_exit(mock_client, runner):
    """Test that --follow exits cleanly on Ctrl+C."""
    from ddogctl.commands.logs import logs

    now = datetime.now()
    mock_logs = [
        create_mock_log("Log entry", "web-api", "info", now),
    ]
    mock_response = Mock(data=mock_logs, meta=Mock(page=Mock(after=None)))
    mock_client.logs.list_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        with patch("ddogctl.commands.logs.time.sleep", side_effect=KeyboardInterrupt):
            result = runner.invoke(logs, ["tail", "*", "--follow"])

            assert result.exit_code == 0
            # Should show a clean exit message
            assert "Follow stopped" in result.output


# Tests for logs with missing attributes (AWS Firelens, etc.)


def test_logs_search_missing_message_attribute(mock_client, runner):
    """Test search handles logs without standard message attribute gracefully."""
    from ddogctl.commands.logs import logs

    now = datetime.now()

    # Create a mock log without message, service, or status attributes
    # (simulates AWS Firelens or other log sources with different structures)
    class MockFirelensLog:
        def __init__(self):
            self.id = "log-firelens-123"
            self.type = "log"
            # Firelens logs might have different attribute names
            # Use spec_set to prevent Mock from creating missing attributes
            self.attributes = Mock(
                spec_set=["log", "timestamp", "tags", "attributes"],
                log="Firelens log content",  # 'log' instead of 'message'
                timestamp=now,
                tags=["source:firelens"],
                attributes={"container_name": "httpd"},
            )

    mock_logs = [MockFirelensLog()]
    mock_response = Mock(data=mock_logs, meta=Mock(page=Mock(after=None)))
    mock_client.logs.list_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["search", "*", "--format", "json"])

        # Should not crash, should handle missing attributes gracefully
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert len(output) == 1
        # Should have fallback values for missing attributes
        assert "message" in output[0]
        assert "service" in output[0]
        assert "status" in output[0]


def test_logs_search_partial_attributes(mock_client, runner):
    """Test search handles logs with only some standard attributes."""
    from ddogctl.commands.logs import logs

    now = datetime.now()

    # Create a log with only message and timestamp
    class MockPartialLog:
        def __init__(self):
            self.id = "log-partial-456"
            self.type = "log"
            self.attributes = Mock(
                spec_set=["message", "timestamp", "tags"],
                message="Partial log entry",
                timestamp=now,
                tags=[],
            )

    mock_logs = [MockPartialLog()]
    mock_response = Mock(data=mock_logs, meta=Mock(page=Mock(after=None)))
    mock_client.logs.list_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["search", "*", "--format", "table"])

        # Should not crash
        assert result.exit_code == 0
        assert "Partial log entry" in result.output


def test_logs_tail_missing_attributes(mock_client, runner):
    """Test tail handles logs with missing attributes."""
    from ddogctl.commands.logs import logs

    now = datetime.now()

    class MockMinimalLog:
        def __init__(self):
            self.id = "log-minimal-789"
            self.type = "log"
            self.attributes = Mock(
                spec_set=["timestamp", "tags", "attributes"],
                timestamp=now,
                tags=[],
                attributes={},  # Empty attributes dict
            )

    mock_logs = [MockMinimalLog()]
    mock_response = Mock(data=mock_logs, meta=Mock(page=Mock(after=None)))
    mock_client.logs.list_logs.return_value = mock_response

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["tail", "*", "--format", "json"])

        # Should not crash
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert len(output) == 1


# Regression tests for issue #52: timestamps must be serialized as UTC ISO
# strings regardless of the host TZ. Previously the code labeled local time
# with a "Z" suffix, silently shifting every query by the local UTC offset.


ISO_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


@pytest.fixture
def _non_utc_tz():
    """Run the test as if the process TZ were America/Sao_Paulo (UTC-3)."""
    original = os.environ.get("TZ")
    os.environ["TZ"] = "America/Sao_Paulo"
    time.tzset()
    try:
        yield
    finally:
        if original is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original
        time.tzset()


def _assert_window_is_utc_now(body, expected_window_seconds, tolerance_seconds=5):
    """Assert filter.from/to are UTC ISO strings spanning the expected window."""
    from_str = body["filter"]["from"]
    to_str = body["filter"]["to"]

    assert ISO_UTC_RE.match(from_str), f"from is not a UTC ISO string: {from_str!r}"
    assert ISO_UTC_RE.match(to_str), f"to is not a UTC ISO string: {to_str!r}"

    from_dt = datetime.strptime(from_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    to_dt = datetime.strptime(to_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)

    # ``to`` is "now" — within a few seconds of UTC wall clock.
    assert (
        abs((now - to_dt).total_seconds()) <= tolerance_seconds
    ), f"'to' {to_dt} is not close to UTC now {now}"

    # Window length is the expected number of seconds.
    window = (to_dt - from_dt).total_seconds()
    assert (
        abs(window - expected_window_seconds) <= tolerance_seconds
    ), f"window {window}s != expected {expected_window_seconds}s"


def test_logs_search_uses_utc_iso_under_non_utc_tz(mock_client, runner, _non_utc_tz):
    """Regression for #52: --from 5m must produce a UTC window, not local-time-as-Z."""
    from ddogctl.commands.logs import logs

    mock_client.logs.list_logs.return_value = Mock(data=[], meta=Mock(page=Mock(after=None)))

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["search", "*", "--from", "5m"])

    assert result.exit_code == 0
    body = mock_client.logs.list_logs.call_args.kwargs["body"]
    _assert_window_is_utc_now(body, expected_window_seconds=5 * 60)


def test_logs_tail_uses_utc_iso_under_non_utc_tz(mock_client, runner, _non_utc_tz):
    """Regression for #52: tail's 15m window must be in UTC."""
    from ddogctl.commands.logs import logs

    mock_client.logs.list_logs.return_value = Mock(data=[], meta=Mock(page=Mock(after=None)))

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["tail", "*"])

    assert result.exit_code == 0
    body = mock_client.logs.list_logs.call_args.kwargs["body"]
    _assert_window_is_utc_now(body, expected_window_seconds=15 * 60)


def test_logs_query_uses_utc_iso_under_non_utc_tz(mock_client, runner, _non_utc_tz):
    """Regression for #52: log analytics path must also serialize UTC."""
    from ddogctl.commands.logs import logs

    mock_client.logs.aggregate_logs.return_value = Mock(data=Mock(buckets=[]))

    with patch("ddogctl.commands.logs.get_datadog_client", return_value=mock_client):
        result = runner.invoke(logs, ["query", "--query", "*", "--from", "1h"])

    assert result.exit_code == 0
    body = mock_client.logs.aggregate_logs.call_args.kwargs["body"]
    _assert_window_is_utc_now(body, expected_window_seconds=60 * 60)
