# CWOP-Diag: Complete Setup Guide

This guide walks you through setting up the entire CWOP-Diag system from scratch. It assumes you are comfortable with software concepts but new to hardware, Raspberry Pi, and Linux system administration.

**What you are building:**
A two-device demo rig that sits on a table. The Pi 5 runs the diagnostic dashboard on a small touchscreen. The Pi Zero 2 W pretends to be a car, sending fake (but realistic) engine data over Bluetooth. Later, you can swap the simulator for a real car by plugging in the Veepeak OBD-II adapter.

**Your hardware:**

| Device | Role |
|--------|------|
| Raspberry Pi 5 | Main diagnostic tool (dashboard + AI) |
| Raspberry Pi Zero 2 W | OBD-II simulator (pretends to be a car) |
| HyperPixel 4 Square | 720x720 touchscreen display for the Pi 5 |
| Veepeak OBDCheck BLE+ | Real OBD-II adapter for actual vehicles (arriving soon) |
| Mac mini M4 (10.10.7.56) | Fallback LLM server running Ollama |

**What you will need to buy/gather (if you do not already have them):**

- 2x microSD cards (32GB or larger, Class 10 or A2 speed rating)
- USB-C power supply for the Pi 5 (official 27W / 5.1V 5A recommended)
- Micro-USB power supply for the Pi Zero 2 W (5V 2.5A)
- A microSD card reader (if your Mac does not have one built in)
- A heatsink or cooling case for the Pi 5 (strongly recommended)

---

## Part 1: Pi 5 Setup (Diagnostic Tool)

This is the main device. It runs the dashboard, the AI engine, and displays everything on the HyperPixel touchscreen.

### Step 1.1: Download Raspberry Pi Imager

On your Mac, download and install **Raspberry Pi Imager**. This is the official tool for writing operating system images to SD cards.

1. Open a browser and go to: https://www.raspberrypi.com/software/
2. Download the macOS version.
3. Open the `.dmg` file and drag Raspberry Pi Imager into your Applications folder.
4. Launch it from Applications.

### Step 1.2: Flash the SD Card

Insert your first microSD card into your Mac (using a USB adapter if needed).

In Raspberry Pi Imager:

1. **Choose Device** -- Select "Raspberry Pi 5".
2. **Choose OS** -- Select "Raspberry Pi OS (other)" then select **"Raspberry Pi OS Lite (64-bit)"**. You want the Lite version (no desktop environment) because the kiosk will handle the display. The 64-bit version is required for llama.cpp performance.
3. **Choose Storage** -- Select your microSD card. Be careful to pick the right drive.
4. Click **Next**. It will ask if you want to customize the OS settings. Click **Edit Settings**.

### Step 1.3: Configure Before First Boot

In the customization dialog, fill in these settings. This saves you from needing to connect a monitor and keyboard to the Pi -- it will be ready to connect over your network on first boot.

**General tab:**

- **Set hostname:** `cwop-diag`
- **Set username and password:** Username `pi`, pick a password you will remember. Write it down.
- **Configure wireless LAN:** Enter your WiFi network name (SSID) and password. Set the country to `US`.
- **Set locale settings:** Timezone to your local timezone, keyboard layout to `us`.

**Services tab:**

- **Enable SSH:** Check this box. Select "Use password authentication".

Click **Save**, then **Yes** to apply the settings, then **Yes** to confirm writing (this erases the SD card).

Wait for the write and verification to finish. This takes a few minutes.

### Step 1.4: First Boot

1. Remove the microSD card from your Mac.
2. Insert it into the Pi 5 microSD slot (on the underside of the board, the spring-loaded metal slot).
3. Plug in the USB-C power cable. The Pi will power on automatically -- there is no power button. You will see a red LED (power) and a green LED (activity, it flickers while booting).
4. Wait about 60-90 seconds for the first boot to complete. The first boot takes longer than normal because it resizes the filesystem and applies your settings.

### Step 1.5: SSH In From Your Mac

Open Terminal on your Mac and type:

```bash
ssh pi@cwop-diag.local
```

If that does not work (sometimes `.local` hostnames take a moment to register), you can find the Pi's IP address from your router's admin page, or try:

```bash
ssh pi@cwop-diag
```

You will see a message like:

