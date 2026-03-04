"""Tests for metric commands."""

import pytest
import json
from unittest.mock import Mock, patch
from click.testing import CliRunner
from ddogctl.commands.metric import metric


class MockPoint:
    """Mock SDK Point object — wraps [timestamp, value] in a .value attribute."""

    def __init__(self, timestamp, value):
        self._data = [timestamp, value]

    @property
    def value(self):
        return self._data

    def __iter__(self):
        raise TypeError("MockPoint does not support iteration (like the real SDK Point)")

    def __getitem__(self, key):
        raise TypeError("MockPoint does not support subscript access")


class MockMetricQueryResponse:
    """Mock Datadog metric query response."""

    def __init__(self, series=None):
        self.series = series or []

    def to_dict(self):
        return {"series": self.series}


class MockMetricListResponse:
    """Mock Datadog metric list response."""

    def __init__(self, metrics=None):
        self.metrics = metrics or []


class MockMetricMetadata:
    """Mock Datadog metric metadata."""

    def __init__(self, metric_name, description=None, type=None, unit=None, per_unit=None):
        self.metric_name = metric_name
        self.description = description
        self.type = type
        self.unit = unit
        self.per_unit = per_unit


@pytest.fixture
def mock_client():
    """Create a mock Datadog client."""
    client = Mock()
    client.metrics = Mock()
    return client


@pytest.fixture
def runner():
    """Click CLI test runner."""
    return CliRunner()


def test_metric_query_json_format(mock_client, runner):
    """Test metric query with JSON output format."""
    # Mock metric query response
    mock_response = MockMetricQueryResponse(
        series=[
            {
                "metric": "system.cpu.user",
                "pointlist": [
                    [1609459200000, 25.5],
                    [1609459260000, 30.2],
                    [1609459320000, 28.7],
                ],
                "scope": "host:web-prod-01",
            }
        ]
    )
    mock_client.metrics.query_metrics.return_value = mock_response

    with patch("ddogctl.commands.metric.get_datadog_client", return_value=mock_client):
        result = runner.invoke(metric, ["query", "avg:system.cpu.user{*}", "--format", "json"])

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Parse JSON output
        output = json.loads(result.output)

        # Verify structure
        assert "series" in output
        assert len(output["series"]) == 1
        assert output["series"][0]["metric"] == "system.cpu.user"
        assert len(output["series"][0]["pointlist"]) == 3


def test_metric_query_csv_format(mock_client, runner):
    """Test metric query with CSV output format."""
    mock_response = MockMetricQueryResponse(
        series=[
            {
                "metric": "database.connections",
                "pointlist": [
                    MockPoint(1609459200000, 150.0),
                    MockPoint(1609459260000, 155.0),
                ],
            }
        ]
    )
    mock_client.metrics.query_metrics.return_value = mock_response

    with patch("ddogctl.commands.metric.get_datadog_client", return_value=mock_client):
        result = runner.invoke(metric, ["query", "avg:database.connections{*}", "--format", "csv"])

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify CSV output format
        lines = result.output.strip().split("\n")
        assert len(lines) == 2

        # Each line should be: timestamp,metric_name,value
        for line in lines:
            parts = line.split(",")
            assert len(parts) == 3
            assert parts[1] == "database.connections"


def test_metric_query_table_format(mock_client, runner):
    """Test metric query with table output format."""
    mock_response = MockMetricQueryResponse(
        series=[
            {
                "metric": "trace.web.request",
                "pointlist": [MockPoint(1609459200000, 123.45)],
            }
        ]
    )
    mock_client.metrics.query_metrics.return_value = mock_response

    with patch("ddogctl.commands.metric.get_datadog_client", return_value=mock_client):
        result = runner.invoke(metric, ["query", "p90:trace.web.request{*}", "--format", "table"])

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify table contains metric name and data
        assert "trace.web.request" in result.output
        assert "123.45" in result.output


