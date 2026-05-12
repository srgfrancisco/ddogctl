"""Investigation workflow commands."""

import click
import json
from rich.console import Console
from rich.table import Table
from ddogctl.client import get_datadog_client
from ddogctl.utils.error import handle_api_error
from ddogctl.utils.time import parse_time_range, to_utc_iso
from ddogctl.utils.spans import aggregate_spans

console = Console()


@click.group()
def investigate():
    """Investigation workflows for troubleshooting."""
    pass


@investigate.command(name="latency")
@click.argument("service")
@click.option("--from", "from_time", default="1h", help="Start time (e.g., 1h, 24h, 7d)")
@click.option("--to", "to_time", default="now", help="End time")
@click.option("--threshold", default=500, type=int, help="Latency threshold (ms)")
@click.option("--format", "fmt", type=click.Choice(["json", "table"]), default="table")
@handle_api_error
def investigate_latency(service, from_time, to_time, threshold, fmt):
    """Investigate high latency issues for a service."""
    client = get_datadog_client()
    from_ts, to_ts = parse_time_range(from_time, to_time)
    from_str = to_utc_iso(from_ts)
    to_str = to_utc_iso(to_ts)

    threshold_ns = threshold * 1_000_000  # convert ms to ns

    with console.status(f"[cyan]Investigating latency for {service}...[/cyan]"):
        # Step 1: Get p99 latency for spans above threshold
        p99_response = aggregate_spans(
            client,
            {
                "query": f"service:{service} @duration:>{threshold_ns}",
                "from": from_str,
                "to": to_str,
            },
            [{"aggregation": "pc99", "metric": "@duration"}],
        )

        # Step 2: Get top slow endpoints
        endpoints_response = aggregate_spans(
            client,
            {"query": f"service:{service}", "from": from_str, "to": to_str},
            [{"aggregation": "pc99", "metric": "@duration"}],
            [{"facet": "resource_name"}],
        )

        # Step 3: Check error logs
        logs_response = client.logs.list_logs(
            body={
                "filter": {
                    "query": f"service:{service} status:error",
                    "from": from_str,
                    "to": to_str,
                },
                "page": {"limit": 100},
            }
        )

    # Extract results
    p99_buckets = p99_response.data.buckets if p99_response.data else []
    p99_ns = p99_buckets[0].computes["c0"] if p99_buckets else 0
    p99_ms = p99_ns / 1_000_000

    endpoint_buckets = endpoints_response.data.buckets if endpoints_response.data else []
    slow_endpoints = []
    for bucket in endpoint_buckets:
        value_ns = bucket.computes["c0"]
        slow_endpoints.append(
            {
                "resource_name": bucket.by.get("resource_name", "N/A"),
                "p99_ms": round(value_ns / 1_000_000, 2),
            }
        )

    error_logs = logs_response.data if logs_response.data else []
    error_count = len(error_logs)

    if fmt == "json":
        output = {
            "service": service,
            "time_range": {"from": from_str, "to": to_str},
            "threshold_ms": threshold,
            "p99_latency_ms": round(p99_ms, 2),
            "slow_endpoints": slow_endpoints,
            "error_count": error_count,
        }
        print(json.dumps(output, indent=2))
    else:
        # Summary table
        table = Table(title=f"Latency Investigation: {service}")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right", style="yellow")

        table.add_row("P99 Latency (ms)", f"{p99_ms:.2f}")
        table.add_row("Threshold (ms)", str(threshold))
        table.add_row("Error Count", str(error_count))
        console.print(table)

        # Slow endpoints table
        if slow_endpoints:
            ep_table = Table(title="Slow Endpoints")
            ep_table.add_column("Endpoint", style="cyan")
            ep_table.add_column("P99 (ms)", justify="right", style="yellow")
            for ep in slow_endpoints:
                ep_table.add_row(ep["resource_name"], f"{ep['p99_ms']:.2f}")
            console.print(ep_table)


