#!/usr/bin/env bash
# Установка LaunchAgent'ов tg_monitor.
# Идемпотентный скрипт: безопасно запускать повторно.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTS_SRC="$SCRIPT_DIR/launchagents"
AGENTS_DST="$HOME/Library/LaunchAgents"

mkdir -p "$AGENTS_DST"

for plist in "$AGENTS_SRC"/*.plist; do
    name="$(basename "$plist")"
    dst="$AGENTS_DST/$name"
    label="${name%.plist}"

    # Если уже загружен — сначала выгружаем
    if launchctl list | grep -q "^[-0-9]*[[:space:]]*[-0-9]*[[:space:]]*${label}$"; then
        echo "Выгружаю $label..."
        launchctl unload "$dst" 2>/dev/null || true
    fi

    cp "$plist" "$dst"
    chmod 644 "$dst"
    echo "Загружаю $label..."
    launchctl load "$dst"
done

echo ""
echo "Готово. Установлены агенты:"
launchctl list | grep tgmonitor || echo "  (агенты пока не отрапортовали — это нормально, проверь через минуту)"
echo ""
echo "Чтобы выгрузить все: ./uninstall_agents.sh"
