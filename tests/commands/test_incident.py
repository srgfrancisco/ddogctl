"""Tests for incident commands."""

import json
from unittest.mock import Mock, patch
from ddogctl.commands.incident import incident


def _make_incident(
    id, title, severity, status, created="2026-01-15T10:00:00Z", modified="2026-01-15T12:00:00Z"
):
    """Create a mock incident object.

    The Datadog v2 SDK exposes the incident lifecycle as ``state`` on
    ``IncidentResponseAttributes`` — not ``status`` — so the mock uses
    ``spec_set`` to reject the old attribute name and keep tests honest.
    """
    inc = Mock()
    inc.id = id
    inc.type = "incidents"
    inc.attributes = Mock(
        spec_set=["title", "severity", "state", "created", "modified", "fields"],
        title=title,
        severity=severity,
        state=status,
        created=created,
        modified=modified,
        fields={},
    )
    return inc


class TestListIncidents:
    def test_list_incidents_table(self, mock_client, runner):
        """Test listing incidents in table format."""
        incidents = [
            _make_incident("inc-1", "Service outage", "SEV-1", "active"),
            _make_incident("inc-2", "Degraded performance", "SEV-3", "stable"),
        ]
        response = Mock(data=incidents)
        mock_client.incidents.list_incidents.return_value = response

        with patch("ddogctl.commands.incident.get_datadog_client", return_value=mock_client):
            result = runner.invoke(incident, ["list"])

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "Service outage" in result.output
        assert "Degraded performance" in result.output
        assert "SEV-1" in result.output
        assert "SEV-3" in result.output
        assert "Total incidents: 2" in result.output

    def test_list_incidents_json(self, mock_client, runner):
        """Test listing incidents in JSON format."""
        incidents = [
            _make_incident("inc-1", "Service outage", "SEV-1", "active"),
            _make_incident("inc-2", "Degraded performance", "SEV-3", "stable"),
        ]
        response = Mock(data=incidents)
        mock_client.incidents.list_incidents.return_value = response

        with patch("ddogctl.commands.incident.get_datadog_client", return_value=mock_client):
            result = runner.invoke(incident, ["list", "--format", "json"])

        assert result.exit_code == 0, f"Command failed: {result.output}"
        output = json.loads(result.output)
        assert len(output) == 2
        assert output[0]["id"] == "inc-1"
        assert output[0]["title"] == "Service outage"
        assert output[0]["severity"] == "SEV-1"
        assert output[0]["status"] == "active"
        assert output[1]["id"] == "inc-2"

    def test_list_incidents_empty(self, mock_client, runner):
        """Test listing incidents when none exist."""
        response = Mock(data=[])
        mock_client.incidents.list_incidents.return_value = response

        with patch("ddogctl.commands.incident.get_datadog_client", return_value=mock_client):
            result = runner.invoke(incident, ["list"])

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "Total incidents: 0" in result.output


class TestGetIncident:
    def test_get_incident_table(self, mock_client, runner):
        """Test getting a single incident in table format."""
        inc = _make_incident("inc-1", "Service outage", "SEV-1", "active")
        response = Mock(data=inc)
        mock_client.incidents.get_incident.return_value = response

        with patch("ddogctl.commands.incident.get_datadog_client", return_value=mock_client):
            result = runner.invoke(incident, ["get", "inc-1"])

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "inc-1" in result.output
        assert "Service outage" in result.output
        assert "SEV-1" in result.output
        assert "active" in result.output
        mock_client.incidents.get_incident.assert_called_once_with(incident_id="inc-1")

    def test_get_incident_json(self, mock_client, runner):
        """Test getting a single incident in JSON format."""
        inc = _make_incident("inc-1", "Service outage", "SEV-1", "active")
        response = Mock(data=inc)
        mock_client.incidents.get_incident.return_value = response

        with patch("ddogctl.commands.incident.get_datadog_client", return_value=mock_client):
            result = runner.invoke(incident, ["get", "inc-1", "--format", "json"])

        assert result.exit_code == 0, f"Command failed: {result.output}"
        output = json.loads(result.output)
        assert output["id"] == "inc-1"
        assert output["title"] == "Service outage"
        assert output["severity"] == "SEV-1"
        assert output["status"] == "active"


class TestCreateIncident:
    def test_create_incident(self, mock_client, runner):
        """Test creating an incident."""
        inc = _make_incident("inc-new", "New outage", "SEV-2", "active")
        response = Mock(data=inc)
        mock_client.incidents.create_incident.return_value = response

        with patch("ddogctl.commands.incident.get_datadog_client", return_value=mock_client):
            result = runner.invoke(
                incident, ["create", "--title", "New outage", "--severity", "SEV-2"]
            )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "inc-new" in result.output
        assert "created" in result.output
        assert "New outage" in result.output
        mock_client.incidents.create_incident.assert_called_once()

    def test_create_incident_json(self, mock_client, runner):
        """Test creating an incident with JSON output."""
        inc = _make_incident("inc-new", "New outage", "SEV-2", "active")
        response = Mock(data=inc)
        mock_client.incidents.create_incident.return_value = response

        with patch("ddogctl.commands.incident.get_datadog_client", return_value=mock_client):
            result = runner.invoke(
                incident,
                ["create", "--title", "New outage", "--severity", "SEV-2", "--format", "json"],
            )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        output = json.loads(result.output)
        assert output["id"] == "inc-new"
        assert output["severity"] == "SEV-2"

    def test_create_incident_missing_title(self, runner):
        """Test that create fails without required --title."""
        result = runner.invoke(incident, ["create", "--severity", "SEV-1"])
        assert result.exit_code != 0
        assert "Missing" in result.output or "required" in result.output.lower()

    def test_create_incident_missing_severity(self, runner):
        """Test that create fails without required --severity."""
        result = runner.invoke(incident, ["create", "--title", "Outage"])
        assert result.exit_code != 0
        assert "Missing" in result.output or "required" in result.output.lower()


