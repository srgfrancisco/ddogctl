"""Tests for Datadog API client wrapper."""

import pytest
from unittest.mock import Mock, patch
from ddogctl.client import DatadogClient, get_datadog_client
from ddogctl.config import DatadogConfig


@pytest.fixture
def mock_config():
    """Create a mock DatadogConfig."""
    return DatadogConfig(
        DD_API_KEY="test_api_key", DD_APP_KEY="test_app_key", DD_SITE="datadoghq.com"
    )


@pytest.fixture
def mock_api_client():
    """Create a mock ApiClient."""
    with patch("ddogctl.client.ApiClient") as mock_client_class:
        mock_instance = Mock()
        mock_client_class.return_value = mock_instance
        yield mock_client_class, mock_instance


@pytest.fixture
def mock_configuration():
    """Create a mock Configuration."""
    with patch("ddogctl.client.Configuration") as mock_config_class:
        mock_instance = Mock()
        mock_instance.api_key = {}
        mock_instance.server_variables = {}
        mock_config_class.return_value = mock_instance
        yield mock_config_class, mock_instance


class TestDatadogClient:
    """Tests for DatadogClient class."""

    def test_client_initialization(self, mock_config, mock_configuration, mock_api_client):
        """Test that DatadogClient initializes correctly."""
        mock_config_class, mock_config_instance = mock_configuration
        mock_client_class, mock_client_instance = mock_api_client

        client = DatadogClient(mock_config)

        # Verify Configuration was created
        mock_config_class.assert_called_once()

        # Verify API keys were set
        assert mock_config_instance.api_key["apiKeyAuth"] == "test_api_key"
        assert mock_config_instance.api_key["appKeyAuth"] == "test_app_key"
        assert mock_config_instance.server_variables["site"] == "datadoghq.com"

        # Verify ApiClient was created with configuration
        mock_client_class.assert_called_once_with(mock_config_instance)

        # Verify api_client attribute is set
        assert client.api_client == mock_client_instance

    @patch("ddogctl.client.monitors_api.MonitorsApi")
    @patch("ddogctl.client.metrics_api.MetricsApi")
    @patch("ddogctl.client.events_api.EventsApi")
    @patch("ddogctl.client.hosts_api.HostsApi")
    @patch("ddogctl.client.tags_api.TagsApi")
    @patch("ddogctl.client.logs_api.LogsApi")
    def test_api_endpoints_initialized(
        self,
        mock_logs_api,
        mock_tags_api,
        mock_hosts_api,
        mock_events_api,
        mock_metrics_api,
        mock_monitors_api,
        mock_config,
        mock_configuration,
        mock_api_client,
    ):
        """Test that all API endpoints are initialized."""
        _, mock_client_instance = mock_api_client

        client = DatadogClient(mock_config)

        # Verify V1 APIs were initialized
        mock_monitors_api.assert_called_once_with(mock_client_instance)
        mock_metrics_api.assert_called_once_with(mock_client_instance)
        mock_events_api.assert_called_once_with(mock_client_instance)
        mock_hosts_api.assert_called_once_with(mock_client_instance)
        mock_tags_api.assert_called_once_with(mock_client_instance)

        # Verify V2 APIs were initialized
        mock_logs_api.assert_called_once_with(mock_client_instance)

        # Verify API attributes are set
        assert hasattr(client, "monitors")
        assert hasattr(client, "metrics")
        assert hasattr(client, "events")
        assert hasattr(client, "hosts")
        assert hasattr(client, "tags")
        assert hasattr(client, "logs")

    def test_client_with_custom_site(self, mock_configuration, mock_api_client):
        """Test client initialization with custom site."""
        _, mock_config_instance = mock_configuration

        custom_config = DatadogConfig(
            DD_API_KEY="test_api_key", DD_APP_KEY="test_app_key", DD_SITE="datadoghq.eu"
        )

        DatadogClient(custom_config)

        # Verify custom site was set
        assert mock_config_instance.server_variables["site"] == "datadoghq.eu"

    def test_client_with_region_shortcut(self, mock_configuration, mock_api_client):
        """Test client initialization with region shortcut."""
        _, mock_config_instance = mock_configuration

        # Config with region shortcut (will be expanded by DatadogConfig)
        custom_config = DatadogConfig(
            DD_API_KEY="test_api_key", DD_APP_KEY="test_app_key", DD_SITE="us3"
        )

        DatadogClient(custom_config)

        # Verify region shortcut was expanded
        assert mock_config_instance.server_variables["site"] == "us3.datadoghq.com"


