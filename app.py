"""
Network Monitor — Application Entry Point
"""

import logging
import os
import sys
from pathlib import Path

from flask import Flask, render_template, send_from_directory


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

    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(cfg)

    # ── File logging ──────────────────────────────────────────────────────────
    if not app.testing:
        fh = logging.FileHandler(cfg.LOG_FILE, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        fh.setLevel(cfg.LOG_LEVEL)
        logging.getLogger().addHandler(fh)

    # ── Database ──────────────────────────────────────────────────────────────
    from backend.database import init_db
    init_db(cfg.DATABASE_PATH)

    # ── API Blueprint ─────────────────────────────────────────────────────────
    from backend.routes import api_bp
    app.register_blueprint(api_bp)

    # ── Background Monitoring ─────────────────────────────────────────────────
    if not app.testing:
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
