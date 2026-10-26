#!/bin/zsh
# Installiert die Jobs des Fliessbands in launchd (wiederholbar): lernen, vorbereiten, bauen, entscheide.
# Nicht automatisch ausführen: erst .env ausfüllen, dann die Tests prüfen (python -m pytest).
set -eu
DIR="${0:A:h:h}"
ZIEL="$HOME/Library/LaunchAgents"
DOMAIN="gui/$(id -u)"
mkdir -p "$ZIEL" "$DIR/logs"
chmod +x "$DIR/launchd/woche.sh" "$DIR/launchd/entscheide.sh" "$DIR/fliessband"

for JOB in lernen vorbereiten bauen entscheide; do
  LABEL="com.example.fliessband-$JOB"
  sed "s#__DIR__#$DIR#g" "$DIR/launchd/$LABEL.plist" > "$ZIEL/$LABEL.plist"
  plutil -lint "$ZIEL/$LABEL.plist" >/dev/null
  # Alten Stand entladen; kurz warten, sonst scheitert bootstrap gleich danach manchmal mit «Input/output error»
  if launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null; then
    sleep 1
  fi
  launchctl bootstrap "$DOMAIN" "$ZIEL/$LABEL.plist"
  echo "Installiert: $LABEL"
done

echo
echo "Noch offen: Wecker für Fr und Sa 21:55. Einmal selbst im Terminal ausführen (fragt nach dem Mac-Passwort):"
echo "  sudo pmset repeat wakeorpoweron FS 21:55:00"
echo "Prüfen mit: pmset -g sched"
echo "Hinweis: lernen läuft Fr 20:00 bis 21:30. Schläft der Mac dann, holt vorbereiten um 22:00 die Lern-Schleife nach."