```
The authenticity of host 'cwop-diag.local' can't be established.
ED25519 key fingerprint is SHA256:xxxxx...
Are you sure you want to continue connecting (yes/no/[fingerprint])?
```

Type `yes` and press Enter. Then enter the password you set in Step 1.3.

You should now see a command prompt like:

```
pi@cwop-diag:~ $
```

You are now logged into your Pi 5 remotely. Everything from here on happens on the Pi through this SSH session.

### Step 1.6: Clone the Repository

```bash
git clone https://github.com/DisruptionEngineer/cwop-diag.git
cd cwop-diag
```

Expected output:

```
Cloning into 'cwop-diag'...
remote: Enumerating objects: ...
...
Resolving deltas: 100% ...
```

### Step 1.7: Run the Setup Script

The `setup.sh` script does a lot of heavy lifting. Here is what each step does before you run it:

| Step | What it does |
|------|-------------|
| 1/7 | Updates all system packages to the latest versions |
| 2/7 | Installs Python virtual environment, pip, and Bluetooth packages; creates a venv and installs the Python dependencies (Flask, python-OBD, requests) |
| 3/7 | Enables Bluetooth and creates a helper script (`obd-bt-setup`) for pairing OBD-II adapters later |
| 4/7 | Downloads and builds llama.cpp from source with OpenBLAS acceleration for ARM64. This is the engine that runs the local AI model. |
| 5/7 | Detects your Pi's RAM and downloads the right AI model from HuggingFace (Qwen2.5-1.5B for 4GB+ RAM) |
| 6/7 | Installs the Pimoroni HyperPixel 4 Square display drivers and Chromium browser for kiosk mode |
| 7/7 | Enables ZRAM (compressed swap in RAM) and disables unnecessary services to free up memory |

Run it:

```bash
chmod +x setup.sh
./setup.sh
```

This will take **15-30 minutes** depending on your internet speed. The llama.cpp compile step is the longest part. You will see progress as each step runs.

When it finishes, you will see:

```
===========================================
  Setup Complete!
===========================================

  Next steps:
  1. Pair your OBD-II adapter:
     sudo obd-bt-setup XX:XX:XX:XX:XX:XX
  2. Start the tool:
     cd /home/pi/cwop-diag && ./start.sh
```

### Step 1.8: HyperPixel 4 Square Display Setup

The HyperPixel 4 Square is a 720x720 IPS display that connects directly to the Pi's GPIO header. It does not use HDMI.

**Physical installation (do this with the Pi powered OFF):**

1. **Shut down the Pi first:** `sudo shutdown -h now` and wait 10 seconds, then unplug the power cable.
2. The HyperPixel has a 40-pin GPIO header on its underside. Line up the pins with the Pi 5's GPIO header. The display should sit directly on top of the Pi like a hat.
3. **Be gentle.** Push straight down, evenly. The pins should slide in smoothly. Do not force it at an angle or you can bend pins.
4. The display should be oriented so that the ribbon cable side of the display aligns with the USB ports of the Pi (check the Pimoroni documentation if you are unsure).

**Important Pi 5 gotchas:**

The Pimoroni HyperPixel 4 drivers were originally written for the Pi 4. On a Pi 5, you may need to use a DPI (Display Parallel Interface) overlay. The `setup.sh` script attempts to install the drivers, but if the display is blank after a reboot, try these steps:

1. Power the Pi back on (plug the USB-C cable back in) and SSH in again.
2. Edit the boot configuration:

```bash
sudo nano /boot/firmware/config.txt
```

3. Look for any `dtoverlay=hyperpixel` lines. If they are not present, add the following at the end of the file:

```
dtoverlay=vc4-kms-dpi-hyperpixel4sq
```

4. Save and exit nano: press `Ctrl+X`, then `Y`, then `Enter`.
5. Reboot:

```bash
sudo reboot
```

6. Wait 60 seconds, then SSH back in: `ssh pi@cwop-diag.local`

If the display shows the console text or a blank white screen, the driver is working. A completely dark/black screen with no backlight means the overlay is not loading correctly -- see Troubleshooting at the end of this guide.

### Step 1.9: Test in Demo Mode First

Before worrying about Bluetooth or OBD-II hardware, make sure the software works:

```bash
cd ~/cwop-diag
source venv/bin/activate
python app.py --demo
```

You should see:

