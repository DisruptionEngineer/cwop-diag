#!/bin/bash
# CWOP-Diag Start Script
# Starts llama.cpp server + Flask dashboard

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MODEL_DIR="$HOME/models"
LLAMA_DIR="$HOME/llama.cpp"

# Detect RAM for model selection
RAM_MB=$(free -m 2>/dev/null | awk '/^Mem:/{print $2}' || echo "0")

# Find model file
if [ -f "$MODEL_DIR/qwen2.5-1.5b-instruct-q4_k_m.gguf" ]; then
    MODEL="$MODEL_DIR/qwen2.5-1.5b-instruct-q4_k_m.gguf"
elif [ -f "$MODEL_DIR/qwen2.5-0.5b-instruct-q4_k_m.gguf" ]; then
    MODEL="$MODEL_DIR/qwen2.5-0.5b-instruct-q4_k_m.gguf"
else
    echo "[!] No model found in $MODEL_DIR"
    echo "    Running in DEMO mode (no LLM)."
    echo ""
    cd "$SCRIPT_DIR"
    source venv/bin/activate 2>/dev/null || true
    python app.py --demo
    exit 0
fi

echo "==========================================="
echo "  CWOP-Diag: Starting"
echo "==========================================="
echo "  Model: $(basename $MODEL)"
echo "  RAM: ${RAM_MB}MB"
echo ""

# Start llama.cpp server in background
echo "[1/2] Starting LLM server..."
LLAMA_SERVER="$LLAMA_DIR/build/bin/llama-server"

if [ ! -f "$LLAMA_SERVER" ]; then
    echo "[!] llama-server not found at $LLAMA_SERVER"
    echo "    Run setup.sh first, or running in demo mode."
    cd "$SCRIPT_DIR"
    source venv/bin/activate 2>/dev/null || true
    python app.py --demo
    exit 0
fi

# Kill any existing llama-server
pkill -f llama-server 2>/dev/null || true
sleep 1

$LLAMA_SERVER \
    -m "$MODEL" \
    -t 4 \
    -c 2048 \
    -b 512 \
    --host 127.0.0.1 \
    --port 8080 \
    --mlock \
    -ngl 0 \
    > /tmp/llama-server.log 2>&1 &

LLAMA_PID=$!
echo "  llama-server PID: $LLAMA_PID"

# Wait for llama.cpp to load model
echo "  Waiting for model to load..."
for i in $(seq 1 60); do
    if curl -s http://127.0.0.1:8080/health > /dev/null 2>&1; then
        echo "  LLM ready!"
        break
    fi
    if [ $i -eq 60 ]; then
        echo "  [!] LLM server did not start in 60s. Check /tmp/llama-server.log"
        echo "  Running in demo mode instead."
        kill $LLAMA_PID 2>/dev/null || true
        cd "$SCRIPT_DIR"
        source venv/bin/activate 2>/dev/null || true
        python app.py --demo
        exit 0
    fi
    sleep 1
done

# Start Flask app
echo "[2/2] Starting dashboard..."
cd "$SCRIPT_DIR"
source venv/bin/activate 2>/dev/null || true

# Trap to clean up llama-server on exit
cleanup() {
    echo ""
    echo "Shutting down..."
    kill $LLAMA_PID 2>/dev/null || true
    exit 0
}
trap cleanup INT TERM

python app.py --backend llamacpp --llm-url http://127.0.0.1:8080

# Clean up
cleanup