class TestContextManager:
    """Tests for context manager support."""

    def test_context_manager_enter(self, mock_config, mock_configuration, mock_api_client):
        """Test that __enter__ returns the client instance."""
        client = DatadogClient(mock_config)

        with client as ctx_client:
            assert ctx_client is client

    def test_context_manager_exit(self, mock_config, mock_configuration, mock_api_client):
        """Test that __exit__ closes the API client."""
        _, mock_client_instance = mock_api_client
        mock_client_instance.close = Mock()

        client = DatadogClient(mock_config)

        with client:
            pass

        # Verify close was called
        mock_client_instance.close.assert_called_once()

    def test_context_manager_exit_with_exception(
        self, mock_config, mock_configuration, mock_api_client
    ):
        """Test that __exit__ closes the API client even when exception occurs."""
        _, mock_client_instance = mock_api_client
        mock_client_instance.close = Mock()

        client = DatadogClient(mock_config)

        try:
            with client:
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Verify close was still called
        mock_client_instance.close.assert_called_once()


class TestGetDatadogClient:
    """Tests for get_datadog_client helper function."""

    @patch("ddogctl.config.load_config")
    @patch("ddogctl.client.DatadogClient")
    def test_get_datadog_client_loads_config(self, mock_client_class, mock_load_config):
        """Test that get_datadog_client loads configuration."""
        mock_config = Mock()
        mock_load_config.return_value = mock_config
        mock_client_instance = Mock()
        mock_client_class.return_value = mock_client_instance

        result = get_datadog_client()

        # Verify load_config was called
        mock_load_config.assert_called_once()

        # Verify DatadogClient was created with the loaded config
        mock_client_class.assert_called_once_with(mock_config)

        # Verify the client instance is returned
        assert result == mock_client_instance

    @patch("ddogctl.config.load_config")
    @patch("ddogctl.client.DatadogClient")
    def test_get_datadog_client_returns_configured_client(
        self, mock_client_class, mock_load_config
    ):
        """Test that get_datadog_client returns a properly configured client."""
        # Create a real config for testing
        test_config = DatadogConfig(
            DD_API_KEY="test_api_key", DD_APP_KEY="test_app_key", DD_SITE="datadoghq.com"
        )
        mock_load_config.return_value = test_config

        mock_client_instance = Mock()
        mock_client_class.return_value = mock_client_instance

        get_datadog_client()

        # Verify client was created with the correct config
        call_args = mock_client_class.call_args
        assert call_args is not None
        config_arg = call_args[0][0]
        assert config_arg.api_key == "test_api_key"
        assert config_arg.app_key == "test_app_key"
        assert config_arg.site == "datadoghq.com"


class TestClientAPIAccess:
    """Tests for accessing API endpoints through the client."""

    @patch("ddogctl.client.monitors_api.MonitorsApi")
    def test_monitors_api_accessible(
        self, mock_monitors_api, mock_config, mock_configuration, mock_api_client
    ):
        """Test that monitors API is accessible through client."""
        mock_monitors_instance = Mock()
        mock_monitors_api.return_value = mock_monitors_instance

        client = DatadogClient(mock_config)

        assert client.monitors == mock_monitors_instance

    @patch("ddogctl.client.metrics_api.MetricsApi")
    def test_metrics_api_accessible(
        self, mock_metrics_api, mock_config, mock_configuration, mock_api_client
    ):
        """Test that metrics API is accessible through client."""
        mock_metrics_instance = Mock()
        mock_metrics_api.return_value = mock_metrics_instance

        client = DatadogClient(mock_config)

        assert client.metrics == mock_metrics_instance

    @patch("ddogctl.client.events_api.EventsApi")
    def test_events_api_accessible(
        self, mock_events_api, mock_config, mock_configuration, mock_api_client
    ):
        """Test that events API is accessible through client."""
        mock_events_instance = Mock()
        mock_events_api.return_value = mock_events_instance

        client = DatadogClient(mock_config)

        assert client.events == mock_events_instance

    @patch("ddogctl.client.hosts_api.HostsApi")
    def test_hosts_api_accessible(
        self, mock_hosts_api, mock_config, mock_configuration, mock_api_client
    ):
        """Test that hosts API is accessible through client."""
        mock_hosts_instance = Mock()
        mock_hosts_api.return_value = mock_hosts_instance

        client = DatadogClient(mock_config)

        assert client.hosts == mock_hosts_instance

    @patch("ddogctl.client.tags_api.TagsApi")
    def test_tags_api_accessible(
        self, mock_tags_api, mock_config, mock_configuration, mock_api_client
    ):
        """Test that tags API is accessible through client."""
        mock_tags_instance = Mock()
        mock_tags_api.return_value = mock_tags_instance

        client = DatadogClient(mock_config)

        assert client.tags == mock_tags_instance

    @patch("ddogctl.client.logs_api.LogsApi")
    def test_logs_api_accessible(
        self, mock_logs_api, mock_config, mock_configuration, mock_api_client
    ):
        """Test that logs API (V2) is accessible through client."""
        mock_logs_instance = Mock()
        mock_logs_api.return_value = mock_logs_instance

        client = DatadogClient(mock_config)

        assert client.logs == mock_logs_instance


