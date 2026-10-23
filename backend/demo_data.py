"""
Network Monitor — Demo Mode Data & Mock Ping
============================================
When DEMO_MODE=true (set automatically on Vercel), this module:
  - Pre-seeds the in-memory SQLite database with realistic sample devices,
    probe results, and events so every page of the UI is fully populated.
  - Replaces the real system ping with a random-walk mock that returns
    plausible latency values without requiring ICMP access.
"""

import random
import time
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── Mock PingResult (mirrors ping_service.PingResult) ─────────────────────────

@dataclass
class PingResult:
    is_reachable: bool
    response_time_ms: float | None
    error_category: str | None
    error_message: str | None
    raw_output: str = ""


# Per-target state for the random-walk mock
_mock_state: dict[str, dict] = {}


def mock_ping(target: str, timeout_sec: int = 5, count: int = 1) -> PingResult:
    """
    Simulate a ping with realistic random-walk latency.
    Occasionally simulates brief outages to make the demo lively.
    """
    state = _mock_state.setdefault(target, {
        "base_ms": random.uniform(5.0, 120.0),
        "offline_until": 0.0,
    })

    now = time.monotonic()

    # 2 % chance to trigger a short outage (5-30 s)
    if random.random() < 0.02 and now > state["offline_until"]:
        state["offline_until"] = now + random.uniform(5, 30)

    if now < state["offline_until"]:
        return PingResult(
            is_reachable=False,
            response_time_ms=None,
            error_category="timeout",
            error_message="No response received (simulated outage).",
        )

    # Random walk on the base latency
    jitter = random.gauss(0, state["base_ms"] * 0.15)
    rtt = max(0.5, state["base_ms"] + jitter)
    state["base_ms"] = max(0.5, state["base_ms"] + random.gauss(0, 1.0))

    return PingResult(
        is_reachable=True,
        response_time_ms=round(rtt, 2),
        error_category=None,
        error_message=None,
    )


# ── Demo seed data ─────────────────────────────────────────────────────────────

_DEMO_DEVICES = [
    # (name, target, device_type, location, description, interval)
    ("Localhost Loopback",  "127.0.0.1",     "Computer", "Local Machine",    "Host loopback for latency baseline",        15),
    ("Google Public DNS",   "8.8.8.8",       "Server",   "Global Anycast",   "Primary Google DNS resolver",               30),
    ("Cloudflare DNS",      "1.1.1.1",       "Server",   "Global Anycast",   "Cloudflare fast & privacy-first resolver",  30),
    ("OpenDNS",             "208.67.222.222","Server",   "San Jose, CA",     "Cisco OpenDNS resolver",                    60),
    ("Home Router",         "192.168.1.1",   "Router",   "Home Office",      "Default gateway / LAN router",              20),
    ("Office Switch",       "10.0.0.2",      "Switch",   "Server Room",      "Core layer-2 switch",                       30),
    ("Quad9 DNS",           "9.9.9.9",       "Server",   "Global Anycast",   "Quad9 security-filtering DNS",              60),
    ("Primary Web Server",  "93.184.216.34", "Server",   "Ashburn, VA",      "example.com web server",                    60),
    ("NTP Pool Server",     "216.239.35.0",  "Server",   "Global",           "Google public NTP server",                  120),
    ("Dev Workstation",     "10.0.0.50",     "Computer", "Engineering Desk", "Main development machine",                  30),
    ("NAS Storage",         "10.0.0.100",    "Other",    "Server Room",      "Network-attached storage array",            60),
    ("IP Camera Front",     "10.0.0.150",    "Other",    "Front Door",       "Security camera — entrance",                120),
]

_DEMO_EVENTS_TEMPLATES = [
    ("device_online",  "info",    "{name} is now ONLINE (avg {rt:.0f} ms)."),
    ("device_offline", "warning", "{name} went OFFLINE. Reason: timeout."),
    ("device_online",  "info",    "{name} recovered. Latency {rt:.0f} ms."),
    ("monitoring_started", "info","Monitoring engine started in demo mode."),
    ("device_offline", "warning", "{name} is not responding (3 consecutive failures)."),
    ("device_online",  "info",    "{name} is back ONLINE after {down:.0f} minutes down."),
]


