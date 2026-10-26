# Mitmachen

Danke, dass du am Content-Fliessband mitarbeiten willst. Die Hinweise unten halten die Arbeit kurz und die Änderungen klar.

## Entwicklung einrichten

```bash
./install.sh                          # Pakete, .env, Aussprache-Agent
.venv/bin/pytest -q -m "not langsam"  # Tests vor jeder Änderung
```

Voraussetzungen stehen in der [README](README.md). Ohne die Social-Media-Agentur von Sebastian Kauffmann laufen Planer und Texter im echten Betrieb nicht. Die meisten Tests nutzen eigene Attrappen der Agentur.

Der Lauf ohne `-m "not langsam"` rendert mit HyperFrames. Er ist langsam und braucht die Node-Pakete.

## Branch und Pull Request

1. Branch vom Hauptbranch anlegen, z.B. `fix/kurzer-name` oder `feat/kurzer-name`.
2. Eine Änderung pro Pull Request. Kleine Schritte lassen sich schneller prüfen.
3. Vor dem Pull Request: Tests grün, neue Funktionen mit Test.
4. Im Pull Request kurz beschreiben, was sich ändert und warum. Bei Änderungen am Server: erwähnen, ob `server/deploy.sh` nötig ist.

## Code-Stil

- Python 3.12, Code und Kommentare auf Deutsch. Bezeichner wie bisher deutsch (z.B. `freigabe`, `entscheide`).
- Kein Linter konfiguriert. Halte dich an den Stil der Datei, die du änderst.
- Schweizer Schreibweise in Texten: «ss» statt «ß».
- Geheimnisse, persönliche Daten und Zugangsdaten gehören nie in Code, Tests oder Beispieldaten. Platzhalter nutzen (`your-…`, `example.com`, `@dein.konto`).
- Neue Konfiguration kommt als Variable in `.env.example` mit Beschreibung.
- Die Marker `[BEISPIEL ... anpassen]` bleiben als Vorlage stehen. Neue Beispielregeln bekommen denselben Marker.

## Issues melden

- Bitte nutze die Vorlagen unter `.github/ISSUE_TEMPLATE/`.
- Bei Fehlern: Schritte zum Nachstellen, erwartetes und tatsächliches Verhalten, Mac-Version, Python- und Node-Version.
- Keine Schlüssel, Tokens, Chat-IDs oder Auszüge aus `.env`, `daten/` oder `logs/` ins Issue kopieren. Ersetze sie durch Platzhalter.
- Sicherheitslücken nicht als öffentliches Issue melden, sondern privat an den Maintainer.

## Using Claude Code

Das Repo enthält eine `CLAUDE.md` mit Befehlen, Architektur und Regeln. Claude Code liest sie beim Start automatisch:

```bash
claude
```

Bitte pflege `CLAUDE.md`, wenn du Befehle, Dateien oder Konfiguration änderst. Sie soll die Angaben im Repo wiedergeben und nie veraltete Befehle enthalten.
