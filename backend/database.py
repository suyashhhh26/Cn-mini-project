"""
Network Monitor — Database Layer
Handles SQLite initialization, connection management, and schema creation.
"""

import sqlite3
import logging
import uuid
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

_db_path: str = ":memory:"
_keepalive_conn: sqlite3.Connection | None = None


def init_db(db_path: str) -> None:
    """Set the database path and create tables if they don't exist."""
    global _db_path, _keepalive_conn
    
    if _keepalive_conn is not None:
        try:
            _keepalive_conn.close()
        except Exception:
            pass
        _keepalive_conn = None

    if db_path == ":memory:":
        mem_id = uuid.uuid4().hex
        _db_path = f"file:netmon_{mem_id}?mode=memory&cache=shared"
        _keepalive_conn = sqlite3.connect(_db_path, uri=True, check_same_thread=False)
    else:
        _db_path = db_path
        if not db_path.startswith("file:"):
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    _create_tables()
    logger.info("Database initialized at: %s", db_path)


def get_connection() -> sqlite3.Connection:
    """Return a new SQLite connection with row_factory set."""
    is_uri = _db_path.startswith("file:")
    conn = sqlite3.connect(_db_path, uri=is_uri, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if not is_uri:
        conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@contextmanager
def get_db():
    """Context manager for database connections with automatic commit/rollback."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _create_tables() -> None:
    """Create all required tables and indexes."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS devices (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                name                TEXT    NOT NULL,
                target              TEXT    NOT NULL,
                device_type         TEXT    NOT NULL DEFAULT 'Other',
                location            TEXT    NOT NULL DEFAULT '',
                description         TEXT    NOT NULL DEFAULT '',
                monitoring_interval INTEGER NOT NULL DEFAULT 30,
                is_monitoring_enabled INTEGER NOT NULL DEFAULT 1,
                current_status      TEXT    NOT NULL DEFAULT 'unknown',
                last_checked_at     TEXT,
                last_success_at     TEXT,
                created_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                updated_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_devices_target ON devices(target);

            CREATE TABLE IF NOT EXISTS probe_results (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id       INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
                checked_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                is_reachable    INTEGER NOT NULL DEFAULT 0,
                response_time_ms REAL,
                error_category  TEXT,
                error_message   TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_probe_device_time
                ON probe_results(device_id, checked_at DESC);

            CREATE TABLE IF NOT EXISTS events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id   INTEGER REFERENCES devices(id) ON DELETE SET NULL,
                event_type  TEXT    NOT NULL,
                severity    TEXT    NOT NULL DEFAULT 'info',
                message     TEXT    NOT NULL,
                created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                is_read     INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_events_device  ON events(device_id);

            CREATE TABLE IF NOT EXISTS settings (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                setting_key   TEXT NOT NULL UNIQUE,
                setting_value TEXT NOT NULL
            );

            INSERT OR IGNORE INTO settings (setting_key, setting_value) VALUES
                ('default_monitoring_interval', '30'),
                ('default_ping_timeout',        '5'),
                ('max_concurrent_probes',        '10'),
                ('data_retention_days',          '30'),
                ('dashboard_refresh_interval',   '5000');
        """)

        if not _db_path.startswith("file:"):
            conn.execute("""
                INSERT OR IGNORE INTO devices (name, target, device_type, location, description, monitoring_interval) VALUES
                    ('Localhost Loopback', '127.0.0.1', 'Computer', 'Local Machine', 'Host loopback interface for latency baseline', 15),
                    ('Google Public DNS', '8.8.8.8', 'Server', 'Global Anycast', 'Primary Google DNS resolver', 30),
                    ('Cloudflare DNS', '1.1.1.1', 'Server', 'Global Anycast', 'Cloudflare security and fast resolver', 30);
            """)
    logger.info("Database tables created / verified.")


def get_setting(key: str, default: str = "") -> str:
    """Read a setting value from the settings table."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT setting_value FROM settings WHERE setting_key = ?", (key,)
        ).fetchone()
    return row["setting_value"] if row else default


def set_setting(key: str, value: str) -> None:
    """Upsert a setting value."""
    with get_db() as conn:
        conn.execute(
            """INSERT INTO settings (setting_key, setting_value) VALUES (?, ?)
               ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value""",
            (key, value),
        )


def purge_old_probe_results(retention_days: int) -> int:
    """Delete probe results older than retention_days. Returns number of deleted rows."""
    with get_db() as conn:
        cur = conn.execute(
            """DELETE FROM probe_results
               WHERE checked_at < strftime('%Y-%m-%dT%H:%M:%SZ','now',?)""",
            (f"-{retention_days} days",),
        )
    return cur.rowcount