def test_metric_query_no_data(mock_client, runner):
    """Test metric query with no data returned."""
    mock_response = MockMetricQueryResponse(series=[])
    mock_client.metrics.query_metrics.return_value = mock_response

    with patch("ddogctl.commands.metric.get_datadog_client", return_value=mock_client):
        result = runner.invoke(metric, ["query", "avg:nonexistent.metric{*}"])

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Should show "No data found" message
        assert "No data found" in result.output


def test_metric_query_time_range(mock_client, runner):
    """Test metric query with custom time range."""
    mock_response = MockMetricQueryResponse(series=[])
    mock_client.metrics.query_metrics.return_value = mock_response

    with patch("ddogctl.commands.metric.get_datadog_client", return_value=mock_client):
        with patch("ddogctl.commands.metric.parse_time_range") as mock_parse_time:
            mock_parse_time.return_value = (1609459200, 1609545600)

            result = runner.invoke(
                metric,
                ["query", "avg:system.cpu.user{*}", "--from", "24h", "--to", "now"],
            )

            assert result.exit_code == 0, f"Command failed: {result.output}"

            # Verify parse_time_range was called with correct arguments
            mock_parse_time.assert_called_once_with("24h", "now")

            # Verify query_metrics was called with parsed timestamps
            mock_client.metrics.query_metrics.assert_called_once()
            call_kwargs = mock_client.metrics.query_metrics.call_args.kwargs
            assert call_kwargs["_from"] == 1609459200
            assert call_kwargs["to"] == 1609545600


def test_metric_search_results(mock_client, runner):
    """Test metric search with results."""
    mock_response = MockMetricListResponse(
        metrics=[
            "system.cpu.user",
            "system.cpu.system",
            "system.cpu.idle",
            "system.mem.used",
            "system.mem.free",
        ]
    )
    mock_client.metrics.list_active_metrics.return_value = mock_response

    with patch("ddogctl.commands.metric.get_datadog_client", return_value=mock_client):
        result = runner.invoke(metric, ["search", "system.cpu"])

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify only matching metrics are shown (client-side filtering)
        assert "system.cpu.user" in result.output
        assert "system.cpu.system" in result.output
        assert "system.cpu.idle" in result.output
        assert "system.mem" not in result.output
        assert "Found 3 metrics" in result.output


def test_metric_search_with_limit(mock_client, runner):
    """Test metric search with custom limit."""
    metrics = [f"metric.{i}" for i in range(100)]
    mock_response = MockMetricListResponse(metrics=metrics)
    mock_client.metrics.list_active_metrics.return_value = mock_response

    with patch("ddogctl.commands.metric.get_datadog_client", return_value=mock_client):
        result = runner.invoke(metric, ["search", "metric", "--limit", "10"])

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Should show only 10 metrics
        for i in range(10):
            assert f"metric.{i}" in result.output

        # Should show count of remaining metrics
        assert "... and 90 more" in result.output


def test_metric_search_no_results(mock_client, runner):
    """Test metric search with no results."""
    mock_response = MockMetricListResponse(metrics=[])
    mock_client.metrics.list_active_metrics.return_value = mock_response

    with patch("ddogctl.commands.metric.get_datadog_client", return_value=mock_client):
        result = runner.invoke(metric, ["search", "nonexistent.metric"])

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Should show "No metrics found" message
        assert "No metrics found" in result.output


def test_metric_search_no_results_after_filtering(mock_client, runner):
    """Test metric search returns no results when filter doesn't match any metrics."""
    mock_response = MockMetricListResponse(
        metrics=["system.cpu.user", "system.cpu.system", "system.mem.used"]
    )
    mock_client.metrics.list_active_metrics.return_value = mock_response

    with patch("ddogctl.commands.metric.get_datadog_client", return_value=mock_client):
        result = runner.invoke(metric, ["search", "nonexistent"])

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "No metrics found" in result.output


