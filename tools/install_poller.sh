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
    <string>--only-hours</string><string>8-17</string>
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

# --- publisher: pushes the laptop's snapshots and rebuilds the page every 30 min ---
PUB_LABEL="com.citina.curblog.publish"
PUB_PLIST="$HOME/Library/LaunchAgents/$PUB_LABEL.plist"
cat > "$PUB_PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$PUB_LABEL</string>
  <key>ProgramArguments</key>
  <!-- Python, not bash: macOS charges file access to the launched program, and
       /bin/bash may not touch ~/Desktop. This interpreter (the poller's) can. -->
  <array><string>/Users/liangshiting/opt/anaconda3/bin/python3</string><string>$DIR/publish.py</string></array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>StartInterval</key><integer>1800</integer>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>
  <key>StandardOutPath</key><string>$DIR/publish.log</string>
  <key>StandardErrorPath</key><string>$DIR/publish.log</string>
</dict>
</plist>
PLISTEOF
launchctl bootout "gui/$(id -u)/$PUB_LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PUB_PLIST"
echo "Installed $PUB_LABEL — publishing every 30 minutes (log: $DIR/publish.log)."
