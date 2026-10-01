"""Tests for config commands."""

import json
from unittest.mock import patch

from ddogctl.commands.config import config


class TestConfigInit:
    """Tests for config init command."""

    def test_init_creates_config_directory_and_file(self, runner, tmp_path):
        """Test that init creates ~/.ddogctl/config.json with prompted values."""
        config_dir = tmp_path / ".ddogctl"
        config_file = config_dir / "config.json"

        with (
            patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
        ):
            result = runner.invoke(
                config,
                ["init"],
                input="my-api-key\nmy-app-key\nus\ndefault\n",
            )

        assert result.exit_code == 0
        assert config_file.exists()

        data = json.loads(config_file.read_text())
        assert data["active_profile"] == "default"
        assert data["profiles"]["default"]["api_key"] == "my-api-key"
        assert data["profiles"]["default"]["app_key"] == "my-app-key"
        assert data["profiles"]["default"]["site"] == "datadoghq.com"

    def test_init_expands_region_shortcuts(self, runner, tmp_path):
        """Test that init expands region shortcuts like 'eu' to full domain."""
        config_dir = tmp_path / ".ddogctl"
        config_file = config_dir / "config.json"

        with (
            patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
        ):
            result = runner.invoke(
                config,
                ["init"],
                input="key1\nkey2\neu\nprod\n",
            )

        assert result.exit_code == 0
        data = json.loads(config_file.read_text())
        assert data["profiles"]["prod"]["site"] == "datadoghq.eu"

    def test_init_preserves_existing_profiles(self, runner, tmp_path):
        """Test that init adds to existing config without overwriting."""
        config_dir = tmp_path / ".ddogctl"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"

        existing = {
            "active_profile": "prod",
            "profiles": {
                "prod": {
                    "api_key": "prod-key",
                    "app_key": "prod-app",
                    "site": "datadoghq.com",
                }
            },
        }
        config_file.write_text(json.dumps(existing))

        with (
            patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
        ):
            result = runner.invoke(
                config,
                ["init"],
                input="staging-key\nstaging-app\neu\nstaging\n",
            )

        assert result.exit_code == 0
        data = json.loads(config_file.read_text())
        # Existing profile preserved
        assert "prod" in data["profiles"]
        assert data["profiles"]["prod"]["api_key"] == "prod-key"
        # New profile added
        assert "staging" in data["profiles"]
        assert data["profiles"]["staging"]["api_key"] == "staging-key"

    def test_init_displays_success_message(self, runner, tmp_path):
        """Test that init shows a success message."""
        config_dir = tmp_path / ".ddogctl"
        config_file = config_dir / "config.json"

        with (
            patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
        ):
            result = runner.invoke(
                config,
                ["init"],
                input="key1\nkey2\nus\nmyprofile\n",
            )

        assert result.exit_code == 0
        assert "myprofile" in result.output


