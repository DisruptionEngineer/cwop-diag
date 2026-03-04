"""
OBD Bridge Service — Flask HTTP API wrapping obd_reader.py + Bluetooth management.
Runs on the Primary Handheld (Pi 5) on port 8081.

Provides REST endpoints for:
  - Bluetooth scanning, connecting, disconnecting
  - OBD-II snapshot reading and DTC lookups
  - Connection status

The CWOP-SDLC gateway on port 18790 proxies to this service.
"""

import json
import os
import subprocess
import threading
import time

from flask import Flask, jsonify, request
from obd_reader import OBDReader, SensorSnapshot
from dtc_database import DTCDatabase

app = Flask(__name__)

# ── State ──────────────────────────────────────────────────────────
reader: OBDReader | None = None
dtc_db = DTCDatabase()
bt_state = {
    "connected": False,
    "device": "",
    "mac": "",
    "source": "none",  # "veepeak" | "obdsim" | "none"
    "port": "/dev/rfcomm0",
}
_lock = threading.Lock()


def cors_response(data, status=200):
    """Return JSON response with CORS headers."""
    resp = jsonify(data)
    resp.status_code = status
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-CWOP-Key"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-CWOP-Key"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


# ── Bluetooth Endpoints ───────────────────────────────────────────

@app.route("/api/bt/scan", methods=["GET"])
def bt_scan():
    """Scan for nearby Bluetooth devices."""
    try:
        # Use bluetoothctl to scan for 5 seconds
        result = subprocess.run(
            ["bluetoothctl", "--timeout", "5", "scan", "on"],
            capture_output=True, text=True, timeout=10
        )
        # Parse paired/known devices
        paired = subprocess.run(
            ["bluetoothctl", "devices"],
            capture_output=True, text=True, timeout=5
        )
        devices = []
        for line in paired.stdout.strip().split("\n"):
            if line.startswith("Device "):
                parts = line.split(" ", 2)
                if len(parts) >= 3:
                    devices.append({
                        "mac": parts[1],
                        "name": parts[2],
                        "type": _classify_device(parts[2]),
                    })
        return cors_response({"devices": devices, "count": len(devices)})
    except subprocess.TimeoutExpired:
        return cors_response({"error": "Scan timed out"}, 504)
    except Exception as e:
        return cors_response({"error": str(e)}, 500)


@app.route("/api/bt/connect", methods=["POST"])
def bt_connect():
    """Connect to a Bluetooth OBD device by MAC address."""
    global reader
    data = request.get_json(silent=True) or {}
    mac = data.get("mac", "").strip()
    name = data.get("name", "Unknown")
    port = data.get("port", "/dev/rfcomm0")

    if not mac:
        return cors_response({"error": "MAC address required"}, 400)

    with _lock:
        # Disconnect existing connection first
        if reader:
            try:
                reader.disconnect()
            except Exception:
                pass
            reader = None

        # Release any existing rfcomm binding
        try:
            subprocess.run(["sudo", "rfcomm", "release", "0"],
                           capture_output=True, timeout=5)
        except Exception:
            pass

        try:
            # Pair if needed
            subprocess.run(
                ["bluetoothctl", "pair", mac],
                capture_output=True, text=True, timeout=10
            )
            # Trust the device
            subprocess.run(
                ["bluetoothctl", "trust", mac],
                capture_output=True, text=True, timeout=5
            )
            # Connect at BT level
            subprocess.run(
                ["bluetoothctl", "connect", mac],
                capture_output=True, text=True, timeout=10
            )

            # Bind rfcomm
            bind_result = subprocess.run(
                ["sudo", "rfcomm", "bind", "0", mac, "1"],
                capture_output=True, text=True, timeout=10
            )

            # Wait for rfcomm device to appear
            time.sleep(1)
            if not os.path.exists(port):
                return cors_response({
                    "error": f"rfcomm device {port} not created",
                    "detail": bind_result.stderr,
                }, 500)

            # Create OBD reader and connect
            reader = OBDReader(port=port)
            connected = reader.connect()

            if connected:
                reader.start_polling(interval=2.0)
                bt_state.update({
                    "connected": True,
                    "device": name,
                    "mac": mac,
                    "source": _classify_device(name),
                    "port": port,
                })
                return cors_response({
                    "connected": True,
                    "device": name,
                    "mac": mac,
                    "source": bt_state["source"],
                })
            else:
                reader = None
                return cors_response({"error": "OBD connection failed"}, 500)

        except subprocess.TimeoutExpired:
            return cors_response({"error": "Connection timed out"}, 504)
        except Exception as e:
            return cors_response({"error": str(e)}, 500)


