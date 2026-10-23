"""
Network Monitor — Application Entry Point
"""

import logging
import os
import sys
from pathlib import Path

from flask import Flask, render_template, send_from_directory, jsonify


if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

# ── Logging Setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def create_app(env: str | None = None) -> Flask:
    """Application factory."""
    from config import get_config
    cfg = get_config(env)

    # ── Demo mode detection ───────────────────────────────────────────────────
    demo_mode: bool = os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes")
    if demo_mode:
        logger.info("DEMO MODE enabled — using in-memory DB, mock ping, no background threads.")

    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(cfg)
    app.config["DEMO_MODE"] = demo_mode

    # ── File logging (skip in demo/serverless) ────────────────────────────────
    if not app.testing and not demo_mode:
        fh = logging.FileHandler(cfg.LOG_FILE, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        fh.setLevel(cfg.LOG_LEVEL)
        logging.getLogger().addHandler(fh)

    # ── Database ──────────────────────────────────────────────────────────────
    from backend.database import init_db
    db_path = ":memory:" if demo_mode else cfg.DATABASE_PATH
    init_db(db_path)

    # ── Demo data seed ────────────────────────────────────────────────────────
    if demo_mode:
        from backend.demo_data import seed_demo_data, mock_ping
        import backend.ping_service as _ping_mod
        _ping_mod.ping = mock_ping          # monkey-patch real ping → mock
        seed_demo_data(db_path)

    # ── API Blueprint ─────────────────────────────────────────────────────────
    from backend.routes import api_bp
    app.register_blueprint(api_bp)

    # ── Background Monitoring (disabled in demo / serverless) ─────────────────
    if not app.testing and not demo_mode:
        from backend.monitoring import start_monitoring
        start_monitoring(
            max_workers=cfg.MAX_CONCURRENT_PROBES,
            ping_timeout=cfg.DEFAULT_PING_TIMEOUT,
        )

    # ── Frontend Routes ───────────────────────────────────────────────────────
    @app.get("/")
    def dashboard():
        return render_template("dashboard.html")

    @app.get("/devices")
    def devices():
        return render_template("devices.html")

    @app.get("/devices/<int:device_id>")
    def device_detail(device_id: int):
        return render_template("device_details.html", device_id=device_id)

    @app.get("/analytics")
    def analytics():
        return render_template("analytics.html")

    @app.get("/events")
    def events():
        return render_template("events.html")

    @app.get("/topology")
    def topology():
        return render_template("topology.html")

    @app.get("/settings")
    def settings():
        return render_template("settings.html")

    @app.get("/about")
    def about():
        return render_template("about.html")

    # ── Error Handlers ────────────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        from flask import request
        if request.path.startswith("/api/"):
            from flask import jsonify
            return jsonify({"success": False, "message": "Endpoint not found."}), 404
        return render_template("dashboard.html"), 404

    @app.errorhandler(500)
    def internal_error(e):
        logger.exception("Internal server error")
        from flask import request, jsonify
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "message": "Internal server error."}), 500
        return render_template("dashboard.html"), 500

    logger.info("Network Monitor application ready.")
    return app


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV", "development") == "development"
    logger.info("Starting Network Monitor on http://127.0.0.1:%d", port)
    # use_reloader=False prevents duplicate monitoring threads on file change
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False)
