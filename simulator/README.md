# Pi Zero 2 W — OBD-II Simulator

Emulates an ELM327 OBD-II Bluetooth adapter on a Raspberry Pi Zero 2 W.
Use this for demos without a vehicle — two devices on the table, one
running the diagnostic tool, the other pretending to be a car.

## How It Works

The Pi Zero broadcasts a Bluetooth Serial Port Profile (SPP) service
that looks like an ELM327 adapter to the main Pi. It responds to
standard AT commands and OBD-II Mode 01 PID requests with simulated
sensor data.

Select from 5 preset scenarios via GPIO button or the web interface.

## Scenarios

| # | Name | DTCs | Key Symptoms |
|---|------|------|-------------|
| 1 | Lean Condition | P0171, P0174 | High LTFT both banks |
| 2 | Cylinder Misfire | P0300, P0301 | Rough idle, high STFT B1 |
| 3 | Catalytic Converter | P0420 | Normal sensors, cat failing |
| 4 | Overheating | P0217, P0116 | Coolant 118C, fan check |
| 5 | Transmission Fault | P0700, P0730 | High RPM, slipping |

## Hardware

- Raspberry Pi Zero 2 W
- Optional: momentary push button on GPIO 17 (cycles scenarios)
- Optional: LED on GPIO 27 (blinks to show active scenario number)

## Setup

```bash
# On the Pi Zero 2 W:
sudo apt-get install -y bluetooth bluez python3-pip
pip3 install flask
sudo python3 obd_simulator.py
```

## Pairing

The simulator advertises as "OBDSIM". On the diagnostic Pi:

```bash
bluetoothctl
> scan on
# Find OBDSIM MAC address
> pair XX:XX:XX:XX:XX:XX
> trust XX:XX:XX:XX:XX:XX
> quit

sudo rfcomm bind 0 XX:XX:XX:XX:XX:XX 1
# Now start cwop-diag with --port /dev/rfcomm0
```
