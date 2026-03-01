"""
DTC (Diagnostic Trouble Code) database.
Provides instant lookups for standard OBD-II codes so the LLM
only needs to handle reasoning, not memorizing code definitions.
"""

import json
import os

# Standard OBD-II DTC categories
DTC_CATEGORIES = {
    "P0": "Powertrain (Generic)",
    "P1": "Powertrain (Manufacturer-specific)",
    "P2": "Powertrain (Generic, additional)",
    "P3": "Powertrain (Generic/Manufacturer)",
    "B0": "Body (Generic)",
    "B1": "Body (Manufacturer-specific)",
    "C0": "Chassis (Generic)",
    "C1": "Chassis (Manufacturer-specific)",
    "U0": "Network (Generic)",
    "U1": "Network (Manufacturer-specific)",
}

# Common DTCs with descriptions, severity, and typical causes.
# This covers the most frequently encountered codes.
# Full database loaded from dtc_codes.json if available.
COMMON_DTCS = {
    # Fuel and Air Metering
    "P0100": {"desc": "Mass Air Flow Circuit Malfunction", "severity": "moderate",
              "system": "fuel_air", "common_causes": ["Dirty/faulty MAF sensor", "Air leak in intake", "Wiring issue"]},
    "P0101": {"desc": "Mass Air Flow Circuit Range/Performance", "severity": "moderate",
              "system": "fuel_air", "common_causes": ["Dirty MAF sensor", "Vacuum leak", "Restricted air filter"]},
    "P0102": {"desc": "Mass Air Flow Circuit Low", "severity": "moderate",
              "system": "fuel_air", "common_causes": ["Faulty MAF sensor", "Open circuit", "Air leak"]},
    "P0106": {"desc": "MAP Sensor Range/Performance", "severity": "moderate",
              "system": "fuel_air", "common_causes": ["Faulty MAP sensor", "Vacuum leak", "Wiring issue"]},
    "P0107": {"desc": "MAP Sensor Circuit Low", "severity": "moderate",
              "system": "fuel_air", "common_causes": ["Faulty MAP sensor", "Short circuit", "Bad ground"]},
    "P0110": {"desc": "Intake Air Temperature Circuit Malfunction", "severity": "low",
              "system": "fuel_air", "common_causes": ["Faulty IAT sensor", "Open/short circuit"]},
    "P0120": {"desc": "Throttle Position Sensor Circuit Malfunction", "severity": "high",
              "system": "fuel_air", "common_causes": ["Faulty TPS", "Wiring issue", "Bad connector"]},
    "P0121": {"desc": "Throttle Position Sensor Range/Performance", "severity": "high",
              "system": "fuel_air", "common_causes": ["Worn TPS", "Carbon buildup on throttle body"]},
    "P0130": {"desc": "O2 Sensor Circuit Malfunction (Bank 1 Sensor 1)", "severity": "moderate",
              "system": "fuel_air", "common_causes": ["Faulty O2 sensor", "Wiring damage", "Exhaust leak"]},
    "P0131": {"desc": "O2 Sensor Circuit Low Voltage (Bank 1 Sensor 1)", "severity": "moderate",
              "system": "fuel_air", "common_causes": ["Lean condition", "Faulty O2 sensor", "Vacuum leak"]},
    "P0133": {"desc": "O2 Sensor Slow Response (Bank 1 Sensor 1)", "severity": "moderate",
              "system": "fuel_air", "common_causes": ["Aging O2 sensor", "Exhaust leak", "Fuel quality"]},
    "P0135": {"desc": "O2 Sensor Heater Circuit Malfunction (Bank 1 Sensor 1)", "severity": "low",
              "system": "fuel_air", "common_causes": ["Blown fuse", "Faulty heater element", "Wiring"]},
    "P0171": {"desc": "System Too Lean (Bank 1)", "severity": "moderate",
              "system": "fuel_air", "common_causes": ["Vacuum leak", "Faulty MAF sensor", "Weak fuel pump", "Dirty fuel injectors", "Intake manifold gasket leak"]},
    "P0172": {"desc": "System Too Rich (Bank 1)", "severity": "moderate",
              "system": "fuel_air", "common_causes": ["Leaking fuel injector", "Faulty O2 sensor", "High fuel pressure", "Dirty air filter"]},
    "P0174": {"desc": "System Too Lean (Bank 2)", "severity": "moderate",
              "system": "fuel_air", "common_causes": ["Vacuum leak", "Faulty MAF sensor", "Weak fuel pump", "Intake manifold gasket leak"]},
    "P0175": {"desc": "System Too Rich (Bank 2)", "severity": "moderate",
              "system": "fuel_air", "common_causes": ["Leaking fuel injector", "Faulty O2 sensor", "High fuel pressure"]},

    # Ignition System
    "P0300": {"desc": "Random/Multiple Cylinder Misfire Detected", "severity": "high",
              "system": "ignition", "common_causes": ["Spark plugs", "Ignition coils", "Fuel delivery issue", "Vacuum leak", "Low compression"]},
    "P0301": {"desc": "Cylinder 1 Misfire Detected", "severity": "high",
              "system": "ignition", "common_causes": ["Spark plug cyl 1", "Ignition coil cyl 1", "Fuel injector cyl 1", "Low compression cyl 1"]},
    "P0302": {"desc": "Cylinder 2 Misfire Detected", "severity": "high",
              "system": "ignition", "common_causes": ["Spark plug cyl 2", "Ignition coil cyl 2", "Fuel injector cyl 2"]},
    "P0303": {"desc": "Cylinder 3 Misfire Detected", "severity": "high",
              "system": "ignition", "common_causes": ["Spark plug cyl 3", "Ignition coil cyl 3", "Fuel injector cyl 3"]},
    "P0304": {"desc": "Cylinder 4 Misfire Detected", "severity": "high",
              "system": "ignition", "common_causes": ["Spark plug cyl 4", "Ignition coil cyl 4", "Fuel injector cyl 4"]},
    "P0305": {"desc": "Cylinder 5 Misfire Detected", "severity": "high",
              "system": "ignition", "common_causes": ["Spark plug cyl 5", "Ignition coil cyl 5", "Fuel injector cyl 5"]},
    "P0306": {"desc": "Cylinder 6 Misfire Detected", "severity": "high",
              "system": "ignition", "common_causes": ["Spark plug cyl 6", "Ignition coil cyl 6", "Fuel injector cyl 6"]},
    "P0307": {"desc": "Cylinder 7 Misfire Detected", "severity": "high",
              "system": "ignition", "common_causes": ["Spark plug cyl 7", "Ignition coil cyl 7", "Fuel injector cyl 7"]},
    "P0308": {"desc": "Cylinder 8 Misfire Detected", "severity": "high",
              "system": "ignition", "common_causes": ["Spark plug cyl 8", "Ignition coil cyl 8", "Fuel injector cyl 8"]},
    "P0335": {"desc": "Crankshaft Position Sensor Circuit Malfunction", "severity": "high",
              "system": "ignition", "common_causes": ["Faulty CKP sensor", "Wiring damage", "Reluctor wheel damage"]},
    "P0340": {"desc": "Camshaft Position Sensor Circuit Malfunction", "severity": "high",
              "system": "ignition", "common_causes": ["Faulty CMP sensor", "Timing chain/belt issue", "Wiring"]},

    # Emission Controls
    "P0401": {"desc": "EGR Flow Insufficient Detected", "severity": "moderate",
              "system": "emissions", "common_causes": ["Clogged EGR valve", "Carbon buildup", "Faulty EGR solenoid"]},
    "P0420": {"desc": "Catalyst System Efficiency Below Threshold (Bank 1)", "severity": "moderate",
              "system": "emissions", "common_causes": ["Failing catalytic converter", "O2 sensor issue", "Exhaust leak"]},
    "P0430": {"desc": "Catalyst System Efficiency Below Threshold (Bank 2)", "severity": "moderate",
              "system": "emissions", "common_causes": ["Failing catalytic converter", "O2 sensor issue"]},
    "P0440": {"desc": "Evaporative Emission System Malfunction", "severity": "low",
              "system": "emissions", "common_causes": ["Loose gas cap", "EVAP canister issue", "Purge valve"]},
    "P0441": {"desc": "EVAP System Incorrect Purge Flow", "severity": "low",
              "system": "emissions", "common_causes": ["Faulty purge valve", "Vacuum leak in EVAP system"]},
    "P0442": {"desc": "EVAP System Small Leak Detected", "severity": "low",
              "system": "emissions", "common_causes": ["Loose gas cap", "Cracked EVAP hose", "Faulty purge valve"]},
    "P0443": {"desc": "EVAP Purge Control Valve Circuit Malfunction", "severity": "low",
              "system": "emissions", "common_causes": ["Faulty purge solenoid", "Wiring issue"]},
    "P0446": {"desc": "EVAP Vent Control Circuit Malfunction", "severity": "low",
              "system": "emissions", "common_causes": ["Faulty vent valve", "Blocked vent line"]},
    "P0455": {"desc": "EVAP System Large Leak Detected", "severity": "low",
              "system": "emissions", "common_causes": ["Missing gas cap", "Major EVAP hose disconnected", "Cracked canister"]},
    "P0456": {"desc": "EVAP System Very Small Leak Detected", "severity": "low",
              "system": "emissions", "common_causes": ["Gas cap seal", "Minor EVAP line crack"]},

    # Cooling System
    "P0115": {"desc": "Engine Coolant Temperature Circuit Malfunction", "severity": "moderate",
              "system": "cooling", "common_causes": ["Faulty ECT sensor", "Wiring issue", "Bad connector"]},
    "P0116": {"desc": "Engine Coolant Temperature Range/Performance", "severity": "moderate",
              "system": "cooling", "common_causes": ["Stuck thermostat", "Faulty ECT sensor", "Low coolant"]},
    "P0117": {"desc": "Engine Coolant Temperature Circuit Low", "severity": "moderate",
              "system": "cooling", "common_causes": ["Short in ECT circuit", "Faulty sensor"]},
    "P0125": {"desc": "Insufficient Coolant Temperature for Closed Loop", "severity": "moderate",
              "system": "cooling", "common_causes": ["Stuck-open thermostat", "Faulty ECT sensor"]},
    "P0128": {"desc": "Coolant Thermostat Below Regulating Temperature", "severity": "low",
              "system": "cooling", "common_causes": ["Stuck-open thermostat", "Low coolant level"]},

    # Transmission
    "P0700": {"desc": "Transmission Control System Malfunction", "severity": "high",
              "system": "transmission", "common_causes": ["TCM fault", "Wiring issue", "Check for additional trans codes"]},
    "P0715": {"desc": "Input/Turbine Speed Sensor Circuit Malfunction", "severity": "high",
              "system": "transmission", "common_causes": ["Faulty speed sensor", "Wiring damage", "Low trans fluid"]},
    "P0720": {"desc": "Output Speed Sensor Circuit Malfunction", "severity": "high",
              "system": "transmission", "common_causes": ["Faulty OSS", "Wiring", "Connector issue"]},
    "P0730": {"desc": "Incorrect Gear Ratio", "severity": "high",
              "system": "transmission", "common_causes": ["Low trans fluid", "Worn clutch packs", "Solenoid failure"]},
    "P0750": {"desc": "Shift Solenoid A Malfunction", "severity": "high",
              "system": "transmission", "common_causes": ["Faulty solenoid", "Dirty trans fluid", "Wiring"]},

    # Vehicle Speed / Idle
    "P0500": {"desc": "Vehicle Speed Sensor Malfunction", "severity": "moderate",
              "system": "drivetrain", "common_causes": ["Faulty VSS", "Wiring damage", "Speedometer gear"]},
    "P0505": {"desc": "Idle Air Control System Malfunction", "severity": "moderate",
              "system": "fuel_air", "common_causes": ["Dirty IAC valve", "Vacuum leak", "Throttle body carbon"]},
    "P0507": {"desc": "Idle Control System RPM Higher Than Expected", "severity": "low",
              "system": "fuel_air", "common_causes": ["Vacuum leak", "Dirty throttle body", "IAC valve issue"]},

    # Fuel System
    "P0190": {"desc": "Fuel Rail Pressure Sensor Circuit Malfunction", "severity": "high",
              "system": "fuel_air", "common_causes": ["Faulty fuel pressure sensor", "Wiring", "Low fuel pressure"]},
    "P0200": {"desc": "Injector Circuit Malfunction", "severity": "high",
              "system": "fuel_air", "common_causes": ["Faulty injector", "Wiring issue", "ECM problem"]},
    "P0201": {"desc": "Injector Circuit Malfunction - Cylinder 1", "severity": "high",
              "system": "fuel_air", "common_causes": ["Faulty injector cyl 1", "Open/short circuit"]},
}


