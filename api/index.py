"""
Vercel serverless entry point for Network Monitor.
Imports and exposes the Flask app created by the application factory.
"""

import sys
import os

# Ensure project root is on the path so imports resolve correctly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app

# Vercel looks for a module-level variable called `app`
app = create_app(env="production")