```
 * Running on http://0.0.0.0:5000
```

Now, from your Mac's browser, open:

```
http://cwop-diag.local:5000
```

You should see the CWOP-Diag dashboard with simulated data -- RPM, coolant temperature, some demo DTCs, and an AI analysis section. If you see this, the software is working.

Press `Ctrl+C` in the SSH session to stop the server.

### Step 1.10: Set Up Kiosk Mode (Auto-start on Boot)

Kiosk mode makes the Pi boot directly into the dashboard on the HyperPixel display, with no desktop environment, no window borders, and no cursor. It looks like a dedicated appliance.

**First, you need a minimal X server to run Chromium.** Install it:

```bash
sudo apt-get install -y xserver-xorg xinit x11-xserver-utils
```

**Make the kiosk script executable:**

```bash
chmod +x ~/cwop-diag/kiosk.sh
```

**Create a systemd service so it starts on boot:**

```bash
sudo nano /etc/systemd/system/cwop-diag.service
```

Paste the following content:

[Unit]
Description=CWOP-Diag Kiosk
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
Environment=DISPLAY=:0
ExecStartPre=/usr/bin/startx -- -nocursor &
ExecStart=/home/pi/cwop-diag/kiosk.sh
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target

Save and exit (`Ctrl+X`, `Y`, `Enter`).

Alternatively, a simpler approach is to add the kiosk script to your `.bashrc` for auto-login, or use the `~/.xinitrc` method:

```bash
echo '~/cwop-diag/kiosk.sh' > ~/.xinitrc
```

Then configure auto-login and auto-start X:

```bash
sudo raspi-config
```

Navigate to: **System Options** > **Boot / Auto Login** > **Console Autologin**. Then exit.

Add to the end of `~/.bash_profile`:

```bash
echo '[[ -z $DISPLAY && $XDG_VTNR -eq 1 ]] && startx' >> ~/.bash_profile
```

This means: when the Pi boots, it auto-logs in as `pi`, which starts X, which runs `kiosk.sh`, which starts the backend and Chromium in fullscreen pointed at the dashboard.

Reboot to test:

```bash
sudo reboot
```

If everything works, the Pi will boot and after about 30-45 seconds the dashboard will appear on the HyperPixel display.

---

## Part 2: Pi Zero 2 W Setup (OBD-II Simulator)

The Pi Zero 2 W acts as a fake car. It advertises itself over Bluetooth as an ELM327 OBD-II adapter and responds with simulated engine data. This lets you demo the entire system without a vehicle.

### Step 2.1: Flash the SD Card

Back on your Mac, insert the second microSD card.

Open Raspberry Pi Imager:

1. **Choose Device** -- Select "Raspberry Pi Zero 2 W".
2. **Choose OS** -- Select **"Raspberry Pi OS Lite (32-bit)"**. The Pi Zero 2 W can technically run 64-bit, but 32-bit is more stable and better supported on the Zero 2 W's limited 512MB RAM. You do not need 64-bit here since you are not running llama.cpp on this device.
3. **Choose Storage** -- Select the microSD card.
4. Click **Next**, then **Edit Settings**.

**General tab:**

- **Set hostname:** `obdsim`
- **Set username and password:** Username `pi`, same password (or a different one -- your choice).
- **Configure wireless LAN:** Same WiFi network as the Pi 5.
- **Set locale settings:** Same timezone and keyboard layout.

**Services tab:**

- **Enable SSH:** Check this box. Use password authentication.

Click **Save**, **Yes**, **Yes**. Wait for it to finish.

### Step 2.2: First Boot

1. Remove the card from your Mac and insert it into the Pi Zero 2 W.
2. The Pi Zero 2 W's microSD slot is on the end of the board (not spring-loaded -- just push it in until it stops).
3. Connect power via the micro-USB port labeled **PWR** (there are two micro-USB ports -- use the one closest to the corner of the board, not the one labeled USB).
4. Wait about 90-120 seconds. The Pi Zero 2 W is slower than the Pi 5, especially on first boot.

### Step 2.3: SSH In

From your Mac:

```bash
ssh pi@obdsim.local
```

If `.local` does not resolve, check your router for the IP address. The Pi Zero 2 W sometimes takes a minute or two to appear on the network after first boot.

### Step 2.4: Install Dependencies

Once logged in:

```bash
sudo apt-get update
sudo apt-get install -y bluetooth bluez python3-pip python3-venv
```

For Bluetooth SPP (Serial Port Profile) support, you need PyBluez:

```bash
sudo apt-get install -y libbluetooth-dev
pip3 install pybluez flask
```

> **Note:** If `pip3 install pybluez` fails, you may need to install it in a virtual environment or use `--break-system-packages` flag: `pip3 install pybluez flask --break-system-packages`. This is safe on a dedicated simulator device.

### Step 2.5: Copy the Simulator Script

You have two options:

**Option A: Clone the repo (easiest):**

```bash
git clone https://github.com/DisruptionEngineer/cwop-diag.git
cd cwop-diag/simulator
```

**Option B: Copy just the simulator file from your Mac:**

On your Mac, run:

```bash
scp /Users/disruptionengineer/cwop-diag/simulator/obd_simulator.py pi@obdsim.local:~/
```

Then on the Pi Zero:

```bash
cd ~
```

### Step 2.6: Configure Bluetooth for SPP Advertising

The simulator needs Bluetooth set up so it can advertise as an OBD-II adapter. Run these commands:

```bash
# Make sure Bluetooth is running
sudo systemctl enable bluetooth
sudo systemctl start bluetooth

# Make the Pi Zero discoverable
sudo bluetoothctl << EOF
power on
discoverable on
agent on
default-agent
EOF
```

For the Bluetooth SPP service to work, you also need to enable the SP profile. Edit the Bluetooth service configuration:

```bash
sudo nano /etc/systemd/system/dbus-org.bluez.service
```

Find the line that starts with `ExecStart=` and add `--compat` at the end:

```
ExecStart=/usr/libexec/bluetooth/bluetoothd --compat
```

Save and exit (`Ctrl+X`, `Y`, `Enter`). Then reload and restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart bluetooth
```

Add the serial port profile:

```bash
sudo sdptool add SP
```

### Step 2.7: Test with TCP Mode First

Before dealing with Bluetooth, verify the simulator works using TCP (a simple network connection):

```bash
cd ~/cwop-diag/simulator   # or cd ~ if you used Option B
sudo python3 obd_simulator.py --tcp 35000
```

You should see:

```
==================================================
  CWOP-Diag: OBD-II Simulator
==================================================
  Scenario: Lean Condition
  DTCs: P0171, P0174
==================================================
[GPIO] Not available (not on Pi or not root)
[WEB] Control panel: http://localhost:8080
[SIM] TCP server listening on port 35000
[SIM] Connect with: python-OBD or 'nc localhost 35000'
[SIM] Waiting for connection...
```

The GPIO warning is normal if you have not wired up the optional button.

From your Mac, test the connection:

```bash
nc obdsim.local 35000
```

You should see `ELM327 v1.5` appear. Type these commands (press Enter after each):

```
ATZ
```

Expected response: `ELM327 v1.5`

```
010C
```

Expected response: something like `41 0C 0B B8` (this is the RPM value in hex)

```
03
```

Expected response: `43 02 01 71 01 74` (the stored DTCs: P0171 and P0174)

Press `Ctrl+C` on both the Mac (to close nc) and the Pi Zero (to stop the simulator).

If you see those responses, the simulator is working.

### Step 2.8: Web Control Panel

The simulator also runs a web control panel that lets you switch between the 5 diagnostic scenarios from any browser. When the simulator is running, open:

```
http://obdsim.local:8080
```

You will see buttons for each scenario. Clicking one instantly changes the simulated engine data and DTCs.

### Step 2.9: Optional GPIO Wiring (Button and LED)

This is completely optional. It lets you cycle through scenarios by pressing a physical button instead of using the web interface.

**You will need:**

- 1x momentary push button (any small tactile switch)
- 1x LED (any color)
- 1x 330 ohm resistor (for the LED)
- A few jumper wires (female-to-female or female-to-male depending on your button)

**Wiring diagram (BCM pin numbering):**

```
GPIO 17 (Pin 11) ----[BUTTON]---- GND (Pin 9)
GPIO 27 (Pin 13) ----[330R]----[LED+]---- GND (Pin 14)
```

How to read this:
- The button connects GPIO 17 to ground. When you press it, the Pi detects it.
- The LED connects GPIO 27 through a 330 ohm resistor to ground. The longer LED leg is positive (goes toward GPIO 27 via the resistor). The shorter leg goes to ground.

**Pin locations on the Pi Zero 2 W header:**

```
Pin 1  (3.3V)     Pin 2  (5V)
Pin 3  (GPIO 2)   Pin 4  (5V)
Pin 5  (GPIO 3)   Pin 6  (GND)
Pin 7  (GPIO 4)   Pin 8  (GPIO 14)
Pin 9  (GND) <--- Button ground
Pin 10 (GPIO 15)
Pin 11 (GPIO 17) <--- Button signal
Pin 12 (GPIO 18)
Pin 13 (GPIO 27) <--- LED signal
Pin 14 (GND) <--- LED ground
...
```

Pin 1 is the pin closest to the corner of the board with the microSD slot. Pins are numbered in a zigzag: odd pins on one side, even on the other.

When you press the button, the scenario cycles (lean -> misfire -> catalyst -> overheat -> trans -> lean...) and the LED blinks a number of times to indicate which scenario is now active (1 blink = lean, 2 = misfire, etc.).

If you wire this up, install the GPIO library:

```bash
sudo apt-get install -y python3-rpi.gpio
```

### Step 2.10: Start the Simulator in Bluetooth Mode

For the actual Bluetooth mode (what the Pi 5 will connect to):

```bash
cd ~/cwop-diag/simulator
sudo python3 obd_simulator.py
```

You should see:

```
==================================================
  CWOP-Diag: OBD-II Simulator
