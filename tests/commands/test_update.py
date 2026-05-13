"""Tests for the update command."""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests
from click.testing import CliRunner

from ddogctl.cli import main


def _mock_pypi_response(version: str) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"info": {"version": version}}
    resp.raise_for_status = MagicMock()
    return resp


class TestUpdateCheck:
    """Behaviour of `ddogctl update` (check-only)."""

    def test_reports_up_to_date_when_versions_match(self):
        runner = CliRunner()
        with (
            patch("ddogctl.commands.update.requests.get") as mock_get,
            patch("ddogctl.commands.update._current_version", return_value="2.0.5"),
        ):
            mock_get.return_value = _mock_pypi_response("2.0.5")
            result = runner.invoke(main, ["update"])

        assert result.exit_code == 0
        assert "up to date" in result.output.lower()
        assert "2.0.5" in result.output

    def test_reports_update_available_when_pypi_is_newer(self):
        runner = CliRunner()
        with (
            patch("ddogctl.commands.update.requests.get") as mock_get,
            patch("ddogctl.commands.update._current_version", return_value="2.0.5"),
        ):
            mock_get.return_value = _mock_pypi_response("2.1.0")
            result = runner.invoke(main, ["update"])

        assert result.exit_code == 0
        assert "2.0.5" in result.output
        assert "2.1.0" in result.output
        # Should hint at an upgrade command
        assert "install" in result.output.lower() or "upgrade" in result.output.lower()

    def test_reports_ahead_when_local_is_newer(self):
        runner = CliRunner()
        with (
            patch("ddogctl.commands.update.requests.get") as mock_get,
            patch("ddogctl.commands.update._current_version", return_value="3.0.0"),
        ):
            mock_get.return_value = _mock_pypi_response("2.0.5")
            result = runner.invoke(main, ["update"])

        assert result.exit_code == 0
        # Local is ahead — message should make that obvious
        assert "ahead" in result.output.lower() or "newer" in result.output.lower()

    def test_uses_pep440_version_comparison(self):
        # 2.0.10 must be greater than 2.0.9 (not a lexical sort)
        runner = CliRunner()
        with (
            patch("ddogctl.commands.update.requests.get") as mock_get,
            patch("ddogctl.commands.update._current_version", return_value="2.0.9"),
        ):
            mock_get.return_value = _mock_pypi_response("2.0.10")
            result = runner.invoke(main, ["update"])

        assert result.exit_code == 0
        assert "2.0.10" in result.output
        assert "install" in result.output.lower() or "upgrade" in result.output.lower()


class TestUpdateNetworkErrors:
    """Network/HTTP error handling."""

    def test_network_failure_exits_nonzero_with_message(self):
        runner = CliRunner()
        with (
            patch("ddogctl.commands.update.requests.get") as mock_get,
            patch("ddogctl.commands.update._current_version", return_value="2.0.5"),
        ):
            mock_get.side_effect = requests.ConnectionError("boom")
            result = runner.invoke(main, ["update"])

        assert result.exit_code != 0
        assert "could not reach" in result.output.lower() or "failed" in result.output.lower()

    def test_http_error_exits_nonzero(self):
        runner = CliRunner()
        with (
            patch("ddogctl.commands.update.requests.get") as mock_get,
            patch("ddogctl.commands.update._current_version", return_value="2.0.5"),
        ):
            err_resp = MagicMock()
            err_resp.raise_for_status.side_effect = requests.HTTPError("500")
            mock_get.return_value = err_resp
            result = runner.invoke(main, ["update"])

        assert result.exit_code != 0


class TestUpdateJsonFormat:
    """`--format json` output contract."""

    def test_json_output_when_up_to_date(self):
        runner = CliRunner()
        with (
            patch("ddogctl.commands.update.requests.get") as mock_get,
            patch("ddogctl.commands.update._current_version", return_value="2.0.5"),
        ):
            mock_get.return_value = _mock_pypi_response("2.0.5")
            result = runner.invoke(main, ["update", "--format", "json"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["current"] == "2.0.5"
        assert payload["latest"] == "2.0.5"
        assert payload["update_available"] is False
        assert "upgrade_command" in payload

    def test_json_output_when_update_available(self):
        runner = CliRunner()
        with (
            patch("ddogctl.commands.update.requests.get") as mock_get,
            patch("ddogctl.commands.update._current_version", return_value="2.0.5"),
        ):
            mock_get.return_value = _mock_pypi_response("2.1.0")
            result = runner.invoke(main, ["update", "--format", "json"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["current"] == "2.0.5"
        assert payload["latest"] == "2.1.0"
        assert payload["update_available"] is True
        assert payload["upgrade_command"]


class TestInstallMethodDetection:
    """Heuristic detection of install method."""

    @pytest.mark.parametrize(
        "executable,expected_substring",
        [
            ("/Users/x/.local/pipx/venvs/ddogctl/bin/python", "pipx"),
            ("/Users/x/.local/share/uv/tools/ddogctl/bin/python", "uv tool"),
            ("/Users/x/some/.venv/bin/python", "pip install --upgrade"),
            ("/usr/local/bin/python3", "pip install --upgrade"),
        ],
    )
    def test_detect_returns_appropriate_command(self, executable, expected_substring):
        from ddogctl.commands.update import _detect_upgrade_command

        cmd = _detect_upgrade_command(executable=executable)
        assert expected_substring in cmd
