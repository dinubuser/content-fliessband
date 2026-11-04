# 5. WordPress-Mediathek

Ziel: Instagram und Facebook holen Bilder und Videos von einer öffentlichen Adresse. Das Fliessband lädt sie dafür in die Mediathek deiner WordPress-Seite und löscht nie gepostete Dateien wieder. Prüfung: `./fliessband einrichten` zeigt Schritt 5 als `[OK]`.

Stand der Klickwege: November 2026, nicht von null getestet.

## Warum

Meta nimmt Bilder und Videos nur über eine öffentlich erreichbare Adresse an, nicht als direkten Upload vom Rechner (so beschreibt es auch die Agentur für Reels). Heute ist dafür WordPress fest eingebaut. Ein Weg ohne WordPress ist noch nicht gebaut. Wer einen anderen Dienst mit öffentlichen Adressen nutzen will, ersetzt die Klasse `Mediathek` (Schnittstelle in `CLAUDE.md`, Abschnitt «Anpassen»).

## Was du brauchst

- Eine WordPress-Seite mit **https**.
- Einen Benutzer mit der Rolle **Redakteur** (das Fliessband braucht keine Administrator-Rechte).
- Ein **Anwendungspasswort** für diesen Benutzer. WordPress bietet es auf der Profilseite des Benutzers an (Abschnitt «Anwendungspasswörter»). Gib ihm einen Namen wie «Fliessband» und kopiere das Passwort, es erscheint nur einmal.

## In die Konfiguration

In `.env`:

```
FLIESSBAND_WP_URL=https://deine-seite.ch
FLIESSBAND_WP_KONTO=dein-wordpress-benutzer
```

Das Anwendungspasswort in den Schlüsselbund (nicht in `.env`):

```bash
security add-generic-password -s fliessband-wp -a dein-wordpress-benutzer -w
```

Den Dienstnamen `fliessband-wp` kannst du mit `FLIESSBAND_WP_DIENST` in `.env` ändern. Mit eigenem Präfix heisst er `<präfix>-wp`. Das Konto (`-a`) muss zu `FLIESSBAND_WP_KONTO` passen.

## Prüfen

```bash
./fliessband einrichten
```

Schritt 5 ist `[OK]`, wenn die Adresse mit `https://` beginnt, das Konto gesetzt ist und das Passwort im Schlüsselbund liegt. Ob WordPress es annimmt, zeigt erst der erste Upload im ersten Lauf (Kapitel 9). Du kannst vorab prüfen, ob die REST-Schnittstelle antwortet: Öffne `https://deine-seite.ch/wp-json/` im Browser, du solltest JSON sehen.

## Wenn es nicht klappt

- «HTTP 401» oder «HTTP 403» beim Upload: Anwendungspasswort oder Benutzer stimmen nicht, oder ein Sicherheits-Plugin blockiert die REST-Schnittstelle.
- «Passwort für ... fehlt im Schlüsselbund»: Dienst und Konto im Schlüsselbund müssen zu `.env` passen.
- Die Seite hat kein https: Zuerst das Zertifikat einrichten. Das Fliessband akzeptiert nur Adressen mit https.
