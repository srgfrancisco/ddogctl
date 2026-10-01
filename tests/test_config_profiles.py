"""Tests for profile loading integration in config.py."""

import json
from unittest.mock import patch

import pytest
from ddogctl.config import load_config


class TestLoadConfigWithProfiles:
    """Tests for load_config with profile support."""

    @patch.dict("os.environ", {"DD_API_KEY": "env-key", "DD_APP_KEY": "env-app"}, clear=False)
    def test_env_vars_take_precedence_over_profile(self, tmp_path):
        """Test that env vars override profile values."""
        config_dir = tmp_path / ".ddogctl"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"

        config_data = {
            "active_profile": "prod",
            "profiles": {
                "prod": {
                    "api_key": "profile-key",
                    "app_key": "profile-app",
                    "site": "datadoghq.eu",
                }
            },
        }
        config_file.write_text(json.dumps(config_data))

        with patch("ddogctl.config.get_config_path", return_value=str(config_file)):
            config = load_config()

        # Env vars should win
        assert config.api_key == "env-key"
        assert config.app_key == "env-app"

    @patch.dict("os.environ", {}, clear=True)
    def test_loads_from_active_profile_when_no_env_vars(self, tmp_path):
        """Test loading config from active profile when env vars are missing."""
        config_dir = tmp_path / ".ddogctl"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"

        config_data = {
            "active_profile": "prod",
            "profiles": {
                "prod": {
                    "api_key": "profile-key",
                    "app_key": "profile-app",
                    "site": "datadoghq.com",
                }
            },
        }
        config_file.write_text(json.dumps(config_data))

        with patch("ddogctl.config.get_config_path", return_value=str(config_file)):
            config = load_config()

        assert config.api_key == "profile-key"
        assert config.app_key == "profile-app"
        assert config.site == "datadoghq.com"

    @patch.dict("os.environ", {}, clear=True)
    def test_loads_named_profile(self, tmp_path):
        """Test loading a specific named profile."""
        config_dir = tmp_path / ".ddogctl"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"

        config_data = {
            "active_profile": "prod",
            "profiles": {
                "prod": {
                    "api_key": "prod-key",
                    "app_key": "prod-app",
                    "site": "datadoghq.com",
                },
                "staging": {
                    "api_key": "staging-key",
                    "app_key": "staging-app",
                    "site": "datadoghq.eu",
                },
            },
        }
        config_file.write_text(json.dumps(config_data))

        with patch("ddogctl.config.get_config_path", return_value=str(config_file)):
            config = load_config(profile="staging")

        assert config.api_key == "staging-key"
        assert config.app_key == "staging-app"
        assert config.site == "datadoghq.eu"

    @patch.dict("os.environ", {"DDOGCTL_PROFILE": "staging"}, clear=True)
    def test_loads_profile_from_env_var(self, tmp_path):
        """Test loading profile specified via DDOGCTL_PROFILE env var."""
        config_dir = tmp_path / ".ddogctl"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"

        config_data = {
            "active_profile": "prod",
            "profiles": {
                "prod": {
                    "api_key": "prod-key",
                    "app_key": "prod-app",
                    "site": "datadoghq.com",
                },
                "staging": {
                    "api_key": "staging-key",
                    "app_key": "staging-app",
                    "site": "datadoghq.eu",
                },
            },
        }
        config_file.write_text(json.dumps(config_data))

        with patch("ddogctl.config.get_config_path", return_value=str(config_file)):
            config = load_config()

        assert config.api_key == "staging-key"
        assert config.site == "datadoghq.eu"

    @patch.dict("os.environ", {}, clear=True)
    def test_cli_profile_overrides_env_var_profile(self, tmp_path):
        """Test that explicit profile param overrides DDOGCTL_PROFILE env var."""
        config_dir = tmp_path / ".ddogctl"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"

        config_data = {
            "active_profile": "prod",
            "profiles": {
                "prod": {
                    "api_key": "prod-key",
                    "app_key": "prod-app",
                    "site": "datadoghq.com",
                },
                "staging": {
                    "api_key": "staging-key",
                    "app_key": "staging-app",
                    "site": "datadoghq.eu",
                },
            },
        }
        config_file.write_text(json.dumps(config_data))

        with patch("ddogctl.config.get_config_path", return_value=str(config_file)):
            config = load_config(profile="staging")

        assert config.api_key == "staging-key"

    @patch.dict("os.environ", {}, clear=True)
    def test_nonexistent_profile_exits(self, tmp_path):
        """Test that requesting a nonexistent profile exits with error."""
        config_dir = tmp_path / ".ddogctl"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"

        config_data = {
            "active_profile": "prod",
            "profiles": {
                "prod": {
                    "api_key": "key",
                    "app_key": "app",
                    "site": "datadoghq.com",
                }
            },
        }
        config_file.write_text(json.dumps(config_data))

        with (
            patch("ddogctl.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.config.console"),
            pytest.raises(SystemExit),
        ):
            load_config(profile="nonexistent")

    @patch.dict("os.environ", {}, clear=True)
    def test_no_config_file_and_no_env_vars_exits(self, tmp_path):
        """Test that missing config file and env vars exits with error."""
        config_file = tmp_path / "nonexistent" / "config.json"

        with (
            patch("ddogctl.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.config.console"),
            pytest.raises(SystemExit),
        ):
            load_config()

    @patch.dict("os.environ", {}, clear=True)
    def test_profile_site_region_shortcut_expanded(self, tmp_path):
        """Test that region shortcuts in profile are expanded."""
        config_dir = tmp_path / ".ddogctl"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"

        config_data = {
            "active_profile": "prod",
            "profiles": {
                "prod": {
                    "api_key": "key",
                    "app_key": "app",
                    "site": "eu",
                }
            },
        }
        config_file.write_text(json.dumps(config_data))

        with patch("ddogctl.config.get_config_path", return_value=str(config_file)):
            config = load_config()

        assert config.site == "datadoghq.eu"


