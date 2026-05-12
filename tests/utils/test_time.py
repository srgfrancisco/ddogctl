"""Tests for time parsing utilities."""

import os
import time
import pytest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

from ddogctl.utils.time import parse_time_range, to_utc_iso, to_utc_datetime


class TestParseTimeRange:
    """Test suite for parse_time_range function."""

    @pytest.fixture
    def mock_now(self):
        """Fixed UTC datetime for predictable testing."""
        return datetime(2026, 2, 11, 15, 30, 0, tzinfo=timezone.utc)

    def test_now_to_now(self, mock_now):
        with patch("ddogctl.utils.time.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_now
            from_ts, to_ts = parse_time_range("now", "now")

            assert from_ts == to_ts
            assert from_ts == int(mock_now.timestamp())

    def test_hours_ago(self, mock_now):
        with patch("ddogctl.utils.time.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_now

            from_ts, to_ts = parse_time_range("1h", "now")
            assert from_ts == int((mock_now - timedelta(hours=1)).timestamp())
            assert to_ts == int(mock_now.timestamp())

            from_ts, _ = parse_time_range("24h", "now")
            assert from_ts == int((mock_now - timedelta(hours=24)).timestamp())

    def test_days_ago(self, mock_now):
        with patch("ddogctl.utils.time.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_now

            from_ts, to_ts = parse_time_range("7d", "now")
            assert from_ts == int((mock_now - timedelta(days=7)).timestamp())
            assert to_ts == int(mock_now.timestamp())

    def test_minutes_ago(self, mock_now):
        with patch("ddogctl.utils.time.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_now

            from_ts, to_ts = parse_time_range("30m", "now")
            assert from_ts == int((mock_now - timedelta(minutes=30)).timestamp())
            assert to_ts == int(mock_now.timestamp())

    def test_iso_datetime_with_tz(self, mock_now):
        """Aware ISO strings should be honored as-is."""
        with patch("ddogctl.utils.time.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_now
            mock_datetime.fromisoformat = datetime.fromisoformat

            from_ts, to_ts = parse_time_range(
                "2026-02-10T10:00:00+00:00",
                "2026-02-11T10:00:00+00:00",
            )

            assert from_ts == int(datetime(2026, 2, 10, 10, 0, 0, tzinfo=timezone.utc).timestamp())
            assert to_ts == int(datetime(2026, 2, 11, 10, 0, 0, tzinfo=timezone.utc).timestamp())

    def test_naive_iso_datetime_treated_as_utc(self, mock_now, monkeypatch):
        """Regression: a naive ISO string must be treated as UTC, not local time."""
        monkeypatch.setenv("TZ", "America/Sao_Paulo")
        time.tzset()
        try:
            with patch("ddogctl.utils.time.datetime") as mock_datetime:
                mock_datetime.now.return_value = mock_now
                mock_datetime.fromisoformat = datetime.fromisoformat

                from_ts, _ = parse_time_range("2026-02-10T10:00:00", "now")

                # Expected: 10:00 UTC, not 10:00 BRT (which would be 13:00 UTC).
                assert from_ts == int(
                    datetime(2026, 2, 10, 10, 0, 0, tzinfo=timezone.utc).timestamp()
                )
        finally:
            monkeypatch.delenv("TZ", raising=False)
            time.tzset()

    def test_default_to_parameter(self, mock_now):
        with patch("ddogctl.utils.time.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_now

            from_ts, to_ts = parse_time_range("1h")

            assert from_ts == int((mock_now - timedelta(hours=1)).timestamp())
            assert to_ts == int(mock_now.timestamp())

    def test_now_is_utc_aware_in_real_call(self):
        """Without mocks, parse_time_range should compute against a UTC clock.

        Regression for #52: previously used the naive ``datetime.now()`` which
        only worked by accident in non-UTC timezones.
        """
        before = int(datetime.now(timezone.utc).timestamp())
        _, to_ts = parse_time_range("1h", "now")
        after = int(datetime.now(timezone.utc).timestamp())

        assert before - 1 <= to_ts <= after + 1

    def test_invalid_format_raises_error(self):
        with pytest.raises(ValueError, match="Invalid time format"):
            parse_time_range("1y")
        with pytest.raises(ValueError, match="Invalid time format"):
            parse_time_range("abc")
        with pytest.raises(ValueError, match="Invalid time format"):
            parse_time_range("10")
        with pytest.raises(ValueError, match="Invalid time format"):
            parse_time_range("2026-99-99")

    def test_malformed_relative_time(self):
        for invalid in ["h1", "1", "1hh", "-1h", "1.5h", "1 h"]:
            with pytest.raises(ValueError, match="Invalid time format"):
                parse_time_range(invalid)

    def test_timestamp_precision(self, mock_now):
        with patch("ddogctl.utils.time.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_now
            from_ts, to_ts = parse_time_range("1h", "now")
            assert isinstance(from_ts, int)
            assert isinstance(to_ts, int)


class TestToUtcIso:
    """Test suite for the to_utc_iso helper (issue #52 fix)."""

    def test_known_epoch_serializes_to_utc(self):
        # 2026-05-12T22:05:00Z
        ts = int(datetime(2026, 5, 12, 22, 5, 0, tzinfo=timezone.utc).timestamp())
        assert to_utc_iso(ts) == "2026-05-12T22:05:00Z"

    def test_non_utc_tz_does_not_shift_output(self, monkeypatch):
        """Regression: output must be UTC regardless of the process TZ.

        Before the fix, ``datetime.fromtimestamp(ts).isoformat() + "Z"`` would
        emit local time mislabeled as UTC, silently shifting every Datadog
        query by the local UTC offset.
        """
        ts = int(datetime(2026, 5, 12, 22, 5, 0, tzinfo=timezone.utc).timestamp())

        for tz in ("America/Sao_Paulo", "Asia/Tokyo", "UTC"):
            monkeypatch.setenv("TZ", tz)
            time.tzset()
            try:
                assert to_utc_iso(ts) == "2026-05-12T22:05:00Z"
            finally:
                monkeypatch.delenv("TZ", raising=False)
                time.tzset()

    def test_format_is_seconds_precision_with_z_suffix(self):
        ts = int(datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
        out = to_utc_iso(ts)
        assert out.endswith("Z")
        assert "." not in out  # no fractional seconds
        assert "+" not in out  # no numeric offset


class TestToUtcDatetime:
    """Test suite for the to_utc_datetime helper."""

    def test_returns_utc_aware_datetime(self):
        ts = int(datetime(2026, 5, 12, 22, 5, 0, tzinfo=timezone.utc).timestamp())
        dt = to_utc_datetime(ts)
        assert dt.tzinfo is not None
        assert dt.utcoffset() == timedelta(0)
        assert dt.year == 2026
        assert dt.month == 5
        assert dt.day == 12
        assert dt.hour == 22
        assert dt.minute == 5

    def test_non_utc_tz_does_not_shift_components(self, monkeypatch):
        ts = int(datetime(2026, 5, 12, 22, 5, 0, tzinfo=timezone.utc).timestamp())
        monkeypatch.setenv("TZ", "America/Sao_Paulo")
        time.tzset()
        try:
            dt = to_utc_datetime(ts)
            assert dt.hour == 22  # not 19
        finally:
            monkeypatch.delenv("TZ", raising=False)
            time.tzset()


@pytest.fixture(autouse=True)
def _restore_tz():
    """Always restore the original process TZ after every test."""
    original = os.environ.get("TZ")
    yield
    if original is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = original
    time.tzset()