class TestSetProfile:
    """Tests for config set-profile command."""

    def test_set_profile_creates_new_profile(self, runner, tmp_path):
        """Test creating a new profile via set-profile."""
        config_dir = tmp_path / ".ddogctl"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"active_profile": "", "profiles": {}}))

        with (
            patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
        ):
            result = runner.invoke(
                config,
                [
                    "set-profile",
                    "prod",
                    "--api-key",
                    "prod-api",
                    "--app-key",
                    "prod-app",
                    "--site",
                    "us",
                ],
            )

        assert result.exit_code == 0
        data = json.loads(config_file.read_text())
        assert "prod" in data["profiles"]
        assert data["profiles"]["prod"]["api_key"] == "prod-api"
        assert data["profiles"]["prod"]["app_key"] == "prod-app"
        assert data["profiles"]["prod"]["site"] == "datadoghq.com"

    def test_set_profile_updates_existing_profile(self, runner, tmp_path):
        """Test updating an existing profile."""
        config_dir = tmp_path / ".ddogctl"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"

        existing = {
            "active_profile": "prod",
            "profiles": {
                "prod": {
                    "api_key": "old-key",
                    "app_key": "old-app",
                    "site": "datadoghq.com",
                }
            },
        }
        config_file.write_text(json.dumps(existing))

        with (
            patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
        ):
            result = runner.invoke(
                config,
                [
                    "set-profile",
                    "prod",
                    "--api-key",
                    "new-key",
                    "--app-key",
                    "new-app",
                    "--site",
                    "eu",
                ],
            )

        assert result.exit_code == 0
        data = json.loads(config_file.read_text())
        assert data["profiles"]["prod"]["api_key"] == "new-key"
        assert data["profiles"]["prod"]["site"] == "datadoghq.eu"

    def test_set_profile_sets_as_active_if_first(self, runner, tmp_path):
        """Test that first profile is automatically set as active."""
        config_dir = tmp_path / ".ddogctl"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"active_profile": "", "profiles": {}}))

        with (
            patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
        ):
            result = runner.invoke(
                config,
                [
                    "set-profile",
                    "prod",
                    "--api-key",
                    "key",
                    "--app-key",
                    "app",
                    "--site",
                    "us",
                ],
            )

        assert result.exit_code == 0
        data = json.loads(config_file.read_text())
        assert data["active_profile"] == "prod"

    def test_set_profile_creates_config_file_if_missing(self, runner, tmp_path):
        """Test that set-profile creates config file if it doesn't exist."""
        config_dir = tmp_path / ".ddogctl"
        config_file = config_dir / "config.json"

        with (
            patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
        ):
            result = runner.invoke(
                config,
                [
                    "set-profile",
                    "prod",
                    "--api-key",
                    "key",
                    "--app-key",
                    "app",
                    "--site",
                    "us",
                ],
            )

        assert result.exit_code == 0
        assert config_file.exists()

    def test_set_profile_requires_api_key(self, runner, tmp_path):
        """Test that set-profile requires --api-key."""
        config_dir = tmp_path / ".ddogctl"
        config_file = config_dir / "config.json"

        with (
            patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
        ):
            result = runner.invoke(
                config,
                ["set-profile", "prod", "--app-key", "app", "--site", "us"],
            )

        assert result.exit_code != 0

    def test_set_profile_requires_app_key(self, runner, tmp_path):
        """Test that set-profile requires --app-key."""
        config_dir = tmp_path / ".ddogctl"
        config_file = config_dir / "config.json"

        with (
            patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
        ):
            result = runner.invoke(
                config,
                ["set-profile", "prod", "--api-key", "key", "--site", "us"],
            )

        assert result.exit_code != 0


