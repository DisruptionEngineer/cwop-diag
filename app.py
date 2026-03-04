"""
CWOP-Diag: Smart Automotive Diagnostic Tool
Main Flask application — serves the tech dashboard, customer screen,
and orchestrates OBD-II data, DTC lookup, LLM inference, payments,
VIN decoding, health scoring, root cause analysis, and service history.

Usage:
    python app.py                    # Normal mode (needs OBD-II adapter)
    python app.py --demo             # Demo mode (simulated data, no LLM needed)
    python app.py --backend ollama   # Use Ollama instead of llama.cpp
    python app.py --backend ollama --llm-url http://10.10.7.56:11434  # Remote Ollama
    python app.py --shop-name "Joe's Auto"  # Custom shop name for customer screen
"""

import argparse
import json
import os
import time
import uuid
from datetime import datetime
from flask import Flask, render_template, jsonify, request

from obd_reader import OBDReader
from dtc_database import DTCDatabase
from llm_engine import LLMEngine
from cwop_engine import CWOPEngine
from vin_decoder import read_vin_from_obd, decode_vin, format_vehicle_string
from health_score import compute_health_score
from root_cause import find_correlations, format_for_llm
import database as db

app = Flask(__name__)

# Global instances (initialized in main)
obd_reader: OBDReader = None
dtc_db: DTCDatabase = None
llm: LLMEngine = None
cwop: CWOPEngine = None

# Stripe (optional — demo payment mode works without it)
stripe = None
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

if STRIPE_SECRET_KEY:
    try:
        import stripe as _stripe
        _stripe.api_key = STRIPE_SECRET_KEY
        stripe = _stripe
    except ImportError:
        pass

# ─── Session State ─────────────────────────────────────────────────
# In-memory session for the current vehicle service.
# Single-user kiosk — no need for Flask sessions or cookies.

session = {
    "id": None,
    "status": "idle",  # idle | scanning | diagnosed | estimated | paying | paid
    "dtcs": [],
    "diagnosis_tech": "",
    "diagnosis_customer": "",
    "estimate": {
        "description": "",
        "diagnosis_fee": 50,
        "parts": 0,
        "labor": 0,
        "total": 50,
    },
    "payment": {
        "status": "none",  # none | pending | completed
        "stripe_session_id": None,
        "amount": 0,
    },
    "shop_name": os.environ.get("SHOP_NAME", "CWOP Auto Diagnostics"),
    # New fields
    "vin": None,
    "vehicle_info": {},
    "health": None,
    "correlations": [],
    "created_at": None,
}

# Sensor logging throttle
_last_sensor_log = 0


def reset_session():
    """Reset session for a new vehicle."""
    global _last_sensor_log
    _last_sensor_log = 0
    session.update({
        "id": str(uuid.uuid4())[:8],
        "status": "idle",
        "dtcs": [],
        "diagnosis_tech": "",
        "diagnosis_customer": "",
        "estimate": {
            "description": "",
            "diagnosis_fee": 50,
            "parts": 0,
            "labor": 0,
            "total": 50,
        },
        "payment": {
            "status": "none",
            "stripe_session_id": None,
            "amount": 0,
        },
        "vin": None,
        "vehicle_info": {},
        "health": None,
        "correlations": [],
        "created_at": time.time(),
    })


# ─── Tech Dashboard Routes ────────────────────────────────────────

@app.route("/")
def dashboard():
    """Serve the main tech dashboard page."""
    return render_template("dashboard.html")


@app.route("/landing")
def landing():
    """Serve the product landing page."""
    return render_template("landing.html")


@app.route("/api/status")
def api_status():
    """Overall system status."""
    return jsonify({
        "obd_connected": obd_reader.demo or (obd_reader.connection and obd_reader.connection.is_connected()),
        "llm_healthy": llm.health_check(),
        "llm_backend": llm.backend,
        "demo_mode": obd_reader.demo,
        "session_id": session["id"],
        "session_status": session["status"],
        "payment_status": session["payment"]["status"],
        "vin": session["vin"],
        "vehicle_info": session["vehicle_info"],
        "health": session["health"],
    })


