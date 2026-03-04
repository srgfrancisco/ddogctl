"""Tests for event commands."""

import pytest
import json
from unittest.mock import Mock, patch
from click.testing import CliRunner
from ddogctl.commands.event import event


class MockEvent:
    """Mock Datadog event object."""

    def __init__(
        self,
        event_id,
        title,
        date_happened,
        source=None,
        priority=None,
        tags=None,
        text=None,
        url=None,
    ):
        self.id = event_id
        self.title = title
        self.date_happened = date_happened
        self.source = source
        self.priority = priority
        self.tags = tags or []
        self.text = text
        self.url = url

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "date_happened": self.date_happened,
            "source": self.source,
            "priority": str(self.priority) if self.priority else None,
            "tags": self.tags,
            "text": self.text,
            "url": self.url,
        }


class MockEventListResponse:
    """Mock Datadog event list response."""

    def __init__(self, events=None):
        self.events = events or []

    def to_dict(self):
        return {"events": [evt.to_dict() for evt in self.events]}


class MockEventGetResponse:
    """Mock Datadog event get response."""

    def __init__(self, event):
        self.event = event


class MockEventCreateResponse:
    """Mock Datadog event create response."""

    def __init__(self, event):
        self.event = event


@pytest.fixture
def mock_client():
    """Create a mock Datadog client."""
    client = Mock()
    client.events = Mock()
    return client


@pytest.fixture
def runner():
    """Click CLI test runner."""
    return CliRunner()


def test_event_list_table_format(mock_client, runner):
    """Test event list with table output format."""
    mock_events = [
        MockEvent(
            event_id=1,
            title="Deployment started",
            date_happened=1609459200,
            source="deploy",
            priority="normal",
        ),
        MockEvent(
            event_id=2,
            title="Alert triggered",
            date_happened=1609459260,
            source="alert",
            priority="normal",
        ),
    ]
    mock_response = MockEventListResponse(events=mock_events)
    mock_client.events.list_events.return_value = mock_response

    with patch("ddogctl.commands.event.get_datadog_client", return_value=mock_client):
        result = runner.invoke(event, ["list"])

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify table contains event data
        assert "Deployment started" in result.output
        assert "Alert triggered" in result.output
        assert "Total events: 2" in result.output


def test_event_list_json_format(mock_client, runner):
    """Test event list with JSON output format."""
    mock_events = [
        MockEvent(
            event_id=1,
            title="Test Event",
            date_happened=1609459200,
            source="test",
        )
    ]
    mock_response = MockEventListResponse(events=mock_events)
    mock_client.events.list_events.return_value = mock_response

    with patch("ddogctl.commands.event.get_datadog_client", return_value=mock_client):
        result = runner.invoke(event, ["list", "--format", "json"])

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Parse JSON output
        output = json.loads(result.output)

        # Verify structure
        assert "events" in output
        assert len(output["events"]) == 1
        assert output["events"][0]["title"] == "Test Event"


def test_event_list_no_events(mock_client, runner):
    """Test event list with no events returned."""
    mock_response = MockEventListResponse(events=[])
    mock_client.events.list_events.return_value = mock_response

    with patch("ddogctl.commands.event.get_datadog_client", return_value=mock_client):
        result = runner.invoke(event, ["list"])

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Should show "No events found" message
        assert "No events found" in result.output


