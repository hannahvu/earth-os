"""
Hourly runner tests — fake sources, metrics and upsert. No network.

Run via PyCharm run button or:
    uv run pytest flows/test/test_ingest.py -s
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

import pytest

import flows.ingest as ingest
from flows.ingest import RunResult, collect, run_hourly
from models.event import EarthEvent

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)


def _event(event_id: str, source: str = "TEST") -> EarthEvent:
    return EarthEvent(
        event_id=event_id, event_type="test", observed_at=NOW,
        latitude=0.0, longitude=0.0, region="R", value=1.0, unit="u",
        origin="observed", source=source, confidence=1.0, ingested_at=NOW,
    )


def _boom() -> List[EarthEvent]:
    raise RuntimeError("API down")


class Recorder:
    """Fake upsert that records each call, plus a shared call log for ordering."""

    def __init__(self, log: list):
        self.calls: List[List[str]] = []
        self.log = log

    def __call__(self, events: List[EarthEvent]) -> int:
        self.calls.append([e.event_id for e in events])
        self.log.append("upsert")
        return len(events)


def _run(sources, metrics):
    log: list = []
    upsert = Recorder(log)

    def tracked(name, fn):
        def wrapper():
            log.append(name)
            return fn()
        return wrapper

    result = run_hourly(
        sources={k: tracked(k, v) for k, v in sources.items()},
        metrics={k: tracked(k, v) for k, v in metrics.items()},
        upsert=upsert,
        init=lambda: None,
    )
    return result, upsert, log


def test_failing_source_does_not_block_others():
    result, upsert, _ = _run(
        sources={"A": lambda: [_event("a1")], "BAD": _boom, "C": lambda: [_event("c1"), _event("c2")]},
        metrics={},
    )
    assert upsert.calls == [["a1", "c1", "c2"]]  # one call, both good sources
    assert result.failed == ["BAD"]
    assert result.counts == {"A": 1, "C": 2}
    assert not result.ok


def test_metrics_run_after_source_upsert():
    _, upsert, log = _run(
        sources={"A": lambda: [_event("a1")]},
        metrics={"M": lambda: [_event("m1", source="EarthOS")]},
    )
    assert log == ["A", "upsert", "M", "upsert"]
    assert upsert.calls == [["a1"], ["m1"]]


def test_failing_metric_is_reported():
    result, upsert, _ = _run(
        sources={"A": lambda: [_event("a1")]},
        metrics={"BAD_METRIC": _boom, "M": lambda: [_event("m1")]},
    )
    assert result.failed == ["BAD_METRIC"]
    assert upsert.calls == [["a1"], ["m1"]]


def test_no_events_means_no_upsert():
    result, upsert, _ = _run(sources={"A": lambda: []}, metrics={"M": lambda: []})
    assert upsert.calls == []
    assert result.ok
    assert result.counts == {"A": 0, "M": 0}


def test_upsert_failure_propagates():
    def bad_upsert(events):
        raise RuntimeError("BigQuery down")

    with pytest.raises(RuntimeError):
        run_hourly(sources={"A": lambda: [_event("a1")]}, metrics={}, upsert=bad_upsert, init=lambda: None)


def test_collect_records_failures():
    result = RunResult()
    events = collect({"A": lambda: [_event("a1")], "BAD": _boom}, result)
    assert [e.event_id for e in events] == ["a1"]
    assert result.failed == ["BAD"]


@pytest.mark.parametrize("failed, code", [([], 0), (["NWS"], 1)])
def test_main_exit_code(monkeypatch, failed, code):
    monkeypatch.setattr(ingest, "run_hourly", lambda: RunResult(counts={"A": 1}, failed=failed))
    assert ingest.main() == code


def test_sources_cover_every_adapter():
    assert set(ingest.SOURCES) == {"EIA-ERCO", "EIA-CISO", "EIA-PJM", "EIA-MISO", "EIA-ISNE", "USGS", "NDBC", "NHC", "NWS"}
    assert set(ingest.METRICS) == {"seismic_proximity", "demand_anomaly", "heat_stress"}


def test_main_silences_httpx_request_logs(monkeypatch):
    """EIA's request URL contains api_key; httpx must not log it in public Actions logs."""
    import logging
    monkeypatch.setattr(ingest, "run_hourly", lambda: RunResult())
    ingest.main()
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