@app.route("/api/snapshot")
def api_snapshot():
    """Get current sensor data and DTCs."""
    global _last_sensor_log
    snap = obd_reader.latest
    dtcs = snap.dtcs if snap.dtcs else obd_reader.read_dtcs()

    # Update CWOP context slots
    dtc_info = dtc_db.lookup_many(dtcs) if dtcs else {}
    dtc_context = dtc_db.format_for_llm(dtcs, snap.to_dict()) if dtcs else ""

    cwop.update_slot("dtc_codes", dtc_context)
    cwop.update_slot("live_data", snap.to_compact())

    # Track session state — move to scanning when DTCs appear
    if dtcs and session["status"] == "idle":
        session["status"] = "scanning"
        # Read VIN on first scan
        _read_vin()

    session["dtcs"] = dtcs

    # Compute health score whenever we have DTCs
    if dtcs:
        health = compute_health_score(snap, dtcs, dtc_info)
        session["health"] = health

    # Find root cause correlations
    if dtcs:
        correlations = find_correlations(dtcs)
        session["correlations"] = correlations
        # Add correlations to CWOP context for LLM
        corr_context = format_for_llm(correlations)
        if corr_context:
            cwop.update_slot("root_cause", corr_context)

    # Log sensors to SQLite (throttled to every 10s)
    now = time.time()
    if session["id"] and now - _last_sensor_log >= 10:
        _last_sensor_log = now
        try:
            db.log_sensors(session["id"], snap)
        except Exception:
            pass

    return jsonify({
        "sensors": snap.to_dict(),
        "dtcs": [
            {
                "code": code,
                "desc": info.get("desc", "Unknown"),
                "severity": info.get("severity", "unknown"),
                "system": info.get("system", "unknown"),
                "common_causes": info.get("common_causes", []),
            }
            for code, info in dtc_info.items()
        ],
        "budget": cwop.get_budget_status(),
        "session_status": session["status"],
        "payment_status": session["payment"]["status"],
        "health": session["health"],
        "correlations": session["correlations"],
        "vehicle_info": session["vehicle_info"],
        "vin": session["vin"],
    })


@app.route("/api/diagnose", methods=["POST"])
def api_diagnose():
    """Run LLM diagnostic analysis on current DTCs + sensor data."""
    data = request.get_json() or {}
    question = data.get("question")

    # Assemble context from CWOP slots
    context = cwop.assemble_context()
    if not context.strip():
        return jsonify({"response": "No diagnostic data available. Connect to a vehicle first.", "tokens": 0, "duration_ms": 0})

    result = llm.diagnose(context, question=question)

    # Store the analysis in its own context slot
    cwop.update_slot("llm_analysis", result["response"])

    # Update session with tech diagnosis
    session["diagnosis_tech"] = result["response"]
    session["status"] = "diagnosed"

    # Generate customer-friendly summary
    customer_result = llm.customer_summary(context, result["response"])
    session["diagnosis_customer"] = customer_result["response"]

    # Save session to SQLite
    _save_session()

    result["budget"] = cwop.get_budget_status()
    result["session_status"] = session["status"]
    return jsonify(result)


@app.route("/api/estimate", methods=["POST"])
def api_estimate():
    """Tech submits repair estimate — pushes to customer screen."""
    data = request.get_json() or {}

    diagnosis_fee = max(0, float(data.get("diagnosis_fee", 50)))
    parts = max(0, float(data.get("parts", 0)))
    labor = max(0, float(data.get("labor", 0)))
    total = diagnosis_fee + parts + labor

    session["estimate"] = {
        "description": data.get("description", session["diagnosis_tech"][:200]),
        "diagnosis_fee": diagnosis_fee,
        "parts": parts,
        "labor": labor,
        "total": total,
    }
    session["status"] = "estimated"
    _save_session()

    return jsonify({"status": "ok", "estimate": session["estimate"], "session_status": session["status"]})


@app.route("/api/clear_dtcs", methods=["POST"])
def api_clear_dtcs():
    """Clear DTCs (demo mode only shows a message)."""
    if obd_reader.demo:
        return jsonify({"status": "Demo mode — DTCs not actually cleared"})
    return jsonify({"status": "DTC clear command sent"})


@app.route("/api/budget")
def api_budget():
    """Get current CWOP context budget status."""
    return jsonify(cwop.get_budget_status())


@app.route("/api/new-session", methods=["POST"])
def api_new_session():
    """Reset everything for the next vehicle."""
    reset_session()
    # Create session record in SQLite
    _save_session()
    return jsonify({"status": "ok", "session_id": session["id"]})


# ─── VIN & Vehicle Info ───────────────────────────────────────────

