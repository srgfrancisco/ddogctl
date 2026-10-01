"""Tests for configuration management."""

import pytest
from unittest.mock import patch
from pydantic import ValidationError
from ddogctl.config import DatadogConfig, load_config


class TestDatadogConfig:
    """Tests for DatadogConfig class."""

    def test_config_with_all_required_fields(self):
        """Test configuration with all required fields."""
        config = DatadogConfig(DD_API_KEY="test_api_key", DD_APP_KEY="test_app_key")

        assert config.api_key == "test_api_key"
        assert config.app_key == "test_app_key"
        assert config.site == "datadoghq.com"  # default value

    def test_config_with_custom_site(self):
        """Test configuration with custom site."""
        config = DatadogConfig(
            DD_API_KEY="test_api_key", DD_APP_KEY="test_app_key", DD_SITE="custom.datadoghq.com"
        )

        assert config.site == "custom.datadoghq.com"

    @patch.dict("os.environ", {}, clear=True)
    def test_config_missing_api_key(self):
        """Test that missing API key raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            DatadogConfig(_env_file=None, DD_APP_KEY="test_app_key")

        assert "DD_API_KEY" in str(exc_info.value)

    @patch.dict("os.environ", {}, clear=True)
    def test_config_missing_app_key(self):
        """Test that missing APP key raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            DatadogConfig(_env_file=None, DD_API_KEY="test_api_key")

        assert "DD_APP_KEY" in str(exc_info.value)

    def test_config_default_client_settings(self):
        """Test default client settings."""
        config = DatadogConfig(DD_API_KEY="test_api_key", DD_APP_KEY="test_app_key")

        assert config.timeout == 30
        assert config.retry_count == 3
        assert config.retry_delay == 1.0

    def test_config_custom_client_settings(self):
        """Test custom client settings."""
        config = DatadogConfig(
            DD_API_KEY="test_api_key",
            DD_APP_KEY="test_app_key",
            timeout=60,
            retry_count=5,
            retry_delay=2.5,
        )

        assert config.timeout == 60
        assert config.retry_count == 5
        assert config.retry_delay == 2.5

    def test_config_default_display_options(self):
        """Test default display options."""
        config = DatadogConfig(DD_API_KEY="test_api_key", DD_APP_KEY="test_app_key")

        assert config.default_format == "table"
        assert config.color_output is True

    def test_config_custom_display_options(self):
        """Test custom display options."""
        config = DatadogConfig(
            DD_API_KEY="test_api_key",
            DD_APP_KEY="test_app_key",
            default_format="json",
            color_output=False,
        )

        assert config.default_format == "json"
        assert config.color_output is False

    def test_config_default_time_range(self):
        """Test default time range."""
        config = DatadogConfig(DD_API_KEY="test_api_key", DD_APP_KEY="test_app_key")

        assert config.default_time_range == "1h"


class TestRegionShortcuts:
    """Tests for region shortcut expansion."""

    @pytest.mark.parametrize(
        "shortcut,expected",
        [
            ("us", "datadoghq.com"),
            ("eu", "datadoghq.eu"),
            ("us3", "us3.datadoghq.com"),
            ("us5", "us5.datadoghq.com"),
            ("ap1", "ap1.datadoghq.com"),
            ("gov", "ddog-gov.com"),
        ],
    )
    def test_region_shortcuts(self, shortcut, expected):
        """Test that region shortcuts are correctly expanded."""
        config = DatadogConfig(
            DD_API_KEY="test_api_key", DD_APP_KEY="test_app_key", DD_SITE=shortcut
        )

        assert config.site == expected

    @pytest.mark.parametrize(
        "shortcut,expected",
        [
            ("US", "datadoghq.com"),
            ("EU", "datadoghq.eu"),
            ("Us3", "us3.datadoghq.com"),
        ],
    )
    def test_region_shortcuts_case_insensitive(self, shortcut, expected):
        """Test that region shortcuts are case-insensitive."""
        config = DatadogConfig(
            DD_API_KEY="test_api_key", DD_APP_KEY="test_app_key", DD_SITE=shortcut
        )

        assert config.site == expected

    def test_custom_domain_not_expanded(self):
        """Test that custom domains are not expanded."""
        custom_domain = "custom.example.com"
        config = DatadogConfig(
            DD_API_KEY="test_api_key", DD_APP_KEY="test_app_key", DD_SITE=custom_domain
        )

        assert config.site == custom_domain

    def test_partial_match_not_expanded(self):
        """Test that partial matches are not expanded."""
        partial = "us-custom"
        config = DatadogConfig(
            DD_API_KEY="test_api_key", DD_APP_KEY="test_app_key", DD_SITE=partial
        )

        assert config.site == partial


