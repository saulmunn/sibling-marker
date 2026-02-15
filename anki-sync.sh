#!/bin/bash

# Anki Sync Script
# Simply triggers an Anki sync - no logging, no once-per-day check.
# Use this for manual syncs.

trigger_sync() {
    osascript <<'APPLESCRIPT'
tell application "System Events"
    tell process "anki"
        set frontmost to true
        perform action "AXRaise" of window "User 1 - Anki"
    end tell
end tell
APPLESCRIPT
    sleep 0.25
    osascript -e 'tell application "System Events" to keystroke "y"'
}

if pgrep -x "anki" > /dev/null; then
    trigger_sync
else
    open -a Anki
fi
