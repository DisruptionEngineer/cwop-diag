"""
CWOP-Diag: Smart Automotive Diagnostic Tool
Main Flask application — serves the dashboard and orchestrates
OBD-II data collection, DTC lookup, and LLM inference.

Usage:
    python app.py                    # Normal mode (needs OBD-II adapter)
    python app.py --demo             # Demo mode (simulated data, no LLM needed)
    python app.py --backend ollama   # Use Ollama instead of llama.cpp
    python app.py --backend ollama --llm-url http://10.10.7.56:11434  # Remote Ollama
"""

import argparse
import json
from flask import Flask, render_template, jsonify, request

from obd_reader import OBDReader
from dtc_database import DTCDatabase
from llm_engine import LLMEngine
from cwop_engine import CWOPEngine

app = Flask(__name__)

# Global instances (initialized in main)
obd_reader: OBDReader = None
dtc_db: DTCDatabase = None
llm: LLMEngine = None
cwop: CWOPEngine = None


@app.route("/")
def dashboard():
    """Serve the main dashboard page."""
    return render_template("dashboard.html")


@app.route("/api/status")
def api_status():
    """Overall system status."""
    return jsonify({
        "obd_connected": obd_reader.demo or (obd_reader.connection and obd_reader.connection.is_connected()),
        "llm_healthy": llm.health_check(),
        "llm_backend": llm.backend,
        "demo_mode": obd_reader.demo,
    })


@app.route("/api/snapshot")
def api_snapshot():
    """Get current sensor data and DTCs."""
    snap = obd_reader.latest
    dtcs = snap.dtcs if snap.dtcs else obd_reader.read_dtcs()

    # Update CWOP context slots
    dtc_info = dtc_db.lookup_many(dtcs) if dtcs else {}
    dtc_context = dtc_db.format_for_llm(dtcs, snap.to_dict()) if dtcs else ""

    cwop.update_slot("dtc_codes", dtc_context)
    cwop.update_slot("live_data", snap.to_compact())

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

    result["budget"] = cwop.get_budget_status()
    return jsonify(result)


@app.route("/api/clear_dtcs", methods=["POST"])
def api_clear_dtcs():
    """Clear DTCs (demo mode only shows a message)."""
    if obd_reader.demo:
        return jsonify({"status": "Demo mode — DTCs not actually cleared"})
    # In real mode, would send OBD-II clear command
    return jsonify({"status": "DTC clear command sent"})


@app.route("/api/budget")
def api_budget():
    """Get current CWOP context budget status."""
    return jsonify(cwop.get_budget_status())


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
    parser.add_argument("--flask-port", type=int, default=5000, help="Flask port")
    args = parser.parse_args()

    # If --demo flag, force demo backends
    if args.demo:
        args.backend = "demo"

    # Initialize components
    print("=" * 50)
    print("  CWOP-Diag: Smart Automotive Diagnostic Tool")
    print("=" * 50)

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

    print(f"\n  Dashboard: http://localhost:{args.flask_port}")
    print(f"  Mode: {'DEMO' if obd_reader.demo else 'LIVE'}")
    print("=" * 50)

    app.run(host=args.host, port=args.flask_port, debug=False)


if __name__ == "__main__":
    main()
