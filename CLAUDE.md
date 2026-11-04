# Content-Fliessband

**Stack:** Python 3.12 (Mac und Server), Node 22 (HyperFrames, GSAP), Claude Code, ElevenLabs, Telegram, Instagram/Facebook Graph API | **Port:** 8096 (Briefkasten auf dem Server) | **Tests:** pytest

## Was
Automatisches Content-Fliessband für Instagram und Facebook. Es plant, baut und postet jede Woche 2 Reels und 2 Karussells. Freigegeben wird nur in Telegram. Das Projekt baut auf der Social-Media-Agentur von Sebastian Kauffmann auf (Skill `agentur`, muss zuerst installiert sein).

## Quick Start

```bash
./install.sh                          # Erste Einrichtung: Pakete, .env, Aussprache-Agent
.venv/bin/pytest -q -m "not langsam"  # Tests (ohne HyperFrames-Render)
./fliessband woche status             # Stand der aktuellen Woche
```

## Commands

```bash
# Mac: Einrichtung und Betrieb
./install.sh                          # Abhängigkeiten, .env, Aussprache-Agent (wiederholbar)
./install.sh --launchd                # zusätzlich launchd-Jobs (nur mit ausgefüllter .env)
./fliessband karussell <beitrag.md> [--termin 2026-10-27T19:00]
./fliessband reel <reel.md> [--termin YYYY-MM-DDTHH:MM]
./fliessband woche vorbereiten|bauen|senden|anmelden|status [--woche 2026-KW44]
./fliessband lernen [--probe]         # Lern-Schleife: Instagram-Zahlen → learnings.md
./fliessband entscheide               # Freigaben aus Telegram umsetzen (launchd, alle 15 Min)
./fliessband bot einrichten           # Chat-ID speichern, nachdem /start geschickt wurde
./fliessband briefkasten umstellen    # Ab jetzt fragt der Server Telegram ab (einmalig)

# Mac: Schalter ohne Server
./fliessband fakten ein|aus|status    # Faktencheck vor dem Bauen (Standard an)
./fliessband trends ein|aus|status|jetzt   # Trend-Scout (Standard aus), jetzt = von Hand laufen lassen
./fliessband plaetze 4|6|status       # Beiträge pro Woche (Standard 4)

# Server: Schalter (laufen über den Briefkasten)
./fliessband poster ein|aus|status
./fliessband facebook ein|aus|status
./fliessband kommentare ein|aus|status

# Tests
.venv/bin/pytest -q -m "not langsam"  # schnell, enthält tests/ und server/tests/
.venv/bin/pytest -q                   # alle, inkl. HyperFrames-Render (braucht node_modules)

# Server-Deployment (vom Mac aus, braucht .env)
server/deploy.sh                      # Code kopieren, Tests dort, Dienst neu starten
```

Es gibt keinen Build-Schritt und keinen Linter. Node-Pakete: `npm ci`.

## Architecture

Der Mac plant, baut und sendet. Der Server nimmt Freigaben aus Telegram an, postet zum geplanten Termin und liest Kommentare. Der Mac holt die Entscheide vom Server ab (`entscheide`).

```
lib/                  Mac: Wochenablauf, Planer, Texter, Bau, Freigabe
  cli.py              Einstieg aller Befehle (./fliessband)
  woche.py            Wochenablauf: vorbereiten, bauen, senden, anmelden
  planer.py           Wochenplan mit den Beiträgen        [BEISPIEL-Regeln]
  texter.py           Texte und START-Prüfung             [BEISPIEL-Regeln]
  lernen.py           Lern-Schleife (learnings.md)        [BEISPIEL]
  konkurrenz.py       Konkurrenz-Accounts                 [BEISPIEL]
  bauer.py            Karussell-Bau (vorlagen/karussell-a)
  reel_bauer.py       Reel-Bau: ElevenLabs, HyperFrames
  aussprache.py       Aussprache-Check mit aussprache.txt
  fakten.py           Faktencheck vor dem Bauen (Agent fakten-agent, Schalter)
  trendscout.py       Trend-Scout: Web-Themen als Quelle für den Planer (Schalter, Standard aus)
  netzgrund.py        Grund bei Netzfehlern als festes Wort für Meldungen und Logs
  entscheide.py       Freigaben vom Server holen und umsetzen
  briefkasten.py      Mac-Seite: HTTP-Client zum Server
  bot.py              Telegram-Bot (Mac, bis zur Umstellung)
server/briefkasten/   Server (Linux, systemd-Dienst)
  dienst.py           HTTP-Dienst, Port 8096
  poster.py           Posten auf Instagram zum Termin
  facebook.py         Spiegel auf die Facebook-Seite
  kommentare.py       START-Kommentare in Telegram melden
  texte.py            Telegram-Texte
launchd/              Mac-Jobs: woche.sh, entscheide.sh, installieren.sh
vorlagen/             karussell-a (Folien), reel-a (Szenen, Figuren)
docs/agents/          Agenten Aussprache, Faktencheck, Trend-Scout (install.sh kopiert sie nach ~/.claude/agents/)
tests/, server/tests/ pytest
daten/, wochen/, logs/, zwischenspeicher/   Laufzeitdaten, nicht in Git
```

