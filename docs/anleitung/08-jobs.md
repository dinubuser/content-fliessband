# 8. Jobs (launchd)

Ziel: Das Fliessband läuft jede Woche von allein. Vier Jobs auf deinem Mac erledigen es. Prüfung: `./fliessband einrichten` zeigt Schritt 8 als `[OK]`.

Richte die Jobs **erst ein, wenn alles andere steht** und der Erste Lauf (Kapitel 9) von Hand geklappt hat. Sonst laufen sie ins Leere.

## Die vier Jobs

| Job | Wann | Was |
|---|---|---|
| `lernen` | Freitag 20:00 | wertet die Zahlen der letzten Beiträge aus und schreibt `learnings.md` fort |
| `vorbereiten` | Freitag 22:00 | plant die nächste Woche und stellt dir Fragen in Telegram |
| `bauen` | Samstag 22:00 | baut Texte, Bilder, Stimme und Video und schickt die Beiträge nach Telegram |
| `entscheide` | alle 15 Minuten | setzt deine Freigaben aus Telegram um |

Die Zeiten sind Ortszeit deines Macs.

## Einrichten

Zuerst muss `.env` vollständig sein, ohne Platzhalter. Das Skript bricht sonst mit einer Meldung ab.

```bash
./install.sh --launchd
```

Es legt die vier Jobs unter `~/Library/LaunchAgents/` an und lädt sie in launchd. Es ist wiederholbar. Die Namen der Jobs beginnen mit `com.example.fliessband-`. Das ist nur ein Name und ändert nichts an der Funktion.

## Der Wecker

Die Jobs laufen nur, wenn der Mac wach ist. Damit er Freitag und Samstag kurz vor 22:00 aufwacht, setze einmal von Hand (fragt nach deinem Mac-Passwort):

```bash
sudo pmset repeat wakeorpoweron FS 21:55:00
pmset -g sched
```

Der zweite Befehl zeigt die gesetzte Zeit. Schläft der Mac am Freitag um 20:00, holt `vorbereiten` um 22:00 die Lern-Schleife nach.

## Wo `claude` und die Programme liegen müssen

launchd startet mit einem kleinen PATH. Das Skript `launchd/woche.sh` setzt ihn auf `~/.local/bin`, `/opt/homebrew/bin`, `/usr/local/bin`, `/usr/bin` und `/bin`. Liegen `claude`, `ffmpeg` oder `node` woanders, finden die Jobs sie nicht. Prüfe: `which claude ffmpeg node`. Liegt eines in einem anderen Ordner, ergänze ihn in `launchd/woche.sh`.

## Logs

Alles landet im Ordner `logs/` des Projekts:

- `logs/launchd.log`: Start und Ende jedes Jobs mit Exit-Code
- `logs/woche-<woche>-<schritt>.log`: der Lauf eines Schritts in einer Woche
- `logs/entscheide.log`: die Freigaben

## Prüfen

```bash
./fliessband einrichten
```

Schritt 8 ist `[OK]`, wenn alle vier Jobs in launchd geladen sind. Der Wecker wird als Hinweis gezeigt, nicht geprüft.

## Jobs wieder entfernen

```bash
for j in lernen vorbereiten bauen entscheide; do
  launchctl bootout "gui/$(id -u)/com.example.fliessband-$j"
  rm ~/Library/LaunchAgents/com.example.fliessband-$j.plist
done
```

## Wenn es nicht klappt

- «Jobs fehlen»: `./install.sh --launchd` ausführen. Es meldet, wenn in `.env` noch Platzhalter stehen.
- Ein Job läuft nie: Steht in `logs/launchd.log` ein Exit-Code ungleich 0, steht die Ursache im Log darüber.
- Der Job meldet «claude: command not found»: siehe PATH oben.
