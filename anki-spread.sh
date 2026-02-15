#!/bin/bash

# Anki Sibling Spread Script
#
# This script ensures sibling cards are spread across different days before
# you start reviewing on mobile.
#
# Triggers:
#   - Cron job at 4:10am (after Anki day resets)
#   - Sleepwatcher on laptop wake
#
# The script only runs once per "Anki day" (resets at 4:09am).
# Calls anki-sync.sh to do the actual sync.

SCRIPT_DIR="$(dirname "$0")"
LOG_FILE="/tmp/anki-spread.log"
LAST_RUN_FILE="$HOME/.anki-spread-lastrun"
RESET_HOUR=4
RESET_MINUTE=9

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S'): $1" >> "$LOG_FILE"
}

# Determine the current "Anki day" (resets at 4:09am)
get_anki_day() {
    current_hour=$(date +%H)
    current_minute=$(date +%M)

    # Before 4:09am = still yesterday's Anki day
    if [ "$current_hour" -lt "$RESET_HOUR" ] || \
       ([ "$current_hour" -eq "$RESET_HOUR" ] && [ "$current_minute" -lt "$RESET_MINUTE" ]); then
        date -v-1d +%Y-%m-%d
    else
        date +%Y-%m-%d
    fi
}

# Check if we already ran for this Anki day
anki_day=$(get_anki_day)
if [ -f "$LAST_RUN_FILE" ]; then
    last_run=$(cat "$LAST_RUN_FILE")
    if [ "$last_run" = "$anki_day" ]; then
        log "Already ran for Anki day $anki_day, skipping"
        exit 0
    fi
fi

# Record that we're running for this Anki day
echo "$anki_day" > "$LAST_RUN_FILE"

log "Running sync for Anki day $anki_day"
"$SCRIPT_DIR/anki-sync.sh"