@app.route("/api/vin")
def api_vin():
    """Get current VIN and vehicle info."""
    if not session["vin"]:
        _read_vin()
    return jsonify({
        "vin": session["vin"],
        "vehicle_info": session["vehicle_info"],
        "vehicle_str": format_vehicle_string(session["vehicle_info"]) if session["vehicle_info"] else None,
    })


# ─── Health Score ─────────────────────────────────────────────────

@app.route("/api/health-score")
def api_health_score():
    """Get current health score."""
    return jsonify(session["health"] or {"total": 0, "grade": "?", "breakdown": {}})


# ─── Service History ──────────────────────────────────────────────

@app.route("/api/history")
def api_history():
    """Get service history for the current VIN."""
    vin = request.args.get("vin") or session.get("vin")
    if not vin:
        return jsonify({"history": [], "vehicle": None})

    history = db.get_vehicle_history(vin, limit=20)
    vehicle = db.get_vehicle(vin)
    return jsonify({"history": history, "vehicle": vehicle})


# ─── Sensor Trends & Anomalies ────────────────────────────────────

@app.route("/api/trends")
def api_trends():
    """Get sensor trend data for the current session."""
    sid = request.args.get("session_id") or session["id"]
    trends = db.get_sensor_trends(sid, limit=60)
    return jsonify({"trends": trends})


@app.route("/api/anomalies")
def api_anomalies():
    """Get detected sensor anomalies."""
    sid = request.args.get("session_id") or session["id"]
    anomalies = db.get_anomalies(sid)
    return jsonify({"anomalies": anomalies})


# ─── Diagnostic Report ────────────────────────────────────────────

def _score_color(score):
    """Map a 0-100 score to a color for the report."""
    if score >= 90:
        return "#10B981"
    elif score >= 75:
        return "#22c55e"
    elif score >= 60:
        return "#eab308"
    elif score >= 40:
        return "#f97316"
    return "#ef4444"


@app.route("/report")
@app.route("/report/<session_id>")
def diagnostic_report(session_id=None):
    """Render a printable diagnostic report."""
    # Use current session or load from DB
    if session_id and session_id != session["id"]:
        saved = db.get_session(session_id)
        if not saved:
            return "Session not found", 404
        # Build report data from saved session
        dtcs_list = json.loads(saved.get("dtcs", "[]"))
        dtc_info = dtc_db.lookup_many(dtcs_list) if dtcs_list else {}
        health_breakdown = json.loads(saved.get("health_breakdown", "{}"))
        report_data = {
            "shop_name": session["shop_name"],
            "date_str": datetime.fromtimestamp(saved.get("created_at", time.time())).strftime("%B %d, %Y at %I:%M %p"),
            "session_id": saved["session_id"],
            "vehicle_str": "Unknown Vehicle",
            "vin": saved.get("vin"),
            "health": {
                "total": saved.get("health_score", 0),
                "grade": _grade_from_score(saved.get("health_score", 0)),
                "breakdown": health_breakdown,
            },
            "dtcs": [
                {
                    "code": c,
                    "desc": dtc_info.get(c, {}).get("desc", "Unknown"),
                    "severity": dtc_info.get(c, {}).get("severity", "unknown"),
                    "common_causes": dtc_info.get(c, {}).get("common_causes", []),
                }
                for c in dtcs_list
            ],
            "correlations": find_correlations(dtcs_list),
            "diagnosis": saved.get("diagnosis_tech", ""),
            "sensors": None,
            "estimate": {
                "diagnosis_fee": saved.get("estimate_diag", 0),
                "parts": saved.get("estimate_parts", 0),
                "labor": saved.get("estimate_labor", 0),
                "total": saved.get("estimate_total", 0),
            },
        }
        # Get vehicle string from DB
        if saved.get("vin"):
            vehicle = db.get_vehicle(saved["vin"])
            if vehicle:
                report_data["vehicle_str"] = format_vehicle_string(vehicle)
    else:
        # Use current live session
        snap = obd_reader.latest
        dtcs_list = session["dtcs"]
        dtc_info = dtc_db.lookup_many(dtcs_list) if dtcs_list else {}
        report_data = {
            "shop_name": session["shop_name"],
            "date_str": datetime.now().strftime("%B %d, %Y at %I:%M %p"),
            "session_id": session["id"],
            "vehicle_str": format_vehicle_string(session["vehicle_info"]) if session["vehicle_info"] else "Unknown Vehicle",
            "vin": session["vin"],
            "health": session["health"] or {"total": 0, "grade": "?", "breakdown": {}},
            "dtcs": [
                {
                    "code": c,
                    "desc": dtc_info.get(c, {}).get("desc", "Unknown"),
                    "severity": dtc_info.get(c, {}).get("severity", "unknown"),
                    "common_causes": dtc_info.get(c, {}).get("common_causes", []),
                }
                for c in dtcs_list
            ],
            "correlations": session["correlations"],
            "diagnosis": session["diagnosis_tech"],
            "sensors": snap.to_dict() if snap else None,
            "estimate": session["estimate"],
        }

    return render_template("report.html", _score_color=_score_color, **report_data)


