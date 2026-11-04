# 1. Voraussetzungen

Ziel: Dein Mac hat alle Programme, und dieses Repo ist installiert. Prüfung: `./fliessband einrichten` zeigt Schritt 1 als `[OK]`.

## Was du brauchst

- **macOS** mit launchd und Schlüsselbund. Die Jobs laufen nur, wenn der Mac wach ist.
- **Python 3.12**, **Node 22 oder neuer**, **ffmpeg**.
- **Claude Code** (der Befehl `claude` muss im PATH sein). Installiere es nach der offiziellen Anleitung von Anthropic.
- **Homebrew**, wenn du die Programme damit installierst.

## Programme installieren

```bash
brew install python@3.12 node ffmpeg
python3.12 --version
node --version
ffmpeg -version | head -1
claude --version
```

`install.sh` ruft ausdrücklich `python3.12` auf. Mit `brew install python@3.12` gibt es diesen Befehl.

## Repo holen und installieren

```bash
git clone https://github.com/dinubuser/content-fliessband.git
cd content-fliessband
./install.sh
```

`install.sh` ist wiederholbar und macht der Reihe nach:

1. Prüft die Voraussetzungen.
2. Legt `.venv` an und installiert die Python-Pakete (`requirements.txt`) und den Chromium-Browser für Playwright.
3. Installiert die Node-Pakete (`hyperframes`, `gsap`) mit `npm ci`.
4. Legt `.env` aus `.env.example` an. Die Platzhalter füllst du in den nächsten Kapiteln.
5. Kopiert die Agenten für Aussprache, Faktencheck und Trend-Scout nach `~/.claude/agents/`. Eine vorhandene, abweichende Datei überschreibt es nicht.

Es fasst den Schlüsselbund nicht an und richtet keine Jobs ein (das kommt in Kapitel 8). Es dauert einige Minuten, weil Chromium und die Node-Pakete heruntergeladen werden.

## Prüfen

```bash
./fliessband einrichten
```

Schritt 1 ist `[OK]`, wenn Python 3.12, Node 22, ffmpeg und claude da sind sowie `.venv` und die Node-Pakete.

## Wenn es nicht klappt

- `python3.12: command not found`: `brew install python@3.12` und ein neues Terminalfenster öffnen.
- Der Assistent meldet «Node 22 oder neuer fehlt», obwohl Node installiert ist: `node --version` im selben Terminal prüfen. Ein älteres Node im PATH gewinnt gegen das neue.
- `.venv` fehlt: `./install.sh` noch einmal ausführen und die Fehlermeldung lesen.
