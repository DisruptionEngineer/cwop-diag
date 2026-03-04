#!/usr/bin/env python3
"""
OBD-II ELM327 Simulator for Pi Zero 2 W.

Emulates an ELM327 Bluetooth OBD-II adapter with preset diagnostic
scenarios. Responds to standard AT commands and Mode 01/03 PID requests.

Usage:
    sudo python3 obd_simulator.py                  # Bluetooth mode
    sudo python3 obd_simulator.py --tcp 35000       # TCP mode (for testing)
    sudo python3 obd_simulator.py --scenario misfire # Start with specific scenario

Requires root for Bluetooth SPP.
"""

import argparse
import json
import os
import random
import signal
import socket
import struct
import subprocess
import sys
import threading
import time

# ===================== SCENARIOS =====================

SCENARIOS = {
    "lean": {
        "name": "Lean Condition",
        "description": "Engine running lean on both banks — vacuum leak or fuel delivery issue",
        "dtcs": ["P0171", "P0174"],
        "pids": {
            "010C": {"name": "RPM", "value": 750, "jitter": 30, "formula": lambda v: format_rpm(v)},
            "010D": {"name": "Speed", "value": 0, "jitter": 0, "formula": lambda v: format_byte(v)},
            "0105": {"name": "Coolant Temp", "value": 88, "jitter": 2, "formula": lambda v: format_temp(v)},
            "010F": {"name": "Intake Temp", "value": 32, "jitter": 3, "formula": lambda v: format_temp(v)},
            "0110": {"name": "MAF", "value": 3.5, "jitter": 0.5, "formula": lambda v: format_maf(v)},
            "0111": {"name": "Throttle", "value": 15, "jitter": 1, "formula": lambda v: format_percent(v)},
            "0104": {"name": "Engine Load", "value": 22, "jitter": 3, "formula": lambda v: format_percent(v)},
            "0106": {"name": "STFT B1", "value": 2.3, "jitter": 1.5, "formula": lambda v: format_fuel_trim(v)},
            "0107": {"name": "LTFT B1", "value": 6.8, "jitter": 0.5, "formula": lambda v: format_fuel_trim(v)},
            "0108": {"name": "STFT B2", "value": 1.8, "jitter": 1.5, "formula": lambda v: format_fuel_trim(v)},
            "0109": {"name": "LTFT B2", "value": 5.2, "jitter": 0.5, "formula": lambda v: format_fuel_trim(v)},
            "010E": {"name": "Timing Adv", "value": 14.5, "jitter": 1, "formula": lambda v: format_timing(v)},
            "0114": {"name": "O2 B1S1", "value": 0.45, "jitter": 0.15, "formula": lambda v: format_o2(v)},
        },
    },
    "misfire": {
        "name": "Cylinder Misfire",
        "description": "Random and cylinder-specific misfires — ignition or fuel issue",
        "dtcs": ["P0300", "P0301"],
        "pids": {
            "010C": {"name": "RPM", "value": 685, "jitter": 60, "formula": lambda v: format_rpm(v)},
            "010D": {"name": "Speed", "value": 0, "jitter": 0, "formula": lambda v: format_byte(v)},
            "0105": {"name": "Coolant Temp", "value": 91, "jitter": 2, "formula": lambda v: format_temp(v)},
            "010F": {"name": "Intake Temp", "value": 34, "jitter": 2, "formula": lambda v: format_temp(v)},
            "0110": {"name": "MAF", "value": 2.8, "jitter": 0.8, "formula": lambda v: format_maf(v)},
            "0111": {"name": "Throttle", "value": 14, "jitter": 2, "formula": lambda v: format_percent(v)},
            "0104": {"name": "Engine Load", "value": 18, "jitter": 5, "formula": lambda v: format_percent(v)},
            "0106": {"name": "STFT B1", "value": 8.1, "jitter": 3, "formula": lambda v: format_fuel_trim(v)},
            "0107": {"name": "LTFT B1", "value": 4.2, "jitter": 0.5, "formula": lambda v: format_fuel_trim(v)},
            "0108": {"name": "STFT B2", "value": 1.2, "jitter": 1, "formula": lambda v: format_fuel_trim(v)},
            "0109": {"name": "LTFT B2", "value": 2.1, "jitter": 0.5, "formula": lambda v: format_fuel_trim(v)},
            "010E": {"name": "Timing Adv", "value": 10.0, "jitter": 3, "formula": lambda v: format_timing(v)},
            "0114": {"name": "O2 B1S1", "value": 0.35, "jitter": 0.2, "formula": lambda v: format_o2(v)},
        },
    },
    "catalyst": {
        "name": "Catalytic Converter",
        "description": "Catalyst efficiency below threshold — aging or failing converter",
        "dtcs": ["P0420"],
        "pids": {
            "010C": {"name": "RPM", "value": 740, "jitter": 25, "formula": lambda v: format_rpm(v)},
            "010D": {"name": "Speed", "value": 0, "jitter": 0, "formula": lambda v: format_byte(v)},
            "0105": {"name": "Coolant Temp", "value": 92, "jitter": 1, "formula": lambda v: format_temp(v)},
            "010F": {"name": "Intake Temp", "value": 30, "jitter": 2, "formula": lambda v: format_temp(v)},
            "0110": {"name": "MAF", "value": 3.8, "jitter": 0.3, "formula": lambda v: format_maf(v)},
            "0111": {"name": "Throttle", "value": 15, "jitter": 1, "formula": lambda v: format_percent(v)},
            "0104": {"name": "Engine Load", "value": 21, "jitter": 2, "formula": lambda v: format_percent(v)},
            "0106": {"name": "STFT B1", "value": 0.8, "jitter": 1, "formula": lambda v: format_fuel_trim(v)},
            "0107": {"name": "LTFT B1", "value": 1.5, "jitter": 0.3, "formula": lambda v: format_fuel_trim(v)},
            "0108": {"name": "STFT B2", "value": 0.4, "jitter": 0.8, "formula": lambda v: format_fuel_trim(v)},
            "0109": {"name": "LTFT B2", "value": 1.2, "jitter": 0.3, "formula": lambda v: format_fuel_trim(v)},
            "010E": {"name": "Timing Adv", "value": 15.0, "jitter": 1, "formula": lambda v: format_timing(v)},
            "0114": {"name": "O2 B1S1", "value": 0.50, "jitter": 0.1, "formula": lambda v: format_o2(v)},
        },
    },
    "overheat": {
        "name": "Overheating",
        "description": "Engine overheating — coolant system failure or fan issue",
        "dtcs": ["P0217", "P0116"],
        "pids": {
            "010C": {"name": "RPM", "value": 780, "jitter": 40, "formula": lambda v: format_rpm(v)},
            "010D": {"name": "Speed", "value": 0, "jitter": 0, "formula": lambda v: format_byte(v)},
            "0105": {"name": "Coolant Temp", "value": 118, "jitter": 3, "formula": lambda v: format_temp(v)},
            "010F": {"name": "Intake Temp", "value": 45, "jitter": 3, "formula": lambda v: format_temp(v)},
            "0110": {"name": "MAF", "value": 3.2, "jitter": 0.5, "formula": lambda v: format_maf(v)},
            "0111": {"name": "Throttle", "value": 16, "jitter": 1, "formula": lambda v: format_percent(v)},
            "0104": {"name": "Engine Load", "value": 26, "jitter": 3, "formula": lambda v: format_percent(v)},
            "0106": {"name": "STFT B1", "value": 3.1, "jitter": 1, "formula": lambda v: format_fuel_trim(v)},
            "0107": {"name": "LTFT B1", "value": 2.8, "jitter": 0.3, "formula": lambda v: format_fuel_trim(v)},
            "0108": {"name": "STFT B2", "value": 2.4, "jitter": 1, "formula": lambda v: format_fuel_trim(v)},
            "0109": {"name": "LTFT B2", "value": 2.2, "jitter": 0.3, "formula": lambda v: format_fuel_trim(v)},
            "010E": {"name": "Timing Adv", "value": 8.0, "jitter": 2, "formula": lambda v: format_timing(v)},
            "0114": {"name": "O2 B1S1", "value": 0.55, "jitter": 0.1, "formula": lambda v: format_o2(v)},
        },
    },
    "trans": {
        "name": "Transmission Fault",
        "description": "Transmission slipping or incorrect gear ratio",
        "dtcs": ["P0700", "P0730"],
        "pids": {
            "010C": {"name": "RPM", "value": 1250, "jitter": 100, "formula": lambda v: format_rpm(v)},
            "010D": {"name": "Speed", "value": 15, "jitter": 3, "formula": lambda v: format_byte(v)},
            "0105": {"name": "Coolant Temp", "value": 90, "jitter": 2, "formula": lambda v: format_temp(v)},
            "010F": {"name": "Intake Temp", "value": 33, "jitter": 2, "formula": lambda v: format_temp(v)},
            "0110": {"name": "MAF", "value": 8.5, "jitter": 2, "formula": lambda v: format_maf(v)},
            "0111": {"name": "Throttle", "value": 22, "jitter": 3, "formula": lambda v: format_percent(v)},
            "0104": {"name": "Engine Load", "value": 32, "jitter": 5, "formula": lambda v: format_percent(v)},
            "0106": {"name": "STFT B1", "value": 1.4, "jitter": 1, "formula": lambda v: format_fuel_trim(v)},
            "0107": {"name": "LTFT B1", "value": 2.0, "jitter": 0.3, "formula": lambda v: format_fuel_trim(v)},
            "0108": {"name": "STFT B2", "value": 0.9, "jitter": 0.8, "formula": lambda v: format_fuel_trim(v)},
            "0109": {"name": "LTFT B2", "value": 1.8, "jitter": 0.3, "formula": lambda v: format_fuel_trim(v)},
            "010E": {"name": "Timing Adv", "value": 12.0, "jitter": 2, "formula": lambda v: format_timing(v)},
            "0114": {"name": "O2 B1S1", "value": 0.48, "jitter": 0.1, "formula": lambda v: format_o2(v)},
        },
    },
    "oil_pressure": {
        "name": "Oil Pressure Warning",
        "description": "Low oil pressure sensor reading — possible oil pump or sensor issue",
        "dtcs": ["P0520", "P0521"],
        "pids": {
            "010C": {"name": "RPM", "value": 740, "jitter": 25, "formula": lambda v: format_rpm(v)},
            "010D": {"name": "Speed", "value": 0, "jitter": 0, "formula": lambda v: format_byte(v)},
            "0105": {"name": "Coolant Temp", "value": 90, "jitter": 2, "formula": lambda v: format_temp(v)},
            "010F": {"name": "Intake Temp", "value": 33, "jitter": 2, "formula": lambda v: format_temp(v)},
            "0110": {"name": "MAF", "value": 3.5, "jitter": 0.3, "formula": lambda v: format_maf(v)},
            "0111": {"name": "Throttle", "value": 15, "jitter": 1, "formula": lambda v: format_percent(v)},
            "0104": {"name": "Engine Load", "value": 19, "jitter": 2, "formula": lambda v: format_percent(v)},
            "0106": {"name": "STFT B1", "value": 0.5, "jitter": 0.8, "formula": lambda v: format_fuel_trim(v)},
            "0107": {"name": "LTFT B1", "value": 1.2, "jitter": 0.3, "formula": lambda v: format_fuel_trim(v)},
            "0108": {"name": "STFT B2", "value": 0.3, "jitter": 0.6, "formula": lambda v: format_fuel_trim(v)},
            "0109": {"name": "LTFT B2", "value": 1.0, "jitter": 0.3, "formula": lambda v: format_fuel_trim(v)},
            "010E": {"name": "Timing Adv", "value": 14.0, "jitter": 1, "formula": lambda v: format_timing(v)},
            "0114": {"name": "O2 B1S1", "value": 0.47, "jitter": 0.1, "formula": lambda v: format_o2(v)},
        },
    },
    "low_coolant": {
        "name": "Stuck Thermostat / Low Coolant",
        "description": "Thermostat stuck open — engine not reaching operating temperature",
        "dtcs": ["P0117", "P0128"],
        "pids": {
            "010C": {"name": "RPM", "value": 780, "jitter": 30, "formula": lambda v: format_rpm(v)},
            "010D": {"name": "Speed", "value": 0, "jitter": 0, "formula": lambda v: format_byte(v)},
            "0105": {"name": "Coolant Temp", "value": 55, "jitter": 3, "formula": lambda v: format_temp(v)},
            "010F": {"name": "Intake Temp", "value": 28, "jitter": 2, "formula": lambda v: format_temp(v)},
            "0110": {"name": "MAF", "value": 3.8, "jitter": 0.4, "formula": lambda v: format_maf(v)},
            "0111": {"name": "Throttle", "value": 16, "jitter": 1, "formula": lambda v: format_percent(v)},
            "0104": {"name": "Engine Load", "value": 24, "jitter": 3, "formula": lambda v: format_percent(v)},
            "0106": {"name": "STFT B1", "value": 4.5, "jitter": 1.5, "formula": lambda v: format_fuel_trim(v)},
            "0107": {"name": "LTFT B1", "value": 5.8, "jitter": 0.5, "formula": lambda v: format_fuel_trim(v)},
            "0108": {"name": "STFT B2", "value": 3.8, "jitter": 1.2, "formula": lambda v: format_fuel_trim(v)},
            "0109": {"name": "LTFT B2", "value": 5.2, "jitter": 0.4, "formula": lambda v: format_fuel_trim(v)},
            "010E": {"name": "Timing Adv", "value": 12.0, "jitter": 1.5, "formula": lambda v: format_timing(v)},
            "0114": {"name": "O2 B1S1", "value": 0.40, "jitter": 0.12, "formula": lambda v: format_o2(v)},
        },
    },
    "o2_sensor": {
        "name": "O2 Sensor Fault",
        "description": "Oxygen sensor stuck low — inaccurate air/fuel readings",
        "dtcs": ["P0131", "P0133"],
        "pids": {
            "010C": {"name": "RPM", "value": 730, "jitter": 25, "formula": lambda v: format_rpm(v)},
            "010D": {"name": "Speed", "value": 0, "jitter": 0, "formula": lambda v: format_byte(v)},
            "0105": {"name": "Coolant Temp", "value": 91, "jitter": 2, "formula": lambda v: format_temp(v)},
            "010F": {"name": "Intake Temp", "value": 33, "jitter": 2, "formula": lambda v: format_temp(v)},
            "0110": {"name": "MAF", "value": 3.6, "jitter": 0.3, "formula": lambda v: format_maf(v)},
            "0111": {"name": "Throttle", "value": 15, "jitter": 1, "formula": lambda v: format_percent(v)},
            "0104": {"name": "Engine Load", "value": 21, "jitter": 2, "formula": lambda v: format_percent(v)},
            "0106": {"name": "STFT B1", "value": 5.5, "jitter": 2, "formula": lambda v: format_fuel_trim(v)},
            "0107": {"name": "LTFT B1", "value": 8.2, "jitter": 0.5, "formula": lambda v: format_fuel_trim(v)},
            "0108": {"name": "STFT B2", "value": 1.0, "jitter": 0.8, "formula": lambda v: format_fuel_trim(v)},
            "0109": {"name": "LTFT B2", "value": 1.5, "jitter": 0.3, "formula": lambda v: format_fuel_trim(v)},
            "010E": {"name": "Timing Adv", "value": 13.5, "jitter": 1, "formula": lambda v: format_timing(v)},
            "0114": {"name": "O2 B1S1", "value": 0.15, "jitter": 0.03, "formula": lambda v: format_o2(v)},
        },
    },
    "egr": {
        "name": "EGR System Fault",
        "description": "Exhaust gas recirculation valve clogged or stuck",
        "dtcs": ["P0401", "P0402"],
        "pids": {
            "010C": {"name": "RPM", "value": 720, "jitter": 45, "formula": lambda v: format_rpm(v)},
            "010D": {"name": "Speed", "value": 0, "jitter": 0, "formula": lambda v: format_byte(v)},
            "0105": {"name": "Coolant Temp", "value": 93, "jitter": 2, "formula": lambda v: format_temp(v)},
            "010F": {"name": "Intake Temp", "value": 48, "jitter": 4, "formula": lambda v: format_temp(v)},
            "0110": {"name": "MAF", "value": 3.2, "jitter": 0.6, "formula": lambda v: format_maf(v)},
            "0111": {"name": "Throttle", "value": 15, "jitter": 2, "formula": lambda v: format_percent(v)},
            "0104": {"name": "Engine Load", "value": 23, "jitter": 4, "formula": lambda v: format_percent(v)},
            "0106": {"name": "STFT B1", "value": 1.8, "jitter": 1.2, "formula": lambda v: format_fuel_trim(v)},
            "0107": {"name": "LTFT B1", "value": 2.5, "jitter": 0.3, "formula": lambda v: format_fuel_trim(v)},
            "0108": {"name": "STFT B2", "value": 1.2, "jitter": 1, "formula": lambda v: format_fuel_trim(v)},
            "0109": {"name": "LTFT B2", "value": 2.0, "jitter": 0.3, "formula": lambda v: format_fuel_trim(v)},
            "010E": {"name": "Timing Adv", "value": 11.0, "jitter": 2, "formula": lambda v: format_timing(v)},
            "0114": {"name": "O2 B1S1", "value": 0.50, "jitter": 0.12, "formula": lambda v: format_o2(v)},
        },
    },
    "evap": {
        "name": "EVAP System Leak",
        "description": "Fuel vapor leak detected — often a loose gas cap",
        "dtcs": ["P0440", "P0455"],
        "pids": {
            "010C": {"name": "RPM", "value": 745, "jitter": 20, "formula": lambda v: format_rpm(v)},
            "010D": {"name": "Speed", "value": 0, "jitter": 0, "formula": lambda v: format_byte(v)},
            "0105": {"name": "Coolant Temp", "value": 90, "jitter": 2, "formula": lambda v: format_temp(v)},
            "010F": {"name": "Intake Temp", "value": 32, "jitter": 2, "formula": lambda v: format_temp(v)},
            "0110": {"name": "MAF", "value": 3.6, "jitter": 0.3, "formula": lambda v: format_maf(v)},
            "0111": {"name": "Throttle", "value": 15, "jitter": 1, "formula": lambda v: format_percent(v)},
            "0104": {"name": "Engine Load", "value": 21, "jitter": 2, "formula": lambda v: format_percent(v)},
            "0106": {"name": "STFT B1", "value": 0.8, "jitter": 0.8, "formula": lambda v: format_fuel_trim(v)},
            "0107": {"name": "LTFT B1", "value": 1.2, "jitter": 0.3, "formula": lambda v: format_fuel_trim(v)},
            "0108": {"name": "STFT B2", "value": 0.5, "jitter": 0.6, "formula": lambda v: format_fuel_trim(v)},
            "0109": {"name": "LTFT B2", "value": 1.0, "jitter": 0.3, "formula": lambda v: format_fuel_trim(v)},
            "010E": {"name": "Timing Adv", "value": 15.0, "jitter": 1, "formula": lambda v: format_timing(v)},
            "0114": {"name": "O2 B1S1", "value": 0.48, "jitter": 0.1, "formula": lambda v: format_o2(v)},
        },
    },
    "idle": {
        "name": "High Idle / Idle Control",
        "description": "Engine idling too high — idle air control valve issue",
        "dtcs": ["P0505", "P0507"],
        "pids": {
            "010C": {"name": "RPM", "value": 1100, "jitter": 50, "formula": lambda v: format_rpm(v)},
            "010D": {"name": "Speed", "value": 0, "jitter": 0, "formula": lambda v: format_byte(v)},
            "0105": {"name": "Coolant Temp", "value": 91, "jitter": 2, "formula": lambda v: format_temp(v)},
            "010F": {"name": "Intake Temp", "value": 34, "jitter": 2, "formula": lambda v: format_temp(v)},
            "0110": {"name": "MAF", "value": 5.2, "jitter": 0.6, "formula": lambda v: format_maf(v)},
            "0111": {"name": "Throttle", "value": 15, "jitter": 1, "formula": lambda v: format_percent(v)},
            "0104": {"name": "Engine Load", "value": 28, "jitter": 3, "formula": lambda v: format_percent(v)},
            "0106": {"name": "STFT B1", "value": -1.5, "jitter": 1, "formula": lambda v: format_fuel_trim(v)},
            "0107": {"name": "LTFT B1", "value": -0.8, "jitter": 0.3, "formula": lambda v: format_fuel_trim(v)},
            "0108": {"name": "STFT B2", "value": -1.2, "jitter": 0.8, "formula": lambda v: format_fuel_trim(v)},
            "0109": {"name": "LTFT B2", "value": -0.5, "jitter": 0.3, "formula": lambda v: format_fuel_trim(v)},
            "010E": {"name": "Timing Adv", "value": 16.0, "jitter": 1, "formula": lambda v: format_timing(v)},
            "0114": {"name": "O2 B1S1", "value": 0.52, "jitter": 0.1, "formula": lambda v: format_o2(v)},
        },
    },
    "knock": {
        "name": "Engine Knock / Detonation",
        "description": "Knock sensor detecting detonation — timing retarded",
        "dtcs": ["P0325", "P0332"],
        "pids": {
            "010C": {"name": "RPM", "value": 735, "jitter": 50, "formula": lambda v: format_rpm(v)},
            "010D": {"name": "Speed", "value": 0, "jitter": 0, "formula": lambda v: format_byte(v)},
            "0105": {"name": "Coolant Temp", "value": 95, "jitter": 3, "formula": lambda v: format_temp(v)},
            "010F": {"name": "Intake Temp", "value": 38, "jitter": 3, "formula": lambda v: format_temp(v)},
            "0110": {"name": "MAF", "value": 3.4, "jitter": 0.5, "formula": lambda v: format_maf(v)},
            "0111": {"name": "Throttle", "value": 15, "jitter": 1, "formula": lambda v: format_percent(v)},
            "0104": {"name": "Engine Load", "value": 25, "jitter": 4, "formula": lambda v: format_percent(v)},
            "0106": {"name": "STFT B1", "value": 2.0, "jitter": 1.5, "formula": lambda v: format_fuel_trim(v)},
            "0107": {"name": "LTFT B1", "value": 3.5, "jitter": 0.5, "formula": lambda v: format_fuel_trim(v)},
            "0108": {"name": "STFT B2", "value": 1.8, "jitter": 1.2, "formula": lambda v: format_fuel_trim(v)},
            "0109": {"name": "LTFT B2", "value": 3.0, "jitter": 0.4, "formula": lambda v: format_fuel_trim(v)},
            "010E": {"name": "Timing Adv", "value": 2.0, "jitter": 1.5, "formula": lambda v: format_timing(v)},
            "0114": {"name": "O2 B1S1", "value": 0.42, "jitter": 0.12, "formula": lambda v: format_o2(v)},
        },
    },
    "fuel_pressure": {
        "name": "Low Fuel Pressure",
        "description": "Fuel rail pressure below normal — weak fuel pump or clogged filter",
        "dtcs": ["P0190", "P0191"],
        "pids": {
            "010C": {"name": "RPM", "value": 710, "jitter": 35, "formula": lambda v: format_rpm(v)},
            "010D": {"name": "Speed", "value": 0, "jitter": 0, "formula": lambda v: format_byte(v)},
            "0105": {"name": "Coolant Temp", "value": 89, "jitter": 2, "formula": lambda v: format_temp(v)},
            "010F": {"name": "Intake Temp", "value": 33, "jitter": 2, "formula": lambda v: format_temp(v)},
            "0110": {"name": "MAF", "value": 2.8, "jitter": 0.4, "formula": lambda v: format_maf(v)},
            "0111": {"name": "Throttle", "value": 14, "jitter": 1, "formula": lambda v: format_percent(v)},
            "0104": {"name": "Engine Load", "value": 20, "jitter": 3, "formula": lambda v: format_percent(v)},
            "0106": {"name": "STFT B1", "value": 7.5, "jitter": 2, "formula": lambda v: format_fuel_trim(v)},
            "0107": {"name": "LTFT B1", "value": 9.8, "jitter": 0.5, "formula": lambda v: format_fuel_trim(v)},
            "0108": {"name": "STFT B2", "value": 6.8, "jitter": 1.8, "formula": lambda v: format_fuel_trim(v)},
            "0109": {"name": "LTFT B2", "value": 8.5, "jitter": 0.5, "formula": lambda v: format_fuel_trim(v)},
            "010E": {"name": "Timing Adv", "value": 13.0, "jitter": 1.5, "formula": lambda v: format_timing(v)},
            "0114": {"name": "O2 B1S1", "value": 0.38, "jitter": 0.15, "formula": lambda v: format_o2(v)},
        },
    },
}