class TestUpdateIncident:
    def test_update_incident(self, mock_client, runner):
        """Test updating an incident."""
        inc = _make_incident("inc-1", "Updated title", "SEV-1", "stable")
        response = Mock(data=inc)
        mock_client.incidents.update_incident.return_value = response

        with patch("ddogctl.commands.incident.get_datadog_client", return_value=mock_client):
            result = runner.invoke(
                incident, ["update", "inc-1", "--title", "Updated title", "--status", "stable"]
            )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "inc-1" in result.output
        assert "updated" in result.output
        assert "Updated title" in result.output
        mock_client.incidents.update_incident.assert_called_once()

    def test_update_incident_severity_only(self, mock_client, runner):
        """Test updating only the severity of an incident."""
        inc = _make_incident("inc-1", "Service outage", "SEV-2", "active")
        response = Mock(data=inc)
        mock_client.incidents.update_incident.return_value = response

        with patch("ddogctl.commands.incident.get_datadog_client", return_value=mock_client):
            result = runner.invoke(incident, ["update", "inc-1", "--severity", "SEV-2"])

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "updated" in result.output

    def test_update_incident_no_fields(self, runner):
        """Test that update fails when no fields are specified."""
        result = runner.invoke(incident, ["update", "inc-1"])
        assert result.exit_code != 0
        assert "No update fields" in result.output

    def test_update_incident_status_sent_as_fields_state(self, mock_client, runner):
        """--status must be sent via fields["state"], not as a top-level attribute.

        Regression test: the Datadog v2 SDK's ``IncidentUpdateAttributes`` has
        no ``status`` (or ``state``) attribute — state changes flow through
        the ``fields`` dict. Putting ``status`` on the attributes object
        silently no-ops the lifecycle update.
        """
        inc = _make_incident("inc-1", "Service outage", "SEV-1", "resolved")
        response = Mock(data=inc)
        mock_client.incidents.update_incident.return_value = response

        with patch("ddogctl.commands.incident.get_datadog_client", return_value=mock_client):
            result = runner.invoke(incident, ["update", "inc-1", "--status", "resolved"])

        assert result.exit_code == 0, f"Command failed: {result.output}"
        mock_client.incidents.update_incident.assert_called_once()
        body = mock_client.incidents.update_incident.call_args.kwargs["body"]
        attrs = body.data.attributes
        state_field = attrs.fields["state"]
        assert str(state_field["type"]) == "dropdown"
        assert str(state_field["value"]) == "resolved"
        assert not hasattr(attrs, "status")
        assert not hasattr(attrs, "state")

    def test_update_incident_json_reads_state(self, mock_client, runner):
        """JSON output's ``status`` key must reflect the SDK's ``state`` attribute."""
        inc = _make_incident("inc-1", "Service outage", "SEV-1", "resolved")
        response = Mock(data=inc)
        mock_client.incidents.update_incident.return_value = response

        with patch("ddogctl.commands.incident.get_datadog_client", return_value=mock_client):
            result = runner.invoke(
                incident,
                ["update", "inc-1", "--status", "resolved", "--format", "json"],
            )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        output = json.loads(result.output)
        assert output["status"] == "resolved"


class TestDeleteIncident:
    def test_delete_incident_with_confirm(self, mock_client, runner):
        """Test deleting an incident with --confirm flag."""
        mock_client.incidents.delete_incident.return_value = None

        with patch("ddogctl.commands.incident.get_datadog_client", return_value=mock_client):
            result = runner.invoke(incident, ["delete", "inc-1", "--confirm"])

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "inc-1" in result.output
        assert "deleted" in result.output
        mock_client.incidents.delete_incident.assert_called_once_with(incident_id="inc-1")

    def test_delete_incident_interactive_yes(self, mock_client, runner):
        """Test deleting an incident with interactive confirmation (user says yes)."""
        mock_client.incidents.delete_incident.return_value = None

        with patch("ddogctl.commands.incident.get_datadog_client", return_value=mock_client):
            result = runner.invoke(incident, ["delete", "inc-1"], input="y\n")

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "deleted" in result.output
        mock_client.incidents.delete_incident.assert_called_once_with(incident_id="inc-1")

    def test_delete_incident_without_confirm(self, mock_client, runner):
        """Test that delete is aborted when user declines confirmation."""
        with patch("ddogctl.commands.incident.get_datadog_client", return_value=mock_client):
            result = runner.invoke(incident, ["delete", "inc-1"], input="n\n")

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "Aborted" in result.output
        mock_client.incidents.delete_incident.assert_not_called()
