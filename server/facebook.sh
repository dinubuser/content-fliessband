#!/bin/zsh
# Auf dem Mac: tauscht den kurzen Nutzer-Schlüssel aus dem Graph API Explorer (Zwischenablage) gegen einen
# dauerhaften Seiten-Schlüssel der Seite aus FLIESSBAND_FB_SEITE und bringt ihn auf den Server
# (/var/lib/fliessband/facebook.json, fliessband:fliessband 600), dann Neustart des Briefkastens.
# App-Geheimcode aus dem Schlüsselbund (Dienst fliessband-facebook-app, Konto aus FLIESSBAND_FB_KONTO). Zeigt nie einen Schlüssel an.
set -euo pipefail
DIR="${0:A:h:h}"
[[ -f "$DIR/.env" ]] && { set -a; source "$DIR/.env"; set +a; }
SERVER="${FLIESSBAND_SERVER:-root@your-server-ip}"
SSH=(ssh -i "${FLIESSBAND_SSH_KEY:-$HOME/.ssh/your_ssh_key}" -o IdentitiesOnly=yes)
APP_ID="${FLIESSBAND_FB_APP_ID:-your-meta-app-id}"
SEITE="${FLIESSBAND_FB_SEITE:-your-page-name}"
KONTO="${FLIESSBAND_FB_KONTO:-fliessband}"
PRAEFIX="${FLIESSBAND_KEYCHAIN_PREFIX:-fliessband}"
GEHEIM="$(security find-generic-password -s "$PRAEFIX-facebook-app" -a "$KONTO" -w 2>/dev/null)" || {
  echo "App-Geheimcode fehlt im Schlüsselbund ($PRAEFIX-facebook-app / $KONTO)." >&2
  exit 1
}
KURZ="$(pbpaste | tr -d '[:space:]')"
if [[ -z "$KURZ" ]]; then
  echo "Die Zwischenablage ist leer. Zuerst den Schlüssel aus dem Graph API Explorer kopieren." >&2
  exit 1
fi
JSON="$(APP_ID="$APP_ID" GEHEIM="$GEHEIM" KURZ="$KURZ" SEITE="$SEITE" "$DIR/.venv/bin/python" - <<'PY'
import json, os, sys, urllib.error, urllib.parse, urllib.request
from datetime import date
API = "https://graph.facebook.com/v26.0"
def rufe(pfad, **felder):
    try:
        return json.load(urllib.request.urlopen(f"{API}{pfad}?{urllib.parse.urlencode(felder)}", timeout=20))
    except urllib.error.HTTPError as e:
        try:
            grund = str((json.load(e).get("error") or {}).get("message") or "")
        except Exception:
            grund = ""
        for geheimes in (f"{app}|{geheim}", geheim, kurz, lang_schluessel):
            if geheimes:
                grund = grund.replace(geheimes, "…")
        sys.exit(f"Facebook lehnt ab bei {pfad} (HTTP {e.code}): {grund[:200] or 'ohne Text'}. Schlüssel neu holen.")
    except Exception as e:
        sys.exit(f"Facebook lehnt ab bei {pfad} ({type(e).__name__}). Schlüssel neu holen.")
app, geheim, kurz = os.environ["APP_ID"], os.environ["GEHEIM"], os.environ["KURZ"]
lang_schluessel = ""
if not kurz.startswith("EA"):
    sys.exit("In der Zwischenablage ist kein Facebook-Schlüssel (beginnt mit EA).")
lang = rufe("/oauth/access_token", grant_type="fb_exchange_token", client_id=app, client_secret=geheim,
            fb_exchange_token=kurz)["access_token"]
lang_schluessel = lang
seiten = rufe("/me/accounts", fields="id,name,access_token", access_token=lang).get("data") or []
seiten_name = os.environ["SEITE"].lower()
treffer = [s for s in seiten if seiten_name in s.get("name", "").lower()]
if len(treffer) != 1:
    sys.exit(f"Seite {os.environ['SEITE']} nicht eindeutig gefunden (Seiten: {', '.join(s.get('name', '?') for s in seiten)}).")
seite = treffer[0]
name = rufe(f"/{seite['id']}", fields="name", access_token=seite["access_token"])["name"]
info = rufe("/debug_token", input_token=seite["access_token"], access_token=f"{app}|{geheim}").get("data") or {}
fehlt = {"pages_manage_posts", "pages_read_engagement"} - set(info.get("scopes") or [])
if fehlt:
    sys.exit(f"Dem Schlüssel fehlen Rechte: {', '.join(sorted(fehlt))}. Im Graph API Explorer ergänzen.")
ablauf = "nie" if not info.get("expires_at") else date.fromtimestamp(info["expires_at"]).isoformat()
print(f"Seite: {name} · läuft ab: {ablauf}", file=sys.stderr)
print(json.dumps({"token": seite["access_token"], "page_id": str(seite["id"]), "erstellt": date.today().isoformat()}))
PY
)"
REMOTE="$(cat <<'SH'
set -eu
umask 077
NEU=/var/lib/fliessband/facebook.json.neu
cat > "$NEU"
if ! python3 -c 'import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
sys.exit(0 if isinstance(d, dict) and all(isinstance(d.get(k), str) and d.get(k).strip() for k in ("token", "page_id", "erstellt")) else 1)' "$NEU" >/dev/null 2>&1; then
  rm -f "$NEU"
  echo "Schlüssel-Datei ungültig (token, page_id oder erstellt fehlt), alte Datei bleibt." >&2
  exit 1
fi
chown fliessband:fliessband "$NEU"
chmod 600 "$NEU"
mv "$NEU" /var/lib/fliessband/facebook.json
systemctl restart fliessband-briefkasten.service
sleep 3
systemctl is-active fliessband-briefkasten.service
SH
)"
printf '%s' "$JSON" | "${SSH[@]}" "$SERVER" "$REMOTE"
echo "Facebook-Schlüssel auf dem Server, Briefkasten neu gestartet."
