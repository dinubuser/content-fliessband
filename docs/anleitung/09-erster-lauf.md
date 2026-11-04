# 9. Erster Lauf

Ziel: Du spielst die Kette einmal von Hand durch, bevor die Jobs es automatisch tun. Prüfung: `./fliessband einrichten` zeigt Schritt 9 als `[OK]`, sobald eine Woche geplant wurde.

Dieser Schritt kostet echtes Guthaben: Zeichen bei ElevenLabs und Kontingent bei Claude. Gehe in dieser Reihenfolge vor und höre bei jedem Fehler auf.

## 1. Die Tests

```bash
.venv/bin/pytest -q -m "not langsam"
```

Das sind die Tests ohne den langsamen Video-Render. Sie laufen mehrere Minuten. Alle sollen grün sein.

## 2. Ein Karussell bauen

Lass dir mit der Agentur einen Karussell-Beitrag schreiben (in Claude Code, `/agentur`). Er liegt danach im Ordner `beitraege/` deiner Agentur-Daten (standardmässig `~/meine-agentur/beitraege/`). Dann:

```bash
./fliessband karussell ~/meine-agentur/beitraege/<datei>.md
```

Am Ende steht `Fertig:` mit dem Ordner der Bilder und der Status. Schau dir die Bilder an: Passen Schrift, Farben und Handle?

## 3. Ein Reel bauen

Dasselbe mit einem Reel-Skript der Agentur:

```bash
./fliessband reel ~/meine-agentur/beitraege/<datei>.md
```

Das Reel braucht ElevenLabs (Stimme) und HyperFrames (Video). Das ist der erste echte Test von Kapitel 3. Hörst du ein falsch gesprochenes Wort, trage es in `aussprache.txt` ein.

## 4. Eine Woche von Hand

```bash
./fliessband woche vorbereiten      # plant die Woche, stellt Fragen in Telegram
./fliessband woche status
./fliessband woche bauen            # baut die Beiträge und schickt sie nach Telegram
./fliessband woche status
```

`woche status` zeigt dir jedes Mal, was als Nächstes dran ist. In Telegram kommt jeder Beitrag mit den Knöpfen ✅ Freigeben, ✏️ Ändern und ❌ Verwerfen. Der Faktencheck läuft vor dem Bauen jedes Beitrags und zeigt in Telegram eine Zeile mit dem Ergebnis.

Antworte auf die Fragen des Planers in Telegram. Deine Antworten sammelt das Fliessband in `meine-agentur/geschichten.md`.

## 5. Der erste Post

Das Posten ist nach der Einrichtung **aus**. Für den ersten echten Post empfehle ich ein **Test-Konto** statt deines Hauptkontos. Gib einen Beitrag in Telegram frei, dann:

```bash
./fliessband poster status      # ist der Schlüssel gültig, welche Posts sind geplant?
./fliessband poster ein
```

Der Server postet nur freigegebene Beiträge und nur zum Termin. Beobachte den ersten Post und die Meldung in Telegram. Zum Stoppen: `./fliessband poster aus` (die Freigaben bleiben).

## Prüfen

```bash
./fliessband einrichten --online
```

Schritt 9 steht auf `[OK]`, sobald es eine geplante Woche gibt. Wenn alle Schritte `[OK]` sind, richte die Jobs ein (Kapitel 8), falls noch nicht geschehen.

## Wenn es nicht klappt

Siehe [Fehlerbehebung](10-fehler.md).
