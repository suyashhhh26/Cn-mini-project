"""
Network Monitor — Ping Service
Executes real system ping commands safely using subprocess.
Supports Windows and Linux/macOS.
"""

import sys
import re
import time
import logging
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Pattern to extract round-trip time from ping output
# Windows: "time=12ms" or "time<1ms"  |  Linux/macOS: "time=1.23 ms"
_RTT_PATTERN = re.compile(
    r"time[=<](\d+(?:\.\d+)?)\s*ms",
    re.IGNORECASE,
)


@dataclass
class PingResult:
    is_reachable: bool
    response_time_ms: float | None   # None when not available
    error_category: str | None       # "timeout", "host_unreachable", "permission", "other", None
    error_message: str | None
    raw_output: str


def _build_ping_command(target: str, count: int = 1, timeout_sec: int = 5) -> list[str]:
    """
    Build a platform-appropriate ping command.
    Uses argument lists (shell=False) to prevent shell injection.
    """
    platform = sys.platform

    if platform == "win32":
        # -n count   : number of echo requests
        # -w ms      : wait timeout in milliseconds
        return ["ping", "-n", str(count), "-w", str(timeout_sec * 1000), target]

    elif platform == "darwin":
        # -c count   : number of packets
        # -W ms      : wait timeout in milliseconds (macOS)
        # -t sec     : overall time limit (macOS)
        return ["ping", "-c", str(count), "-W", str(timeout_sec * 1000),
                "-t", str(timeout_sec + 1), target]

    else:
        # Linux
        # -c count   : number of packets
        # -W sec     : wait timeout in seconds
        # -w sec     : deadline
        return ["ping", "-c", str(count), "-W", str(timeout_sec),
                "-w", str(timeout_sec + 1), target]


def ping(target: str, timeout_sec: int = 5, count: int = 1) -> PingResult:
    """
    Execute a real system ping command against the target.

    Args:
        target:      IP address or hostname to ping.
        timeout_sec: Per-packet timeout (seconds).
        count:       Number of ICMP echo requests (default 1).

    Returns:
        PingResult dataclass with all collected data.
    """
    cmd = _build_ping_command(target, count=count, timeout_sec=timeout_sec)
    logger.debug("Executing ping: %s", " ".join(cmd))

    start_wall = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec + 5,   # subprocess timeout slightly larger than ping timeout
            shell=False,
        )
        elapsed_ms = (time.monotonic() - start_wall) * 1000
        raw_output = result.stdout + result.stderr

        logger.debug("Ping return code: %d | output: %s", result.returncode, raw_output[:200])

        if result.returncode == 0:
            # Extract RTT from output; fall back to elapsed time if not parseable
            rtt = _extract_rtt_ms(raw_output, elapsed_ms)
            return PingResult(
                is_reachable=True,
                response_time_ms=round(rtt, 2),
                error_category=None,
                error_message=None,
                raw_output=raw_output,
            )
        else:
            # Classify the failure
            cat = _classify_error(raw_output, result.returncode)
            return PingResult(
                is_reachable=False,
                response_time_ms=None,
                error_category=cat,
                error_message=_summarize_error(raw_output, cat),
                raw_output=raw_output,
            )

    except subprocess.TimeoutExpired as exc:
        logger.warning("Ping subprocess timed out for %s: %s", target, exc)
        return PingResult(
            is_reachable=False,
            response_time_ms=None,
            error_category="timeout",
            error_message="Ping subprocess exceeded timeout.",
            raw_output="",
        )
    except FileNotFoundError:
        logger.error("'ping' executable not found on this system.")
        return PingResult(
            is_reachable=False,
            response_time_ms=None,
            error_category="other",
            error_message="'ping' command not found. Ensure it is available in PATH.",
            raw_output="",
        )
    except PermissionError as exc:
        logger.warning("Permission denied when executing ping for %s: %s", target, exc)
        return PingResult(
            is_reachable=False,
            response_time_ms=None,
            error_category="permission",
            error_message="Permission denied when running ping.",
            raw_output="",
        )
    except Exception as exc:                    # noqa: BLE001
        logger.exception("Unexpected error pinging %s", target)
        return PingResult(
            is_reachable=False,
            response_time_ms=None,
            error_category="other",
            error_message=f"Unexpected error: {type(exc).__name__}",
            raw_output="",
        )


def _extract_rtt_ms(output: str, fallback_ms: float) -> float:
    """
    Parse the first RTT value from ping output.
    Falls back to the subprocess wall-clock time if parsing fails.
    """
    # Windows reports sub-millisecond ping as time<1ms
    if re.search(r"time<1\s*ms", output, re.IGNORECASE):
        return 0.0
    match = _RTT_PATTERN.search(output)
    if match:
        return float(match.group(1))
    return round(fallback_ms, 2)


def _classify_error(output: str, returncode: int) -> str:
    """Classify ping failure into a category based on output text."""
    out_lower = output.lower()
    if "request timed out" in out_lower or "100% packet loss" in out_lower:
        return "timeout"
    if "destination host unreachable" in out_lower or "unreachable" in out_lower:
        return "host_unreachable"
    if "network is unreachable" in out_lower:
        return "host_unreachable"
    if "cannot resolve" in out_lower or "unknown host" in out_lower or "name or service not known" in out_lower:
        return "dns_failure"
    return "other"


def _summarize_error(output: str, category: str) -> str:
    """Return a short human-readable error message."""
    summaries = {
        "timeout":          "No response received (request timed out).",
        "host_unreachable": "Host is unreachable on the network.",
        "dns_failure":      "Hostname could not be resolved (DNS failure).",
        "permission":       "Permission denied.",
        "other":            "Ping failed (see application log for details).",
    }
    return summaries.get(category, "Ping failed.")