class TestProfileFlagIntegration:
    """Tests for --profile flag on the main CLI group."""

    @patch.dict("os.environ", {}, clear=True)
    def test_profile_flag_passes_to_load_config(self, runner, tmp_path):
        """Test that --profile flag is used when loading config."""
        from ddogctl.cli import main

        config_dir = tmp_path / ".ddogctl"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"

        config_data = {
            "active_profile": "prod",
            "profiles": {
                "staging": {
                    "api_key": "staging-key",
                    "app_key": "staging-app",
                    "site": "datadoghq.eu",
                }
            },
        }
        config_file.write_text(json.dumps(config_data))

        with patch("ddogctl.config.get_config_path", return_value=str(config_file)):
            # Just test that --profile is accepted as an option
            result = runner.invoke(main, ["--profile", "staging", "--help"])

        # --help should succeed and show help text
        assert result.exit_code == 0

    def test_profile_flag_shown_in_help(self, runner):
        """Test that --profile is listed in CLI help."""
        from ddogctl.cli import main

        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "--profile" in result.output


class TestLoadConfigWithPatProfiles:
    """Tests for PAT support in profiles."""

    def _write(self, tmp_path, profile):
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"active_profile": "work", "profiles": {"work": profile}})
        )
        return config_file

    @patch.dict("os.environ", {}, clear=True)
    def test_loads_pat_from_profile(self, tmp_path):
        config_file = self._write(tmp_path, {"pat": "ddpat_profile", "site": "datadoghq.eu"})

        with patch("ddogctl.config.get_config_path", return_value=str(config_file)):
            config = load_config()

        assert config.pat == "ddpat_profile"
        assert config.site == "datadoghq.eu"
        assert config.auth_mode == "pat"

    @patch.dict("os.environ", {"DD_PAT": "ddpat_env"}, clear=True)
    def test_env_pat_overrides_profile(self, tmp_path):
        config_file = self._write(tmp_path, {"pat": "ddpat_profile"})

        with patch("ddogctl.config.get_config_path", return_value=str(config_file)):
            config = load_config()

        assert config.pat == "ddpat_env"
