#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_NAME="com.voice-insight.worker-manager"
PLIST_PATH="$HOME/Library/LaunchAgents/${SERVICE_NAME}.plist"

echo "Installing Voice Insight Worker Manager service..."

# Create LaunchAgents directory if needed
mkdir -p "$HOME/Library/LaunchAgents"

# Get Python path from uv
PYTHON_PATH=$(cd "$PROJECT_DIR" && uv run which python)

# Create plist file
cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${SERVICE_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>-m</string>
        <string>src.worker_manager</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>${PROJECT_DIR}</string>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/voice-insight-worker-manager.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/voice-insight-worker-manager.log</string>
</dict>
</plist>
EOF

echo "Service installed at: $PLIST_PATH"
echo ""
echo "To start the service:"
echo "  launchctl load $PLIST_PATH"
echo ""
echo "To stop the service:"
echo "  launchctl unload $PLIST_PATH"
echo ""
echo "To view logs:"
echo "  tail -f /tmp/voice-insight-worker-manager.log"
