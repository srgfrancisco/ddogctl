"""Shared test fixtures and utilities."""

import pytest
from unittest.mock import Mock
from click.testing import CliRunner


@pytest.fixture
def mock_client():
    """Create a mock Datadog client with common attributes.

    This fixture provides a base mock client that can be used across all test modules.
    Individual tests should configure specific API methods (monitors, hosts, metrics, etc.)
    as needed.

    Example:
        def test_something(mock_client):
            mock_client.monitors.list_monitors.return_value = [...]
            with patch('ddogctl.commands.monitor.get_datadog_client', return_value=mock_client):
                # test code
    """
    client = Mock()
    client.monitors = Mock()
    client.hosts = Mock()
    client.metrics = Mock()
    client.events = Mock()
    client.spans = Mock()
    client.logs = Mock()
    client.dbm = Mock()
    client.service_definitions = Mock()
    client.service_checks = Mock()
    client.downtimes = Mock()
    client.slos = Mock()
    client.dashboards = Mock()
    client.incidents = Mock()
    client.users = Mock()
    client.usage = Mock()
    client.synthetics = Mock()
    client.rum = Mock()
    client.ci_pipelines = Mock()
    client.ci_tests = Mock()
    client.notebooks = Mock()
    return client


@pytest.fixture
def runner():
    """Click CLI test runner.

    Use this fixture to invoke Click commands in tests.

    Example:
        def test_command(runner):
            result = runner.invoke(my_command, ['--option', 'value'])
            assert result.exit_code == 0
    """
    return CliRunner()


# Data factory functions for common test objects


def create_mock_monitor(
    id, name, state, tags=None, monitor_type="metric alert", query="avg:system.cpu.user{*}"
):
    """Factory function to create mock monitor objects.

    Args:
        id: Monitor ID
        name: Monitor name
        state: Monitor state (MonitorOverallStates enum)
        tags: List of tags (default: [])
        monitor_type: Monitor type (default: "metric alert")
        query: Monitor query (default: "avg:system.cpu.user{*}")

    Returns:
        Mock monitor object with to_dict() method
    """

    class MockMonitor:
        def __init__(self, id, name, overall_state, tags, type, query):
            self.id = id
            self.name = name
            self.overall_state = overall_state
            self.tags = tags or []
            self.type = type
            self.query = query
            self.message = f"Test monitor: {name}"

        def to_dict(self):
            return {
                "id": self.id,
                "name": self.name,
                "overall_state": str(self.overall_state),
                "type": self.type,
                "query": self.query,
                "message": self.message,
                "tags": self.tags,
            }

    return MockMonitor(id, name, state, tags, monitor_type, query)


def create_mock_host(
    name, is_up=True, apps=None, last_reported_time=None, host_name=None, tags_by_source=None
):
    """Factory function to create mock host objects.

    Args:
        name: Host name
        is_up: Whether host is up (default: True)
        apps: List of apps running on host (default: [])
        last_reported_time: Unix timestamp of last report (default: None)
        host_name: Actual hostname (default: same as name)
        tags_by_source: Dict of tag sources to tag lists (default: {})

    Returns:
        Mock host object with to_dict() method
    """

    class MockHost:
        def __init__(self, name, is_up, apps, last_reported_time, host_name, tags_by_source):
            self.name = name
            self.is_up = is_up
            self.apps = apps or []
            self.last_reported_time = last_reported_time
            self.host_name = host_name or name
            self.tags_by_source = tags_by_source or {}

        def to_dict(self):
            return {
                "name": self.name,
                "is_up": self.is_up,
                "apps": self.apps,
                "last_reported_time": self.last_reported_time,
                "host_name": self.host_name,
                "tags_by_source": self.tags_by_source,
            }

    return MockHost(name, is_up, apps, last_reported_time, host_name, tags_by_source)


def create_mock_host_list_response(host_list, total_matching=None):
    """Factory function to create mock host list response.

    Args:
        host_list: List of mock host objects
        total_matching: Total matching hosts (default: len(host_list))

    Returns:
        Mock response object with host_list and total_matching attributes
    """

    class MockHostListResponse:
        def __init__(self, host_list, total_matching):
            self.host_list = host_list
            self.total_matching = total_matching if total_matching is not None else len(host_list)

        def to_dict(self):
            return {
                "host_list": [h.to_dict() for h in self.host_list],
                "total_matching": self.total_matching,
            }

    return MockHostListResponse(host_list, total_matching)


def create_mock_host_totals(total_active, total_up, total_down=None):
    """Factory function to create mock host totals response.

    Args:
        total_active: Number of active hosts
        total_up: Number of up hosts
        total_down: Number of down hosts (default: None)

    Returns:
        Mock totals object with total_active, total_up, and optionally total_down
    """

    class MockHostTotals:
        def __init__(self, total_active, total_up, total_down):
            self.total_active = total_active
            self.total_up = total_up
            if total_down is not None:
                self.total_down = total_down

    return MockHostTotals(total_active, total_up, total_down)