def _grade_from_score(score):
    if score >= 90: return "A"
    elif score >= 75: return "B"
    elif score >= 60: return "C"
    elif score >= 40: return "D"
    return "F"


# ─── Customer Screen Routes ───────────────────────────────────────

@app.route("/customer")
def customer_screen():
    """Serve the customer-facing display."""
    return render_template(
        "customer.html",
        shop_name=session["shop_name"],
        stripe_key=STRIPE_PUBLISHABLE_KEY,
    )


@app.route("/api/customer-state")
def api_customer_state():
    """Customer screen polls this for current state."""
    dtc_details = []
    for code in session["dtcs"]:
        info = dtc_db.lookup(code) if dtc_db else None
        if info:
            dtc_details.append({"code": code, "desc": info["desc"], "severity": info["severity"]})
        else:
            dtc_details.append({"code": code, "desc": "Unknown", "severity": "unknown"})

    return jsonify({
        "status": session["status"],
        "shop_name": session["shop_name"],
        "dtc_count": len(session["dtcs"]),
        "dtcs": dtc_details,
        "diagnosis": session["diagnosis_customer"],
        "estimate": session["estimate"],
        "payment": session["payment"],
        "health": session["health"],
        "vehicle_info": session["vehicle_info"],
        "vin": session["vin"],
    })


@app.route("/api/checkout", methods=["POST"])
def api_checkout():
    """Create Stripe Checkout Session (or demo payment)."""
    total = session["estimate"]["total"]
    if total <= 0:
        return jsonify({"error": "No estimate to pay"}), 400

    # Demo mode — simulate payment
    if not stripe:
        session["payment"] = {
            "status": "completed",
            "stripe_session_id": f"demo_{uuid.uuid4().hex[:8]}",
            "amount": total,
        }
        session["status"] = "paid"
        _save_session()
        return jsonify({"demo": True, "status": "completed"})

    # Real Stripe Checkout
    try:
        host = request.host_url.rstrip("/")
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": f"Vehicle Diagnostic & Repair",
                        "description": (session["estimate"]["description"][:200]
                                        or "Automotive diagnostic service"),
                    },
                    "unit_amount": int(total * 100),
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=host + "/customer?payment=success&session_id={CHECKOUT_SESSION_ID}",
            cancel_url=host + "/customer?payment=cancelled",
            metadata={
                "cwop_session_id": session["id"],
            },
        )

        session["payment"]["stripe_session_id"] = checkout_session.id
        session["payment"]["status"] = "pending"
        session["payment"]["amount"] = total
        session["status"] = "paying"
        _save_session()

        return jsonify({"url": checkout_session.url, "session_id": checkout_session.id})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/payment-status")
def api_payment_status():
    """Check payment completion (polled by customer screen after redirect)."""
    sid = request.args.get("session_id") or session["payment"].get("stripe_session_id")

    if not sid:
        return jsonify({"status": session["payment"]["status"]})

    # Demo payments are always complete
    if sid.startswith("demo_"):
        return jsonify({"status": "completed"})

    # Verify with Stripe
    if stripe and sid:
        try:
            cs = stripe.checkout.Session.retrieve(sid)
            if cs.payment_status == "paid":
                session["payment"]["status"] = "completed"
                session["status"] = "paid"
                _save_session()
        except Exception:
            pass

    return jsonify({"status": session["payment"]["status"]})


# ─── Stripe Webhook ───────────────────────────────────────────────

@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    """Handle Stripe webhook events for reliable payment confirmation."""
    if not stripe or not STRIPE_WEBHOOK_SECRET:
        return jsonify({"status": "webhook not configured"}), 200

    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return jsonify({"error": "Invalid signature"}), 400

    if event["type"] == "checkout.session.completed":
        checkout = event["data"]["object"]
        cwop_session_id = checkout.get("metadata", {}).get("cwop_session_id")

        # Update current session if it matches
        if cwop_session_id == session["id"]:
            session["payment"]["status"] = "completed"
            session["payment"]["amount"] = checkout["amount_total"] / 100
            session["status"] = "paid"
            _save_session()

    return jsonify({"status": "ok"}), 200


