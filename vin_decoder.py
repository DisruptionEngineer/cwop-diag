"""
VIN decoder for CWOP-Diag.
Reads VIN from OBD-II Mode 09 PID 02, then decodes
year/make/model/engine via the free NHTSA vPIC API.
"""

import re
import requests

NHTSA_API = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues"


def read_vin_from_obd(obd_reader) -> str | None:
    """
    Read VIN from the vehicle via OBD-II Mode 09 PID 02.
    Returns the 17-character VIN string or None.
    """
    if obd_reader.demo:
        return "1HGCM82633A004352"  # Demo: 2003 Honda Accord

    try:
        import obd
        if not obd_reader.connection or not obd_reader.connection.is_connected():
            return None
        resp = obd_reader.connection.query(obd.commands.VIN)
        if resp.is_null():
            return None
        vin = str(resp.value).strip()
        # Validate: 17 alphanumeric, no I/O/Q
        if re.match(r'^[A-HJ-NPR-Z0-9]{17}$', vin.upper()):
            return vin.upper()
        return None
    except Exception:
        return None


# Demo fallback — used when NHTSA API is unreachable
DEMO_VINS = {
    "1HGCM82633A004352": {
        "vin": "1HGCM82633A004352",
        "year": 2003,
        "make": "Honda",
        "model": "Accord",
        "engine": "2.4L I4",
        "displacement_l": 2.4,
        "cylinders": 4,
        "fuel_type": "Gasoline",
        "body_class": "Sedan",
        "drive_type": "FWD",
    },
}


def decode_vin(vin: str) -> dict:
    """
    Decode a VIN using the NHTSA vPIC API (free, no key needed).
    Falls back to local demo data if API is unreachable.
    Returns dict with year, make, model, engine, trim, etc.
    """
    if not vin or len(vin) != 17:
        return {}

    try:
        r = requests.get(
            f"{NHTSA_API}/{vin}",
            params={"format": "json"},
            timeout=5,
        )
        r.raise_for_status()
        data = r.json()

        results = data.get("Results", [{}])[0]

        # Extract the key fields
        info = {
            "vin": vin,
            "year": _int_or_none(results.get("ModelYear")),
            "make": _clean(results.get("Make")),
            "model": _clean(results.get("Model")),
            "trim": _clean(results.get("Trim")),
            "engine": _build_engine_string(results),
            "body_class": _clean(results.get("BodyClass")),
            "drive_type": _clean(results.get("DriveType")),
            "fuel_type": _clean(results.get("FuelTypePrimary")),
            "cylinders": _int_or_none(results.get("EngineCylinders")),
            "displacement_l": _float_or_none(results.get("DisplacementL")),
            "plant_city": _clean(results.get("PlantCity")),
            "plant_country": _clean(results.get("PlantCountry")),
        }
        decoded = {k: v for k, v in info.items() if v is not None}
        # If API returned only VIN (no make/model), fall back to demo data
        if decoded.get("make"):
            return decoded
        return DEMO_VINS.get(vin, decoded)

    except Exception:
        # Network failure — use demo fallback if available
        return DEMO_VINS.get(vin, {"vin": vin})


def format_vehicle_string(info: dict) -> str:
    """Format vehicle info into a display string like '2003 Honda Accord 2.4L'."""
    parts = []
    if info.get("year"):
        parts.append(str(info["year"]))
    if info.get("make"):
        parts.append(info["make"])
    if info.get("model"):
        parts.append(info["model"])
    if info.get("displacement_l"):
        parts.append(f"{info['displacement_l']}L")
    return " ".join(parts) if parts else "Unknown Vehicle"


def _clean(val):
    if not val or str(val).strip() in ("", "Not Applicable", "null"):
        return None
    return str(val).strip()


def _int_or_none(val):
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _float_or_none(val):
    try:
        return round(float(val), 1)
    except (TypeError, ValueError):
        return None


def _build_engine_string(results):
    parts = []
    disp = _float_or_none(results.get("DisplacementL"))
    cyls = _int_or_none(results.get("EngineCylinders"))
    config = _clean(results.get("EngineConfiguration"))
    if disp:
        parts.append(f"{disp}L")
    if cyls and config:
        parts.append(f"{config}{cyls}")
    elif cyls:
        parts.append(f"{cyls}-cyl")
    fuel = _clean(results.get("FuelTypePrimary"))
    if fuel and fuel.lower() not in ("gasoline", ""):
        parts.append(fuel)
    return " ".join(parts) if parts else None
