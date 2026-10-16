"""
Network Monitor — Analytics Module
Computes statistics from stored probe results.
"""

import logging
from backend.database import get_db

logger = logging.getLogger(__name__)


def _time_filter_clause(since_iso: str | None, until_iso: str | None) -> tuple[str, list]:
    """Return a SQL WHERE fragment and params for time range filtering."""
    clause = ""
    params: list = []
    if since_iso:
        clause += " AND checked_at >= ?"
        params.append(since_iso)
    if until_iso:
        clause += " AND checked_at <= ?"
        params.append(until_iso)
    return clause, params


def get_device_analytics(
    device_id: int | None,
    since_iso: str | None = None,
    until_iso: str | None = None,
) -> dict:
    """
    Compute probe-based analytics for one device or all devices combined.

    Returns a dict with:
        total_probes, successful_probes, failed_probes,
        availability_pct, avg_response_ms, min_response_ms, max_response_ms,
        packet_loss_pct, total_downtime_estimates (count of consecutive offline probes)
    """
    time_clause, time_params = _time_filter_clause(since_iso, until_iso)

    if device_id is not None:
        device_filter = " AND device_id = ?"
        id_param = [device_id]
    else:
        device_filter = ""
        id_param = []

    base_where = f" WHERE 1=1{device_filter}{time_clause}"
    all_params = id_param + time_params

    with get_db() as conn:
        # Aggregate statistics
        agg = conn.execute(
            f"""SELECT
                COUNT(*) AS total_probes,
                SUM(CASE WHEN is_reachable=1 THEN 1 ELSE 0 END) AS successful_probes,
                SUM(CASE WHEN is_reachable=0 THEN 1 ELSE 0 END) AS failed_probes,
                AVG(CASE WHEN is_reachable=1 AND response_time_ms IS NOT NULL
                         THEN response_time_ms ELSE NULL END) AS avg_response_ms,
                MIN(CASE WHEN is_reachable=1 AND response_time_ms IS NOT NULL
                         THEN response_time_ms ELSE NULL END) AS min_response_ms,
                MAX(CASE WHEN is_reachable=1 AND response_time_ms IS NOT NULL
                         THEN response_time_ms ELSE NULL END) AS max_response_ms
            FROM probe_results{base_where}""",
            all_params,
        ).fetchone()

    total     = agg["total_probes"]   or 0
    success   = agg["successful_probes"] or 0
    failed    = agg["failed_probes"]  or 0
    avg_rt    = round(agg["avg_response_ms"],  2) if agg["avg_response_ms"] is not None else None
    min_rt    = round(agg["min_response_ms"],  2) if agg["min_response_ms"] is not None else None
    max_rt    = round(agg["max_response_ms"],  2) if agg["max_response_ms"] is not None else None

    availability_pct = round(success / total * 100, 2) if total > 0 else None
    packet_loss_pct  = round(failed  / total * 100, 2) if total > 0 else None

    return {
        "total_probes":       total,
        "successful_probes":  success,
        "failed_probes":      failed,
        "availability_pct":   availability_pct,
        "packet_loss_pct":    packet_loss_pct,
        "avg_response_ms":    avg_rt,
        "min_response_ms":    min_rt,
        "max_response_ms":    max_rt,
    }


def get_response_time_series(
    device_id: int,
    since_iso: str | None = None,
    until_iso: str | None = None,
    limit: int = 200,
) -> list[dict]:
    """
    Return a time-ordered list of {checked_at, response_time_ms, is_reachable}
    for chart rendering.
    """
    time_clause, time_params = _time_filter_clause(since_iso, until_iso)
    with get_db() as conn:
        rows = conn.execute(
            f"""SELECT checked_at, response_time_ms, is_reachable
                FROM probe_results
                WHERE device_id = ?{time_clause}
                ORDER BY checked_at DESC
                LIMIT ?""",
            [device_id] + time_params + [limit],
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def get_availability_trend(
    device_id: int | None,
    since_iso: str | None = None,
    until_iso: str | None = None,
    bucket: str = "hour",   # "hour" | "day"
) -> list[dict]:
    """
    Return bucketed availability percentages for trend chart.
    """
    if bucket == "day":
        fmt = "%Y-%m-%d"
        trunc = "strftime('%Y-%m-%d', checked_at)"
    else:
        fmt = "%Y-%m-%dT%H:00:00Z"
        trunc = "strftime('%Y-%m-%dT%H:00:00Z', checked_at)"

    time_clause, time_params = _time_filter_clause(since_iso, until_iso)
    device_clause = " AND device_id = ?" if device_id is not None else ""
    id_param = [device_id] if device_id is not None else []

    with get_db() as conn:
        rows = conn.execute(
            f"""SELECT
                {trunc} AS bucket,
                COUNT(*) AS total,
                SUM(CASE WHEN is_reachable=1 THEN 1 ELSE 0 END) AS successful
            FROM probe_results
            WHERE 1=1{device_clause}{time_clause}
            GROUP BY bucket
            ORDER BY bucket ASC""",
            id_param + time_params,
        ).fetchall()

    result = []
    for r in rows:
        t = r["total"] or 0
        s = r["successful"] or 0
        result.append({
            "bucket": r["bucket"],
            "availability_pct": round(s / t * 100, 1) if t > 0 else None,
            "total": t,
            "successful": s,
        })
    return result


def get_recent_probes(device_id: int, limit: int = 50) -> list[dict]:
    """Return the most recent probe results for a device."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM probe_results
               WHERE device_id = ?
               ORDER BY checked_at DESC
               LIMIT ?""",
            (device_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_overall_avg_response_ms() -> float | None:
    """Return the average response time across all recent probes (last 24 h)."""
    with get_db() as conn:
        row = conn.execute(
            """SELECT AVG(response_time_ms) AS avg_ms
               FROM probe_results
               WHERE is_reachable = 1
                 AND response_time_ms IS NOT NULL
                 AND checked_at >= strftime('%Y-%m-%dT%H:%M:%SZ','now','-24 hours')"""
        ).fetchone()
    val = row["avg_ms"] if row else None
    return round(val, 2) if val is not None else None