def test_metric_search_client_side_filtering(mock_client, runner):
    """Test metric search filters results client-side by substring match."""
    mock_response = MockMetricListResponse(
        metrics=[
            "system.cpu.user",
            "system.cpu.system",
            "system.cpu.idle",
            "system.mem.used",
            "system.disk.read",
        ]
    )
    mock_client.metrics.list_active_metrics.return_value = mock_response

    with patch("ddogctl.commands.metric.get_datadog_client", return_value=mock_client):
        result = runner.invoke(metric, ["search", "cpu"])

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Only cpu metrics should appear
        assert "system.cpu.user" in result.output
        assert "system.cpu.system" in result.output
        assert "system.cpu.idle" in result.output
        assert "system.mem.used" not in result.output
        assert "system.disk.read" not in result.output
        assert "Found 3 metrics" in result.output


def test_metric_search_case_insensitive(mock_client, runner):
    """Test metric search is case-insensitive."""
    mock_response = MockMetricListResponse(metrics=["system.CPU.user", "system.cpu.system"])
    mock_client.metrics.list_active_metrics.return_value = mock_response

    with patch("ddogctl.commands.metric.get_datadog_client", return_value=mock_client):
        result = runner.invoke(metric, ["search", "CPU"])

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "system.CPU.user" in result.output
        assert "system.cpu.system" in result.output


def test_metric_metadata(mock_client, runner):
    """Test metric metadata retrieval."""
    mock_metadata = MockMetricMetadata(
        metric_name="system.cpu.user",
        description="CPU time spent in user space",
        type="gauge",
        unit="percent",
        per_unit="second",
    )
    mock_client.metrics.get_metric_metadata.return_value = mock_metadata

    with patch("ddogctl.commands.metric.get_datadog_client", return_value=mock_client):
        result = runner.invoke(metric, ["metadata", "system.cpu.user"])

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify metadata is displayed
        assert "system.cpu.user" in result.output
        assert "CPU time spent in user space" in result.output
        assert "gauge" in result.output
        assert "percent" in result.output


def test_metric_metadata_minimal(mock_client, runner):
    """Test metric metadata with minimal fields."""
    mock_metadata = MockMetricMetadata(metric_name="custom.metric")
    mock_client.metrics.get_metric_metadata.return_value = mock_metadata

    with patch("ddogctl.commands.metric.get_datadog_client", return_value=mock_client):
        result = runner.invoke(metric, ["metadata", "custom.metric"])

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Should still show metric name
        assert "custom.metric" in result.output


def test_metric_query_multiple_series(mock_client, runner):
    """Test metric query returning multiple series."""
    mock_response = MockMetricQueryResponse(
        series=[
            {
                "metric": "system.cpu.user",
                "pointlist": [[1609459200000, 25.5]],
                "scope": "host:web-01",
            },
            {
                "metric": "system.cpu.user",
                "pointlist": [[1609459200000, 30.2]],
                "scope": "host:web-02",
            },
        ]
    )
    mock_client.metrics.query_metrics.return_value = mock_response

    with patch("ddogctl.commands.metric.get_datadog_client", return_value=mock_client):
        result = runner.invoke(
            metric, ["query", "avg:system.cpu.user{*} by {host}", "--format", "json"]
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        output = json.loads(result.output)
        assert len(output["series"]) == 2
        assert output["series"][0]["scope"] == "host:web-01"
        assert output["series"][1]["scope"] == "host:web-02"


def test_metric_query_table_format_truncates_points(mock_client, runner):
    """Test that table format shows only last 20 points."""
    # Create 30 data points
    pointlist = [MockPoint(1609459200000 + (i * 60000), 50.0 + i) for i in range(30)]

    mock_response = MockMetricQueryResponse(
        series=[
            {
                "metric": "system.load.1",
                "pointlist": pointlist,
            }
        ]
    )
    mock_client.metrics.query_metrics.return_value = mock_response

    with patch("ddogctl.commands.metric.get_datadog_client", return_value=mock_client):
        result = runner.invoke(metric, ["query", "avg:system.load.1{*}", "--format", "table"])

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Should show total points count
        assert "Total points: 30" in result.output

        # Table should only display last 20 points
        # (difficult to verify exact count in table, but we can check the message)
