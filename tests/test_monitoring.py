"""
Tests for the ping_service module using mocks.
Does NOT require real network access or administrator privileges.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import patch, MagicMock
import subprocess

from backend.ping_service import ping, PingResult, _extract_rtt_ms, _classify_error


# ─── PingResult construction ──────────────────────────────────────

class TestPingResult:
    def test_reachable_result(self):
        r = PingResult(is_reachable=True, response_time_ms=12.5,
                       error_category=None, error_message=None, raw_output="")
        assert r.is_reachable
        assert r.response_time_ms == 12.5
        assert r.error_category is None

    def test_unreachable_result(self):
        r = PingResult(is_reachable=False, response_time_ms=None,
                       error_category="timeout", error_message="Timed out", raw_output="")
        assert not r.is_reachable
        assert r.response_time_ms is None
        assert r.error_category == "timeout"


# ─── _extract_rtt_ms ─────────────────────────────────────────────

class TestExtractRttMs:
    def test_windows_format(self):
        output = "Reply from 192.168.1.1: bytes=32 time=15ms TTL=64"
        assert _extract_rtt_ms(output, 999) == 15.0

    def test_linux_format(self):
        output = "64 bytes from 192.168.1.1: icmp_seq=1 ttl=64 time=8.23 ms"
        assert _extract_rtt_ms(output, 999) == 8.23

    def test_fallback_to_elapsed(self):
        output = "No RTT information here"
        assert _extract_rtt_ms(output, 42.0) == 42.0

    def test_time_less_than(self):
        output = "Reply from 192.168.1.1: bytes=32 time<1ms TTL=64"
        assert _extract_rtt_ms(output, 999) == 0.0  # time<1 → 0 matched, not ideal but handled


# ─── _classify_error ─────────────────────────────────────────────

class TestClassifyError:
    def test_timeout(self):
        assert _classify_error("Request timed out.", 1) == "timeout"

    def test_100_percent_loss(self):
        assert _classify_error("100% packet loss", 1) == "timeout"

    def test_unreachable(self):
        assert _classify_error("Destination host unreachable.", 1) == "host_unreachable"

    def test_dns_failure(self):
        assert _classify_error("ping: cannot resolve unknown-host: Name or service not known", 2) == "dns_failure"

    def test_other(self):
        assert _classify_error("Some unexpected error", 42) == "other"


# ─── ping() with mocked subprocess ───────────────────────────────

class TestPingFunction:
    def _make_result(self, returncode, stdout, stderr=""):
        mock = MagicMock()
        mock.returncode = returncode
        mock.stdout = stdout
        mock.stderr = stderr
        return mock

    @patch("backend.ping_service.subprocess.run")
    def test_successful_ping_windows(self, mock_run):
        mock_run.return_value = self._make_result(
            0,
            "Reply from 192.168.1.1: bytes=32 time=12ms TTL=64\n"
            "Ping statistics for 192.168.1.1:\n"
            "    Packets: Sent = 1, Received = 1, Lost = 0 (0% loss)\n",
        )
        result = ping("192.168.1.1", timeout_sec=5)
        assert result.is_reachable
        assert result.response_time_ms == 12.0
        assert result.error_category is None

    @patch("backend.ping_service.subprocess.run")
    def test_successful_ping_linux(self, mock_run):
        mock_run.return_value = self._make_result(
            0,
            "64 bytes from 192.168.1.1: icmp_seq=1 ttl=64 time=8.23 ms\n"
            "--- 192.168.1.1 ping statistics ---\n"
            "1 packets transmitted, 1 received, 0% packet loss, time 0ms\n",
        )
        result = ping("192.168.1.1", timeout_sec=5)
        assert result.is_reachable
        assert result.response_time_ms == 8.23

    @patch("backend.ping_service.subprocess.run")
    def test_failed_ping_timeout(self, mock_run):
        mock_run.return_value = self._make_result(
            1,
            "Request timed out.\n"
            "Ping statistics for 10.0.0.99:\n"
            "    Packets: Sent = 1, Received = 0, Lost = 1 (100% loss)\n",
        )
        result = ping("10.0.0.99", timeout_sec=5)
        assert not result.is_reachable
        assert result.response_time_ms is None
        assert result.error_category == "timeout"

    @patch("backend.ping_service.subprocess.run")
    def test_dns_failure(self, mock_run):
        mock_run.return_value = self._make_result(
            2, "", "ping: cannot resolve notahost: Name or service not known\n"
        )
        result = ping("notahost", timeout_sec=5)
        assert not result.is_reachable
        assert result.error_category == "dns_failure"

    @patch("backend.ping_service.subprocess.run")
    def test_subprocess_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(["ping"], 5)
        result = ping("10.0.0.1", timeout_sec=5)
        assert not result.is_reachable
        assert result.error_category == "timeout"

    @patch("backend.ping_service.subprocess.run")
    def test_file_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("ping not found")
        result = ping("10.0.0.1", timeout_sec=5)
        assert not result.is_reachable
        assert result.error_category == "other"

    @patch("backend.ping_service.subprocess.run")
    def test_permission_error(self, mock_run):
        mock_run.side_effect = PermissionError("Permission denied")
        result = ping("10.0.0.1", timeout_sec=5)
        assert not result.is_reachable
        assert result.error_category == "permission"
