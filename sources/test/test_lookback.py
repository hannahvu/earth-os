"""
Lookback / watermark cutoff tests — pure, no network.

    uv run pytest sources/test/test_lookback.py
"""
from datetime import datetime, timedelta, timezone

from sources.lookback import LOOKBACK, MAX_LOOKBACK, OVERLAP, cutoff_from_watermark, lookback_cutoff

NOW = datetime(2026, 11, 24, 22, 0, tzinfo=timezone.utc)


def test_fresh_watermark_uses_min_lookback():
    assert cutoff_from_watermark(NOW - timedelta(minutes=10), now=NOW) == NOW - LOOKBACK


def test_gap_reaches_back_to_watermark_minus_overlap():
    wm = NOW - timedelta(hours=8)
    assert cutoff_from_watermark(wm, now=NOW) == wm - OVERLAP


def test_very_old_watermark_capped_at_max_lookback():
    assert cutoff_from_watermark(NOW - timedelta(days=30), now=NOW) == NOW - MAX_LOOKBACK


def test_missing_watermark_starts_at_max_lookback():
    assert cutoff_from_watermark(None, now=NOW) == NOW - MAX_LOOKBACK


def test_custom_min_lookback():
    assert cutoff_from_watermark(NOW, now=NOW, min_lookback=timedelta(hours=100)) == NOW - timedelta(hours=100)


def test_lookback_cutoff_unchanged():
    assert lookback_cutoff(NOW) == NOW - LOOKBACK