@app.route("/api/bt/disconnect", methods=["POST"])
def bt_disconnect():
    """Disconnect from the current Bluetooth OBD device."""
    global reader
    with _lock:
        if reader:
            try:
                reader.disconnect()
            except Exception:
                pass
            reader = None

        # Release rfcomm
        try:
            subprocess.run(["sudo", "rfcomm", "release", "0"],
                           capture_output=True, timeout=5)
        except Exception:
            pass

        # Disconnect BT if we have a MAC
        if bt_state["mac"]:
            try:
                subprocess.run(
                    ["bluetoothctl", "disconnect", bt_state["mac"]],
                    capture_output=True, timeout=5
                )
            except Exception:
                pass

        bt_state.update({
            "connected": False,
            "device": "",
            "mac": "",
            "source": "none",
            "port": "/dev/rfcomm0",
        })

        return cors_response({"connected": False})


@app.route("/api/bt/status", methods=["GET"])
def bt_status():
    """Get current Bluetooth/OBD connection status."""
    # Verify reader is still alive
    connected = False
    if reader and bt_state["connected"]:
        try:
            # Check if rfcomm device still exists
            connected = os.path.exists(bt_state["port"])
        except Exception:
            connected = False

    if not connected and bt_state["connected"]:
        bt_state["connected"] = False

    return cors_response({
        "connected": bt_state["connected"],
        "device": bt_state["device"],
        "mac": bt_state["mac"],
        "source": bt_state["source"],
    })


# ── OBD Data Endpoints ───────────────────────────────────────────

@app.route("/api/obd/snapshot", methods=["GET"])
def obd_snapshot():
    """Get current OBD sensor snapshot."""
    if not reader or not bt_state["connected"]:
        return cors_response({"error": "Not connected to OBD device"}, 503)

    snap = reader.latest
    return cors_response({
        "timestamp": snap.timestamp,
        "rpm": round(snap.rpm, 0),
        "speed": round(snap.speed, 0),
        "coolantTemp": round(snap.coolant_temp, 1),
        "intakeTemp": round(snap.intake_temp, 1),
        "maf": round(snap.maf, 2),
        "throttlePos": round(snap.throttle_pos, 1),
        "engineLoad": round(snap.engine_load, 1),
        "fuelPressure": round(snap.fuel_pressure, 1),
        "stftB1": round(snap.short_fuel_trim_1, 2),
        "ltftB1": round(snap.long_fuel_trim_1, 2),
        "stftB2": round(snap.short_fuel_trim_2, 2),
        "ltftB2": round(snap.long_fuel_trim_2, 2),
        "timingAdvance": round(snap.timing_advance, 1),
        "o2VoltageB1S1": round(snap.o2_voltage_b1s1, 3),
        "fuelStatus": snap.fuel_status,
        "dtcs": snap.dtcs,
        "source": bt_state["source"],
        "formatted": snap.to_dict(),
    })


@app.route("/api/obd/dtcs", methods=["GET"])
def obd_dtcs():
    """Get current DTCs with descriptions and severity."""
    if not reader or not bt_state["connected"]:
        return cors_response({"error": "Not connected to OBD device"}, 503)

    codes = reader.latest.dtcs
    details = dtc_db.lookup_many(codes) if codes else {}

    dtc_list = []
    for code, info in details.items():
        dtc_list.append({
            "code": code,
            "desc": info["desc"],
            "severity": info["severity"],
            "system": info.get("system", "unknown"),
            "commonCauses": info.get("common_causes", []),
        })

    return cors_response({
        "dtcs": dtc_list,
        "count": len(dtc_list),
        "source": bt_state["source"],
    })


@app.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return cors_response({
        "status": "ok",
        "service": "obd-bridge",
        "btConnected": bt_state["connected"],
        "device": bt_state["device"],
        "source": bt_state["source"],
    })


# ── Helpers ───────────────────────────────────────────────────────

def _classify_device(name: str) -> str:
    """Classify a BT device as veepeak, obdsim, or unknown."""
    name_lower = name.lower()
    if "veepeak" in name_lower or "vlink" in name_lower or "obd" in name_lower:
        return "veepeak"
    if "obdsim" in name_lower or "elm" in name_lower or "sim" in name_lower:
        return "obdsim"
    return "unknown"


# ── Main ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("[OBD Bridge] Starting on port 8081")
    print("[OBD Bridge] Endpoints:")
    print("  GET  /api/bt/scan       — Scan for BT devices")
    print("  POST /api/bt/connect    — Connect to OBD device")
    print("  POST /api/bt/disconnect — Disconnect")
    print("  GET  /api/bt/status     — Connection status")
    print("  GET  /api/obd/snapshot  — Current sensor data")
    print("  GET  /api/obd/dtcs      — Current DTCs with details")
    print("  GET  /api/health        — Health check")
    app.run(host="127.0.0.1", port=8081, threaded=True)