==================================================
  Scenario: Lean Condition
  DTCs: P0171, P0174
==================================================
[SIM] Bluetooth SPP listening on RFCOMM channel X
[SIM] Advertised as 'OBDSIM'
[SIM] Waiting for connection...
```

The simulator is now advertising itself as "OBDSIM" over Bluetooth. Leave it running.

You can start with a specific scenario using:

```bash
sudo python3 obd_simulator.py --scenario misfire
```

Available scenarios: `lean`, `misfire`, `catalyst`, `overheat`, `trans`.

---

## Part 3: Connecting the Two Devices

Now you will pair the Pi 5 (diagnostic tool) with the Pi Zero 2 W (simulator) over Bluetooth.

### Step 3.1: Make Sure Both Devices Are On

- **Pi Zero 2 W:** Running the simulator in Bluetooth mode (`sudo python3 obd_simulator.py`)
- **Pi 5:** SSH in from your Mac: `ssh pi@cwop-diag.local`

### Step 3.2: Scan for the Simulator from the Pi 5

On the Pi 5:

```bash
sudo bluetoothctl
```

You will enter the `bluetoothctl` interactive prompt. Type these commands one at a time:

```
power on
```

Expected: `Changing power on succeeded`

```
agent on
```

Expected: `Agent registered`

```
scan on
```

Now wait 10-20 seconds. You will see a list of Bluetooth devices appearing. Look for one called **OBDSIM** or one with the Pi Zero's MAC address. It will look something like:

```
[NEW] Device AA:BB:CC:DD:EE:FF OBDSIM
```

**Write down that MAC address** (the `AA:BB:CC:DD:EE:FF` part). You will need it.

Stop scanning:

```
scan off
```

### Step 3.3: Pair and Trust

Still in `bluetoothctl`:

```
pair AA:BB:CC:DD:EE:FF
```

(Replace `AA:BB:CC:DD:EE:FF` with the actual MAC address you noted.)

If it asks for a PIN, try `1234` or `0000`. Some Bluetooth SPP devices do not require a PIN.

```
trust AA:BB:CC:DD:EE:FF
```

Expected: `Changing AA:BB:CC:DD:EE:FF trust succeeded`

```
quit
```

### Step 3.4: Create the Serial Port Connection

The `rfcomm` command creates a virtual serial port (`/dev/rfcomm0`) that maps to the Bluetooth connection:

```bash
sudo rfcomm bind 0 AA:BB:CC:DD:EE:FF 1
```

Verify it was created:

```bash
ls -l /dev/rfcomm0
```

Expected output:

```
crw-rw---- 1 root dialout 216, 0 ... /dev/rfcomm0
```

On the Pi Zero, you should see the simulator print:

```
[SIM] Connected: ('AA:BB:CC:DD:EE:FF', 1)
```

### Step 3.5: Start CWOP-Diag Pointed at the Simulator

On the Pi 5:

```bash
cd ~/cwop-diag
source venv/bin/activate
python app.py --port /dev/rfcomm0
```

The dashboard should now be reading live (simulated) data from the Pi Zero via Bluetooth.

If you have the HyperPixel set up, you will see the dashboard displaying RPM, coolant temperature, fuel trims, and the active DTCs from whatever scenario the simulator is running.

### Step 3.6: Verify Data Flow

Open the dashboard in your Mac's browser at `http://cwop-diag.local:5000` and confirm:

