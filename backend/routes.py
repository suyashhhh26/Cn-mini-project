"""
Network Monitor — REST API Routes
All /api/* endpoints.
"""

import logging
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify, current_app

from backend.models import (
    create_device, get_device_by_id, get_device_by_target,
    get_all_devices, update_device, delete_device,
    set_monitoring_enabled, get_status_counts,
    STATUS_ONLINE, STATUS_OFFLINE, STATUS_UNKNOWN,
)
from backend.analytics import (
    get_device_analytics, get_response_time_series,
    get_availability_trend, get_recent_probes,
    get_overall_avg_response_ms,
)
from backend.event_service import (
    get_events, get_unread_count, mark_event_read, mark_all_events_read,
)
from backend.database import get_db, get_setting, set_setting
from backend.validators import (
    validate_device_payload, ValidationError,
    validate_setting, SETTINGS_SCHEMA,
)
from backend.monitoring import get_engine

logger = logging.getLogger(__name__)
api_bp = Blueprint("api", __name__, url_prefix="/api")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _ok(data=None, **kwargs):
    payload = {"success": True}
    if data is not None:
        payload["data"] = data
    payload.update(kwargs)
    return jsonify(payload), 200


def _created(data=None, **kwargs):
    payload = {"success": True}
    if data is not None:
        payload["data"] = data
    payload.update(kwargs)
    return jsonify(payload), 201


def _error(message: str, status: int = 400, field: str | None = None):
    payload = {"success": False, "message": message}
    if field:
        payload["field"] = field
    return jsonify(payload), status


def _not_found(entity: str = "Resource"):
    return _error(f"{entity} not found.", 404)


