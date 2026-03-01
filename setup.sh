#!/bin/bash
# CWOP-Diag Setup Script for Raspberry Pi 4
# Run this once on a fresh Raspberry Pi OS 64-bit install.

set -e

echo "==========================================="
echo "  CWOP-Diag: Raspberry Pi Setup"
echo "==========================================="

# --- System Updates ---
echo "[1/7] Updating system packages..."
sudo apt-get update -qq
sudo apt-get upgrade -y -qq

# --- Python Environment ---
echo "[2/7] Setting up Python environment..."
sudo apt-get install -y -qq python3-venv python3-pip bluetooth bluez
cd "$(dirname "$0")"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

# --- Bluetooth Setup ---
echo "[3/7] Configuring Bluetooth for OBD-II..."
sudo systemctl enable bluetooth
sudo systemctl start bluetooth

# Create rfcomm binding script for ELM327
cat > /tmp/obd-bt-setup.sh << 'BTEOF'
#!/bin/bash
# Pair and bind OBD-II adapter
# Usage: ./obd-bt-setup.sh XX:XX:XX:XX:XX:XX
if [ -z "$1" ]; then
    echo "Usage: $0 <OBD-II-MAC-ADDRESS>"
    echo "Find your adapter MAC: bluetoothctl → scan on → look for OBD/Veepeak/Vgate"
    exit 1
fi
MAC=$1
echo "Pairing with $MAC..."
bluetoothctl << EOF
power on
agent on
pair $MAC
trust $MAC
EOF
echo "Creating /dev/rfcomm0..."
sudo rfcomm bind 0 $MAC 1
echo "Done! OBD-II adapter bound to /dev/rfcomm0"
BTEOF
chmod +x /tmp/obd-bt-setup.sh
sudo cp /tmp/obd-bt-setup.sh /usr/local/bin/obd-bt-setup

# --- llama.cpp Build ---
echo "[4/7] Building llama.cpp for ARM64..."
sudo apt-get install -y -qq build-essential cmake libopenblas-dev

if [ ! -d "$HOME/llama.cpp" ]; then
    git clone https://github.com/ggml-org/llama.cpp.git "$HOME/llama.cpp"
fi

cd "$HOME/llama.cpp"
git pull -q
cmake -B build \
    -DGGML_OPENBLAS=ON \
    -DGGML_NATIVE=ON \
    -DCMAKE_BUILD_TYPE=Release 2>/dev/null
cmake --build build -j4 --target llama-server llama-cli 2>&1 | tail -5

echo "[llama.cpp] Built successfully at $HOME/llama.cpp/build/bin/"

# --- Download Model ---
echo "[5/7] Downloading LLM model..."
MODEL_DIR="$HOME/models"
mkdir -p "$MODEL_DIR"

# Detect RAM and choose model
RAM_MB=$(free -m | awk '/^Mem:/{print $2}')
echo "  Detected RAM: ${RAM_MB}MB"

if [ "$RAM_MB" -ge 7000 ]; then
    MODEL_NAME="qwen2.5-1.5b-instruct-q4_k_m.gguf"
    MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"
    echo "  8GB Pi detected → Qwen2.5-1.5B Q4_K_M"
elif [ "$RAM_MB" -ge 3000 ]; then
    MODEL_NAME="qwen2.5-1.5b-instruct-q4_k_m.gguf"
    MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"
    echo "  4GB Pi detected → Qwen2.5-1.5B Q4_K_M"
else
    MODEL_NAME="qwen2.5-0.5b-instruct-q4_k_m.gguf"
    MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf"
    echo "  2GB Pi detected → Qwen2.5-0.5B Q4_K_M"
fi

if [ ! -f "$MODEL_DIR/$MODEL_NAME" ]; then
    echo "  Downloading model (this may take a few minutes)..."
    wget -q --show-progress -O "$MODEL_DIR/$MODEL_NAME" "$MODEL_URL"
else
    echo "  Model already downloaded."
fi

# --- HyperPixel Setup ---
echo "[6/7] Installing HyperPixel 4 Square drivers..."
# Pimoroni HyperPixel driver
if [ ! -d "$HOME/hyperpixel4sq" ]; then
    git clone https://github.com/pimoroni/hyperpixel4 "$HOME/hyperpixel4sq" 2>/dev/null || true
    cd "$HOME/hyperpixel4sq"
    sudo ./install.sh 2>/dev/null || echo "  HyperPixel driver may need manual setup — see README"
fi

# Install Chromium for kiosk mode
sudo apt-get install -y -qq chromium-browser unclutter

# --- Optimization ---
echo "[7/7] Applying Pi optimizations..."

# Enable ZRAM (compressed swap in RAM)
sudo apt-get install -y -qq zram-tools
echo 'ALGO=lz4' | sudo tee /etc/default/zramswap > /dev/null
echo 'PERCENT=50' | sudo tee -a /etc/default/zramswap > /dev/null
sudo systemctl enable zramswap
sudo systemctl restart zramswap

# Disable unnecessary services to free RAM
sudo systemctl disable --now triggerhappy 2>/dev/null || true
sudo systemctl disable --now avahi-daemon 2>/dev/null || true

echo ""
echo "==========================================="
echo "  Setup Complete!"
echo "==========================================="
echo ""
echo "  Next steps:"
echo "  1. Pair your OBD-II adapter:"
echo "     sudo obd-bt-setup XX:XX:XX:XX:XX:XX"
echo "  2. Start the tool:"
echo "     cd $(pwd) && ./start.sh"
echo ""
echo "  Model: $MODEL_DIR/$MODEL_NAME"
echo "  llama.cpp: $HOME/llama.cpp/build/bin/llama-server"
echo ""