class TestClientConfiguration:
    """Tests for client configuration handling."""

    def test_client_uses_config_api_key(self, mock_configuration, mock_api_client):
        """Test that client uses the API key from config."""
        _, mock_config_instance = mock_configuration

        config = DatadogConfig(
            DD_API_KEY="specific_api_key", DD_APP_KEY="test_app_key", DD_SITE="datadoghq.com"
        )

        DatadogClient(config)

        assert mock_config_instance.api_key["apiKeyAuth"] == "specific_api_key"

    def test_client_uses_config_app_key(self, mock_configuration, mock_api_client):
        """Test that client uses the APP key from config."""
        _, mock_config_instance = mock_configuration

        config = DatadogConfig(
            DD_API_KEY="test_api_key", DD_APP_KEY="specific_app_key", DD_SITE="datadoghq.com"
        )

        DatadogClient(config)

        assert mock_config_instance.api_key["appKeyAuth"] == "specific_app_key"

    def test_client_uses_config_site(self, mock_configuration, mock_api_client):
        """Test that client uses the site from config."""
        _, mock_config_instance = mock_configuration

        config = DatadogConfig(
            DD_API_KEY="test_api_key", DD_APP_KEY="test_app_key", DD_SITE="custom.datadoghq.com"
        )

        DatadogClient(config)

        assert mock_config_instance.server_variables["site"] == "custom.datadoghq.com"

    @pytest.mark.parametrize(
        "site_input,expected_site",
        [
            ("us", "datadoghq.com"),
            ("eu", "datadoghq.eu"),
            ("us3", "us3.datadoghq.com"),
            ("us5", "us5.datadoghq.com"),
            ("ap1", "ap1.datadoghq.com"),
            ("gov", "ddog-gov.com"),
        ],
    )
    def test_client_handles_region_shortcuts(
        self, site_input, expected_site, mock_configuration, mock_api_client
    ):
        """Test that client correctly handles region shortcuts via config."""
        _, mock_config_instance = mock_configuration

        config = DatadogConfig(
            DD_API_KEY="test_api_key", DD_APP_KEY="test_app_key", DD_SITE=site_input
        )

        DatadogClient(config)

        assert mock_config_instance.server_variables["site"] == expected_site


class TestDBMClient:
    """Tests for DBMClient direct HTTP call wrapper."""

    def test_call_api_arg_order_resource_path_before_method(self):
        """Verify call_api receives (resource_path, method), not (method, resource_path).

        Regression test for #46: reversed arg order caused the HTTP method to be
        concatenated to the hostname (e.g. api.datadoghq.comget).
        """
        import json as json_mod

        mock_api_client = Mock()
        mock_api_client.call_api.return_value = Mock(
            response=Mock(data=json_mod.dumps({"data": []}).encode())
        )

        from ddogctl.client import DBMClient

        client = DBMClient(mock_api_client)
        client.list_hosts()

        call_kwargs = mock_api_client.call_api.call_args.kwargs
        assert call_kwargs["resource_path"] == "/api/v2/dbm/hosts"
        assert call_kwargs["method"] == "GET"
