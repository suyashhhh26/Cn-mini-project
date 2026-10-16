"""
Tests for the validators module.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from backend.validators import (
    is_valid_ip, is_valid_hostname, is_valid_target,
    validate_device_payload, ValidationError, validate_setting,
)


# ─── IP Validation ─────────────────────────────────────────────────

class TestIsValidIp:
    def test_valid_ipv4(self):
        assert is_valid_ip("192.168.1.1")
        assert is_valid_ip("10.0.0.1")
        assert is_valid_ip("8.8.8.8")
        assert is_valid_ip("0.0.0.0")
        assert is_valid_ip("255.255.255.255")

    def test_valid_ipv6(self):
        assert is_valid_ip("::1")
        assert is_valid_ip("2001:db8::1")
        assert is_valid_ip("fe80::1")

    def test_invalid_ip(self):
        assert not is_valid_ip("999.0.0.1")
        assert not is_valid_ip("192.168.1")
        assert not is_valid_ip("not-an-ip")
        assert not is_valid_ip("")
        assert not is_valid_ip("192.168.1.1.1")


# ─── Hostname Validation ───────────────────────────────────────────

class TestIsValidHostname:
    def test_valid_hostnames(self):
        assert is_valid_hostname("localhost")
        assert is_valid_hostname("router.local")
        assert is_valid_hostname("my-server")
        assert is_valid_hostname("host01")
        assert is_valid_hostname("www.example.com")
        assert is_valid_hostname("a.b.c.d")

    def test_invalid_hostnames(self):
        assert not is_valid_hostname("")
        assert not is_valid_hostname("-router")
        assert not is_valid_hostname("router-")
        assert not is_valid_hostname("ro..ter")
        assert not is_valid_hostname("a" * 254)  # too long
        assert not is_valid_hostname("host name")  # space

    def test_labels_too_long(self):
        long_label = "a" * 64
        assert not is_valid_hostname(f"{long_label}.example.com")


# ─── is_valid_target ──────────────────────────────────────────────

class TestIsValidTarget:
    def test_accepts_ip(self):
        ok, norm = is_valid_target("192.168.1.1")
        assert ok
        assert norm == "192.168.1.1"

    def test_accepts_hostname(self):
        ok, norm = is_valid_target("my-router.local")
        assert ok
        assert norm == "my-router.local"

    def test_normalises_case(self):
        ok, norm = is_valid_target("  ROUTER.LOCAL  ")
        assert ok
        assert norm == "router.local"

    def test_rejects_invalid(self):
        ok, _ = is_valid_target("not a valid target!")
        assert not ok

    def test_rejects_empty(self):
        ok, _ = is_valid_target("")
        assert not ok


# ─── validate_device_payload ──────────────────────────────────────

class TestValidateDevicePayload:
    def test_valid_full_payload(self):
        data = {
            "name": "Test Router",
            "target": "192.168.1.1",
            "device_type": "Router",
            "location": "Rack A",
            "description": "Primary gateway",
            "monitoring_interval": 60,
        }
        cleaned = validate_device_payload(data)
        assert cleaned["name"] == "Test Router"
        assert cleaned["target"] == "192.168.1.1"
        assert cleaned["device_type"] == "Router"
        assert cleaned["monitoring_interval"] == 60

    def test_defaults_applied(self):
        cleaned = validate_device_payload({"name": "Dev", "target": "10.0.0.1"})
        assert cleaned["device_type"] == "Other"
        assert cleaned["monitoring_interval"] == 30
        assert cleaned["location"] == ""
        assert cleaned["description"] == ""

    def test_missing_name_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_device_payload({"target": "10.0.0.1"})
        assert exc_info.value.field == "name"

    def test_missing_target_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_device_payload({"name": "Dev"})
        assert exc_info.value.field == "target"

    def test_invalid_ip_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_device_payload({"name": "Dev", "target": "999.0.0.1"})
        assert exc_info.value.field == "target"

    def test_invalid_device_type_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_device_payload({"name": "Dev", "target": "10.0.0.1", "device_type": "Toaster"})
        assert exc_info.value.field == "device_type"

    def test_interval_too_small_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_device_payload({"name": "Dev", "target": "10.0.0.1", "monitoring_interval": 2})
        assert exc_info.value.field == "monitoring_interval"

    def test_interval_too_large_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_device_payload({"name": "Dev", "target": "10.0.0.1", "monitoring_interval": 9999})
        assert exc_info.value.field == "monitoring_interval"

    def test_update_mode_skips_missing_fields(self):
        cleaned = validate_device_payload({"name": "Updated Name"}, is_update=True)
        assert "name" in cleaned
        assert "target" not in cleaned

    def test_name_too_long_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_device_payload({"name": "a" * 101, "target": "10.0.0.1"})
        assert exc_info.value.field == "name"


# ─── validate_setting ─────────────────────────────────────────────

class TestValidateSetting:
    def test_valid_interval(self):
        ok, msg = validate_setting("default_monitoring_interval", "60")
        assert ok
        assert msg == ""

    def test_invalid_key(self):
        ok, msg = validate_setting("nonexistent_key", "anything")
        assert not ok

    def test_below_min(self):
        ok, msg = validate_setting("default_monitoring_interval", "1")
        assert not ok

    def test_above_max(self):
        ok, msg = validate_setting("default_monitoring_interval", "99999")
        assert not ok

    def test_non_integer(self):
        ok, msg = validate_setting("default_monitoring_interval", "not_a_number")
        assert not ok
