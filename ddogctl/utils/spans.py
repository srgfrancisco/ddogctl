"""Spans API helpers: aggregation, paginated search, and span field access."""

from datetime import date, datetime

# Spans list API caps page[limit] at 1000.
MAX_PAGE_LIMIT = 1000


def aggregate_spans(client, filter_dict, compute_list, group_by_list=None):
    """Call aggregate_spans with proper data envelope and normalize response.

    The Datadog SDK v2 requires a data.attributes wrapper for aggregate_spans.
    This function wraps the request and normalizes the response so commands
    can use a consistent interface: response.data.buckets[].computes/.by

    Args:
        client: DatadogClient instance
        filter_dict: {"query": ..., "from": ..., "to": ...}
        compute_list: [{"aggregation": ..., "metric": ...}]
        group_by_list: [{"facet": ...}] or None

    Returns:
        Response with .data.buckets[].computes/.by interface
    """
    attributes = {
        "filter": filter_dict,
        "compute": compute_list,
    }
    if group_by_list:
        attributes["group_by"] = group_by_list

    body = {
        "data": {
            "type": "aggregate_request",
            "attributes": attributes,
        }
    }

    response = client.spans.aggregate_spans(body=body)
    raw_data = response.data

    # Mock responses return .data.buckets (old format) — pass through as-is
    if hasattr(raw_data, "buckets"):
        return response

    # Real API returns .data as a list of SpansAggregateBucket
    raw_buckets = raw_data if isinstance(raw_data, list) else []

    class NormalizedBucket:
        def __init__(self, bucket):
            self.by = bucket.attributes.by
            self.computes = bucket.attributes.compute

    class NormalizedData:
        def __init__(self, buckets):
            self.buckets = buckets

    class NormalizedResponse:
        def __init__(self, buckets):
            self.data = NormalizedData(buckets)

    return NormalizedResponse([NormalizedBucket(b) for b in raw_buckets])


def search_spans(client, query, from_str, to_str, limit, sort="-timestamp"):
    """Search spans, following cursor pagination until `limit` spans are collected.

    Returns:
        (spans, truncated) where truncated is True if more results were available.
    """
    from datadog_api_client.v2.model.spans_sort import SpansSort

    spans: list = []
    cursor = None
    while len(spans) < limit:
        kwargs = {
            "filter_query": query,
            "filter_from": from_str,
            "filter_to": to_str,
            "sort": SpansSort(sort),
            "page_limit": min(limit - len(spans), MAX_PAGE_LIMIT),
        }
        if cursor:
            kwargs["page_cursor"] = cursor
        response = client.spans.list_spans_get(**kwargs)
        spans.extend(getattr(response, "data", None) or [])
        cursor = _next_cursor(response)
        if not cursor:
            return spans[:limit], False
    return spans[:limit], True


def _next_cursor(response):
    meta = getattr(response, "meta", None)
    page = getattr(meta, "page", None) if meta else None
    return getattr(page, "after", None) if page else None


def span_to_dict(span):
    """Convert a Span to a JSON-serializable dict with every attribute plus duration_ms."""
    attrs = span.attributes.to_dict()
    for key, value in attrs.items():
        if isinstance(value, (datetime, date)):
            attrs[key] = value.isoformat()
    attrs["duration_ms"] = span_duration_ms(span)
    return attrs


def span_duration_ms(span):
    """Span duration in milliseconds.

    The API reports duration in nanoseconds under `custom.duration`; SpansAttributes has
    no top-level `duration`. Falls back to end - start timestamps.
    """
    attrs = span.attributes
    custom = getattr(attrs, "custom", None) or {}
    duration_ns = custom.get("duration") if isinstance(custom, dict) else None
    if isinstance(duration_ns, (int, float)):
        return round(duration_ns / 1_000_000, 2)
    start = getattr(attrs, "start_timestamp", None)
    end = getattr(attrs, "end_timestamp", None)
    if isinstance(start, datetime) and isinstance(end, datetime):
        return round((end - start).total_seconds() * 1000, 2)
    return 0.0


def get_span_field(span_dict, field):
    """Look up a field in a span dict.

    `@a.b` resolves to custom attributes (custom["a"]["b"]); anything else is a top-level
    attribute such as `trace_id` or `env`.
    """
    if field.startswith("@"):
        value = span_dict.get("custom") or {}
        path = field[1:].split(".")
    else:
        value = span_dict
        path = [field]
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value