# ===================== PID FORMATTERS =====================
# ELM327 returns hex bytes. These encode sensor values per SAE J1979.

def format_rpm(rpm):
    """RPM = ((A*256)+B)/4"""
    v = int(max(0, rpm) * 4)
    a = (v >> 8) & 0xFF
    b = v & 0xFF
    return f"41 0C {a:02X} {b:02X}"


def format_byte(val):
    """Single byte value (speed, etc.)"""
    v = int(max(0, min(255, val)))
    return f"41 0D {v:02X}"


def format_temp(temp):
    """Temp = A - 40 (range: -40 to 215C)"""
    v = int(max(0, min(255, temp + 40)))
    return f"41 05 {v:02X}"


def format_percent(pct):
    """Percent = A * 100 / 255"""
    v = int(max(0, min(255, pct * 255 / 100)))
    return f"41 04 {v:02X}"


def format_fuel_trim(trim):
    """Fuel trim: (A - 128) * 100 / 128 (range: -100% to +99.2%)"""
    v = int(max(0, min(255, (trim * 128 / 100) + 128)))
    return f"41 06 {v:02X}"


def format_maf(maf):
    """MAF = ((A*256)+B) / 100 (g/s)"""
    v = int(max(0, maf * 100))
    a = (v >> 8) & 0xFF
    b = v & 0xFF
    return f"41 10 {a:02X} {b:02X}"