@investigate.command(name="errors")
@click.argument("service")
@click.option("--from", "from_time", default="1h", help="Start time (e.g., 1h, 24h, 7d)")
@click.option("--to", "to_time", default="now", help="End time")
@click.option("--format", "fmt", type=click.Choice(["json", "table"]), default="table")
@handle_api_error
def investigate_errors(service, from_time, to_time, fmt):
    """Investigate error patterns for a service."""
    client = get_datadog_client()
    from_ts, to_ts = parse_time_range(from_time, to_time)
    from_str = to_utc_iso(from_ts)
    to_str = to_utc_iso(to_ts)

    with console.status(f"[cyan]Investigating errors for {service}...[/cyan]"):
        # Step 1: Count error traces
        error_count_response = aggregate_spans(
            client,
            {"query": f"service:{service} status:error", "from": from_str, "to": to_str},
            [{"aggregation": "count"}],
        )

        # Step 2: Get error traces by endpoint
        by_endpoint_response = aggregate_spans(
            client,
            {"query": f"service:{service} status:error", "from": from_str, "to": to_str},
            [{"aggregation": "count"}],
            [{"facet": "resource_name"}],
        )

        # Step 3: Search error logs
        logs_response = client.logs.list_logs(
            body={
                "filter": {
                    "query": f"service:{service} status:error",
                    "from": from_str,
                    "to": to_str,
                },
                "page": {"limit": 100},
            }
        )

    # Extract results
    count_buckets = error_count_response.data.buckets if error_count_response.data else []
    error_count = count_buckets[0].computes["c0"] if count_buckets else 0

    endpoint_buckets = by_endpoint_response.data.buckets if by_endpoint_response.data else []
    by_endpoint = []
    for bucket in endpoint_buckets:
        by_endpoint.append(
            {
                "resource_name": bucket.by.get("resource_name", "N/A"),
                "count": bucket.computes["c0"],
            }
        )

    error_logs = logs_response.data if logs_response.data else []
    recent_logs = [log.attributes.message for log in error_logs]

    if fmt == "json":
        output = {
            "service": service,
            "time_range": {"from": from_str, "to": to_str},
            "error_count": error_count,
            "by_endpoint": by_endpoint,
            "recent_logs": recent_logs,
        }
        print(json.dumps(output, indent=2))
    else:
        # Summary table
        table = Table(title=f"Error Investigation: {service}")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right", style="yellow")
        table.add_row("Total Errors", str(error_count))
        table.add_row("Error Log Count", str(len(recent_logs)))
        console.print(table)

        # Errors by endpoint
        if by_endpoint:
            ep_table = Table(title="Errors by Endpoint")
            ep_table.add_column("Endpoint", style="cyan")
            ep_table.add_column("Count", justify="right", style="yellow")
            for ep in by_endpoint:
                ep_table.add_row(ep["resource_name"], str(ep["count"]))
            console.print(ep_table)

        # Recent error logs
        if recent_logs:
            log_table = Table(title="Recent Error Logs")
            log_table.add_column("Message", style="red")
            for msg in recent_logs:
                log_table.add_row(msg)
            console.print(log_table)


@investigate.command(name="throughput")
@click.argument("service")
@click.option("--from", "from_time", default="1h", help="Start time (e.g., 1h, 24h, 7d)")
@click.option("--to", "to_time", default="now", help="End time")
@click.option("--format", "fmt", type=click.Choice(["json", "table"]), default="table")
@handle_api_error
def investigate_throughput(service, from_time, to_time, fmt):
    """Investigate throughput for a service."""
    client = get_datadog_client()
    from_ts, to_ts = parse_time_range(from_time, to_time)
    from_str = to_utc_iso(from_ts)
    to_str = to_utc_iso(to_ts)

    with console.status(f"[cyan]Investigating throughput for {service}...[/cyan]"):
        # Step 1: Get total request count
        total_response = aggregate_spans(
            client,
            {"query": f"service:{service}", "from": from_str, "to": to_str},
            [{"aggregation": "count"}],
        )

        # Step 2: Get requests by endpoint
        by_endpoint_response = aggregate_spans(
            client,
            {"query": f"service:{service}", "from": from_str, "to": to_str},
            [{"aggregation": "count"}],
            [{"facet": "resource_name"}],
        )

    # Extract results
    total_buckets = total_response.data.buckets if total_response.data else []
    total_requests = total_buckets[0].computes["c0"] if total_buckets else 0

    endpoint_buckets = by_endpoint_response.data.buckets if by_endpoint_response.data else []
    by_endpoint = []
    for bucket in endpoint_buckets:
        by_endpoint.append(
            {
                "resource_name": bucket.by.get("resource_name", "N/A"),
                "count": bucket.computes["c0"],
            }
        )

    if fmt == "json":
        output = {
            "service": service,
            "time_range": {"from": from_str, "to": to_str},
            "total_requests": total_requests,
            "by_endpoint": by_endpoint,
        }
        print(json.dumps(output, indent=2))
    else:
        # Summary table
        table = Table(title=f"Throughput Investigation: {service}")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right", style="yellow")
        table.add_row("Total Requests", str(total_requests))
        console.print(table)

        # Requests by endpoint
        if by_endpoint:
            ep_table = Table(title="Requests by Endpoint")
            ep_table.add_column("Endpoint", style="cyan")
            ep_table.add_column("Count", justify="right", style="yellow")
            for ep in by_endpoint:
                ep_table.add_row(ep["resource_name"], str(ep["count"]))
            console.print(ep_table)


