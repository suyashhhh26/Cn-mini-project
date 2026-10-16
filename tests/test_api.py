"""
Tests for the REST API endpoints.
Uses Flask test client with in-memory SQLite.
All ping operations are mocked.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import patch, MagicMock
from app import create_app


@pytest.fixture(scope="module")
def app():
    application = create_app("testing")
    return application


@pytest.fixture(scope="module")
def client(app):
    return app.test_client()


@pytest.fixture(scope="module")
def device_id(client):
    """Create a test device and return its ID."""
    resp = client.post("/api/devices", json={
        "name":               "Test Device",
        "target":             "127.0.0.1",
        "device_type":        "Computer",
        "monitoring_interval": 30,
    })
    assert resp.status_code == 201
    return resp.get_json()["data"]["id"]


# ─── Health ────────────────────────────────────────────────────────

class TestHealth:
    def test_health_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.get_json()
        assert data["success"]
        assert "timestamp" in data["data"]


# ─── Devices CRUD ─────────────────────────────────────────────────

class TestDeviceCRUD:
    def test_list_devices_empty_initially(self, client):
        r = client.get("/api/devices")
        assert r.status_code == 200
        assert r.get_json()["success"]

    def test_create_device(self, client):
        r = client.post("/api/devices", json={
            "name": "API Test Router",
            "target": "10.0.0.254",
            "device_type": "Router",
            "monitoring_interval": 60,
        })
        assert r.status_code == 201
        d = r.get_json()["data"]
        assert d["target"] == "10.0.0.254"
        assert d["device_type"] == "Router"

    def test_create_duplicate_rejected(self, client):
        # First create
        client.post("/api/devices", json={"name": "Dup", "target": "172.16.0.1"})
        # Second with same target
        r = client.post("/api/devices", json={"name": "Dup2", "target": "172.16.0.1"})
        assert r.status_code == 409

    def test_create_invalid_ip_rejected(self, client):
        r = client.post("/api/devices", json={"name": "Bad", "target": "999.0.0.1"})
        assert r.status_code == 422
        assert r.get_json()["field"] == "target"

    def test_create_missing_name_rejected(self, client):
        r = client.post("/api/devices", json={"target": "10.1.1.1"})
        assert r.status_code == 422
        assert r.get_json()["field"] == "name"

    def test_create_invalid_interval_rejected(self, client):
        r = client.post("/api/devices", json={
            "name": "Bad Interval", "target": "10.2.2.2", "monitoring_interval": 3
        })
        assert r.status_code == 422

    def test_get_device(self, client, device_id):
        r = client.get(f"/api/devices/{device_id}")
        assert r.status_code == 200
        d = r.get_json()["data"]
        assert d["id"] == device_id

    def test_get_nonexistent_device(self, client):
        r = client.get("/api/devices/99999")
        assert r.status_code == 404

    def test_update_device(self, client, device_id):
        r = client.put(f"/api/devices/{device_id}", json={"name": "Updated Name"})
        assert r.status_code == 200
        assert r.get_json()["data"]["name"] == "Updated Name"

    def test_delete_device(self, client):
        # Create then delete
        r = client.post("/api/devices", json={"name": "ToDelete", "target": "10.99.99.99"})
        did = r.get_json()["data"]["id"]
        dr = client.delete(f"/api/devices/{did}")
        assert dr.status_code == 200
        # Confirm gone
        gr = client.get(f"/api/devices/{did}")
        assert gr.status_code == 404

    def test_toggle_monitoring(self, client, device_id):
        r = client.post(f"/api/devices/{device_id}/monitoring", json={"enabled": False})
        assert r.status_code == 200
        assert r.get_json()["data"]["is_monitoring_enabled"] == 0

        r = client.post(f"/api/devices/{device_id}/monitoring", json={"enabled": True})
        assert r.status_code == 200
        assert r.get_json()["data"]["is_monitoring_enabled"] == 1


# ─── Manual Test ──────────────────────────────────────────────────

class TestManualTest:
    @patch("backend.monitoring.ping")
    def test_manual_test_online(self, mock_ping, client, device_id):
        from backend.ping_service import PingResult
        mock_ping.return_value = PingResult(
            is_reachable=True, response_time_ms=5.0,
            error_category=None, error_message=None, raw_output=""
        )
        r = client.post(f"/api/devices/{device_id}/test", json={})
        assert r.status_code == 200
        data = r.get_json()
        assert data["success"]

    def test_manual_test_nonexistent(self, client):
        r = client.post("/api/devices/99999/test", json={})
        assert r.status_code == 404


# ─── Dashboard ────────────────────────────────────────────────────

class TestDashboard:
    def test_dashboard_returns_counts(self, client):
        r = client.get("/api/dashboard")
        assert r.status_code == 200
        data = r.get_json()["data"]
        assert "counts" in data
        assert "total" in data["counts"]

    def test_dashboard_has_events(self, client):
        r = client.get("/api/dashboard")
        data = r.get_json()["data"]
        assert "recent_events" in data


# ─── Events ───────────────────────────────────────────────────────

class TestEvents:
    def test_list_events(self, client):
        r = client.get("/api/events")
        assert r.status_code == 200
        assert isinstance(r.get_json()["data"], list)

    def test_mark_event_read(self, client):
        # Get an event first
        r = client.get("/api/events?limit=1")
        events = r.get_json()["data"]
        if events:
            eid = events[0]["id"]
            mr = client.patch(f"/api/events/{eid}/read", json={})
            assert mr.status_code == 200


# ─── Analytics ────────────────────────────────────────────────────

class TestAnalytics:
    def test_analytics_no_data(self, client):
        r = client.get("/api/analytics?range=1h&device_id=999999")
        assert r.status_code == 200
        data = r.get_json()["data"]
        assert "analytics" in data
        assert data["analytics"]["total_probes"] == 0

    def test_analytics_with_device(self, client, device_id):
        r = client.get(f"/api/analytics?range=24h&device_id={device_id}")
        assert r.status_code == 200


# ─── Settings ─────────────────────────────────────────────────────

class TestSettings:
    def test_get_settings(self, client):
        r = client.get("/api/settings")
        assert r.status_code == 200
        s = r.get_json()["data"]
        assert "default_monitoring_interval" in s

    def test_update_settings_valid(self, client):
        r = client.put("/api/settings", json={
            "default_monitoring_interval": "45",
            "default_ping_timeout": "8",
        })
        assert r.status_code == 200

    def test_update_settings_invalid(self, client):
        r = client.put("/api/settings", json={"default_monitoring_interval": "9999"})
        assert r.status_code == 422