# Common test data patterns

# Typical host configurations for testing
MOCK_HOSTS = {
    "web_prod": create_mock_host(
        "web-prod-01",
        is_up=True,
        apps=["nginx", "app"],
        last_reported_time=1644000000,
        tags_by_source={"Datadog": ["env:prod", "service:web"]},
    ),
    "web_down": create_mock_host(
        "web-prod-02", is_up=False, apps=["nginx"], last_reported_time=1644000000
    ),
    "db_prod": create_mock_host(
        "db-prod-01",
        is_up=True,
        apps=["postgresql"],
        last_reported_time=1644000000,
        tags_by_source={"Datadog": ["env:prod", "service:database"]},
    ),
}


# Monitor states for testing
def get_monitor_states():
    """Get MonitorOverallStates enum for use in tests."""
    from datadog_api_client.v1.model.monitor_overall_states import MonitorOverallStates

    return MonitorOverallStates


# APM factory functions


def create_mock_service_list(services):
    """Factory function to create mock ServiceDefinition list response.

    Args:
        services: List of service names (strings)

    Returns:
        Mock response matching ServiceDefinitionApi.list_service_definitions()
    """
    data = []
    for name in services:
        schema = Mock()
        schema.dd_service = name
        schema.team = ""
        schema.type = "custom"
        schema.languages = []
        item = Mock()
        item.attributes = Mock(schema=schema)
        data.append(item)

    return Mock(data=data)


def create_mock_span(span_id, service, resource_name, trace_id, start_ts, end_ts):
    """Factory function to create mock Span object with duration calculation.

    Args:
        span_id: Span ID (string)
        service: Service name (string)
        resource_name: Resource name (string, e.g., "GET /api/users")
        trace_id: Trace ID (string)
        start_ts: Start timestamp (datetime)
        end_ts: End timestamp (datetime)

    Returns:
        Mock Span object with attributes and duration in nanoseconds
    """
    duration_ns = int((end_ts - start_ts).total_seconds() * 1_000_000_000)

    class MockSpan:
        def __init__(self):
            self.id = span_id
            self.type = "span"
            self.attributes = Mock(
                service=service,
                resource_name=resource_name,
                trace_id=trace_id,
                span_id=span_id,
                start_timestamp=start_ts,
                end_timestamp=end_ts,
                duration=duration_ns,
            )

        def to_dict(self):
            return {
                "id": self.id,
                "type": self.type,
                "attributes": {
                    "service": self.attributes.service,
                    "resource_name": self.attributes.resource_name,
                    "trace_id": self.attributes.trace_id,
                    "span_id": self.attributes.span_id,
                    "start_timestamp": (
                        self.attributes.start_timestamp.isoformat()
                        if self.attributes.start_timestamp
                        else None
                    ),
                    "end_timestamp": (
                        self.attributes.end_timestamp.isoformat()
                        if self.attributes.end_timestamp
                        else None
                    ),
                    "duration": self.attributes.duration,
                },
            }

    return MockSpan()


# Logs factory functions


def create_mock_log(message, service, status, timestamp, attributes=None, trace_id=None):
    """Factory for mock log objects."""

    class MockLog:
        def __init__(self):
            self.id = f"log-{abs(hash(message)) % 10000}"
            self.type = "log"
            attrs = attributes or {}
            if trace_id:
                attrs["trace_id"] = trace_id
            self.attributes = Mock(
                message=message,
                service=service,
                status=status,
                timestamp=timestamp,
                attributes=attrs,
                tags=[f"service:{service}"],
            )

        def to_dict(self):
            return {
                "id": self.id,
                "attributes": {
                    "message": self.attributes.message,
                    "service": self.attributes.service,
                    "status": self.attributes.status,
                    "timestamp": str(self.attributes.timestamp),
                },
            }

    return MockLog()


# RUM factory functions


def create_mock_rum_event(event_id, event_type, timestamp, attributes=None, tags=None):
    """Factory for mock RUM event objects.

    Args:
        event_id: Event ID (string)
        event_type: Event type (e.g., "view", "action", "error", "resource", "long_task")
        timestamp: Event timestamp (datetime)
        attributes: Dict of event attributes (default: {})
        tags: List of tags (default: [])

    Returns:
        Mock RUM event object
    """

    class MockRUMEvent:
        def __init__(self):
            self.id = event_id
            self.type = event_type
            self.attributes = Mock(
                type=event_type,
                timestamp=timestamp,
                attributes=attributes or {},
                tags=tags or [],
            )

    return MockRUMEvent()