class DTCDatabase:
    """Fast local DTC code lookup — no LLM needed for basic definitions."""

    def __init__(self, data_dir="data"):
        self.codes = dict(COMMON_DTCS)
        # Load extended database if available
        json_path = os.path.join(data_dir, "dtc_codes.json")
        if os.path.exists(json_path):
            with open(json_path) as f:
                extra = json.load(f)
                self.codes.update(extra)

    def lookup(self, code: str) -> dict | None:
        """Look up a single DTC code. Returns dict or None."""
        code = code.upper().strip()
        return self.codes.get(code)

    def lookup_many(self, codes: list[str]) -> dict:
        """Look up multiple DTC codes. Returns {code: info} dict."""
        results = {}
        for code in codes:
            info = self.lookup(code)
            if info:
                results[code] = info
            else:
                results[code] = {
                    "desc": f"Unknown code {code}",
                    "severity": "unknown",
                    "system": self._guess_system(code),
                    "common_causes": [],
                }
        return results

    def _guess_system(self, code: str) -> str:
        """Guess the system from the code prefix."""
        if len(code) >= 2:
            prefix = code[:2].upper()
            return DTC_CATEGORIES.get(prefix, "unknown")
        return "unknown"

    def format_for_llm(self, codes: list[str], live_data: dict | None = None) -> str:
        """Format DTC info + live data into a compact prompt for the LLM."""
        results = self.lookup_many(codes)
        lines = ["## Active Diagnostic Trouble Codes\n"]

        for code, info in results.items():
            severity = info["severity"].upper()
            lines.append(f"**{code}** [{severity}]: {info['desc']}")
            if info.get("common_causes"):
                causes = ", ".join(info["common_causes"][:4])
                lines.append(f"  Common causes: {causes}")
            lines.append("")

        if live_data:
            lines.append("## Live Sensor Data\n")
            for key, val in live_data.items():
                lines.append(f"- {key}: {val}")
            lines.append("")

        return "\n".join(lines)
