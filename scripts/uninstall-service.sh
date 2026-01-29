#!/bin/bash
set -e

SERVICE_NAME="com.voice-insight.worker-manager"
PLIST_PATH="$HOME/Library/LaunchAgents/${SERVICE_NAME}.plist"

echo "Uninstalling Voice Insight Worker Manager service..."

# Stop service if running
if launchctl list | grep -q "$SERVICE_NAME"; then
    echo "Stopping service..."
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
fi

# Remove plist
if [ -f "$PLIST_PATH" ]; then
    rm "$PLIST_PATH"
    echo "Removed: $PLIST_PATH"
fi

# Stop any running workers
echo "Stopping any running workers..."
curl -s -X POST http://localhost:8100/stop-all 2>/dev/null || true

echo "Service uninstalled"