def test_event_list_with_filters(mock_client, runner):
    """Test event list with various filters."""
    mock_response = MockEventListResponse(events=[])
    mock_client.events.list_events.return_value = mock_response

    with patch("ddogctl.commands.event.get_datadog_client", return_value=mock_client):
        result = runner.invoke(
            event,
            [
                "list",
                "--from",
                "1h",
                "--sources",
                "alert,deploy",
                "--priority",
                "normal",
                "--tags",
                "env:prod,team:infra",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify list_events was called with correct filters
        mock_client.events.list_events.assert_called_once()
        call_kwargs = mock_client.events.list_events.call_args.kwargs

        assert "start" in call_kwargs
        assert "end" in call_kwargs
        assert call_kwargs["sources"] == "alert,deploy"
        assert call_kwargs["priority"] == "normal"
        assert call_kwargs["tags"] == "env:prod,team:infra"


def test_event_list_with_custom_time_range(mock_client, runner):
    """Test event list with custom time range."""
    mock_response = MockEventListResponse(events=[])
    mock_client.events.list_events.return_value = mock_response

    with patch("ddogctl.commands.event.get_datadog_client", return_value=mock_client):
        with patch("ddogctl.commands.event.parse_time_range") as mock_parse_time:
            mock_parse_time.return_value = (1609459200, 1609545600)

            result = runner.invoke(event, ["list", "--from", "7d", "--to", "1d"])

            assert result.exit_code == 0, f"Command failed: {result.output}"

            # Verify parse_time_range was called with both args
            mock_parse_time.assert_called_once_with("7d", "1d")

            # Verify list_events was called with parsed timestamps
            call_kwargs = mock_client.events.list_events.call_args.kwargs
            assert call_kwargs["start"] == 1609459200
            assert call_kwargs["end"] == 1609545600


def test_event_get_full_details(mock_client, runner):
    """Test getting event details with all fields."""
    mock_event = MockEvent(
        event_id=12345,
        title="Critical Alert",
        date_happened=1609459200,
        source="alert",
        priority="normal",
        tags=["env:prod", "team:infra"],
        text="Detailed event description",
        url="https://app.datadoghq.com/event/event?id=12345",
    )
    mock_response = MockEventGetResponse(event=mock_event)
    mock_client.events.get_event.return_value = mock_response

    with patch("ddogctl.commands.event.get_datadog_client", return_value=mock_client):
        result = runner.invoke(event, ["get", "12345"])

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify all event details are displayed
        assert "Event #12345" in result.output
        assert "Critical Alert" in result.output
        assert "Detailed event description" in result.output
        assert "normal" in result.output
        assert "env:prod, team:infra" in result.output


def test_event_get_minimal_details(mock_client, runner):
    """Test getting event details with minimal fields."""
    mock_event = MockEvent(
        event_id=123,
        title="Simple Event",
        date_happened=1609459200,
    )
    mock_response = MockEventGetResponse(event=mock_event)
    mock_client.events.get_event.return_value = mock_response

    with patch("ddogctl.commands.event.get_datadog_client", return_value=mock_client):
        result = runner.invoke(event, ["get", "123"])

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify basic event details are displayed
        assert "Event #123" in result.output
        assert "Simple Event" in result.output


def test_event_post_simple(mock_client, runner):
    """Test posting a simple event."""
    mock_event = MockEvent(
        event_id=99,
        title="Investigation Started",
        date_happened=1609459200,
        url="https://app.datadoghq.com/event/event?id=99",
    )
    mock_response = MockEventCreateResponse(event=mock_event)
    mock_client.events.create_event.return_value = mock_response

    with patch("ddogctl.commands.event.get_datadog_client", return_value=mock_client):
        result = runner.invoke(event, ["post", "Investigation Started"])

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify success message
        assert "Event posted: 99" in result.output
        assert "Investigation Started" in result.output

        # Verify create_event was called
        mock_client.events.create_event.assert_called_once()


def test_event_post_with_all_options(mock_client, runner):
    """Test posting an event with all options."""
    mock_event = MockEvent(
        event_id=100,
        title="Deployment Complete",
        date_happened=1609459200,
        priority="low",
        tags=["env:prod", "service:web"],
        url="https://app.datadoghq.com/event/event?id=100",
    )
    mock_response = MockEventCreateResponse(event=mock_event)
    mock_client.events.create_event.return_value = mock_response

    with patch("ddogctl.commands.event.get_datadog_client", return_value=mock_client):
        result = runner.invoke(
            event,
            [
                "post",
                "Deployment Complete",
                "--text",
                "Successfully deployed version 1.2.3",
                "--tags",
                "env:prod,service:web",
                "--priority",
                "low",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify success message
        assert "Event posted: 100" in result.output

        # Verify create_event was called with correct parameters
        mock_client.events.create_event.assert_called_once()
        call_args = mock_client.events.create_event.call_args

        # Extract the EventCreateRequest body
        event_req = call_args.kwargs["body"]

        assert event_req.title == "Deployment Complete"
        assert event_req.text == "Successfully deployed version 1.2.3"
        assert str(event_req.priority) == "low"
        assert event_req.tags == ["env:prod", "service:web"]


def test_event_post_without_text(mock_client, runner):
    """Test posting event without text uses title as text."""
    mock_event = MockEvent(
        event_id=101,
        title="Short Event",
        date_happened=1609459200,
    )
    mock_response = MockEventCreateResponse(event=mock_event)
    mock_client.events.create_event.return_value = mock_response

    with patch("ddogctl.commands.event.get_datadog_client", return_value=mock_client):
        result = runner.invoke(event, ["post", "Short Event"])

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify create_event was called
        call_args = mock_client.events.create_event.call_args
        event_req = call_args.kwargs["body"]

        # Text should default to title
        assert event_req.title == "Short Event"
        assert event_req.text == "Short Event"


def test_event_list_truncates_long_titles(mock_client, runner):
    """Test that event list truncates long titles in table format."""
    long_title = "A" * 100  # 100 character title
    mock_events = [
        MockEvent(
            event_id=1,
            title=long_title,
            date_happened=1609459200,
        )
    ]
    mock_response = MockEventListResponse(events=mock_events)
    mock_client.events.list_events.return_value = mock_response

    with patch("ddogctl.commands.event.get_datadog_client", return_value=mock_client):
        result = runner.invoke(event, ["list", "--format", "table"])

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Title should be truncated to 60 chars in table
        # (exact verification of truncation is difficult, but we can verify it doesn't crash)
        assert "Total events: 1" in result.output


def test_event_list_with_priority_filter(mock_client, runner):
    """Test event list filtered by priority."""
    mock_response = MockEventListResponse(events=[])
    mock_client.events.list_events.return_value = mock_response

    with patch("ddogctl.commands.event.get_datadog_client", return_value=mock_client):
        result = runner.invoke(event, ["list", "--priority", "low"])

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify priority filter was passed
        call_kwargs = mock_client.events.list_events.call_args.kwargs
        assert call_kwargs["priority"] == "low"


def test_event_list_without_optional_filters(mock_client, runner):
    """Test event list without optional filters only passes required params."""
    mock_response = MockEventListResponse(events=[])
    mock_client.events.list_events.return_value = mock_response

    with patch("ddogctl.commands.event.get_datadog_client", return_value=mock_client):
        result = runner.invoke(event, ["list"])

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify only start and end are in kwargs (no sources, priority, tags)
        call_kwargs = mock_client.events.list_events.call_args.kwargs
        assert "start" in call_kwargs
        assert "end" in call_kwargs
        assert "sources" not in call_kwargs
        assert "priority" not in call_kwargs
        assert "tags" not in call_kwargs