Geheimnisse liegen im macOS-Schlüsselbund (Mac) und in `/etc/fliessband/geheim.env` (Server). Das Mac-Skript `server/zugang.sh` richtet den Zugang zwischen beiden ein.

## Key Files

- `fliessband`: Startskript, nutzt `.venv`
- `lib/cli.py`: alle Befehle und Hilfetexte
- `lib/woche.py`: Ablauf und Schritte einer Woche
- `lib/konfig.py`: liest Umgebung, dann `.env`, dann Standard
- `launchd/installieren.sh`: richtet die Mac-Jobs ein (wird von `install.sh --launchd` aufgerufen)
- `server/briefkasten/dienst.py`: Einstieg des Servers
- `server/deploy.sh`: Server-Deployment
- `docs/agents/aussprache-agent.md`: Prüfer für Sprechtexte
- `vorlagen/karussell-a/stil.css`, `vorlagen/reel-a/stil.css`: Gestaltung

## Configuration

Alle Werte stehen in `.env.example`. Umgebungsvariable, dann `.env`, dann Standard im Code. Platzhalter (`your-…`, `example.com`, `@dein.konto`) vor dem Einsatz ersetzen.

| Variable | Pflicht | Beschreibung |
|----------|---------|--------------|
| `FLIESSBAND_HANDLE` | ja | Instagram-Handle für Beschriftung und Prompts |
| `FLIESSBAND_AGENTUR_DIR` | ja | Ordner der Agentur mit profil.md, stimme.md, learnings.md, geschichten.md |
| `FLIESSBAND_AGENTUR_SKILL` | ja | Skill-Ordner der Agentur (mit `tools/`) |
| `FLIESSBAND_AGENTUR_PYTHON` | ja | Python-Interpreter der Agentur |
| `ELEVENLABS_VOICE_ID` | ja | Stimmen-ID in ElevenLabs für die Reels |
| `FLIESSBAND_WP_URL`, `_WP_DIENST`, `_WP_KONTO` | ja | WordPress-Mediathek für öffentliche Medien-URLs |
| `FLIESSBAND_BRIEFKASTEN_URL` | ja | Adresse des Servers, z.B. über Tailscale |
| `FLIESSBAND_SERVER`, `FLIESSBAND_SSH_KEY` | Server | SSH-Ziel und Schlüssel für die Server-Skripte |
| `FLIESSBAND_FB_APP_ID`, `FLIESSBAND_FB_SEITE`, `FLIESSBAND_FB_KONTO` | nur Facebook | Meta-App-ID, Name der Seite, Schlüsselbund-Konto |
| `FLIESSBAND_HOST`, `FLIESSBAND_ENV`, `FLIESSBAND_DB` u.a. | nur Server | in `/etc/fliessband/konfig.env` bzw. Standard |

Schlüsselbund (`security add-generic-password`): `fliessband-telegram` (Bot-Token), `fliessband-briefkasten` (Konto `fliessband`), `fliessband-facebook-app` (App-Geheimcode), `elevenlabs-api`, `FLIESSBAND_WP_DIENST` (WordPress-Anwendungspasswort).

## Anpassen

Die Regeln für Stimme, Marke und Themen sind Beispiele. Sie stehen mit dem Marker `[BEISPIEL ... anpassen]` in `lib/planer.py`, `lib/texter.py`, `lib/lernen.py` und `lib/konkurrenz.py`. Dazu kommen `docs/agents/aussprache-agent.md` (Helvetismen, Handle) und `aussprache.txt` (Wörter für die Stimme).

## Wichtige Regeln

- Nichts geht ohne Freigabe online. Der Server postet nur freigegebene Beiträge zum Termin.
- Geheimnisse nie in Git und nie in `.env`. Schlüssel liegen im Schlüsselbund bzw. in `geheim.env`.
- Aussprache: Auto-Funde landen in `daten/aussprache-auto.txt` (nicht in Git). `aussprache.txt` gewinnt bei gleichem Wort.
- Faktencheck: Läuft vor dem Bauen jedes Beitrags (Schalter `fakten`, Log `logs/fakten.log`). Ohne brauchbare Korrektur wird eine Stelle «offen» (Marker [prüfen]), der Betreiber klärt sie. Die Prüfung lässt nie einen Bau scheitern.
- Plätze pro Woche: `fliessband plaetze 4|6`. Mit 6 kommen Mo Karussell und Fr Reel dazu. Der Planer liest Zahl und Formate aus den Terminen.
- Trend-Scout: Standard aus. Ein Websuche-Lauf pro Woche beim Planen (Zeitlimit 8 Minuten, höchstens 12 Suchen, 10 Themen), Ergebnis `wochen/<KW>/trends.json`, Log `logs/trendscout.log`. Fällt die Suche aus, plant der Planer ohne Trend-Quelle.
- Kontakt: Jeder Beitrag endet mit «… Kommentiere START.». Der Server meldet START-Kommentare in Telegram. Keine automatischen Antworten, keine Links in Beitrag oder Bio.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
