"""
Network Monitor — Event Service
Creates and manages event log entries.
"""

import logging
from datetime import datetime, timezone
from backend.database import get_db

logger = logging.getLogger(__name__)

# ─── Severity Levels ─────────────────────────────────────────────────────────
SEVERITY_INFO    = "info"
SEVERITY_WARNING = "warning"
SEVERITY_ERROR   = "error"
SEVERITY_CRITICAL = "critical"

# ─── Event Types ─────────────────────────────────────────────────────────────
EVT_DEVICE_ONLINE    = "device_online"
EVT_DEVICE_OFFLINE   = "device_offline"
EVT_DEVICE_ADDED     = "device_added"
EVT_DEVICE_UPDATED   = "device_updated"
EVT_DEVICE_DELETED   = "device_deleted"
EVT_MONITORING_START = "monitoring_start"
EVT_MONITORING_STOP  = "monitoring_stop"
EVT_MONITORING_ERROR = "monitoring_error"
EVT_MANUAL_TEST      = "manual_test"
EVT_SETTINGS_CHANGED = "settings_changed"


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log_event(
    event_type: str,
    message: str,
    device_id: int | None = None,
    severity: str = SEVERITY_INFO,
) -> int:
    """
    Insert a new event record. Returns the new event ID.
    """
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO events (device_id, event_type, severity, message, created_at, is_read)
               VALUES (?, ?, ?, ?, ?, 0)""",
            (device_id, event_type, severity, message, _now_utc()),
        )
        return cur.lastrowid


def get_events(
    device_id: int | None = None,
    severity: str | None = None,
    event_type: str | None = None,
    is_read: bool | None = None,
    search: str | None = None,
    since_iso: str | None = None,
    until_iso: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    """Return events matching optional filters."""
    query = "SELECT e.*, d.name AS device_name FROM events e LEFT JOIN devices d ON e.device_id = d.id WHERE 1=1"
    params: list = []

    if device_id is not None:
        query += " AND e.device_id = ?"
        params.append(device_id)
    if severity:
        query += " AND e.severity = ?"
        params.append(severity)
    if event_type:
        query += " AND e.event_type = ?"
        params.append(event_type)
    if is_read is not None:
        query += " AND e.is_read = ?"
        params.append(1 if is_read else 0)
    if search:
        query += " AND (e.message LIKE ? OR d.name LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    if since_iso:
        query += " AND e.created_at >= ?"
        params.append(since_iso)
    if until_iso:
        query += " AND e.created_at <= ?"
        params.append(until_iso)

    query += " ORDER BY e.created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_unread_count() -> int:
    """Return the number of unread events."""
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM events WHERE is_read = 0").fetchone()
    return row["cnt"] if row else 0


def mark_event_read(event_id: int) -> bool:
    """Mark a single event as read. Returns True if found."""
    with get_db() as conn:
        cur = conn.execute("UPDATE events SET is_read = 1 WHERE id = ?", (event_id,))
    return cur.rowcount > 0


def mark_all_events_read() -> int:
    """Mark all events as read. Returns count updated."""
    with get_db() as conn:
        cur = conn.execute("UPDATE events SET is_read = 1 WHERE is_read = 0")
    return cur.rowcount