def _time_range_from_request() -> tuple[str | None, str | None]:
    """Parse ?range=1h|24h|7d|custom&since=ISO&until=ISO from query string."""
    range_param = request.args.get("range", "24h")
    now_utc = datetime.now(timezone.utc)

    since_iso: str | None = None
    until_iso: str | None = request.args.get("until")

    if range_param == "1h":
        since_iso = (now_utc - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    elif range_param == "24h":
        since_iso = (now_utc - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    elif range_param == "7d":
        since_iso = (now_utc - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    elif range_param == "30d":
        since_iso = (now_utc - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    elif range_param == "custom":
        since_iso = request.args.get("since")

    return since_iso, until_iso


# ─── Health ───────────────────────────────────────────────────────────────────

@api_bp.get("/health")
def health():
    engine = get_engine()
    return _ok({
        "status": "ok",
        "monitoring_running": engine.is_running,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })


# ─── Dashboard ────────────────────────────────────────────────────────────────

@api_bp.get("/dashboard")
def dashboard():
    counts = get_status_counts()
    avg_rt = get_overall_avg_response_ms()
    total  = counts.get("total", 0)
    online = counts.get(STATUS_ONLINE, 0)
    availability_pct = round(online / total * 100, 1) if total > 0 else 0.0

    recent_events = get_events(limit=20)
    devices       = get_all_devices()

    # Enrich devices with latest probe response time
    since_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    analytics_cache: dict[int, dict] = {}
    for d in devices:
        a = get_device_analytics(d["id"], since_iso=since_24h)
        analytics_cache[d["id"]] = a

    engine = get_engine()
    return _ok({
        "counts": counts,
        "avg_response_ms": avg_rt,
        "availability_pct": availability_pct,
        "recent_events": recent_events,
        "devices": devices,
        "analytics": analytics_cache,
        "unread_events": get_unread_count(),
        "monitoring_running": engine.is_running,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })


# ─── Devices ──────────────────────────────────────────────────────────────────

@api_bp.get("/devices")
def list_devices():
    status      = request.args.get("status")
    device_type = request.args.get("type")
    search      = request.args.get("q")
    devices = get_all_devices(status=status, device_type=device_type, search=search)
    return _ok(devices)


@api_bp.post("/devices")
def add_device():
    data = request.get_json(silent=True)
    if not data:
        return _error("Request body must be JSON.", 400)

    try:
        cleaned = validate_device_payload(data)
    except ValidationError as exc:
        return _error(exc.message, 422, field=exc.field)

    # Duplicate check
    existing = get_device_by_target(cleaned["target"])
    if existing:
        return _error(
            f"A device with target '{cleaned['target']}' already exists (ID {existing['id']}).",
            409,
            field="target",
        )

    device = create_device(cleaned)
    return _created(device)


@api_bp.get("/devices/<int:device_id>")
def get_device(device_id: int):
    device = get_device_by_id(device_id)
    if not device:
        return _not_found("Device")
    return _ok(device)


@api_bp.put("/devices/<int:device_id>")
def edit_device(device_id: int):
    device = get_device_by_id(device_id)
    if not device:
        return _not_found("Device")

    data = request.get_json(silent=True)
    if not data:
        return _error("Request body must be JSON.", 400)

    try:
        cleaned = validate_device_payload(data, is_update=True)
    except ValidationError as exc:
        return _error(exc.message, 422, field=exc.field)

    # If target changed, check uniqueness
    if "target" in cleaned and cleaned["target"] != device["target"]:
        existing = get_device_by_target(cleaned["target"])
        if existing and existing["id"] != device_id:
            return _error(
                f"Target '{cleaned['target']}' is already used by device ID {existing['id']}.",
                409,
                field="target",
            )

    updated = update_device(device_id, cleaned)
    return _ok(updated)


@api_bp.delete("/devices/<int:device_id>")
def remove_device(device_id: int):
    if not get_device_by_id(device_id):
        return _not_found("Device")
    delete_device(device_id)
    return _ok({"deleted_id": device_id})


@api_bp.post("/devices/<int:device_id>/test")
def manual_test(device_id: int):
    device = get_device_by_id(device_id)
    if not device:
        return _not_found("Device")

    engine = get_engine()
    result = engine.manual_test(
        device_id=device_id,
        target=device["target"],
        device_name=device["name"],
        rate_limit_sec=int(get_setting("manual_test_rate_limit", "10")),
    )

    if result.get("rate_limited"):
        return jsonify({"success": False, **result}), 429

    return _ok(result)


@api_bp.post("/devices/<int:device_id>/monitoring")
def toggle_monitoring(device_id: int):
    data = request.get_json(silent=True) or {}
    enabled = data.get("enabled")
    if enabled is None:
        return _error("'enabled' field (true/false) is required.", 400)

    device = set_monitoring_enabled(device_id, bool(enabled))
    if not device:
        return _not_found("Device")
    return _ok(device)


@api_bp.get("/devices/<int:device_id>/history")
def device_history(device_id: int):
    if not get_device_by_id(device_id):
        return _not_found("Device")

    since, until = _time_range_from_request()
    analytics    = get_device_analytics(device_id, since_iso=since, until_iso=until)
    time_series  = get_response_time_series(device_id, since_iso=since, until_iso=until, limit=200)
    trend        = get_availability_trend(device_id, since_iso=since, until_iso=until)
    probes       = get_recent_probes(device_id, limit=50)
    events       = get_events(device_id=device_id, limit=50)

    return _ok({
        "analytics":   analytics,
        "time_series": time_series,
        "trend":       trend,
        "probes":      probes,
        "events":      events,
    })


# ─── Events ───────────────────────────────────────────────────────────────────

@api_bp.get("/events")
def list_events():
    device_id  = request.args.get("device_id", type=int)
    severity   = request.args.get("severity")
    event_type = request.args.get("event_type")
    search     = request.args.get("q")
    since, until = _time_range_from_request()
    limit      = min(request.args.get("limit", 100, type=int), 500)
    offset     = request.args.get("offset", 0, type=int)

    is_read_str = request.args.get("is_read")
    is_read: bool | None = None
    if is_read_str is not None:
        is_read = is_read_str.lower() in ("1", "true", "yes")

    events = get_events(
        device_id=device_id,
        severity=severity,
        event_type=event_type,
        is_read=is_read,
        search=search,
        since_iso=since,
        until_iso=until,
        limit=limit,
        offset=offset,
    )
    return _ok(events, unread_count=get_unread_count())


@api_bp.patch("/events/<int:event_id>/read")
def mark_read(event_id: int):
    if not mark_event_read(event_id):
        return _not_found("Event")
    return _ok({"event_id": event_id})


@api_bp.post("/events/read-all")
def read_all_events():
    count = mark_all_events_read()
    return _ok({"marked_read": count})


# ─── Analytics ────────────────────────────────────────────────────────────────

@api_bp.get("/analytics")
def analytics():
    device_id_str = request.args.get("device_id")
    device_id: int | None = int(device_id_str) if device_id_str else None
    since, until = _time_range_from_request()

    stats  = get_device_analytics(device_id, since_iso=since, until_iso=until)
    trend  = get_availability_trend(device_id, since_iso=since, until_iso=until)

    if device_id:
        ts = get_response_time_series(device_id, since_iso=since, until_iso=until)
    else:
        ts = []

    return _ok({
        "analytics":        stats,
        "availability_trend": trend,
        "time_series":      ts,
    })


# ─── Settings ─────────────────────────────────────────────────────────────────

@api_bp.get("/settings")
def get_settings():
    with get_db() as conn:
        rows = conn.execute("SELECT setting_key, setting_value FROM settings").fetchall()
    return _ok({r["setting_key"]: r["setting_value"] for r in rows})


@api_bp.put("/settings")
def update_settings():
    data = request.get_json(silent=True)
    if not data:
        return _error("Request body must be JSON.", 400)

    errors = {}
    for key, value in data.items():
        ok, msg = validate_setting(key, str(value))
        if not ok:
            errors[key] = msg

    if errors:
        return jsonify({"success": False, "errors": errors}), 422

    for key, value in data.items():
        if key in SETTINGS_SCHEMA:
            set_setting(key, str(value))

    return _ok({"message": "Settings updated."})
