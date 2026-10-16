"""
Network Monitor — Background Monitoring Engine
Executes real ping checks for registered devices at their configured intervals.
Uses threading with a dedicated scheduler thread.
"""

import threading
import logging
import time
from datetime import datetime, timezone

from backend.ping_service import ping
from backend.database import get_db
from backend.models import (
    get_all_devices, update_device_status,
    STATUS_ONLINE, STATUS_OFFLINE, STATUS_UNKNOWN,
)
from backend.event_service import (
    log_event,
    EVT_DEVICE_ONLINE, EVT_DEVICE_OFFLINE, EVT_MONITORING_ERROR,
    SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_ERROR,
)

logger = logging.getLogger(__name__)


class MonitoringEngine:
    """
    Background monitoring engine.

    Launches one scheduler thread that maintains per-device timers.
    Device checks run in a bounded thread pool to prevent runaway concurrency.
    """

    def __init__(self, max_workers: int = 10, ping_timeout: int = 5):
        self._max_workers = max_workers
        self._ping_timeout = ping_timeout
        self._lock = threading.Lock()
        self._scheduler_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        # device_id → last probe UNIX timestamp
        self._last_probe: dict[int, float] = {}
        # Semaphore to limit concurrent pings
        self._semaphore = threading.Semaphore(max_workers)
        # Track last-known status to detect transitions
        self._last_status: dict[int, str] = {}
        # Rate-limit manual tests: device_id → last manual test timestamp
        self._manual_test_times: dict[int, float] = {}
        self._manual_test_lock = threading.Lock()

        self._running = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the background scheduler thread (idempotent)."""
        with self._lock:
            if self._running:
                logger.debug("MonitoringEngine already running.")
                return
            self._stop_event.clear()
            self._scheduler_thread = threading.Thread(
                target=self._scheduler_loop,
                name="NetworkMonitor-Scheduler",
                daemon=True,
            )
            self._scheduler_thread.start()
            self._running = True
            logger.info("MonitoringEngine started.")

    def stop(self) -> None:
        """Signal the scheduler to stop and wait for it."""
        with self._lock:
            if not self._running:
                return
            self._stop_event.set()
            self._running = False

        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=10)
        logger.info("MonitoringEngine stopped.")

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Scheduler Loop ────────────────────────────────────────────────────────

    def _scheduler_loop(self) -> None:
        """Main loop: check which devices are due for a probe, dispatch workers."""
        while not self._stop_event.is_set():
            try:
                devices = get_all_devices(enabled_only=True)
                now = time.monotonic()

                for device in devices:
                    device_id = device["id"]
                    interval  = device["monitoring_interval"]
                    last      = self._last_probe.get(device_id, 0)

                    if now - last >= interval:
                        self._last_probe[device_id] = now
                        self._dispatch_probe(device)

            except Exception:           # noqa: BLE001
                logger.exception("Error in scheduler loop")

            # Tick every second so intervals are respected closely
            self._stop_event.wait(timeout=1)

    def _dispatch_probe(self, device: dict) -> None:
        """Launch a probe in a separate daemon thread (bounded by semaphore)."""
        t = threading.Thread(
            target=self._run_probe,
            args=(device,),
            name=f"NetworkMonitor-Probe-{device['id']}",
            daemon=True,
        )
        t.start()

    # ── Probe Execution ───────────────────────────────────────────────────────

    def _run_probe(self, device: dict) -> None:
        """
        Execute a single ping probe, store result, handle status transitions.
        """
        device_id = device["id"]
        target    = device["target"]

        acquired = self._semaphore.acquire(blocking=False)
        if not acquired:
            logger.warning("Probe skipped for %s — max concurrency reached.", target)
            return

        try:
            result = ping(target, timeout_sec=self._ping_timeout)
            self._store_and_update(device_id, device["name"], result)
        except Exception:               # noqa: BLE001
            logger.exception("Unexpected error probing %s", target)
            log_event(
                EVT_MONITORING_ERROR,
                f"Unexpected error while probing '{device['name']}' ({target}).",
                device_id=device_id,
                severity=SEVERITY_ERROR,
            )
        finally:
            self._semaphore.release()

    def _store_and_update(self, device_id: int, device_name: str, result) -> None:
        """Persist probe result and handle status change events."""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        new_status = STATUS_ONLINE if result.is_reachable else STATUS_OFFLINE

        # Store probe result
        with get_db() as conn:
            conn.execute(
                """INSERT INTO probe_results
                   (device_id, checked_at, is_reachable, response_time_ms,
                    error_category, error_message)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    device_id,
                    now_iso,
                    1 if result.is_reachable else 0,
                    result.response_time_ms,
                    result.error_category,
                    result.error_message,
                ),
            )

        # Update device status
        previous_status = update_device_status(
            device_id,
            new_status,
            response_time_ms=result.response_time_ms,
            last_success=result.is_reachable,
        )

        # Log status-change events only on transitions
        prev_known = self._last_status.get(device_id, STATUS_UNKNOWN)
        self._last_status[device_id] = new_status

        if new_status == STATUS_ONLINE and prev_known != STATUS_ONLINE:
            rt_str = f" ({result.response_time_ms:.1f} ms)" if result.response_time_ms else ""
            log_event(
                EVT_DEVICE_ONLINE,
                f"'{device_name}' is now ONLINE{rt_str}.",
                device_id=device_id,
                severity=SEVERITY_INFO,
            )
            logger.info("Device %s (%d) came ONLINE.", device_name, device_id)

        elif new_status == STATUS_OFFLINE and prev_known == STATUS_ONLINE:
            err = result.error_category or "unknown"
            log_event(
                EVT_DEVICE_OFFLINE,
                f"'{device_name}' went OFFLINE. Reason: {err}.",
                device_id=device_id,
                severity=SEVERITY_WARNING,
            )
            logger.warning("Device %s (%d) went OFFLINE.", device_name, device_id)

    # ── Manual Test ───────────────────────────────────────────────────────────

    def manual_test(
        self,
        device_id: int,
        target: str,
        device_name: str,
        rate_limit_sec: int = 10,
    ) -> dict:
        """
        Run an immediate connectivity test outside the normal schedule.
        Rate-limited per device.

        Returns a dict with the probe result.
        """
        now = time.monotonic()
        with self._manual_test_lock:
            last = self._manual_test_times.get(device_id, 0)
            if now - last < rate_limit_sec:
                remaining = int(rate_limit_sec - (now - last))
                return {
                    "rate_limited": True,
                    "retry_after_seconds": remaining,
                    "message": f"Please wait {remaining}s before testing again.",
                }
            self._manual_test_times[device_id] = now

        result = ping(target, timeout_sec=self._ping_timeout)
        self._store_and_update(device_id, device_name, result)

        return {
            "rate_limited": False,
            "is_reachable": result.is_reachable,
            "response_time_ms": result.response_time_ms,
            "error_category": result.error_category,
            "error_message": result.error_message,
        }


# ── Module-level singleton ────────────────────────────────────────────────────

_engine: MonitoringEngine | None = None


def get_engine() -> MonitoringEngine:
    """Return the global MonitoringEngine singleton (create if needed)."""
    global _engine
    if _engine is None:
        _engine = MonitoringEngine()
    return _engine


def start_monitoring(max_workers: int = 10, ping_timeout: int = 5) -> None:
    """Initialize and start the global monitoring engine."""
    global _engine
    if _engine is None:
        _engine = MonitoringEngine(max_workers=max_workers, ping_timeout=ping_timeout)
    _engine.start()


def stop_monitoring() -> None:
    """Stop the global monitoring engine."""
    global _engine
    if _engine:
        _engine.stop()