def seed_demo_data(db_path: str) -> None:
    """
    Insert demo devices, probe history (last 7 days), and events into the DB.
    Safe to call multiple times — uses INSERT OR IGNORE / INSERT OR REPLACE.
    """
    from backend.database import get_db

    logger.info("Seeding demo data…")

    with get_db() as conn:
        # Insert devices
        for name, target, dtype, location, desc, interval in _DEMO_DEVICES:
            conn.execute(
                """INSERT OR IGNORE INTO devices
                   (name, target, device_type, location, description, monitoring_interval)
                   VALUES (?,?,?,?,?,?)""",
                (name, target, dtype, location, desc, interval),
            )

        # Fetch inserted IDs
        rows = conn.execute(
            "SELECT id, target FROM devices ORDER BY id"
        ).fetchall()
        device_ids = [(r["id"], r["target"]) for r in rows]

        now_utc = datetime.now(timezone.utc)

        # Generate probe history for 7 days
        for device_id, target in device_ids:
            base_ms = random.uniform(5.0, 100.0)
            offline_until: datetime | None = None
            t = now_utc - timedelta(days=7)

            while t < now_utc:
                # Random interval between 15–120 s per probe
                step = timedelta(seconds=random.randint(15, 120))
                t += step

                if offline_until and t < offline_until:
                    is_reachable = False
                    rt = None
                    err_cat = "timeout"
                    err_msg = "No response received."
                elif random.random() < 0.02:
                    # trigger an outage
                    offline_until = t + timedelta(minutes=random.randint(2, 20))
                    is_reachable = False
                    rt = None
                    err_cat = "timeout"
                    err_msg = "No response received."
                else:
                    offline_until = None
                    jitter = random.gauss(0, base_ms * 0.12)
                    rt = max(0.3, round(base_ms + jitter, 2))
                    base_ms = max(0.3, base_ms + random.gauss(0, 0.5))
                    is_reachable = True
                    err_cat = None
                    err_msg = None

                conn.execute(
                    """INSERT INTO probe_results
                       (device_id, checked_at, is_reachable, response_time_ms,
                        error_category, error_message)
                       VALUES (?,?,?,?,?,?)""",
                    (
                        device_id,
                        t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        1 if is_reachable else 0,
                        rt,
                        err_cat,
                        err_msg,
                    ),
                )

        # Update device current_status from latest probe
        conn.executescript("""
            UPDATE devices SET current_status = 'online',
                last_checked_at = (
                    SELECT checked_at FROM probe_results
                    WHERE device_id = devices.id ORDER BY checked_at DESC LIMIT 1
                ),
                last_success_at = (
                    SELECT checked_at FROM probe_results
                    WHERE device_id = devices.id AND is_reachable = 1
                    ORDER BY checked_at DESC LIMIT 1
                )
            WHERE id IN (
                SELECT device_id FROM probe_results
                WHERE is_reachable = 1
                ORDER BY checked_at DESC
            );

            UPDATE devices SET current_status = 'offline'
            WHERE id IN (
                SELECT device_id FROM (
                    SELECT device_id, is_reachable,
                           ROW_NUMBER() OVER (PARTITION BY device_id ORDER BY checked_at DESC) AS rn
                    FROM probe_results
                ) WHERE rn = 1 AND is_reachable = 0
            );
        """)

        # Seed events
        for i, (device_id, target) in enumerate(device_ids[:6]):
            name = _DEMO_DEVICES[i][0]
            evt_type, severity, tmpl = random.choice(_DEMO_EVENTS_TEMPLATES)
            msg = tmpl.format(name=name, rt=random.uniform(5, 80), down=random.uniform(2, 15))
            ts = now_utc - timedelta(hours=random.uniform(0, 48))
            conn.execute(
                """INSERT INTO events (device_id, event_type, severity, message, created_at)
                   VALUES (?,?,?,?,?)""",
                (device_id, evt_type, severity, msg, ts.strftime("%Y-%m-%dT%H:%M:%SZ")),
            )

        conn.execute(
            """INSERT INTO events (device_id, event_type, severity, message, created_at)
               VALUES (NULL,'monitoring_started','info',
                       'Network Monitor is running in read-only demo mode on Vercel.',
                       ?)""",
            (now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),),
        )

    logger.info("Demo data seeded: %d devices.", len(device_ids))