- **Sensor data** is updating (RPM should be around 750, fluctuating slightly).
- **DTCs** are showing (P0171 and P0174 for the default "lean" scenario).
- **AI analysis** is running (if llama.cpp started successfully) or showing a placeholder (if in demo mode).

### Step 3.7: Cycle Scenarios on the Pi Zero

You can change what the simulator is reporting in three ways:

1. **Web interface:** Open `http://obdsim.local:8080` in your Mac's browser and click a scenario button.
2. **GPIO button:** If you wired up the button, press it to cycle to the next scenario.
3. **Restart with a flag:** Stop the simulator (`Ctrl+C`) and restart with `sudo python3 obd_simulator.py --scenario overheat`.

When you switch scenarios, the Pi 5 dashboard should update within a few seconds to show the new DTCs and sensor values.

---

## Part 4: Real Vehicle Setup (When OBD-II Adapter Arrives)

Once your Veepeak OBDCheck BLE+ arrives, you can connect to a real car.

### Step 4.1: Pair the Veepeak Adapter

1. Plug the Veepeak adapter into your vehicle's OBD-II port. **Where is it?** On most cars, the OBD-II port is under the dashboard on the driver's side, usually below and to the left of the steering column. It may be hidden behind a small panel. It is a trapezoidal 16-pin connector. The adapter plugs in with a satisfying click.

2. **Turn the vehicle's ignition to "ON"** (or start the engine). The Veepeak adapter powers itself from the OBD-II port and will start blinking.

3. On the Pi 5, scan for it:

```bash
sudo bluetoothctl
power on
agent on
scan on
```

Look for a device named **Veepeak** or **OBDBLE** or **V-LINK**. Note the MAC address.

```
scan off
pair AA:BB:CC:DD:EE:FF
trust AA:BB:CC:DD:EE:FF
quit
```

4. Bind the serial port:

```bash
sudo rfcomm bind 0 AA:BB:CC:DD:EE:FF 1
```

> **Note:** If you previously had the simulator bound to `/dev/rfcomm0`, release it first:
> ```bash
> sudo rfcomm release 0
> ```

### Step 4.2: Start CWOP-Diag in Live Mode

```bash
cd ~/cwop-diag
source venv/bin/activate
python app.py --port /dev/rfcomm0
```

Or, to use the full llama.cpp backend for real AI analysis:

```bash
./start.sh
```

The `start.sh` script automatically starts the llama.cpp server, waits for the model to load, and then launches the Flask dashboard.

### Step 4.3: What to Expect on First Real Scan

- **RPM:** Will show real engine RPM (around 650-900 at idle for most cars).
- **Coolant Temp:** Will climb from ambient to operating temperature (~85-100C) over a few minutes if you just started the car.
- **DTCs:** If your check engine light is on, you will see the stored diagnostic trouble codes. If no light is on, you may see zero DTCs.
- **Fuel Trims:** Real STFT and LTFT values. These fluctuate more than the simulator.
- **Speed:** 0 if parked, real speed if driving (do not use the touchscreen while driving).

> **Safety note:** Do not interact with the touchscreen while the vehicle is in motion. Set everything up while parked.

---

## Part 5: Using Mac Mini as Fallback LLM

Your Mac mini M4 at `10.10.7.56` runs Ollama with `qwen3:8b-optimized` -- a much more powerful model than what the Pi can run locally. You can point CWOP-Diag at it for better AI diagnostics.

### Step 5.1: Configure CWOP-Diag for Remote Ollama

Instead of using the local llama.cpp server on the Pi, tell the app to use your Mac mini:

```bash
cd ~/cwop-diag
source venv/bin/activate
python app.py --backend ollama --llm-url http://10.10.7.56:11434 --model qwen3:8b-optimized --port /dev/rfcomm0
```

