"""
Vehicle Health Score for CWOP-Diag.
Computes a 0-100 composite score from live sensor data and DTCs.
Each subsystem gets a sub-score; weighted average produces the total.
"""


# Subsystem weights (must sum to 1.0)
WEIGHTS = {
    "engine": 0.25,
    "fuel_system": 0.25,
    "emissions": 0.20,
    "cooling": 0.15,
    "ignition": 0.15,
}


def compute_health_score(snapshot, dtcs: list, dtc_info: dict) -> dict:
    """
    Compute vehicle health score.

    Args:
        snapshot: SensorSnapshot from obd_reader
        dtcs: List of DTC code strings
        dtc_info: Dict of {code: {severity, system, ...}} from dtc_database

    Returns:
        {
            "total": 0-100,
            "grade": "A" | "B" | "C" | "D" | "F",
            "breakdown": {
                "engine": {"score": 0-100, "issues": [...]},
                "fuel_system": {"score": 0-100, "issues": [...]},
                ...
            }
        }
    """
    breakdown = {}

    # Score each subsystem
    breakdown["engine"] = _score_engine(snapshot, dtcs, dtc_info)
    breakdown["fuel_system"] = _score_fuel_system(snapshot, dtcs, dtc_info)
    breakdown["emissions"] = _score_emissions(dtcs, dtc_info)
    breakdown["cooling"] = _score_cooling(snapshot, dtcs, dtc_info)
    breakdown["ignition"] = _score_ignition(dtcs, dtc_info)

    # Weighted total
    total = sum(
        breakdown[sys]["score"] * WEIGHTS[sys]
        for sys in WEIGHTS
    )
    total = max(0, min(100, round(total)))

    return {
        "total": total,
        "grade": _grade(total),
        "breakdown": breakdown,
    }


def _grade(score):
    if score >= 90:
        return "A"
    elif score >= 75:
        return "B"
    elif score >= 60:
        return "C"
    elif score >= 40:
        return "D"
    return "F"


# ─── Subsystem Scorers ───

def _score_engine(snapshot, dtcs, dtc_info):
    score = 100
    issues = []

    # RPM check (idle should be 600-1000)
    if snapshot.rpm > 0:
        if snapshot.rpm > 5000:
            score -= 30
            issues.append("RPM very high")
        elif snapshot.rpm < 500:
            score -= 15
            issues.append("RPM low — possible stalling")

    # Engine load at idle should be 15-40%
    if snapshot.engine_load > 80:
        score -= 20
        issues.append("Engine load abnormally high")
    elif snapshot.engine_load > 60:
        score -= 10
        issues.append("Engine load elevated")

    # DTC penalties for engine-related codes
    score -= _dtc_penalty(dtcs, dtc_info, ["fuel_air", "drivetrain"])
    if score < 100:
        issues.extend(_dtc_issues(dtcs, dtc_info, ["fuel_air", "drivetrain"]))

    return {"score": max(0, score), "issues": issues}


def _score_fuel_system(snapshot, dtcs, dtc_info):
    score = 100
    issues = []

    # Long-term fuel trim analysis
    # Normal: -5% to +5%. Warn: +/-10%. Alert: +/-15%
    for label, val in [("B1", snapshot.long_fuel_trim_1), ("B2", snapshot.long_fuel_trim_2)]:
        absval = abs(val)
        if absval > 20:
            score -= 25
            issues.append(f"LTFT {label} severely out of range ({val:+.1f}%)")
        elif absval > 15:
            score -= 15
            issues.append(f"LTFT {label} high ({val:+.1f}%)")
        elif absval > 10:
            score -= 8
            issues.append(f"LTFT {label} elevated ({val:+.1f}%)")

    # Short-term fuel trim
    for label, val in [("B1", snapshot.short_fuel_trim_1), ("B2", snapshot.short_fuel_trim_2)]:
        if abs(val) > 25:
            score -= 15
            issues.append(f"STFT {label} erratic ({val:+.1f}%)")

    # O2 sensor voltage (normal cycling: 0.1-0.9V)
    if snapshot.o2_voltage_b1s1 > 0:
        if snapshot.o2_voltage_b1s1 > 0.95 or snapshot.o2_voltage_b1s1 < 0.05:
            score -= 10
            issues.append(f"O2 sensor B1S1 stuck ({snapshot.o2_voltage_b1s1:.2f}V)")

    return {"score": max(0, score), "issues": issues}


def _score_emissions(dtcs, dtc_info):
    score = 100
    issues = []

    score -= _dtc_penalty(dtcs, dtc_info, ["emissions"])
    issues.extend(_dtc_issues(dtcs, dtc_info, ["emissions"]))

    return {"score": max(0, score), "issues": issues}


def _score_cooling(snapshot, dtcs, dtc_info):
    score = 100
    issues = []

    if snapshot.coolant_temp > 115:
        score -= 40
        issues.append(f"OVERHEATING: {snapshot.coolant_temp:.0f}C")
    elif snapshot.coolant_temp > 105:
        score -= 25
        issues.append(f"Coolant temp high: {snapshot.coolant_temp:.0f}C")
    elif snapshot.coolant_temp > 98:
        score -= 10
        issues.append(f"Coolant temp elevated: {snapshot.coolant_temp:.0f}C")
    elif snapshot.coolant_temp < 60 and snapshot.coolant_temp > 0:
        score -= 10
        issues.append("Engine not reaching operating temp — possible thermostat issue")

    score -= _dtc_penalty(dtcs, dtc_info, ["cooling"])
    issues.extend(_dtc_issues(dtcs, dtc_info, ["cooling"]))

    return {"score": max(0, score), "issues": issues}


def _score_ignition(dtcs, dtc_info):
    score = 100
    issues = []

    # Count misfire codes
    misfire_codes = [c for c in dtcs if c.startswith("P030")]
    if len(misfire_codes) >= 3:
        score -= 40
        issues.append(f"Multiple misfire codes ({len(misfire_codes)} cylinders)")
    elif len(misfire_codes) >= 1:
        score -= 20
        issues.append(f"Misfire detected: {', '.join(misfire_codes)}")

    score -= _dtc_penalty(dtcs, dtc_info, ["ignition"])
    issues.extend(_dtc_issues(dtcs, dtc_info, ["ignition"]))

    return {"score": max(0, score), "issues": issues}


# ─── Helpers ───

def _dtc_penalty(dtcs, dtc_info, systems):
    """Calculate penalty from DTCs in the given systems."""
    penalty = 0
    severity_map = {"high": 20, "moderate": 10, "low": 5, "unknown": 8}
    for code in dtcs:
        info = dtc_info.get(code, {})
        if info.get("system") in systems or not systems:
            penalty += severity_map.get(info.get("severity", "unknown"), 8)
    return min(penalty, 50)  # Cap at 50 to avoid going to 0 from DTCs alone


def _dtc_issues(dtcs, dtc_info, systems):
    """Get issue descriptions from DTCs in the given systems."""
    issues = []
    for code in dtcs:
        info = dtc_info.get(code, {})
        if info.get("system") in systems:
            issues.append(f"{code}: {info.get('desc', 'Unknown')}")
    return issues
