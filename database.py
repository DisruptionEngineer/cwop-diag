"""
SQLite persistence layer for CWOP-Diag.
Stores service history, sensor trends, and vehicle records.
All data persists across restarts — no more lost sessions.
"""

import os
import json
import sqlite3
import time
from contextlib import contextmanager

DB_PATH = os.environ.get("CWOP_DB_PATH", "data/cwop_diag.db")


def _ensure_dir():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Create all tables if they don't exist."""
    _ensure_dir()
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS vehicles (
                vin TEXT PRIMARY KEY,
                year INTEGER,
                make TEXT,
                model TEXT,
                engine TEXT,
                trim TEXT,
                first_seen REAL,
                last_seen REAL,
                total_sessions INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                vin TEXT,
                status TEXT DEFAULT 'idle',
                dtcs TEXT DEFAULT '[]',
                diagnosis_tech TEXT DEFAULT '',
                diagnosis_customer TEXT DEFAULT '',
                health_score INTEGER DEFAULT 0,
                health_breakdown TEXT DEFAULT '{}',
                estimate_diag REAL DEFAULT 0,
                estimate_parts REAL DEFAULT 0,
                estimate_labor REAL DEFAULT 0,
                estimate_total REAL DEFAULT 0,
                payment_status TEXT DEFAULT 'none',
                payment_amount REAL DEFAULT 0,
                payment_stripe_id TEXT,
                created_at REAL,
                completed_at REAL,
                FOREIGN KEY (vin) REFERENCES vehicles(vin)
            );

            CREATE TABLE IF NOT EXISTS sensor_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                timestamp REAL,
                rpm REAL,
                coolant_temp REAL,
                engine_load REAL,
                throttle_pos REAL,
                short_fuel_trim_1 REAL,
                long_fuel_trim_1 REAL,
                short_fuel_trim_2 REAL,
                long_fuel_trim_2 REAL,
                maf REAL,
                intake_temp REAL,
                o2_voltage REAL,
                timing_advance REAL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );

            CREATE INDEX IF NOT EXISTS idx_sensor_session ON sensor_log(session_id);
            CREATE INDEX IF NOT EXISTS idx_sensor_time ON sensor_log(timestamp);
            CREATE INDEX IF NOT EXISTS idx_sessions_vin ON sessions(vin);
            CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at);
        """)


# ─── Vehicle Operations ───

def upsert_vehicle(vin, year=None, make=None, model=None, engine=None, trim=None):
    """Insert or update a vehicle record."""
    now = time.time()
    with get_db() as db:
        existing = db.execute("SELECT * FROM vehicles WHERE vin = ?", (vin,)).fetchone()
        if existing:
            db.execute("""
                UPDATE vehicles SET last_seen = ?,
                    year = COALESCE(?, year),
                    make = COALESCE(?, make),
                    model = COALESCE(?, model),
                    engine = COALESCE(?, engine),
                    trim = COALESCE(?, trim),
                    total_sessions = total_sessions + 1
                WHERE vin = ?
            """, (now, year, make, model, engine, trim, vin))
        else:
            db.execute("""
                INSERT INTO vehicles (vin, year, make, model, engine, trim, first_seen, last_seen, total_sessions)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (vin, year, make, model, engine, trim, now, now))


def get_vehicle(vin):
    """Get vehicle info by VIN."""
    with get_db() as db:
        row = db.execute("SELECT * FROM vehicles WHERE vin = ?", (vin,)).fetchone()
        return dict(row) if row else None


# ─── Session Operations ───

