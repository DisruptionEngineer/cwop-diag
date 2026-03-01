#!/bin/bash
# Launch CWOP-Diag in kiosk mode on HyperPixel 4 Square
# Add this to autostart for a plug-and-play diagnostic tool

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

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

# Launch Chromium in kiosk mode
chromium-browser \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --disable-translate \
    --no-first-run \
    --window-size=720,720 \
    --window-position=0,0 \
    http://localhost:5000
