"""
Tests for the analytics module.
Uses in-memory SQLite so no external database is needed.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from datetime import datetime, timezone, timedelta

import backend.database as db_module
from backend.database import init_db, get_db
from backend.models import create_device
from backend.analytics import (
    get_device_analytics, get_response_time_series,
    get_availability_trend, get_recent_probes,
)


@pytest.fixture(autouse=True)
def fresh_db():
    """Reset the in-memory DB before each test."""
    init_db(":memory:")
    yield


def _now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ago(seconds):
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _insert_probe(device_id, is_reachable, response_time_ms=None, offset_seconds=0):
    ts = _ago(offset_seconds)
    with get_db() as conn:
        conn.execute(
            """INSERT INTO probe_results (device_id, checked_at, is_reachable, response_time_ms)
               VALUES (?, ?, ?, ?)""",
            (device_id, ts, 1 if is_reachable else 0, response_time_ms),
        )


@pytest.fixture
def device():
    d = create_device({"name": "Test", "target": "10.0.0.1"})
    return d


# ─── No Data Cases ────────────────────────────────────────────────

class TestNoData:
    def test_analytics_no_probes(self, device):
        a = get_device_analytics(device["id"])
        assert a["total_probes"] == 0
        assert a["availability_pct"] is None
        assert a["avg_response_ms"] is None

    def test_time_series_empty(self, device):
        ts = get_response_time_series(device["id"])
        assert ts == []

    def test_trend_empty(self, device):
        trend = get_availability_trend(device["id"])
        assert trend == []

    def test_recent_probes_empty(self, device):
        probes = get_recent_probes(device["id"])
        assert probes == []


# ─── With Data ────────────────────────────────────────────────────

class TestWithData:
    def test_availability_100_pct(self, device):
        _insert_probe(device["id"], True,  10.0,  10)
        _insert_probe(device["id"], True,  20.0,  20)
        _insert_probe(device["id"], True,  15.0,  30)
        a = get_device_analytics(device["id"])
        assert a["total_probes"]      == 3
        assert a["successful_probes"] == 3
        assert a["failed_probes"]     == 0
        assert a["availability_pct"]  == 100.0
        assert a["packet_loss_pct"]   == 0.0

    def test_availability_50_pct(self, device):
        _insert_probe(device["id"], True,  10.0, 10)
        _insert_probe(device["id"], False, None,  20)
        a = get_device_analytics(device["id"])
        assert a["availability_pct"] == 50.0
        assert a["packet_loss_pct"]  == 50.0

    def test_avg_response_ms(self, device):
        _insert_probe(device["id"], True, 10.0, 10)
        _insert_probe(device["id"], True, 20.0, 20)
        a = get_device_analytics(device["id"])
        assert a["avg_response_ms"] == 15.0

    def test_min_max_response_ms(self, device):
        _insert_probe(device["id"], True, 5.0,  10)
        _insert_probe(device["id"], True, 50.0, 20)
        _insert_probe(device["id"], True, 25.0, 30)
        a = get_device_analytics(device["id"])
        assert a["min_response_ms"] == 5.0
        assert a["max_response_ms"] == 50.0

    def test_time_series_ordered(self, device):
        _insert_probe(device["id"], True, 10.0, 30)
        _insert_probe(device["id"], True, 20.0, 20)
        _insert_probe(device["id"], True, 15.0, 10)
        ts = get_response_time_series(device["id"])
        assert len(ts) == 3
        # Should be in ascending time order
        times = [p["checked_at"] for p in ts]
        assert times == sorted(times)

    def test_recent_probes_limit(self, device):
        for i in range(10):
            _insert_probe(device["id"], True, float(i), i * 5)
        probes = get_recent_probes(device["id"], limit=5)
        assert len(probes) == 5

    def test_analytics_all_devices(self, device):
        d2 = create_device({"name": "D2", "target": "10.0.0.2"})
        _insert_probe(device["id"], True,  10.0, 5)
        _insert_probe(d2["id"],     False, None,  5)
        a = get_device_analytics(None)  # all devices
        assert a["total_probes"]      == 2
        assert a["successful_probes"] == 1
        assert a["failed_probes"]     == 1

    def test_offline_probe_does_not_count_for_avg_rt(self, device):
        _insert_probe(device["id"], True,  100.0, 10)
        _insert_probe(device["id"], False, None,   5)
        a = get_device_analytics(device["id"])
        # avg should be only from successful probe
        assert a["avg_response_ms"] == 100.0

    def test_time_range_filter(self, device):
        _insert_probe(device["id"], True, 10.0, 3600)  # 1h ago
        _insert_probe(device["id"], True, 20.0, 60)    # 1m ago
        since = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        a = get_device_analytics(device["id"], since_iso=since)
        assert a["total_probes"] == 1  # only the recent one
