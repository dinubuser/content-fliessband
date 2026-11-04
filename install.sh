#!/usr/bin/env bash
# Content-Fliessband: Installation auf dem Mac. Wiederholbar, ändert nichts, was schon stimmt.
#
#   ./install.sh            Voraussetzungen, Python- und Node-Pakete, .env, Agenten
#   ./install.sh --launchd  zusätzlich die Jobs in launchd einrichten (erst, wenn .env ausgefüllt ist)
#
# Liest und schreibt keine Geheimnisse: der Schlüsselbund bleibt unangetastet.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

LAUNCHD=0
case "${1:-}" in
  "") ;;
  --launchd) LAUNCHD=1 ;;
  -h|--help)
    sed -n '2,6p' "$0"
    exit 0
    ;;
  *)
    echo "Unbekannte Option: $1 (erlaubt: --launchd, --help)" >&2
    exit 2
    ;;
esac

schritt() { echo; echo "== $1"; }
fehler() { echo "Fehler: $1" >&2; exit 1; }

# --- 1. Voraussetzungen ---------------------------------------------------------------
schritt "Voraussetzungen prüfen"
[[ "$(uname -s)" == "Darwin" ]] || fehler "install.sh läuft nur auf macOS (launchd und Schlüsselbund)."
command -v security >/dev/null 2>&1 || fehler "security (Schlüsselbund) nicht gefunden."

fehlt=0
pruefe() {
  if command -v "$1" >/dev/null 2>&1; then
    echo "  ok: $1"
  else
    echo "  fehlt: $1 ($2)"
    fehlt=1
  fi
}
pruefe python3.12 "brew install python@3.12"
pruefe node "brew install node@22"
pruefe npm "kommt mit node"
pruefe ffmpeg "brew install ffmpeg"
pruefe claude "Claude Code installieren, danach einmal im Terminal 'claude' starten"
if command -v node >/dev/null 2>&1; then
  major="$(node -p 'process.versions.node.split(".")[0]')"
  if [[ "$major" -lt 22 ]]; then
    echo "  zu alt: node $major (nötig: 22 oder neuer)"
    fehlt=1
  fi
fi
[[ "$fehlt" -eq 0 ]] || fehler "Voraussetzungen fehlen (siehe oben). Danach ./install.sh erneut starten."

# --- 2. Python --------------------------------------------------------------------------
schritt "Python-Umgebung (.venv)"
if [[ ! -x .venv/bin/python ]]; then
  python3.12 -m venv .venv
  echo "  .venv angelegt"
fi
.venv/bin/python -m pip install --quiet -r requirements.txt
echo "  Python-Pakete installiert (requirements.txt)"
# Playwright braucht einen eigenen Chromium-Browser; ist er schon da, passiert nichts Neues
.venv/bin/playwright install chromium
echo "  Chromium für Playwright bereit"

# --- 3. Node ----------------------------------------------------------------------------
schritt "Node-Pakete (hyperframes, gsap)"
if [[ -f package-lock.json ]]; then
  npm ci --no-audit --no-fund
else
  npm install --no-audit --no-fund
fi

# --- 4. Konfiguration -------------------------------------------------------------------
schritt "Konfiguration (.env)"
if [[ -f .env ]]; then
  echo "  .env existiert schon und bleibt unverändert."
else
  cp .env.example .env
  chmod 600 .env
  echo "  .env aus .env.example angelegt. Die Platzhalter müssen noch ersetzt werden."
fi

# Agentur-Werkzeug: nur prüfen, nicht installieren (es ist ein eigenes Projekt, siehe README)
schritt "Agentur-Werkzeug (Social-Media-Agentur)"
skill="$( (grep -E '^FLIESSBAND_AGENTUR_SKILL=' .env 2>/dev/null || true) | tail -n 1 | cut -d= -f2-)"
skill="${skill:-$HOME/.claude/skills/agentur}"
skill="${skill/#\~/$HOME}"
if [[ -d "$skill" ]]; then
  echo "  ok: Skill gefunden ($skill)"
else
  echo "  Hinweis: Skill der Agentur fehlt unter $skill."
  echo "  Die Social-Media-Agentur von Sebastian Kauffmann muss zuerst installiert sein (README, Abschnitt Voraussetzungen)."
fi

# --- 5. Agenten (Aussprache, Faktencheck, Trend-Scout) ----------------------------------
schritt "Agenten (Aussprache, Faktencheck, Trend-Scout)"
ziel_ordner="$HOME/.claude/agents"
for name in aussprache-agent fakten-agent trend-scout; do
  quelle="docs/agents/$name.md"
  ziel="$ziel_ordner/$name.md"
  if [[ -f "$quelle" ]]; then
    mkdir -p "$ziel_ordner"
    if [[ ! -f "$ziel" ]]; then
      cp "$quelle" "$ziel"
      echo "  installiert: $ziel"
    elif cmp -s "$quelle" "$ziel"; then
      echo "  schon aktuell: $ziel"
    else
      echo "  $ziel gibt es schon und weicht ab. Nicht überschrieben."
      echo "  Bei Bedarf von Hand übernehmen: cp $quelle $ziel"
    fi
  fi
done

# --- 6. launchd (nur mit --launchd) -----------------------------------------------------
schritt "launchd-Jobs"
if [[ "$LAUNCHD" -eq 1 ]]; then
  if grep -vE '^[[:space:]]*#' .env | grep -qE 'your[-_]|dein\.konto|example\.com'; then
    fehler "In .env stehen noch Platzhalter (your-…, your_…, @dein.konto, example.com). Zuerst ersetzen, dann ./install.sh --launchd."
  fi
  zsh "$DIR/launchd/installieren.sh"
else
  echo "  Nicht eingerichtet. Erst .env ausfüllen, dann: ./install.sh --launchd"
fi

# --- Nächste Schritte -------------------------------------------------------------------
echo
echo "=== Installation abgeschlossen ==="
echo
echo "Nächste Schritte:"
echo "  1. .env ausfüllen (alle Platzhalter ersetzen). Geheimnisse nur in den Schlüsselbund, nie in .env."
echo "  2. Tests prüfen: .venv/bin/pytest -q -m \"not langsam\""
echo "  3. Telegram-Bot: Token in den Schlüsselbund, dem Bot /start schicken, dann ./fliessband bot einrichten"
echo "  4. Einrichtung abschliessen (Server, Meta-App, Keychain): siehe README, Abschnitt Einrichtung"
echo "  5. Wenn alles steht: ./install.sh --launchd"
echo "  Claude Code liest CLAUDE.md automatisch: claude"
