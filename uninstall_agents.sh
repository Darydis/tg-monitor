#!/usr/bin/env bash
# Выгрузить и удалить LaunchAgent'ы tg_monitor.

set -euo pipefail

AGENTS_DST="$HOME/Library/LaunchAgents"

for label in com.tgmonitor.collect com.tgmonitor.subs com.tgmonitor.daily com.tgmonitor.menubar; do
    plist="$AGENTS_DST/$label.plist"
    if [ -f "$plist" ]; then
        echo "Выгружаю $label..."
        launchctl unload "$plist" 2>/dev/null || true
        rm -f "$plist"
    fi
done

echo "Готово."
