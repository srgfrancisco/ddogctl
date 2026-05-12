"""Time parsing utilities."""

from datetime import datetime, timedelta, timezone
import re


def parse_time_range(from_str: str, to_str: str = "now") -> tuple[int, int]:
    """Parse time range strings to Unix timestamps.

    Supported formats:
    - "now"
    - "1h" (1 hour ago)
    - "24h" (24 hours ago)
    - "7d" (7 days ago)
    - "2026-02-10T10:00:00" (ISO datetime; naive values are treated as UTC)

    Returns:
        Tuple of (from_timestamp, to_timestamp) as integer Unix epochs.
    """
    now = datetime.now(timezone.utc)

    def parse_relative(s: str) -> datetime:
        if s == "now":
            return now

        match = re.match(r"^(\d+)([hdm])$", s)
        if match:
            value = int(match.group(1))
            unit = match.group(2)

            if unit == "h":
                return now - timedelta(hours=value)
            elif unit == "d":
                return now - timedelta(days=value)
            elif unit == "m":
                return now - timedelta(minutes=value)

        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            raise ValueError(f"Invalid time format: {s}")

        # Treat naive ISO strings as UTC rather than local — matches the
        # rest of the CLI, which always talks to Datadog in UTC.
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    from_dt = parse_relative(from_str)
    to_dt = parse_relative(to_str)

    return int(from_dt.timestamp()), int(to_dt.timestamp())


def to_utc_iso(ts: int) -> str:
    """Convert a Unix timestamp to a UTC ISO-8601 string (``YYYY-MM-DDTHH:MM:SSZ``).

    Datadog's Logs/APM/RUM search APIs accept ISO-8601 timestamps and assume the
    ``Z`` suffix means UTC. Callers must therefore format the epoch in UTC; using
    naive ``datetime.fromtimestamp`` produces *local* time and then mislabels it as
    UTC, silently shifting every query by the local UTC offset (issue #52).
    """
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_utc_datetime(ts: int) -> datetime:
    """Convert a Unix timestamp to a UTC-aware datetime.

    Use this when handing a value to the Datadog SDK as a ``datetime`` (e.g. the
    CI Visibility client takes ``filter_from``/``filter_to`` as datetimes). A
    naive datetime would be serialized by the SDK in local time.
    """
    return datetime.fromtimestamp(ts, tz=timezone.utc)