# ─── Internal Helpers ─────────────────────────────────────────────

def _read_vin():
    """Read and decode VIN from the vehicle."""
    vin = read_vin_from_obd(obd_reader)
    if vin:
        session["vin"] = vin
        # Decode vehicle info
        info = decode_vin(vin)
        session["vehicle_info"] = info
        # Save vehicle to database
        try:
            db.upsert_vehicle(
                vin=vin,
                year=info.get("year"),
                make=info.get("make"),
                model=info.get("model"),
                engine=info.get("engine"),
                trim=info.get("trim"),
            )
        except Exception:
            pass
        # Update CWOP context with vehicle info
        vehicle_str = format_vehicle_string(info)
        cwop.update_slot("vehicle_info", f"Vehicle: {vehicle_str} (VIN: {vin})")


def _save_session():
    """Save current session state to SQLite."""
    try:
        session_data = dict(session)
        if session["health"]:
            session_data["health_score"] = session["health"]["total"]
            session_data["health_breakdown"] = session["health"].get("breakdown", {})
        db.save_session(session_data)
    except Exception:
        pass


# ─── Main ─────────────────────────────────────────────────────────

def main():
    global obd_reader, dtc_db, llm, cwop

    parser = argparse.ArgumentParser(description="CWOP-Diag: Smart Automotive Diagnostic Tool")
    parser.add_argument("--demo", action="store_true", help="Run in demo mode (no hardware needed)")
    parser.add_argument("--port", default="/dev/rfcomm0", help="OBD-II serial port")
    parser.add_argument("--backend", default="demo", choices=["llamacpp", "ollama", "demo"],
                        help="LLM backend (default: demo)")
    parser.add_argument("--llm-url", default=None, help="LLM API base URL")
    parser.add_argument("--model", default="qwen2.5:1.5b", help="Ollama model name")
    parser.add_argument("--host", default="0.0.0.0", help="Flask host")
    parser.add_argument("--flask-port", type=int, default=5005, help="Flask port")
    parser.add_argument("--shop-name", default=None, help="Shop name for customer display")
    args = parser.parse_args()

    # If --demo flag, force demo backends
    if args.demo:
        args.backend = "demo"

    if args.shop_name:
        session["shop_name"] = args.shop_name

    # Initialize components
    print("=" * 50)
    print("  CWOP-Diag: Smart Automotive Diagnostic Tool")
    print("=" * 50)

    # Initialize SQLite database
    db.init_db()
    print("[DB] SQLite initialized")

    dtc_db = DTCDatabase()
    print(f"[DTC] Loaded {len(dtc_db.codes)} diagnostic trouble codes")

    cwop = CWOPEngine(total_budget=1500)
    print(f"[CWOP] Context budget: {cwop.total_budget} tokens")

    llm = LLMEngine(backend=args.backend, base_url=args.llm_url, model=args.model)
    print(f"[LLM] Backend: {args.backend}")
    if args.backend == "ollama":
        print(f"[LLM] Model: {args.model}")
        print(f"[LLM] URL: {llm.base_url}")

    obd_reader = OBDReader(port=args.port, demo=args.demo or args.backend == "demo")
    if obd_reader.connect():
        obd_reader.start_polling(interval=2.0)
        print("[OBD] Polling started (2s interval)")
    else:
        print("[OBD] Running without vehicle connection")

    if stripe:
        print(f"[Pay] Stripe live (key: ...{STRIPE_SECRET_KEY[-4:]})")
        if STRIPE_WEBHOOK_SECRET:
            print(f"[Pay] Webhook secret configured")
    else:
        print(f"[Pay] Demo payment mode (set STRIPE_SECRET_KEY for live)")

    reset_session()
    # Save initial session to DB
    _save_session()

    print(f"\n  Tech Dashboard:    http://localhost:{args.flask_port}")
    print(f"  Customer Screen:   http://localhost:{args.flask_port}/customer")
    print(f"  Diagnostic Report: http://localhost:{args.flask_port}/report")
    print(f"  Shop Name:         {session['shop_name']}")
    print(f"  Mode: {'DEMO' if obd_reader.demo else 'LIVE'}")
    print("=" * 50)

    app.run(host=args.host, port=args.flask_port, debug=False)


if __name__ == "__main__":
    main()
