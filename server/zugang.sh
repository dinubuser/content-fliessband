#!/bin/zsh
# Auf dem Mac: legt /etc/fliessband/geheim.env auf dem Server an (Telegram-Token aus dem Schlüsselbund,
# Chat-ID aus daten/bot.json, neuer API-Schlüssel) und speichert den API-Schlüssel im Schlüsselbund
# (Dienst fliessband-briefkasten). Nichts davon wird angezeigt. Wiederholbar (neuer Schlüssel).
set -euo pipefail
DIR="${0:A:h:h}"
[[ -f "$DIR/.env" ]] && { set -a; source "$DIR/.env"; set +a; }
SERVER="${FLIESSBAND_SERVER:-root@your-server-ip}"
SSH=(ssh -i "${FLIESSBAND_SSH_KEY:-$HOME/.ssh/your_ssh_key}" -o IdentitiesOnly=yes)
PRAEFIX="${FLIESSBAND_KEYCHAIN_PREFIX:-fliessband}"   # eigener Präfix, wenn auf diesem Mac schon ein anderes Fliessband läuft
TOKEN="$(security find-generic-password -s "$PRAEFIX-telegram" -w)"
CHAT="$("$DIR/.venv/bin/python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["chat_id"])' "$DIR/daten/bot.json")"
SCHLUESSEL="$(openssl rand -hex 32)"
printf 'TELEGRAM_TOKEN=%s\nCHAT_ID=%s\nAPI_SCHLUESSEL=%s\n' "$TOKEN" "$CHAT" "$SCHLUESSEL" | \
  "${SSH[@]}" "$SERVER" 'umask 027 && cat > /etc/fliessband/geheim.env.neu && chown root:fliessband /etc/fliessband/geheim.env.neu && chmod 640 /etc/fliessband/geheim.env.neu && mv /etc/fliessband/geheim.env.neu /etc/fliessband/geheim.env'
security add-generic-password -U -s "$PRAEFIX-briefkasten" -a fliessband -w "$SCHLUESSEL"
echo "Zugang eingerichtet (Server und Schlüsselbund). Als Nächstes: server/deploy.sh"
echo "Hinweis: Nach einem neuen Schlüssel muss der Dienst neu starten (server/deploy.sh oder systemctl restart fliessband-briefkasten)."