def format_timing(deg):
    """Timing advance = A / 2 - 64"""
    v = int(max(0, min(255, (deg + 64) * 2)))
    return f"41 0E {v:02X}"


def format_o2(volts):
    """O2 voltage = A / 200 (0-1.275V)"""
    v = int(max(0, min(255, volts * 200)))
    return f"41 14 {v:02X} FF"


def format_dtc(code):
    """Convert DTC string (e.g. 'P0171') to two-byte hex."""
    prefix = {"P": 0, "C": 1, "B": 2, "U": 3}
    p = prefix.get(code[0], 0)
    num = int(code[1:], 16)
    val = (p << 14) | num
    a = (val >> 8) & 0xFF
    b = val & 0xFF
    return f"{a:02X} {b:02X}"


# ===================== ELM327 EMULATOR =====================

class ELM327Emulator:
    """Emulates ELM327 OBD-II adapter AT and OBD commands."""

    def __init__(self, scenario="lean"):
        self.scenario_name = scenario
        self.scenario = SCENARIOS[scenario]
        self.echo = True
        self.linefeed = True
        self.headers = False
        self.protocol = "auto"

    def set_scenario(self, name):
        if name in SCENARIOS:
            self.scenario_name = name
            self.scenario = SCENARIOS[name]
            print(f"[SIM] Scenario: {self.scenario['name']}")

    def cycle_scenario(self):
        names = list(SCENARIOS.keys())
        idx = (names.index(self.scenario_name) + 1) % len(names)
        self.set_scenario(names[idx])

    def process_command(self, cmd):
        """Process an ELM327/OBD command and return the response."""
        cmd = cmd.strip().upper()

        # Remove spaces
        cmd_clean = cmd.replace(" ", "")

        # AT commands
        if cmd_clean.startswith("AT"):
            return self._handle_at(cmd_clean[2:])

        # OBD Mode 01 (current data)
        if cmd_clean.startswith("01"):
            pid = cmd_clean[:4]
            return self._handle_mode01(pid)

        # OBD Mode 03 (stored DTCs)
        if cmd_clean == "03":
            return self._handle_mode03()

        # OBD Mode 04 (clear DTCs)
        if cmd_clean == "04":
            return "44"

        # OBD Mode 09 (vehicle info)
        if cmd_clean.startswith("09"):
            return self._handle_mode09(cmd_clean)

        return "?"

    def _handle_at(self, cmd):
        """Handle AT (adapter) commands."""
        if cmd in ("Z", "WS"):
            return "ELM327 v1.5"
        if cmd == "E0":
            self.echo = False
            return "OK"
        if cmd == "E1":
            self.echo = True
            return "OK"
        if cmd == "L0":
            self.linefeed = False
            return "OK"
        if cmd == "L1":
            self.linefeed = True
            return "OK"
        if cmd == "H0":
            self.headers = False
            return "OK"
        if cmd == "H1":
            self.headers = True
            return "OK"
        if cmd.startswith("SP"):
            self.protocol = cmd[2:]
            return "OK"
        if cmd == "DPN":
            return "A6"  # ISO 15765-4 CAN
        if cmd == "RV":
            return "12.6V"
        if cmd == "I":
            return "ELM327 v1.5"
        if cmd == "D":
            return "OK"
        if cmd.startswith("ST") or cmd.startswith("AT"):
            return "OK"
        return "OK"

    def _handle_mode01(self, pid):
        """Handle Mode 01 PID request."""
        # Supported PIDs
        if pid == "0100":
            return "41 00 BE 3F A8 13"  # Supported PIDs 01-20
        if pid == "0120":
            return "41 20 80 00 00 00"  # Supported PIDs 21-40

        pid_upper = pid.upper()
        if pid_upper in self.scenario["pids"]:
            p = self.scenario["pids"][pid_upper]
            val = p["value"] + random.gauss(0, p["jitter"] * 0.5)
            return p["formula"](val)

        return "NO DATA"

    def _handle_mode03(self):
        """Handle Mode 03 — return stored DTCs."""
        dtcs = self.scenario["dtcs"]
        if not dtcs:
            return "43 00"

        parts = ["43"]
        count = len(dtcs)
        parts.append(f"{count:02X}")
        for code in dtcs:
            parts.append(format_dtc(code))
        return " ".join(parts)

    def _handle_mode09(self, cmd):
        """Handle Mode 09 (vehicle info)."""
        if cmd == "0902":
            # VIN
            return "49 02 01 57 42 41 50 42 35 43 35 35 46 41 31 32 33 34 35 36"
        return "NO DATA"


