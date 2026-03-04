"""
Multi-DTC Root Cause Correlation Engine for CWOP-Diag.
Maps known combinations of DTCs to shared root causes,
preventing the LLM from treating each code independently.
"""


# Known DTC combinations and their likely shared root causes.
# Format: (frozenset of codes, root cause description, confidence, fix suggestion)
CORRELATION_RULES = [
    # Lean conditions on both banks = shared air/fuel issue
    {
        "codes": {"P0171", "P0174"},
        "root_cause": "Shared vacuum/intake leak affecting both banks",
        "confidence": 0.9,
        "fix": "Check intake manifold gasket, vacuum hoses, and MAF sensor",
        "system": "fuel_air",
    },
    # Rich on both banks
    {
        "codes": {"P0172", "P0175"},
        "root_cause": "Shared over-fueling condition — likely fuel pressure or MAF issue",
        "confidence": 0.85,
        "fix": "Check fuel pressure regulator, MAF sensor, and purge valve",
        "system": "fuel_air",
    },
    # Lean B1 + MAF issue
    {
        "codes": {"P0171", "P0101"},
        "root_cause": "MAF sensor reporting incorrect airflow — causing lean condition",
        "confidence": 0.85,
        "fix": "Clean or replace MAF sensor; check for air leaks between MAF and throttle body",
        "system": "fuel_air",
    },
    {
        "codes": {"P0171", "P0100"},
        "root_cause": "MAF circuit fault causing lean fuel delivery",
        "confidence": 0.8,
        "fix": "Inspect MAF wiring and connector; test MAF sensor",
        "system": "fuel_air",
    },
    # Random misfire + cylinder-specific misfires = ignition system
    {
        "codes": {"P0300", "P0301"},
        "root_cause": "Cylinder 1 is the primary misfire source causing random misfire detection",
        "confidence": 0.85,
        "fix": "Start with cylinder 1: swap coil/plug to confirm, then check injector",
        "system": "ignition",
    },
    {
        "codes": {"P0300", "P0301", "P0304"},
        "root_cause": "Cylinders 1 & 4 share a coil pack (waste-spark system) — likely bad coil",
        "confidence": 0.9,
        "fix": "Replace coil pack for cylinders 1/4; inspect spark plugs and wires",
        "system": "ignition",
    },
    {
        "codes": {"P0300", "P0302", "P0303"},
        "root_cause": "Cylinders 2 & 3 share a coil pack — likely bad coil or connector",
        "confidence": 0.9,
        "fix": "Replace coil pack for cylinders 2/3; inspect spark plugs",
        "system": "ignition",
    },
    # Catalyst + O2 sensor
    {
        "codes": {"P0420", "P0130"},
        "root_cause": "O2 sensor issue may be triggering false catalyst efficiency code",
        "confidence": 0.75,
        "fix": "Replace Bank 1 Sensor 1 O2 sensor first, clear codes, retest cat efficiency",
        "system": "emissions",
    },
    {
        "codes": {"P0420", "P0133"},
        "root_cause": "Slow O2 sensor response causing false catalyst code",
        "confidence": 0.8,
        "fix": "Replace aging O2 sensor B1S1; if P0420 returns, catalyst is failing",
        "system": "emissions",
    },
    # EVAP system codes
    {
        "codes": {"P0440", "P0442"},
        "root_cause": "Small EVAP leak — most commonly a gas cap issue",
        "confidence": 0.85,
        "fix": "Replace gas cap first; if codes return, smoke test EVAP system",
        "system": "emissions",
    },
    {
        "codes": {"P0440", "P0455"},
        "root_cause": "Large EVAP leak — likely disconnected hose or cracked canister",
        "confidence": 0.85,
        "fix": "Visual inspection of EVAP hoses and canister; smoke test if not obvious",
        "system": "emissions",
    },
    {
        "codes": {"P0441", "P0443"},
        "root_cause": "Purge valve circuit failure preventing proper EVAP operation",
        "confidence": 0.85,
        "fix": "Test purge solenoid circuit; replace purge valve if faulty",
        "system": "emissions",
    },
    # Transmission combo
    {
        "codes": {"P0700", "P0730"},
        "root_cause": "Transmission gear ratio error — likely low fluid or worn clutch packs",
        "confidence": 0.8,
        "fix": "Check transmission fluid level and condition; scan for additional TCM codes",
        "system": "transmission",
    },
    {
        "codes": {"P0700", "P0750"},
        "root_cause": "Shift solenoid A failure — causing transmission control malfunction",
        "confidence": 0.85,
        "fix": "Test shift solenoid A; check wiring; may need solenoid replacement",
        "system": "transmission",
    },
    # Cooling system
    {
        "codes": {"P0115", "P0128"},
        "root_cause": "ECT sensor or thermostat failure — conflicting temperature readings",
        "confidence": 0.8,
        "fix": "Test ECT sensor resistance; if normal, replace thermostat",
        "system": "cooling",
    },
    {
        "codes": {"P0116", "P0128"},
        "root_cause": "Stuck-open thermostat — engine not reaching operating temperature",
        "confidence": 0.9,
        "fix": "Replace thermostat; verify ECT sensor after replacement",
        "system": "cooling",
    },
    # Crank + Cam position
    {
        "codes": {"P0335", "P0340"},
        "root_cause": "Timing chain/belt issue affecting both crank and cam position readings",
        "confidence": 0.85,
        "fix": "Inspect timing chain/belt tension and alignment; check for jumped timing",
        "system": "ignition",
    },
    # Throttle position + idle
    {
        "codes": {"P0120", "P0507"},
        "root_cause": "TPS fault causing erratic idle control",
        "confidence": 0.85,
        "fix": "Replace throttle position sensor; clean throttle body",
        "system": "fuel_air",
    },
    # Lean + misfire (vacuum leak causing both)
    {
        "codes": {"P0171", "P0300"},
        "root_cause": "Vacuum leak causing both lean condition and misfires",
        "confidence": 0.85,
        "fix": "Locate and repair vacuum leak — this should resolve both codes simultaneously",
        "system": "fuel_air",
    },
]


def find_correlations(dtcs: list[str]) -> list[dict]:
    """
    Find root cause correlations for a set of DTCs.

    Args:
        dtcs: List of DTC code strings (e.g., ["P0171", "P0174"])

    Returns:
        List of matching correlations, sorted by confidence (highest first).
        Each item: {codes, root_cause, confidence, fix, system}
    """
    dtc_set = set(c.upper().strip() for c in dtcs)
    matches = []

    for rule in CORRELATION_RULES:
        required = rule["codes"]
        if required.issubset(dtc_set):
            matches.append({
                "codes": sorted(required),
                "root_cause": rule["root_cause"],
                "confidence": rule["confidence"],
                "fix": rule["fix"],
                "system": rule["system"],
            })

    # Sort by confidence descending, then by number of matching codes
    matches.sort(key=lambda m: (-m["confidence"], -len(m["codes"])))
    return matches


def format_for_llm(correlations: list[dict]) -> str:
    """Format correlations into context for the LLM."""
    if not correlations:
        return ""

    lines = ["## Root Cause Correlations\n"]
    for i, corr in enumerate(correlations, 1):
        codes = " + ".join(corr["codes"])
        conf_pct = int(corr["confidence"] * 100)
        lines.append(f"{i}. **{codes}** ({conf_pct}% confidence)")
        lines.append(f"   Root cause: {corr['root_cause']}")
        lines.append(f"   Suggested fix: {corr['fix']}")
        lines.append("")

    return "\n".join(lines)
