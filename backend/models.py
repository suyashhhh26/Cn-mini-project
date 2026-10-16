"""
Network Monitor — Device Model
CRUD operations and status management for monitored devices.
"""

import logging
from datetime import datetime, timezone
from backend.database import get_db
from backend.event_service import (
    log_event,
    EVT_DEVICE_ADDED, EVT_DEVICE_UPDATED, EVT_DEVICE_DELETED,
    EVT_MONITORING_START, EVT_MONITORING_STOP,
    SEVERITY_INFO, SEVERITY_WARNING,
)

logger = logging.getLogger(__name__)

STATUS_ONLINE  = "online"
STATUS_OFFLINE = "offline"
STATUS_UNKNOWN = "unknown"


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─── Device CRUD ─────────────────────────────────────────────────────────────

def create_device(data: dict) -> dict:
    """Insert a new device. Returns the created device as a dict."""
    now = _now_utc()
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO devices
               (name, target, device_type, location, description,
                monitoring_interval, is_monitoring_enabled,
                current_status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'unknown', ?, ?)""",
            (
                data["name"],
                data["target"],
                data.get("device_type", "Other"),
                data.get("location", ""),
                data.get("description", ""),
                data.get("monitoring_interval", 30),
                data.get("is_monitoring_enabled", 1),
                now, now,
            ),
        )
        device_id = cur.lastrowid

    device = get_device_by_id(device_id)
    log_event(
        EVT_DEVICE_ADDED,
        f"Device '{data['name']}' ({data['target']}) added.",
        device_id=device_id,
        severity=SEVERITY_INFO,
    )
    logger.info("Device created: id=%d target=%s", device_id, data["target"])
    return device


def get_device_by_id(device_id: int) -> dict | None:
    """Return a single device dict or None."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    return dict(row) if row else None


def get_device_by_target(target: str) -> dict | None:
    """Return the device with the given target or None."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM devices WHERE target = ?", (target.strip().lower(),)
        ).fetchone()
    return dict(row) if row else None


def get_all_devices(
    status: str | None = None,
    device_type: str | None = None,
    search: str | None = None,
    enabled_only: bool = False,
) -> list[dict]:
    """Return all devices matching optional filters."""
    query = "SELECT * FROM devices WHERE 1=1"
    params: list = []

    if status:
        query += " AND current_status = ?"
        params.append(status)
    if device_type:
        query += " AND device_type = ?"
        params.append(device_type)
    if search:
        query += " AND (name LIKE ? OR target LIKE ? OR location LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    if enabled_only:
        query += " AND is_monitoring_enabled = 1"

    query += " ORDER BY name ASC"

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def update_device(device_id: int, data: dict) -> dict | None:
    """Update device fields. Returns updated device or None if not found."""
    if not data:
        return get_device_by_id(device_id)

    now = _now_utc()
    sets = ", ".join(f"{k} = ?" for k in data.keys())
    values = list(data.values()) + [now, device_id]

    with get_db() as conn:
        cur = conn.execute(
            f"UPDATE devices SET {sets}, updated_at = ? WHERE id = ?", values
        )
    if cur.rowcount == 0:
        return None

    device = get_device_by_id(device_id)
    log_event(
        EVT_DEVICE_UPDATED,
        f"Device '{device['name']}' updated.",
        device_id=device_id,
        severity=SEVERITY_INFO,
    )
    return device


def delete_device(device_id: int) -> bool:
    """Delete a device and all associated probe_results (via CASCADE). Returns True on success."""
    device = get_device_by_id(device_id)
    if not device:
        return False

    with get_db() as conn:
        conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))

    log_event(
        EVT_DEVICE_DELETED,
        f"Device '{device['name']}' ({device['target']}) deleted.",
        device_id=None,  # device gone
        severity=SEVERITY_WARNING,
    )
    logger.info("Device deleted: id=%d target=%s", device_id, device["target"])
    return True


def set_monitoring_enabled(device_id: int, enabled: bool) -> dict | None:
    """Enable or disable monitoring for a device."""
    device = get_device_by_id(device_id)
    if not device:
        return None

    now = _now_utc()
    with get_db() as conn:
        conn.execute(
            "UPDATE devices SET is_monitoring_enabled = ?, updated_at = ? WHERE id = ?",
            (1 if enabled else 0, now, device_id),
        )

    evt_type = EVT_MONITORING_START if enabled else EVT_MONITORING_STOP
    msg = (
        f"Monitoring {'enabled' if enabled else 'disabled'} for '{device['name']}'."
    )
    log_event(evt_type, msg, device_id=device_id, severity=SEVERITY_INFO)
    return get_device_by_id(device_id)


# ─── Status Updates ───────────────────────────────────────────────────────────

def update_device_status(
    device_id: int,
    new_status: str,
    response_time_ms: float | None = None,
    last_success: bool = False,
) -> str:
    """
    Persist the new current_status. Returns the previous status string.
    Caller is responsible for event logging on transitions.
    """
    device = get_device_by_id(device_id)
    if not device:
        return STATUS_UNKNOWN

    previous_status = device["current_status"]
    now = _now_utc()

    extra: dict = {}
    if last_success:
        extra["last_success_at"] = now

    sets = "current_status = ?, last_checked_at = ?, updated_at = ?"
    values = [new_status, now, now]
    for k, v in extra.items():
        sets += f", {k} = ?"
        values.append(v)
    values.append(device_id)

    with get_db() as conn:
        conn.execute(f"UPDATE devices SET {sets} WHERE id = ?", values)

    return previous_status


# ─── Dashboard Counts ─────────────────────────────────────────────────────────

def get_status_counts() -> dict:
    """Return a dict with counts of online/offline/unknown/total devices."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT current_status, COUNT(*) AS cnt FROM devices GROUP BY current_status"
        ).fetchall()
    counts = {STATUS_ONLINE: 0, STATUS_OFFLINE: 0, STATUS_UNKNOWN: 0, "total": 0}
    for row in rows:
        status = row["current_status"]
        cnt = row["cnt"]
        if status in counts:
            counts[status] += cnt
        else:
            counts[status] = cnt
        counts["total"] += cnt
    return counts