@investigate.command(name="compare")
@click.argument("service")
@click.option("--from", "from_time", default="1h", help="Current period start (e.g., 1h, 24h)")
@click.option("--baseline", default="2h", help="Baseline period duration before --from")
@click.option("--format", "fmt", type=click.Choice(["json", "table"]), default="table")
@handle_api_error
def investigate_compare(service, from_time, baseline, fmt):
    """Compare current period metrics against a baseline period."""
    client = get_datadog_client()

    # Current period: from_time ago to now
    current_from_ts, current_to_ts = parse_time_range(from_time, "now")
    current_from_str = to_utc_iso(current_from_ts)
    current_to_str = to_utc_iso(current_to_ts)

    # Baseline period: baseline ago to from_time ago
    baseline_from_ts, _ = parse_time_range(baseline, "now")
    baseline_to_ts = current_from_ts
    baseline_from_str = to_utc_iso(baseline_from_ts)
    baseline_to_str = to_utc_iso(baseline_to_ts)

    with console.status(f"[cyan]Comparing metrics for {service}...[/cyan]"):
        # Current period: count
        current_count_response = aggregate_spans(
            client,
            {"query": f"service:{service}", "from": current_from_str, "to": current_to_str},
            [{"aggregation": "count"}],
        )

        # Current period: p99
        current_p99_response = aggregate_spans(
            client,
            {"query": f"service:{service}", "from": current_from_str, "to": current_to_str},
            [{"aggregation": "pc99", "metric": "@duration"}],
        )

        # Baseline period: count
        baseline_count_response = aggregate_spans(
            client,
            {"query": f"service:{service}", "from": baseline_from_str, "to": baseline_to_str},
            [{"aggregation": "count"}],
        )

        # Baseline period: p99
        baseline_p99_response = aggregate_spans(
            client,
            {"query": f"service:{service}", "from": baseline_from_str, "to": baseline_to_str},
            [{"aggregation": "pc99", "metric": "@duration"}],
        )

    # Extract current metrics
    current_count_buckets = (
        current_count_response.data.buckets if current_count_response.data else []
    )
    current_count = current_count_buckets[0].computes["c0"] if current_count_buckets else 0

    current_p99_buckets = current_p99_response.data.buckets if current_p99_response.data else []
    current_p99_ns = current_p99_buckets[0].computes["c0"] if current_p99_buckets else 0
    current_p99_ms = current_p99_ns / 1_000_000

    # Extract baseline metrics
    baseline_count_buckets = (
        baseline_count_response.data.buckets if baseline_count_response.data else []
    )
    baseline_count = baseline_count_buckets[0].computes["c0"] if baseline_count_buckets else 0

    baseline_p99_buckets = baseline_p99_response.data.buckets if baseline_p99_response.data else []
    baseline_p99_ns = baseline_p99_buckets[0].computes["c0"] if baseline_p99_buckets else 0
    baseline_p99_ms = baseline_p99_ns / 1_000_000

    # Compute deltas
    count_change = current_count - baseline_count
    count_pct = round((count_change / baseline_count * 100), 1) if baseline_count else 0.0

    p99_change_ms = round(current_p99_ms - baseline_p99_ms, 2)
    p99_pct = round((p99_change_ms / baseline_p99_ms * 100), 1) if baseline_p99_ms else 0.0

    if fmt == "json":
        output = {
            "service": service,
            "current": {
                "request_count": current_count,
                "p99_latency_ms": round(current_p99_ms, 2),
            },
            "baseline": {
                "request_count": baseline_count,
                "p99_latency_ms": round(baseline_p99_ms, 2),
            },
            "delta": {
                "request_count_change": count_change,
                "request_count_pct": count_pct,
                "p99_latency_change_ms": p99_change_ms,
                "p99_latency_pct": p99_pct,
            },
        }
        print(json.dumps(output, indent=2))
    else:
        table = Table(title=f"Comparison: {service}")
        table.add_column("Metric", style="cyan")
        table.add_column("Current", justify="right", style="yellow")
        table.add_column("Baseline", justify="right", style="dim")
        table.add_column("Change", justify="right", style="green")

        table.add_row(
            "Request Count",
            str(current_count),
            str(baseline_count),
            f"{count_change:+d} ({count_pct:+.1f}%)",
        )
        table.add_row(
            "P99 Latency (ms)",
            f"{current_p99_ms:.2f}",
            f"{baseline_p99_ms:.2f}",
            f"{p99_change_ms:+.2f} ({p99_pct:+.1f}%)",
        )
        console.print(table)
