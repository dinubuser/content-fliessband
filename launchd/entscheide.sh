#!/bin/zsh
# Entscheide aus Telegram umsetzen, gestartet von launchd (com.example.fliessband-entscheide) alle 15 Minuten,
# solange der Mac wach ist. Ausgaben im Log logs/entscheide.log (nur wenn etwas passiert).
set -u
DIR="${0:A:h:h}"
# launchd startet mit minimalem PATH: claude liegt in ~/.local/bin, ffmpeg in /opt/homebrew/bin, node in /usr/local/bin
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
export PYTHONIOENCODING="utf-8"
export PYTHONUNBUFFERED=1
export LANG="de_CH.UTF-8"
mkdir -p "$DIR/logs"
# caffeinate: Ein Neubau dauert Minuten, der Mac soll dabei nicht einschlafen
caffeinate -i "$DIR/fliessband" entscheide