class TestLoadConfig:
    """Tests for load_config function."""

    @patch.dict(
        "os.environ", {"DD_API_KEY": "env_api_key", "DD_APP_KEY": "env_app_key", "DD_SITE": "eu"}
    )
    def test_load_config_from_environment(self):
        """Test loading configuration from environment variables."""
        config = load_config()

        assert config.api_key == "env_api_key"
        assert config.app_key == "env_app_key"
        assert config.site == "datadoghq.eu"  # 'eu' should be expanded

    @patch("ddogctl.config.console")
    @patch("ddogctl.config.DatadogConfig")
    def test_load_config_missing_credentials_exits(self, mock_config_class, mock_console):
        """Test that load_config exits when credentials are missing."""
        # Make DatadogConfig raise ValidationError
        from pydantic import ValidationError as PydanticValidationError

        mock_config_class.side_effect = PydanticValidationError.from_exception_data(
            "DatadogConfig",
            [{"type": "missing", "loc": ("DD_APP_KEY",), "msg": "Field required", "input": {}}],
        )

        with pytest.raises(SystemExit) as exc_info:
            load_config()

        assert exc_info.value.code == 1

        # Verify error messages were printed
        mock_console.print.assert_called()
        calls = [str(call) for call in mock_console.print.call_args_list]
        assert any("Configuration error" in str(call) for call in calls)
        assert any("DD_API_KEY" in str(call) for call in calls)
        assert any("DD_APP_KEY" in str(call) for call in calls)

    @patch.dict("os.environ", {"DD_API_KEY": "env_api_key", "DD_APP_KEY": "env_app_key"})
    def test_load_config_with_defaults(self):
        """Test that load_config applies default values correctly."""
        config = load_config()

        assert config.site == "datadoghq.com"
        assert config.timeout == 30
        assert config.default_format == "table"
        assert config.color_output is True
        assert config.default_time_range == "1h"

    @patch.dict(
        "os.environ",
        {
            "DD_API_KEY": "env_api_key",
            "DD_APP_KEY": "env_app_key",
            "DD_SITE": "datadoghq.eu",
            "timeout": "60",
            "default_format": "json",
        },
    )
    def test_load_config_with_custom_values(self):
        """Test loading configuration with custom values."""
        config = load_config()

        assert config.api_key == "env_api_key"
        assert config.app_key == "env_app_key"
        assert config.site == "datadoghq.eu"


class TestConfigExtraFields:
    """Tests for handling extra fields in configuration."""

    def test_extra_fields_ignored(self):
        """Test that extra fields are ignored per model_config."""
        # This should not raise an error due to extra='ignore'
        config = DatadogConfig(
            DD_API_KEY="test_api_key", DD_APP_KEY="test_app_key", unknown_field="should_be_ignored"
        )

        assert config.api_key == "test_api_key"
        assert config.app_key == "test_app_key"
        assert not hasattr(config, "unknown_field")


class TestPersonalAccessToken:
    """Tests for Personal Access Token (PAT) auth."""

    @patch.dict("os.environ", {}, clear=True)
    def test_pat_alone_is_valid(self):
        config = DatadogConfig(_env_file=None, DD_PAT="ddpat_abc_secret")

        assert config.pat == "ddpat_abc_secret"
        assert config.api_key is None
        assert config.auth_mode == "pat"

    @patch.dict("os.environ", {}, clear=True)
    def test_pat_in_app_key_is_detected(self):
        config = DatadogConfig(_env_file=None, DD_APP_KEY="ddpat_abc_secret")

        assert config.pat == "ddpat_abc_secret"
        assert config.app_key is None
        assert config.auth_mode == "pat"

    @patch.dict("os.environ", {}, clear=True)
    def test_pat_with_api_key_keeps_api_key(self):
        config = DatadogConfig(_env_file=None, DD_PAT="ddpat_abc_secret", DD_API_KEY="api")

        assert config.api_key == "api"
        assert config.auth_mode == "pat"

    @patch.dict("os.environ", {}, clear=True)
    def test_keys_mode(self):
        config = DatadogConfig(_env_file=None, DD_API_KEY="api", DD_APP_KEY="app")

        assert config.auth_mode == "keys"

    @patch.dict("os.environ", {}, clear=True)
    def test_no_credentials_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            DatadogConfig(_env_file=None)

        assert "DD_PAT" in str(exc_info.value)

    @patch.dict("os.environ", {"DD_PAT": "ddpat_env_secret"}, clear=True)
    def test_load_config_from_pat_env(self):
        config = load_config()

        assert config.pat == "ddpat_env_secret"
