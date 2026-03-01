# CWOP-Diag: Smart Automotive Diagnostic Tool

An AI-powered OBD-II diagnostic tool running entirely on a Raspberry Pi 4 with a HyperPixel 4 Square touchscreen display. Reads live vehicle data, interprets diagnostic trouble codes, and provides repair recommendations using a local LLM.

## Hardware Requirements

| Component | Model | Est. Cost |
|-----------|-------|-----------|
| Raspberry Pi 4 | 4GB or 8GB recommended | ~$55-75 |
| HyperPixel 4 Square | Pimoroni, 720x720 touch | ~$55 |
| OBD-II Adapter | Veepeak OBDCheck BLE+ or Vgate iCar Pro | ~$20-30 |
| Power Supply | Official 5.1V/3A USB-C | ~$10 |
| microSD Card | 32GB+ Class 10/A2 | ~$10 |
| Heatsink + Fan | Any Pi 4 cooling kit | ~$10 |

**Total: ~$160-190** (assuming you have a Pi 4 already)

> **BlueDriver will NOT work.** It uses a proprietary Bluetooth protocol locked to its app. You need a standard ELM327-compatible adapter.

## Software Stack

- **OS:** Raspberry Pi OS 64-bit Lite
- **LLM:** llama.cpp with Qwen2.5-1.5B-Instruct (Q4_K_M)
- **OBD-II:** python-OBD (Bluetooth ELM327)
- **Backend:** Python / Flask
- **Frontend:** HTML/CSS/JS (720x720 kiosk)
- **Database:** SQLite (DTC codes, sessions)

## Quick Start (on Pi)

```bash
# 1. Clone
git clone https://github.com/DisruptionEngineer/cwop-diag.git
cd cwop-diag

# 2. Run setup (installs everything)
chmod +x setup.sh
./setup.sh

# 3. Start the diagnostic tool
./start.sh
```

## Quick Start (Development on Mac)

```bash
# 1. Clone and setup
cd cwop-diag
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Run in demo mode (no OBD-II hardware needed)
python app.py --demo

# 3. Open browser to http://localhost:5000
```

## Architecture

```
┌─────────────────────────────────────────┐
│         Raspberry Pi 4                  │
│                                         │
│  python-OBD ──▶ CWOP Engine ──▶ LLM    │
│  (Bluetooth)    (context slots)  (local)│
│       │              │             │    │
│       └──────────────┴─────────────┘    │
│                    │                    │
│            Flask Web Server             │
│            Chromium Kiosk               │
│            HyperPixel 4" 720x720       │
└─────────────────────────────────────────┘
        ▲ Bluetooth
   Veepeak/Vgate ELM327 ──── Car OBD-II
```

## Project Structure

```
cwop-diag/
├── app.py                 # Main Flask application
├── obd_reader.py          # OBD-II data collection
├── llm_engine.py          # LLM inference (llama.cpp / Ollama)
├── cwop_engine.py         # Context window orchestration
├── dtc_database.py        # DTC code lookup database
├── requirements.txt       # Python dependencies
├── setup.sh               # Pi setup script
├── start.sh               # Launch script
├── data/
│   └── dtc_codes.json     # Standard OBD-II DTC database
├── static/
│   ├── style.css          # Dashboard styles (720x720)
│   └── app.js             # Frontend logic
├── templates/
│   └── dashboard.html     # Main dashboard template
└── tests/
    ├── test_obd_reader.py
    └── test_cwop_engine.py
```

## Display

The HyperPixel 4 Square (720x720) runs a touch-optimized dashboard showing:
- Active DTCs with severity indicators
- Live sensor data (RPM, coolant temp, fuel trims, etc.)
- AI diagnostic recommendations
- Context budget visualization

## LLM Model Options

| Pi 4 RAM | Recommended Model | Speed |
|----------|-------------------|-------|
| 2GB | Qwen2.5-0.5B Q4_K_M | ~8 tok/s |
| 4GB | Qwen2.5-1.5B Q4_K_M | ~4 tok/s |
| 8GB | Phi-4-Mini 3.8B Q4_K_M | ~2 tok/s |

## License

MIT
