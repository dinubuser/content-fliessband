#!/bin/zsh
# Wochen-Job des Content-Fliessbands, gestartet von launchd (com.example.fliessband-lernen Fr 20:00,
# com.example.fliessband-vorbereiten Fr 22:00, com.example.fliessband-bauen Sa 22:00). Zeitfenster, Nachholen und Ausfall-Meldung regelt «fliessband woche job».
# Aufruf: woche.sh lernen|vorbereiten|bauen
set -u
DIR="${0:A:h:h}"
# launchd startet mit minimalem PATH: claude liegt in ~/.local/bin, ffmpeg in /opt/homebrew/bin, node in /usr/local/bin
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
export PYTHONIOENCODING="utf-8"
# Ausgabe sofort ins Log (logs/launchd.log), auch wenn der Job abgebrochen wird
export PYTHONUNBUFFERED=1
export LANG="de_CH.UTF-8"

SCHRITT="${1:-}"
if [[ "$SCHRITT" != "lernen" && "$SCHRITT" != "vorbereiten" && "$SCHRITT" != "bauen" ]]; then
  echo "Aufruf: woche.sh lernen|vorbereiten|bauen" >&2
  exit 2
fi

mkdir -p "$DIR/logs"
echo "$(date '+%F %T') Start Job $SCHRITT"
# caffeinate: nach dem pmset-Wecker nicht wieder einschlafen, solange der Job läuft
caffeinate -i "$DIR/fliessband" woche job "$SCHRITT"
RC=$?
echo "$(date '+%F %T') Ende Job $SCHRITT (Exit $RC)"
exit $RC
