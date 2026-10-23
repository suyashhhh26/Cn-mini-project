"""
Vercel serverless entry point for Network Monitor.

Forces DEMO_MODE so the app uses an in-memory SQLite database,
skips file-system logging, and skips background monitoring threads —
all required because Vercel's runtime has a read-only filesystem
and does not support persistent subprocess/threads.
"""

import sys
import os

# ── Must be set BEFORE importing app so create_app() sees it ──────────────────
os.environ.setdefault("DEMO_MODE", "1")

# Ensure project root is on the path so imports resolve correctly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app

# Vercel looks for a module-level variable called `app`
app = create_app(env="demo")
