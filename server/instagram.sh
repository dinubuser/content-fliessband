#!/bin/zsh
# Auf dem Mac: bringt den Instagram-Schlüssel der Agentur (~/.agentur-werkzeug/instagram_token und _datum) auf den
# Server (/var/lib/fliessband/instagram.json, fliessband:fliessband 600) und startet den Briefkasten neu.
# Prüft den Schlüssel vorher bei Instagram. Zeigt ihn nie an. Wiederholbar.
set -euo pipefail
DIR="${0:A:h:h}"
[[ -f "$DIR/.env" ]] && { set -a; source "$DIR/.env"; set +a; }
SERVER="${FLIESSBAND_SERVER:-root@your-server-ip}"
SSH=(ssh -i "${FLIESSBAND_SSH_KEY:-$HOME/.ssh/your_ssh_key}" -o IdentitiesOnly=yes)
JSON="$("$DIR/.venv/bin/python" - <<'PY'
import json, pathlib, sys, urllib.parse, urllib.request
ordner = pathlib.Path.home() / ".agentur-werkzeug"
token = (ordner / "instagram_token").read_text(encoding="utf-8").strip()
erstellt = (ordner / "instagram_token_datum").read_text(encoding="utf-8").strip()
url = "https://graph.instagram.com/v26.0/me?" + urllib.parse.urlencode({"fields": "user_id,username", "access_token": token})
try:
    me = json.load(urllib.request.urlopen(url, timeout=20))
except Exception as e:
    sys.exit(f"Instagram lehnt den Schlüssel ab ({type(e).__name__}). Zuerst Instagram neu verbinden.")
print(f"Konto: {me.get('username')}", file=sys.stderr)
print(json.dumps({"token": token, "erstellt": erstellt, "user_id": str(me["user_id"])}))
PY
)"
# Auf dem Server: erst prüfen, dass die .neu-Datei gültiges JSON mit token, erstellt und user_id ist (sonst .neu
# löschen und abbrechen, die alte Datei bleibt), dann ersetzen. Prüf-Ausgaben gehen nach /dev/null (Token-Schutz).
REMOTE="$(cat <<'SH'
set -eu
umask 077
NEU=/var/lib/fliessband/instagram.json.neu
cat > "$NEU"
if ! python3 -c 'import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
sys.exit(0 if isinstance(d, dict) and all(isinstance(d.get(k), str) and d.get(k).strip() for k in ("token", "erstellt", "user_id")) else 1)' "$NEU" >/dev/null 2>&1; then
  rm -f "$NEU"
  echo "Schlüssel-Datei ungültig (token, erstellt oder user_id fehlt), alte Datei bleibt." >&2
  exit 1
fi
chown fliessband:fliessband "$NEU"
chmod 600 "$NEU"
mv "$NEU" /var/lib/fliessband/instagram.json
systemctl restart fliessband-briefkasten.service
sleep 3
systemctl is-active fliessband-briefkasten.service
SH
)"
printf '%s' "$JSON" | "${SSH[@]}" "$SERVER" "$REMOTE"
echo "Instagram-Schlüssel auf dem Server, Briefkasten neu gestartet."
