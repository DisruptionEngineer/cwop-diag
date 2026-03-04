"""
Vercel serverless entry point for CWOP-Diag.
Runs in demo mode with simulated OBD-II data.
"""

import sys
import os

# Add parent directory to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use /tmp for SQLite on Vercel (filesystem is read-only elsewhere)
os.environ.setdefault("CWOP_DB_PATH", "/tmp/cwop_diag.db")

from app import app, reset_session
from obd_reader import OBDReader
from dtc_database import DTCDatabase
from llm_engine import LLMEngine
from cwop_engine import CWOPEngine
import database as db
import app as app_module

# Initialize all components in demo mode (runs once per cold start)
if app_module.dtc_db is None:
    db.init_db()
    app_module.dtc_db = DTCDatabase()
    app_module.cwop = CWOPEngine(total_budget=1500)
    app_module.llm = LLMEngine(backend="demo")
    app_module.obd_reader = OBDReader(port="/dev/null", demo=True)
    app_module.obd_reader.connect()
    app_module.obd_reader.start_polling(interval=2.0)
    reset_session()

# Vercel expects the WSGI app
app = app
