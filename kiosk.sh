#!/bin/bash
# Launch CWOP-Diag in kiosk mode
# Supports dual-screen (HyperPixel 720x720 + Touch Display 2 720x1280)
# Falls back to single-screen if only one display is connected.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FLASK_PORT=5005

# Wait for display to be ready
sleep 5

# Hide cursor
unclutter -idle 0.5 -root &

# Disable screen blanking
xset s off
xset -dpms
xset s noblank

# Start the backend
"$SCRIPT_DIR/start.sh" &
sleep 10

# Detect connected displays
DISPLAY_COUNT=$(xrandr --query 2>/dev/null | grep -c " connected")

if [ "$DISPLAY_COUNT" -ge 2 ]; then
    echo "[Kiosk] Dual-screen mode ($DISPLAY_COUNT displays detected)"

    # Screen 1: Tech dashboard (HyperPixel 720x720, primary)
    chromium-browser \
        --kiosk \
        --noerrdialogs \
        --disable-infobars \
        --disable-session-crashed-bubble \
        --disable-translate \
        --no-first-run \
        --user-data-dir=/tmp/cwop-tech \
        --window-size=720,720 \
        --window-position=0,0 \
        http://localhost:$FLASK_PORT &

    sleep 2

    # Screen 2: Customer screen (Touch Display 2 720x1280)
    chromium-browser \
        --kiosk \
        --noerrdialogs \
        --disable-infobars \
        --disable-session-crashed-bubble \
        --disable-translate \
        --no-first-run \
        --user-data-dir=/tmp/cwop-customer \
        --window-size=720,1280 \
        --window-position=720,0 \
        http://localhost:$FLASK_PORT/customer &

else
    echo "[Kiosk] Single-screen mode"

    # Single screen: Tech dashboard only
    chromium-browser \
        --kiosk \
        --noerrdialogs \
        --disable-infobars \
        --disable-session-crashed-bubble \
        --disable-translate \
        --no-first-run \
        --window-size=720,720 \
        --window-position=0,0 \
        http://localhost:$FLASK_PORT
fi