Breaking down the flags:

| Flag | Meaning |
|------|---------|
| `--backend ollama` | Use the Ollama API instead of llama.cpp |
| `--llm-url http://10.10.7.56:11434` | Point to your Mac mini's Ollama instance |
| `--model qwen3:8b-optimized` | Use the 8B parameter model (much smarter than the Pi's 1.5B) |
| `--port /dev/rfcomm0` | OBD-II serial port (simulator or real adapter) |

### Step 5.2: When to Use Local vs. Remote LLM

| Situation | Recommended LLM | Why |
|-----------|-----------------|-----|
| Demo at home (on WiFi) | Remote Mac mini | Faster, smarter responses |
| Demo away from home | Local Pi llama.cpp | No dependency on network |
| In a real car (garage WiFi) | Remote Mac mini | Better diagnostic reasoning |
| In a real car (no WiFi) | Local Pi llama.cpp | Only option available |
| Quick test / development | `--demo` flag | No LLM at all, fastest |

### Step 5.3: Demo Mode (No LLM At All)

For quick testing without any LLM:

```bash
python app.py --demo
```

This uses pre-written sample responses instead of real AI analysis. Useful for testing the UI and OBD-II connection without waiting for model loading.

### Step 5.4: Verify Ollama Is Reachable

From the Pi 5, test that it can reach your Mac mini:

```bash
curl http://10.10.7.56:11434/api/tags
```

You should see a JSON response listing available models, including `qwen3:8b-optimized`. If you get "Connection refused" or a timeout, make sure:

- The Mac mini is powered on.
- Ollama is running on the Mac mini.
- Both devices are on the same network.
- No firewall is blocking port 11434.

---

## Tips and Troubleshooting

### Common Bluetooth Issues on Pi

**"No default controller available"**

The Bluetooth hardware is not being detected. Try:

```bash
sudo systemctl restart bluetooth
sudo hciconfig hci0 up
```

If `hciconfig` says "No such device", the Bluetooth adapter may not be enabled in the firmware. Check:

```bash
sudo nano /boot/firmware/config.txt
```

Make sure this line is NOT present or is not set to off:

```
dtoverlay=disable-bt
```

Reboot after any changes: `sudo reboot`

**"Failed to pair"**

- Make sure the other device is in discoverable mode.
- Try removing the device and re-pairing: `bluetoothctl` then `remove AA:BB:CC:DD:EE:FF`, then pair again.
- For the simulator, restart it: `Ctrl+C` then run again.

**rfcomm connection drops**

If the Bluetooth connection is unstable:

```bash
# Release and rebind
sudo rfcomm release 0
sudo rfcomm bind 0 AA:BB:CC:DD:EE:FF 1
```

### If HyperPixel Display Is Blank

**Completely black (no backlight):**

- The display overlay is not loaded. Make sure `/boot/firmware/config.txt` has the correct `dtoverlay` line (see Step 1.8).
- Try the alternative overlay name: `dtoverlay=hyperpixel4sq` or `dtoverlay=vc4-kms-dpi-hyperpixel4sq`.
- Reboot after changes.

**White screen or garbled colors:**

- The overlay is loading but the configuration may not match. Check Pimoroni's GitHub for Pi 5 compatibility notes.
- Try: `sudo apt-get install hyperpixel4` if Pimoroni has packaged the driver.

**Backlight on but nothing displayed:**

- X server may not be running. Try starting it manually: `startx` from the console.
- Check if Chromium launched: `ps aux | grep chromium`.

**Touch input not working or inverted:**

The HyperPixel touch input sometimes needs calibration or axis swapping. Create a calibration file:

```bash
sudo nano /etc/X11/xorg.conf.d/99-hyperpixel.conf
```

Try this configuration:

```
Section "InputClass"
    Identifier "HyperPixel4 Touch"
    MatchProduct "Goodix"
    Option "TransformationMatrix" "0 1 0 -1 0 1 0 0 1"
EndSection
```

The matrix values depend on orientation. `0 1 0 -1 0 1 0 0 1` is for 90-degree rotation. Try `1 0 0 0 1 0 0 0 1` for default (no rotation) first.

### If llama.cpp Model Fails to Load (RAM Issues)

The Pi 5 with 4GB or 8GB RAM should handle Qwen2.5-1.5B Q4_K_M (about 1.1GB model file). If you get out-of-memory errors:

```bash
# Check available memory
free -m

# Check what is using memory
top
```

**Free up RAM:**

```bash
# Disable unnecessary services
sudo systemctl stop avahi-daemon
sudo systemctl stop triggerhappy

# Make sure ZRAM is enabled (setup.sh should have done this)
sudo systemctl status zramswap
```

If the model still will not load, use the smaller 0.5B model:

```bash
# Download smaller model
wget -O ~/models/qwen2.5-0.5b-instruct-q4_k_m.gguf \
  https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf
```

Or skip the local model entirely and use the Mac mini Ollama backend (see Part 5).

### Cooling Recommendations

**Pi 5 (IMPORTANT):** The Pi 5 runs hotter than the Pi 4, especially when running llama.cpp. Running without cooling will cause thermal throttling (the CPU slows down to avoid overheating) and may trigger a warning icon on HDMI output.

- **Minimum:** A heatsink on the CPU. Passive aluminum heatsinks are about $5.
- **Recommended:** An active cooling case with a fan. The official Raspberry Pi Active Cooler ($5) clips directly onto the Pi 5 and keeps it well under 60C under load.
- **Best for this project:** A case that accommodates both the active cooler AND the HyperPixel display. This can be tricky -- you may need a case with an extended GPIO header or a tall case that fits both. Check Pimoroni's website for compatible cases.

**Pi Zero 2 W:** Runs cool enough for this application. No heatsink needed unless you are running it in an enclosed case in a hot environment.

### Power Supply Requirements

**Pi 5:**

- **Required:** USB-C, 5.1V, 5A (27W). The official Raspberry Pi 27W power supply is the safest choice.
- **Why it matters:** The Pi 5 draws more power than the Pi 4. An underpowered supply causes a yellow lightning bolt icon on screen, random crashes, and USB device failures.
- **Do NOT** use a phone charger. Most only supply 5V/2A or 3A, which is not enough.

**Pi Zero 2 W:**

- **Required:** Micro-USB, 5V, 2.5A. Almost any decent USB power supply works.
- **In the car:** You can power it from a USB car charger plugged into the cigarette lighter / 12V socket.

**In a vehicle:**

- The Pi 5 can be powered from a high-quality USB-C car charger (must output 5V/5A or support USB PD at 5V).
- The OBD-II adapter (Veepeak) powers itself from the car's OBD-II port. No separate power needed.

### Quick Reference: All Command-Line Flags

```bash
# App flags
python app.py --demo                         # Demo mode, no hardware needed
python app.py --port /dev/rfcomm0            # Specify OBD-II serial port
python app.py --backend ollama               # Use Ollama backend
python app.py --backend llamacpp             # Use llama.cpp backend
python app.py --llm-url http://IP:PORT       # LLM API URL
python app.py --model MODEL_NAME             # Ollama model name
python app.py --host 0.0.0.0                 # Flask bind address
python app.py --flask-port 5000              # Flask port number

# Simulator flags
sudo python3 obd_simulator.py               # Bluetooth mode (default)
sudo python3 obd_simulator.py --tcp 35000   # TCP mode for testing
sudo python3 obd_simulator.py --scenario X  # Start with specific scenario
sudo python3 obd_simulator.py --web-port 8080  # Web control panel port
sudo python3 obd_simulator.py --no-web      # Disable web control panel
```

### Quick Reference: Common Diagnostic Scenarios

| Scenario | DTCs | What It Simulates |
|----------|------|-------------------|
| `lean` | P0171, P0174 | Engine running lean (too much air, not enough fuel). Common cause: vacuum leak or failing MAF sensor. |
| `misfire` | P0300, P0301 | Cylinder misfires. Rough idle. Common cause: bad spark plug or ignition coil. |
| `catalyst` | P0420 | Catalytic converter below efficiency threshold. Common on older vehicles. |
| `overheat` | P0217, P0116 | Engine overheating. Coolant temp reads 118C (way too hot). Common cause: thermostat stuck closed, failed water pump, or low coolant. |
| `trans` | P0700, P0730 | Transmission slipping. High RPM with low speed. Common cause: worn clutch packs or low transmission fluid. |