class TestUseProfile:
    """Tests for config use-profile command."""

    def test_use_profile_sets_active_profile(self, runner, tmp_path):
        """Test switching active profile."""
        config_dir = tmp_path / ".ddogctl"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"

        existing = {
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
        config_file.write_text(json.dumps(existing))

        with (
            patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
        ):
            result = runner.invoke(config, ["use-profile", "staging"])

        assert result.exit_code == 0
        data = json.loads(config_file.read_text())
        assert data["active_profile"] == "staging"

    def test_use_profile_nonexistent_profile_fails(self, runner, tmp_path):
        """Test that using a nonexistent profile shows an error."""
        config_dir = tmp_path / ".ddogctl"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"

        existing = {
            "active_profile": "prod",
            "profiles": {
                "prod": {
                    "api_key": "key",
                    "app_key": "app",
                    "site": "datadoghq.com",
                }
            },
        }
        config_file.write_text(json.dumps(existing))

        with (
            patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
        ):
            result = runner.invoke(config, ["use-profile", "nonexistent"])

        assert result.exit_code != 0
        assert "nonexistent" in result.output

    def test_use_profile_no_config_file_fails(self, runner, tmp_path):
        """Test that use-profile fails when config file doesn't exist."""
        config_dir = tmp_path / ".ddogctl"
        config_file = config_dir / "config.json"

        with (
            patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
        ):
            result = runner.invoke(config, ["use-profile", "prod"])

        assert result.exit_code != 0


class TestListProfiles:
    """Tests for config list-profiles command."""

    def test_list_profiles_shows_all_profiles(self, runner, tmp_path):
        """Test listing all profiles."""
        config_dir = tmp_path / ".ddogctl"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"

        existing = {
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
        config_file.write_text(json.dumps(existing))

        with (
            patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
        ):
            result = runner.invoke(config, ["list-profiles"])

        assert result.exit_code == 0
        assert "prod" in result.output
        assert "staging" in result.output
        assert "datadoghq.com" in result.output
        assert "datadoghq.eu" in result.output

    def test_list_profiles_marks_active_profile(self, runner, tmp_path):
        """Test that the active profile is marked."""
        config_dir = tmp_path / ".ddogctl"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"

        existing = {
            "active_profile": "prod",
            "profiles": {
                "prod": {
                    "api_key": "key",
                    "app_key": "app",
                    "site": "datadoghq.com",
                },
                "staging": {
                    "api_key": "key2",
                    "app_key": "app2",
                    "site": "datadoghq.eu",
                },
            },
        }
        config_file.write_text(json.dumps(existing))

        with (
            patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
        ):
            result = runner.invoke(config, ["list-profiles"])

        assert result.exit_code == 0
        # Active profile should be indicated with an asterisk or similar marker
        assert "*" in result.output or "active" in result.output.lower()

    def test_list_profiles_no_config_file(self, runner, tmp_path):
        """Test listing profiles when no config file exists."""
        config_dir = tmp_path / ".ddogctl"
        config_file = config_dir / "config.json"

        with (
            patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
        ):
            result = runner.invoke(config, ["list-profiles"])

        assert result.exit_code == 0
        assert "No profiles" in result.output or "no config" in result.output.lower()

    def test_list_profiles_masks_api_keys(self, runner, tmp_path):
        """Test that API keys are masked in output."""
        config_dir = tmp_path / ".ddogctl"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"

        existing = {
            "active_profile": "prod",
            "profiles": {
                "prod": {
                    "api_key": "abcdef1234567890",
                    "app_key": "xyz9876543210abc",
                    "site": "datadoghq.com",
                }
            },
        }
        config_file.write_text(json.dumps(existing))

        with (
            patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
        ):
            result = runner.invoke(config, ["list-profiles"])

        assert result.exit_code == 0
        # Full keys should NOT appear in output
        assert "abcdef1234567890" not in result.output
        assert "xyz9876543210abc" not in result.output


class TestGetConfig:
    """Tests for config get command."""

    def test_get_site_value(self, runner, tmp_path):
        """Test getting the site value from active profile."""
        config_dir = tmp_path / ".ddogctl"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"

        existing = {
            "active_profile": "prod",
            "profiles": {
                "prod": {
                    "api_key": "key",
                    "app_key": "app",
                    "site": "datadoghq.com",
                }
            },
        }
        config_file.write_text(json.dumps(existing))

        with (
            patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
        ):
            result = runner.invoke(config, ["get", "site"])

        assert result.exit_code == 0
        assert "datadoghq.com" in result.output

    def test_get_api_key_masked(self, runner, tmp_path):
        """Test that getting api_key shows a masked value."""
        config_dir = tmp_path / ".ddogctl"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"

        existing = {
            "active_profile": "prod",
            "profiles": {
                "prod": {
                    "api_key": "abcdef1234567890",
                    "app_key": "app",
                    "site": "datadoghq.com",
                }
            },
        }
        config_file.write_text(json.dumps(existing))

        with (
            patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
        ):
            result = runner.invoke(config, ["get", "api_key"])

        assert result.exit_code == 0
        # Full key should NOT appear
        assert "abcdef1234567890" not in result.output
        # But last 4 chars should be visible
        assert "7890" in result.output

    def test_get_active_profile(self, runner, tmp_path):
        """Test getting the active_profile value."""
        config_dir = tmp_path / ".ddogctl"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"

        existing = {
            "active_profile": "prod",
            "profiles": {
                "prod": {
                    "api_key": "key",
                    "app_key": "app",
                    "site": "datadoghq.com",
                }
            },
        }
        config_file.write_text(json.dumps(existing))

        with (
            patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
        ):
            result = runner.invoke(config, ["get", "active_profile"])

        assert result.exit_code == 0
        assert "prod" in result.output

    def test_get_invalid_key(self, runner, tmp_path):
        """Test getting an invalid key shows an error."""
        config_dir = tmp_path / ".ddogctl"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"

        existing = {
            "active_profile": "prod",
            "profiles": {
                "prod": {
                    "api_key": "key",
                    "app_key": "app",
                    "site": "datadoghq.com",
                }
            },
        }
        config_file.write_text(json.dumps(existing))

        with (
            patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
        ):
            result = runner.invoke(config, ["get", "nonexistent_key"])

        assert result.exit_code != 0

    def test_get_no_config_file(self, runner, tmp_path):
        """Test get when no config file exists."""
        config_dir = tmp_path / ".ddogctl"
        config_file = config_dir / "config.json"

        with (
            patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
        ):
            result = runner.invoke(config, ["get", "site"])

        assert result.exit_code != 0


class TestRegionExpansion:
    """Tests for region shortcut expansion in config commands."""

    def test_set_profile_expands_all_regions(self, runner, tmp_path):
        """Test that all region shortcuts are expanded correctly."""
        regions = {
            "us": "datadoghq.com",
            "eu": "datadoghq.eu",
            "us3": "us3.datadoghq.com",
            "us5": "us5.datadoghq.com",
            "ap1": "ap1.datadoghq.com",
            "gov": "ddog-gov.com",
        }

        for shortcut, expected in regions.items():
            config_dir = tmp_path / f".ddogctl-{shortcut}"
            config_file = config_dir / "config.json"

            with (
                patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
                patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
            ):
                result = runner.invoke(
                    config,
                    [
                        "set-profile",
                        f"test-{shortcut}",
                        "--api-key",
                        "key",
                        "--app-key",
                        "app",
                        "--site",
                        shortcut,
                    ],
                )

            assert result.exit_code == 0, f"Failed for region {shortcut}: {result.output}"
            data = json.loads(config_file.read_text())
            assert (
                data["profiles"][f"test-{shortcut}"]["site"] == expected
            ), f"Expected {expected} for {shortcut}"

    def test_set_profile_full_domain_not_expanded(self, runner, tmp_path):
        """Test that full domain names are not modified."""
        config_dir = tmp_path / ".ddogctl"
        config_file = config_dir / "config.json"

        with (
            patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
        ):
            result = runner.invoke(
                config,
                [
                    "set-profile",
                    "custom",
                    "--api-key",
                    "key",
                    "--app-key",
                    "app",
                    "--site",
                    "custom.datadoghq.com",
                ],
            )

        assert result.exit_code == 0
        data = json.loads(config_file.read_text())
        assert data["profiles"]["custom"]["site"] == "custom.datadoghq.com"


class TestPatProfiles:
    """Tests for PAT support in config commands."""

    def _paths(self, tmp_path):
        config_dir = tmp_path / ".ddogctl"
        return config_dir, config_dir / "config.json"

    def test_init_with_pat(self, runner, tmp_path):
        config_dir, config_file = self._paths(tmp_path)
        with (
            patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
        ):
            result = runner.invoke(
                config, ["init", "--auth", "pat"], input="ddpat_abc_secret\nus\nwork\n"
            )

        assert result.exit_code == 0, result.output
        profile = json.loads(config_file.read_text())["profiles"]["work"]
        assert profile == {"pat": "ddpat_abc_secret", "site": "datadoghq.com"}

    def test_set_profile_with_pat(self, runner, tmp_path):
        config_dir, config_file = self._paths(tmp_path)
        with (
            patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
        ):
            result = runner.invoke(config, ["set-profile", "work", "--pat", "ddpat_abc_secret"])

        assert result.exit_code == 0, result.output
        profile = json.loads(config_file.read_text())["profiles"]["work"]
        assert profile["pat"] == "ddpat_abc_secret"
        assert "api_key" not in profile

    def test_set_profile_with_pat_and_api_key(self, runner, tmp_path):
        config_dir, config_file = self._paths(tmp_path)
        with (
            patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
        ):
            result = runner.invoke(
                config, ["set-profile", "work", "--pat", "ddpat_abc_secret", "--api-key", "api"]
            )

        assert result.exit_code == 0, result.output
        profile = json.loads(config_file.read_text())["profiles"]["work"]
        assert profile["api_key"] == "api"

    def test_set_profile_without_credentials_fails(self, runner, tmp_path):
        config_dir, config_file = self._paths(tmp_path)
        with (
            patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)),
            patch("ddogctl.commands.config.get_config_dir", return_value=str(config_dir)),
        ):
            result = runner.invoke(config, ["set-profile", "work"])

        assert result.exit_code != 0
        assert not config_file.exists()

    def test_get_pat_masked(self, runner, tmp_path):
        config_dir, config_file = self._paths(tmp_path)
        config_dir.mkdir()
        config_file.write_text(
            json.dumps({"active_profile": "work", "profiles": {"work": {"pat": "ddpat_x_wxyz"}}})
        )
        with patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)):
            result = runner.invoke(config, ["get", "pat"])

        assert result.exit_code == 0
        assert "****wxyz" in result.output
        assert "ddpat_x" not in result.output

    def test_list_profiles_masks_pat(self, runner, tmp_path):
        config_dir, config_file = self._paths(tmp_path)
        config_dir.mkdir()
        config_file.write_text(
            json.dumps({"active_profile": "work", "profiles": {"work": {"pat": "ddpat_x_wxyz"}}})
        )
        with patch("ddogctl.commands.config.get_config_path", return_value=str(config_file)):
            result = runner.invoke(config, ["list-profiles"])

        assert result.exit_code == 0
        assert "****wxyz" in result.output
        assert "ddpat_x" not in result.output
