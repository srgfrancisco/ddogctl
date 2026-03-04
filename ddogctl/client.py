"""Unified Datadog API client wrapper."""

import os
from datadog_api_client import ApiClient, Configuration
from datadog_api_client.v1.api import (
    monitors_api,
    metrics_api,
    events_api,
    hosts_api,
    tags_api,
    service_checks_api,
    downtimes_api,
    service_level_objectives_api,
    dashboards_api,
    usage_metering_api,
    synthetics_api,
    notebooks_api,
)
from datadog_api_client.v2.api import (
    logs_api,
    spans_api,
    service_definition_api,
    incidents_api,
    users_api,
    rum_api,
    ci_visibility_pipelines_api,
    ci_visibility_tests_api,
)
from ddogctl.config import DatadogConfig


class _Namespace:
    """Simple namespace for attribute access on API response data."""

    def __init__(self, data):
        for key, value in data.items():
            setattr(self, key, value)


class _Response:
    """Minimal response wrapper with a .data attribute."""

    def __init__(self, data):
        self.data = data


class DBMClient:
    """Lightweight wrapper for DBM API endpoints using direct HTTP calls."""

    def __init__(self, api_client):
        self._api_client = api_client

    def _call(self, method, path, **query_params):
        """Make a direct REST call through the SDK's ApiClient."""
        params = {k: v for k, v in query_params.items() if v is not None}
        response = self._api_client.call_api(
            method, path, query_params=params, header_params={"Accept": "application/json"}
        )
        import json

        body = json.loads(response.response.data) if response.response.data else {}
        data_raw = body.get("data", [])
        if isinstance(data_raw, list):
            return _Response(
                [_Namespace(item) if isinstance(item, dict) else item for item in data_raw]
            )
        elif isinstance(data_raw, dict):
            return _Response(_Namespace(data_raw))
        return _Response(data_raw)

    def list_hosts(self, **kwargs):
        return self._call("GET", "/api/v2/dbm/hosts", **kwargs)

    def list_queries(self, **kwargs):
        return self._call("GET", "/api/v2/dbm/activity", **kwargs)

    def get_query_plan(self, query_id, **kwargs):
        return self._call("GET", f"/api/v2/dbm/query/{query_id}/plan", **kwargs)

    def list_query_samples(self, query_id, **kwargs):
        return self._call("GET", f"/api/v2/dbm/query/{query_id}/samples", **kwargs)


class DatadogClient:
    """Unified Datadog API client."""

    def __init__(self, config: DatadogConfig):
        configuration = Configuration()
        configuration.api_key["apiKeyAuth"] = config.api_key
        configuration.api_key["appKeyAuth"] = config.app_key
        configuration.server_variables["site"] = config.site

        proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
        if proxy:
            configuration.proxy = proxy

        self.api_client = ApiClient(configuration)

        # V1 APIs
        self.monitors = monitors_api.MonitorsApi(self.api_client)
        self.metrics = metrics_api.MetricsApi(self.api_client)
        self.events = events_api.EventsApi(self.api_client)
        self.hosts = hosts_api.HostsApi(self.api_client)
        self.tags = tags_api.TagsApi(self.api_client)
        self.service_checks = service_checks_api.ServiceChecksApi(self.api_client)
        self.downtimes = downtimes_api.DowntimesApi(self.api_client)
        self.slos = service_level_objectives_api.ServiceLevelObjectivesApi(self.api_client)
        self.dashboards = dashboards_api.DashboardsApi(self.api_client)
        self.usage = usage_metering_api.UsageMeteringApi(self.api_client)
        self.synthetics = synthetics_api.SyntheticsApi(self.api_client)
        self.notebooks = notebooks_api.NotebooksApi(self.api_client)

        # V2 APIs
        self.logs = logs_api.LogsApi(self.api_client)
        self.spans = spans_api.SpansApi(self.api_client)
        self.service_definitions = service_definition_api.ServiceDefinitionApi(self.api_client)
        self.incidents = incidents_api.IncidentsApi(self.api_client)
        self.users = users_api.UsersApi(self.api_client)
        self.rum = rum_api.RUMApi(self.api_client)
        self.ci_pipelines = ci_visibility_pipelines_api.CIVisibilityPipelinesApi(self.api_client)
        self.ci_tests = ci_visibility_tests_api.CIVisibilityTestsApi(self.api_client)

        # DBM (direct HTTP — no dedicated SDK module)
        self.dbm = DBMClient(self.api_client)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.api_client.close()


def get_datadog_client() -> DatadogClient:
    """Get configured Datadog client.

    Reads the --profile option from Click context if available.
    """
    import click
    from ddogctl.config import load_config

    profile = None
    try:
        ctx = click.get_current_context(silent=True)
        if ctx and ctx.obj:
            profile = ctx.obj.get("profile")
    except RuntimeError:
        pass

    config = load_config(profile=profile)
    return DatadogClient(config)
