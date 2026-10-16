"""
Network Monitor — Application Configuration
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(exist_ok=True)


class Config:
    # ── Flask ────────────────────────────────────────────────────────────
    SECRET_KEY = os.environ.get("SECRET_KEY", os.urandom(32).hex())
    DEBUG = False
    TESTING = False

    # ── Database ─────────────────────────────────────────────────────────
    DATABASE_PATH = str(INSTANCE_DIR / "network_monitor.db")

    # ── Monitoring ───────────────────────────────────────────────────────
    MIN_MONITORING_INTERVAL = 5        # seconds
    MAX_MONITORING_INTERVAL = 300      # seconds
    DEFAULT_MONITORING_INTERVAL = 30   # seconds
    DEFAULT_PING_TIMEOUT = 5           # seconds
    MAX_CONCURRENT_PROBES = 10
    MANUAL_TEST_RATE_LIMIT = 10        # seconds between manual tests per device

    # ── Data Retention ───────────────────────────────────────────────────
    DATA_RETENTION_DAYS = 30           # days to keep probe results

    # ── Dashboard ────────────────────────────────────────────────────────
    DASHBOARD_REFRESH_INTERVAL = 5000  # milliseconds

    # ── Logging ──────────────────────────────────────────────────────────
    LOG_LEVEL = "INFO"
    LOG_FILE = str(INSTANCE_DIR / "network_monitor.log")


class DevelopmentConfig(Config):
    DEBUG = True
    LOG_LEVEL = "DEBUG"


class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    DATABASE_PATH = ":memory:"


class ProductionConfig(Config):
    DEBUG = False


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}


def get_config(env: str | None = None) -> Config:
    env = env or os.environ.get("FLASK_ENV", "default")
    return CONFIG_MAP.get(env, DevelopmentConfig)()
