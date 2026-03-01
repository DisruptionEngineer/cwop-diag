"""
OBD-II data collection layer.
Connects to an ELM327-compatible Bluetooth adapter via python-OBD.
Provides live sensor data and DTC reading.

In demo mode, generates realistic simulated data for development
without requiring a car or OBD-II adapter.
"""

import time
import random
import threading
from dataclasses import dataclass, field

try:
    import obd
    OBD_AVAILABLE = True
except ImportError:
    OBD_AVAILABLE = False


@dataclass
class SensorSnapshot:
    """A point-in-time snapshot of vehicle sensor data."""
    timestamp: float = 0.0
    rpm: float = 0.0
    speed: float = 0.0
    coolant_temp: float = 0.0
    intake_temp: float = 0.0
    maf: float = 0.0
    throttle_pos: float = 0.0
    engine_load: float = 0.0
    fuel_pressure: float = 0.0
    short_fuel_trim_1: float = 0.0
    long_fuel_trim_1: float = 0.0
    short_fuel_trim_2: float = 0.0
    long_fuel_trim_2: float = 0.0
    timing_advance: float = 0.0
    o2_voltage_b1s1: float = 0.0
    fuel_status: str = ""
    dtcs: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "RPM": f"{self.rpm:.0f}",
            "Speed": f"{self.speed:.0f} km/h",
            "Coolant Temp": f"{self.coolant_temp:.0f} C",
            "Intake Temp": f"{self.intake_temp:.0f} C",
            "MAF": f"{self.maf:.1f} g/s",
            "Throttle": f"{self.throttle_pos:.1f}%",
            "Engine Load": f"{self.engine_load:.1f}%",
            "STFT B1": f"{self.short_fuel_trim_1:+.1f}%",
            "LTFT B1": f"{self.long_fuel_trim_1:+.1f}%",
            "STFT B2": f"{self.short_fuel_trim_2:+.1f}%",
            "LTFT B2": f"{self.long_fuel_trim_2:+.1f}%",
            "O2 B1S1": f"{self.o2_voltage_b1s1:.2f}V",
            "Timing Adv": f"{self.timing_advance:.1f} deg",
        }

    def to_compact(self) -> str:
        """Compact string for LLM context (saves tokens)."""
        parts = []
        for k, v in self.to_dict().items():
            parts.append(f"{k}={v}")
        return " | ".join(parts)


class OBDReader:
    """Reads live data from an ELM327 OBD-II adapter via Bluetooth."""

    def __init__(self, port: str = "/dev/rfcomm0", demo: bool = False):
        self.port = port
        self.demo = demo
        self.connection = None
        self.latest = SensorSnapshot()
        self._running = False
        self._thread = None

    def connect(self) -> bool:
        """Connect to the OBD-II adapter."""
        if self.demo:
            print("[OBD] Running in DEMO mode (simulated data)")
            return True

        if not OBD_AVAILABLE:
            print("[OBD] python-obd not installed. Run: pip install obd")
            return False

        try:
            self.connection = obd.OBD(self.port, fast=False, timeout=30)
            if self.connection.is_connected():
                print(f"[OBD] Connected to {self.port}")
                print(f"[OBD] Protocol: {self.connection.protocol_name()}")
                return True
            else:
                print(f"[OBD] Failed to connect to {self.port}")
                return False
        except Exception as e:
            print(f"[OBD] Connection error: {e}")
            return False

    def disconnect(self):
        """Disconnect from the adapter."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        if self.connection:
            self.connection.close()
            self.connection = None

    def read_dtcs(self) -> list[str]:
        """Read active DTCs from the vehicle."""
        if self.demo:
            return self._demo_dtcs()

        if not self.connection or not self.connection.is_connected():
            return []

        response = self.connection.query(obd.commands.GET_DTC)
        if response.is_null():
            return []

        return [code for code, desc in response.value]

    def read_snapshot(self) -> SensorSnapshot:
        """Read a single snapshot of all sensor data."""
        if self.demo:
            return self._demo_snapshot()

        snap = SensorSnapshot(timestamp=time.time())

        if not self.connection or not self.connection.is_connected():
            return snap

        queries = {
            "rpm": obd.commands.RPM,
            "speed": obd.commands.SPEED,
            "coolant_temp": obd.commands.COOLANT_TEMP,
            "intake_temp": obd.commands.INTAKE_TEMP,
            "maf": obd.commands.MAF,
            "throttle_pos": obd.commands.THROTTLE_POS,
            "engine_load": obd.commands.ENGINE_LOAD,
            "short_fuel_trim_1": obd.commands.SHORT_FUEL_TRIM_1,
            "long_fuel_trim_1": obd.commands.LONG_FUEL_TRIM_1,
            "timing_advance": obd.commands.TIMING_ADVANCE,
        }

        for attr, cmd in queries.items():
            try:
                resp = self.connection.query(cmd)
                if not resp.is_null():
                    setattr(snap, attr, resp.value.magnitude)
            except Exception:
                pass

        return snap

    def start_polling(self, interval: float = 2.0):
        """Start background polling of sensor data."""
        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop, args=(interval,), daemon=True
        )
        self._thread.start()

    def _poll_loop(self, interval: float):
        while self._running:
            try:
                self.latest = self.read_snapshot()
                self.latest.dtcs = self.read_dtcs()
            except Exception as e:
                print(f"[OBD] Poll error: {e}")
            time.sleep(interval)

    # --- Demo mode (simulated data) ---

    def _demo_snapshot(self) -> SensorSnapshot:
        """Generate realistic simulated sensor data."""
        base_rpm = 750 + random.gauss(0, 30)
        return SensorSnapshot(
            timestamp=time.time(),
            rpm=max(0, base_rpm),
            speed=0,
            coolant_temp=88 + random.gauss(0, 2),
            intake_temp=32 + random.gauss(0, 3),
            maf=3.5 + random.gauss(0, 0.5),
            throttle_pos=15.2 + random.gauss(0, 1),
            engine_load=22.0 + random.gauss(0, 3),
            fuel_pressure=35 + random.gauss(0, 2),
            short_fuel_trim_1=2.3 + random.gauss(0, 1),
            long_fuel_trim_1=6.8 + random.gauss(0, 0.5),
            short_fuel_trim_2=1.8 + random.gauss(0, 1),
            long_fuel_trim_2=5.2 + random.gauss(0, 0.5),
            timing_advance=14.5 + random.gauss(0, 1),
            o2_voltage_b1s1=0.45 + random.gauss(0, 0.15),
            fuel_status="Closed loop",
        )

    def _demo_dtcs(self) -> list[str]:
        """Return a fixed set of demo DTCs for testing."""
        return ["P0171", "P0174"]
