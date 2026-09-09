#!/bin/bash
# Install (or reinstall) the 10-minute LADOT occupancy poller as a LaunchAgent.
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABEL="com.citina.curblog.poll"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/liangshiting/opt/anaconda3/bin/python3</string>
    <string>$DIR/poll_live.py</string>
    <string>--ids</string><string>$DIR/sensored_ids.txt</string>
    <string>--data-dir</string><string>$DIR/data</string>
    <string>--collector</string><string>laptop</string>
    <string>--only-hours</string><string>8-18</string>
    <string>--only-weekdays</string>
  </array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>StartInterval</key><integer>300</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$DIR/poll.log</string>
  <key>StandardErrorPath</key><string>$DIR/poll.err</string>
</dict>
</plist>
PLISTEOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed $LABEL — polling every 5 minutes."
echo "  status:    launchctl list | grep $LABEL"
echo "  log:       tail -f $DIR/poll.log"
echo "  stop:      launchctl bootout gui/$(id -u)/$LABEL"