def save_session(session_dict):
    """Save or update a session record."""
    with get_db() as db:
        db.execute("""
            INSERT OR REPLACE INTO sessions
                (session_id, vin, status, dtcs, diagnosis_tech, diagnosis_customer,
                 health_score, health_breakdown,
                 estimate_diag, estimate_parts, estimate_labor, estimate_total,
                 payment_status, payment_amount, payment_stripe_id,
                 created_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_dict.get("id"),
            session_dict.get("vin"),
            session_dict.get("status"),
            json.dumps(session_dict.get("dtcs", [])),
            session_dict.get("diagnosis_tech", ""),
            session_dict.get("diagnosis_customer", ""),
            session_dict.get("health_score", 0),
            json.dumps(session_dict.get("health_breakdown", {})),
            session_dict.get("estimate", {}).get("diagnosis_fee", 0),
            session_dict.get("estimate", {}).get("parts", 0),
            session_dict.get("estimate", {}).get("labor", 0),
            session_dict.get("estimate", {}).get("total", 0),
            session_dict.get("payment", {}).get("status", "none"),
            session_dict.get("payment", {}).get("amount", 0),
            session_dict.get("payment", {}).get("stripe_session_id"),
            session_dict.get("created_at", time.time()),
            session_dict.get("completed_at"),
        ))


def get_vehicle_history(vin, limit=20):
    """Get service history for a vehicle."""
    with get_db() as db:
        rows = db.execute("""
            SELECT * FROM sessions WHERE vin = ?
            ORDER BY created_at DESC LIMIT ?
        """, (vin, limit)).fetchall()
        return [dict(r) for r in rows]


def get_session(session_id):
    """Get a specific session."""
    with get_db() as db:
        row = db.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        return dict(row) if row else None


# ─── Sensor Trend Operations ───

def log_sensors(session_id, snapshot):
    """Log a sensor snapshot for trend analysis."""
    with get_db() as db:
        db.execute("""
            INSERT INTO sensor_log
                (session_id, timestamp, rpm, coolant_temp, engine_load, throttle_pos,
                 short_fuel_trim_1, long_fuel_trim_1, short_fuel_trim_2, long_fuel_trim_2,
                 maf, intake_temp, o2_voltage, timing_advance)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id,
            snapshot.timestamp,
            snapshot.rpm,
            snapshot.coolant_temp,
            snapshot.engine_load,
            snapshot.throttle_pos,
            snapshot.short_fuel_trim_1,
            snapshot.long_fuel_trim_1,
            snapshot.short_fuel_trim_2,
            snapshot.long_fuel_trim_2,
            snapshot.maf,
            snapshot.intake_temp,
            snapshot.o2_voltage_b1s1,
            snapshot.timing_advance,
        ))


def get_sensor_trends(session_id, limit=60):
    """Get recent sensor readings for trend analysis."""
    with get_db() as db:
        rows = db.execute("""
            SELECT * FROM sensor_log WHERE session_id = ?
            ORDER BY timestamp DESC LIMIT ?
        """, (session_id, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]


def get_anomalies(session_id, window=30):
    """Detect sensor anomalies by comparing recent values to session baseline."""
    trends = get_sensor_trends(session_id, limit=window)
    if len(trends) < 5:
        return []

    anomalies = []
    sensors = {
        "coolant_temp": {"name": "Coolant Temp", "warn": 100, "alert": 110, "unit": "C", "direction": "rising"},
        "long_fuel_trim_1": {"name": "LTFT B1", "warn": 12, "alert": 20, "unit": "%", "direction": "abs"},
        "long_fuel_trim_2": {"name": "LTFT B2", "warn": 12, "alert": 20, "unit": "%", "direction": "abs"},
        "rpm": {"name": "RPM", "warn": 5500, "alert": 6500, "unit": "", "direction": "rising"},
    }

    recent = trends[-5:]
    for key, cfg in sensors.items():
        values = [t.get(key, 0) for t in recent if t.get(key) is not None]
        if not values:
            continue

        avg = sum(values) / len(values)
        check_val = abs(avg) if cfg["direction"] == "abs" else avg

        if check_val >= cfg["alert"]:
            anomalies.append({
                "sensor": cfg["name"],
                "value": round(avg, 1),
                "threshold": cfg["alert"],
                "level": "alert",
                "message": f"{cfg['name']} at {avg:.1f}{cfg['unit']} — exceeds alert threshold",
            })
        elif check_val >= cfg["warn"]:
            anomalies.append({
                "sensor": cfg["name"],
                "value": round(avg, 1),
                "threshold": cfg["warn"],
                "level": "warn",
                "message": f"{cfg['name']} at {avg:.1f}{cfg['unit']} — trending toward alert",
            })

    # Rate-of-change detection for coolant temp
    if len(trends) >= 10:
        early = [t.get("coolant_temp", 0) for t in trends[:5]]
        late = [t.get("coolant_temp", 0) for t in trends[-5:]]
        early_avg = sum(early) / len(early)
        late_avg = sum(late) / len(late)
        delta = late_avg - early_avg
        if delta > 5:
            anomalies.append({
                "sensor": "Coolant Temp",
                "value": round(late_avg, 1),
                "threshold": 5,
                "level": "warn",
                "message": f"Coolant rising rapidly (+{delta:.1f}C in recent readings)",
            })

    return anomalies
