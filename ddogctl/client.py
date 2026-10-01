"""Unified Datadog API client wrapper."""

import json
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
from datadog_api_client.v2.api import metrics_api as metrics_api_v2
from ddogctl.config import DatadogConfig


class DBMClient:
    """Database Monitoring data access.

    Datadog has no dedicated DBM API. Per Datadog's "Building applications with the
    Database Monitoring API" guide, query metrics come from the v2 scalar metrics API,
    and query samples / explain plans from the logs-analytics list endpoint on
    app.<site>, which needs an unscoped application key.
    """

    def __init__(self, api_client, site):
        self._api_client = api_client
        self._metrics = metrics_api_v2.MetricsApi(api_client)
        self.app_url = f"https://app.{site}"

    def query_scalar(self, body):
        return self._metrics.query_scalar_data(body)

    def search_events(self, query, from_ms, to_ms, limit):
        """Search the databasequery index (dbm_type:activity samples, dbm_type:plan plans)."""
        # call_api does not apply auth settings, so add the auth headers here.
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        for setting in self._api_client.configuration.auth_settings().values():
            headers[setting["key"]] = setting["value"]
        body = {
            "list": {
                "indexes": ["databasequery"],
                "limit": limit,
                "search": {"query": query},
                "sorts": [{"time": {"order": "desc"}}],
                "time": {"from": from_ms, "to": to_ms},
            }
        }
        # Keyword args: positional ones once glued the method onto the host (#46, #50).
        response = self._api_client.call_api(
            resource_path="/api/v1/logs-analytics/list",
            method="POST",
            query_params=[("type", "databasequery")],
            header_params=headers,
            body=body,
            host=self.app_url,
            preload_content=False,
        )
        payload = json.loads(response.data) if response.data else {}
        return payload.get("result", {}).get("events", [])


class DatadogClient:
    """Unified Datadog API client."""

    def __init__(self, config: DatadogConfig):
        configuration = Configuration()
        # A PAT goes in DD-APPLICATION-KEY; DD-API-KEY is then optional and only
        # sent when present (intake endpoints like event post still need it).
        if config.api_key:
            configuration.api_key["apiKeyAuth"] = config.api_key
        configuration.api_key["appKeyAuth"] = config.pat or config.app_key
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

        # DBM (no dedicated SDK module: scalar metrics + logs-analytics)
        self.dbm = DBMClient(self.api_client, config.site)

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
