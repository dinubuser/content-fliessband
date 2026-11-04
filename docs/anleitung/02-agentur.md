# 2. Agentur und Konto

Ziel: Die Social-Media-Agentur ist installiert, ihre Daten sind da, und das Fliessband kennt dein Handle. Prüfung: `./fliessband einrichten` zeigt Schritt 2 als `[OK]`.

## Die Agentur installieren

Das Fliessband baut auf der Social-Media-Agentur von **Sebastian Kauffmann** auf: <https://github.com/sebaskauf/social-agentur>. Sie ist seine Arbeit und nicht Teil dieses Repos. Installiere sie zuerst nach ihrer eigenen Anleitung, am einfachsten so: In Claude Code einfügen

```
Richte mir bitte die Social-Media-Agentur ein: https://github.com/sebaskauf/social-agentur
```

Danach liegt der Skill unter `~/.claude/skills/agentur`, das Werkzeug unter `~/.social-agentur/`, und sieben Agenten liegen in `~/.claude/agents/` (analyse, community, content, follower, profil, trend, viral). Das Fliessband ruft davon fünf auf: `content-agent`, `trend-agent`, `follower-agent`, `viral-agent` und `analyse-agent`.

## Deine Daten

Die Agentur legt den Ordner `meine-agentur/` **in dem Ordner an, in dem du Claude Code startest**. Das Fliessband sucht ihn standardmässig unter `~/meine-agentur`. Starte die Einrichtung der Agentur darum im Home-Ordner:

```bash
cd ~
claude
```

Dort tippst du `/agentur start`. Die Agentur fragt dich nach deinem Profil und deiner Stimme und legt die Dateien an. Hast du `meine-agentur/` schon woanders, setze `FLIESSBAND_AGENTUR_DIR` in `.env` auf diesen Ordner (siehe unten).

Das Fliessband liest daraus:

| Datei | Inhalt |
|---|---|
| `profil.md` | Wer du bist, für wen du schreibst, welche Themen |
| `stimme.md` | Wie du klingst |
| `learnings.md` | Was bisher gut lief (das Fliessband schreibt sie jede Woche fort) |

Fülle `profil.md` und `stimme.md` so, wie es die Agentur beschreibt. Je genauer, desto besser die Texte. `geschichten.md` brauchst du nicht anzulegen: Das Fliessband hängt dort die Antworten auf Fragen des Planers an.

Liegen deine Ordner woanders, setze in `.env` die Pfade `FLIESSBAND_AGENTUR_DIR`, `FLIESSBAND_AGENTUR_SKILL` und `FLIESSBAND_AGENTUR_PYTHON`. Ein `~/` am Anfang ist erlaubt.

## Dein Handle

Trage in `.env` dein Instagram-Handle ein:

```
FLIESSBAND_HANDLE=@deinkonto
```

Es erscheint in der Fusszeile der Bilder und in den Prompts.

## Regeln an dich anpassen

Die Regeln für Stimme, Marke und Themen in diesem Repo sind Beispiele. Sie tragen den Marker `[BEISPIEL ... anpassen]`. Finde sie so:

```bash
grep -rn "BEISPIEL" lib docs/agents
```

Prüfe jede Stelle: Passt sie zu dir, lass sie stehen oder lösche den Marker. Wenn nicht, ändere sie. Besonders wichtig sind die Finanz-Regel (keine Anlageberatung, keine Gewinnversprechen) und die Themenfelder des Trend-Scouts, falls du ihn einschaltest.

Wenn du die Farben und die Schrift ändern willst, steht der Hinweis dazu in `CLAUDE.md` unter «Anpassen».

## Optional: Zwei Quellen für den Planer

Beide sind freiwillig. Fehlt eine, plant der Planer ohne sie und schreibt einen Vermerk in den Wochenplan.

- **Apple-Notiz «Content-Ideen»:** Lege in der Notizen-App eine Notiz mit genau diesem Namen an. Jede Zeile ist eine Idee. Das Fliessband liest sie nur, ändert sie nie und merkt sich verwendete Zeilen. Beim ersten Zugriff fragt macOS nach der Freigabe unter Datenschutz, Automation. Ohne Freigabe steht im Wochenplan «Apple-Notiz nicht gelesen».
- **Apify für Konkurrenz-Zahlen:** Die Agentur beschreibt in Abschnitt 5 ihrer README, wie du das Apify-Konto anlegst und den Schlüssel in `~/.social-agentur/apify_token` ablegst. Das Fliessband lässt Apify erst laufen, wenn mindestens 2 $ Monatsguthaben da sind, und gibt pro Lauf höchstens 0.50 $ aus.

## Prüfen

```bash
./fliessband einrichten
```

Schritt 2 ist `[OK]`, wenn der Skill, das Agentur-Python, die drei Dateien, die acht Agenten und dein Handle da sind.

## Wenn es nicht klappt

- «Agenten fehlen»: Die Agentur noch einmal installieren (derselbe Befehl aktualisiert sie) und `./install.sh` ausführen. Es kopiert die drei Agenten dieses Repos.
- «FLIESSBAND_HANDLE fehlt oder ist noch ein Platzhalter»: In `.env` steht noch `@dein.konto`.