# ===================== BLUETOOTH SPP SERVER =====================

def start_bluetooth_server(emulator):
    """Start Bluetooth SPP server (requires root and bluez)."""
    try:
        import bluetooth
    except ImportError:
        print("[SIM] PyBluez not installed. Install with: pip3 install pybluez")
        print("[SIM] Falling back to TCP mode on port 35000")
        start_tcp_server(emulator, 35000)
        return

    server_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
    server_sock.bind(("", bluetooth.PORT_ANY))
    server_sock.listen(1)
    port = server_sock.getsockname()[1]

    uuid = "00001101-0000-1000-8000-00805F9B34FB"  # SPP UUID
    bluetooth.advertise_service(
        server_sock, "OBDSIM",
        service_id=uuid,
        service_classes=[uuid, bluetooth.SERIAL_PORT_CLASS],
        profiles=[bluetooth.SERIAL_PORT_PROFILE],
    )

    print(f"[SIM] Bluetooth SPP listening on RFCOMM channel {port}")
    print(f"[SIM] Advertised as 'OBDSIM'")
    print(f"[SIM] Scenario: {emulator.scenario['name']}")

    while True:
        print("[SIM] Waiting for connection...")
        client_sock, client_info = server_sock.accept()
        print(f"[SIM] Connected: {client_info}")
        handle_client(client_sock, emulator)


def start_tcp_server(emulator, port):
    """Start TCP server for testing without Bluetooth."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", port))
    server.listen(1)
    print(f"[SIM] TCP server listening on port {port}")
    print(f"[SIM] Scenario: {emulator.scenario['name']}")
    print(f"[SIM] Connect with: python-OBD or 'nc localhost {port}'")

    while True:
        print("[SIM] Waiting for connection...")
        client, addr = server.accept()
        print(f"[SIM] Connected: {addr}")
        handle_client(client, emulator)


def handle_client(sock, emulator):
    """Handle a connected client (Bluetooth or TCP)."""
    try:
        # Send initial prompt
        sock.sendall(b"ELM327 v1.5\r\n>")
        buf = ""
        while True:
            data = sock.recv(1024)
            if not data:
                break
            buf += data.decode("ascii", errors="ignore")

            # Process complete commands (terminated by \r)
            while "\r" in buf:
                cmd, buf = buf.split("\r", 1)
                cmd = cmd.strip()
                if not cmd:
                    sock.sendall(b">")
                    continue

                response = emulator.process_command(cmd)
                reply = f"{response}\r\n>"
                sock.sendall(reply.encode("ascii"))

    except (ConnectionResetError, BrokenPipeError, OSError):
        print("[SIM] Client disconnected")
    finally:
        sock.close()


# ===================== GPIO (optional) =====================

def setup_gpio(emulator):
    """Set up GPIO button to cycle scenarios (Pi Zero 2 W)."""
    try:
        import RPi.GPIO as GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(17, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(27, GPIO.OUT)

        def button_callback(channel):
            emulator.cycle_scenario()
            # Blink LED to show scenario number
            idx = list(SCENARIOS.keys()).index(emulator.scenario_name) + 1
            for _ in range(idx):
                GPIO.output(27, GPIO.HIGH)
                time.sleep(0.15)
                GPIO.output(27, GPIO.LOW)
                time.sleep(0.15)

        GPIO.add_event_detect(17, GPIO.FALLING, callback=button_callback, bouncetime=500)
        print("[GPIO] Button on pin 17, LED on pin 27")
        return True
    except (ImportError, RuntimeError):
        print("[GPIO] Not available (not on Pi or not root)")
        return False


# ===================== WEB CONTROL =====================

def start_web_control(emulator, port=8080):
    """Simple web interface to switch scenarios."""
    from flask import Flask, jsonify, request, make_response

    web = Flask(__name__)

    def cors_response(data, status=200):
        """Create a JSON response with CORS headers."""
        resp = make_response(jsonify(data), status)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return resp

    @web.after_request
    def add_cors(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    @web.route("/")
    def index():
        html = "<h2>CWOP-Diag OBD-II Simulator</h2>"
        html += f"<p>Current: <strong>{emulator.scenario['name']}</strong></p>"
        html += f"<p>DTCs: {', '.join(emulator.scenario['dtcs'])}</p><hr>"
        for name, s in SCENARIOS.items():
            active = " (ACTIVE)" if name == emulator.scenario_name else ""
            html += f'<a href="/scenario/{name}"><button style="margin:4px;padding:8px 16px">{s["name"]}{active}</button></a>'
        return html

    @web.route("/scenario/<name>")
    def set_scenario(name):
        if name in SCENARIOS:
            emulator.set_scenario(name)
            return cors_response({"status": "ok", "scenario": name, "name": SCENARIOS[name]["name"]})
        return cors_response({"status": "error", "message": f"Unknown scenario: {name}"}, 400)

    @web.route("/api/status")
    def status():
        return cors_response({
            "scenario": emulator.scenario_name,
            "name": emulator.scenario["name"],
            "dtcs": emulator.scenario["dtcs"],
            "description": emulator.scenario.get("description", ""),
        })

    @web.route("/api/scenarios")
    def list_scenarios():
        scenarios = []
        for key, s in SCENARIOS.items():
            scenarios.append({
                "key": key,
                "name": s["name"],
                "description": s.get("description", ""),
                "dtcs": s["dtcs"],
                "active": key == emulator.scenario_name,
            })
        return cors_response({"scenarios": scenarios, "count": len(scenarios)})

    @web.route("/api/pids")
    def current_pids():
        """Return current PID values decoded as human-readable."""
        pids = {}
        for pid_key, pid_info in emulator.scenario["pids"].items():
            val = pid_info["value"] + random.gauss(0, pid_info["jitter"] * 0.5)
            pids[pid_info["name"]] = round(val, 2)
        return cors_response({
            "scenario": emulator.scenario_name,
            "pids": pids,
            "dtcs": emulator.scenario["dtcs"],
        })

    threading.Thread(target=lambda: web.run(host="0.0.0.0", port=port, debug=False), daemon=True).start()
    print(f"[WEB] Control panel: http://localhost:{port}")


# ===================== MAIN =====================

def main():
    parser = argparse.ArgumentParser(description="OBD-II ELM327 Simulator for Pi Zero 2 W")
    parser.add_argument("--scenario", default="lean", choices=SCENARIOS.keys(),
                        help="Starting scenario")
    parser.add_argument("--tcp", type=int, default=None, metavar="PORT",
                        help="Use TCP instead of Bluetooth (for testing)")
    parser.add_argument("--web-port", type=int, default=8080,
                        help="Web control panel port")
    parser.add_argument("--no-web", action="store_true",
                        help="Disable web control panel")
    args = parser.parse_args()

    emulator = ELM327Emulator(scenario=args.scenario)

    print("=" * 50)
    print("  CWOP-Diag: OBD-II Simulator")
    print("=" * 50)
    print(f"  Scenario: {emulator.scenario['name']}")
    print(f"  DTCs: {', '.join(emulator.scenario['dtcs'])}")
    print("=" * 50)

    # Set up GPIO if on Pi
    setup_gpio(emulator)

    # Start web control panel
    if not args.no_web:
        try:
            start_web_control(emulator, args.web_port)
        except ImportError:
            print("[WEB] Flask not installed, skipping web control")

    # Start server
    if args.tcp:
        start_tcp_server(emulator, args.tcp)
    else:
        start_bluetooth_server(emulator)


if __name__ == "__main__":
    main()
