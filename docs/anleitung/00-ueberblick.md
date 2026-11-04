# Anleitung: Content-Fliessband einrichten

Am Ende läuft jede Woche dieser Zyklus von allein: Das Fliessband plant vier Beiträge, baut Texte, Bilder, Stimme und Video, schickt sie dir in Telegram zur Freigabe und postet nur, was du freigibst. Ohne dein Ja geht nichts online.

**Stand dieser Anleitung:** Entwurf. Sie ist noch nicht von null auf einem frischen Mac mit frischen Konten durchgespielt. Die Befehle stammen aus dem Code dieses Repos. Die Klickwege bei Fremddiensten (Telegram, ElevenLabs, WordPress, Meta, Tailscale) sind Stand November 2026 und können sich ändern. Wenn ein Schritt abweicht, gilt die offizielle Anleitung des Dienstes.

## Für wen

Du hast Claude Code und die Social-Media-Agentur von Sebastian Kauffmann schon installiert oder bist bereit, das zuerst zu tun (Kapitel 2). Dieses Repo ist eine Erweiterung der Agentur, kein Ersatz.

## Die neun Schritte

| Schritt | Kapitel | Was du tust | Wo |
|---|---|---|---|
| 1 | [Voraussetzungen](01-voraussetzungen.md) | Programme und dieses Repo installieren | Terminal |
| 2 | [Agentur und Konto](02-agentur.md) | Agentur-Daten, Handle, Regeln anpassen | Terminal, Editor |
| 3 | [Stimme (ElevenLabs)](03-elevenlabs.md) | Konto, Schlüssel, Stimmen-ID | Browser, Terminal |
| 4 | [Telegram](04-telegram.md) | Bot anlegen, mit dem Fliessband verbinden | Handy, Terminal |
| 5 | [WordPress-Mediathek](05-wordpress.md) | Öffentliche Adressen für Bilder und Videos | Browser, Terminal |
| 6 | [Server und Briefkasten](06-server.md) | Kleiner Server, Tailscale, Briefkasten | Browser, Terminal |
| 7 | [Instagram und Facebook](07-instagram-facebook.md) | Schlüssel auf den Server, Poster einschalten | Browser, Terminal |
| 8 | [Jobs (launchd)](08-jobs.md) | Die Wochen-Jobs einrichten | Terminal |
| 9 | [Erster Lauf](09-erster-lauf.md) | Alles einmal von Hand durchspielen | Terminal, Telegram |

Bei Problemen: [Fehlerbehebung](10-fehler.md).

## Der Assistent prüft jeden Schritt

```bash
./fliessband einrichten             # prüft alles, was auf deinem Mac liegt
./fliessband einrichten --online    # fragt zusätzlich den Server ab (Schritt 6 und 7)
```

Er zeigt die neun Schritte mit `[OK]`, `[OFFEN]`, `[ÜBERSPRUNGEN]` oder `[VON HAND]` und nennt den nächsten offenen Schritt samt Kapitel. Er liest nur: Er ändert nichts, legt keine Konten an und zeigt nie einen Wert aus deiner `.env` oder deinem Schlüsselbund. Im Schlüsselbund fragt er nur, ob ein Eintrag da ist.

Arbeite die Kapitel der Reihe nach ab. Nach jedem Kapitel einmal `./fliessband einrichten`.

## Was das kostet

Die Posten, ohne Preise (die ändern sich):

- **Claude Code** mit Abo: Die Agenten laufen über `claude -p`.
- **ElevenLabs:** ein Plan mit genug Zeichen für die Stimme der Reels.
- **Kleiner Linux-Server:** monatliche Miete beim Anbieter deiner Wahl.
- **WordPress-Seite** mit Mediathek: hast du schon oder brauchst Hosting.
- **Apify** (optional, für Konkurrenz-Zahlen): hat ein Gratis-Guthaben im Monat. Das Fliessband setzt eine Obergrenze von 0.50 $ pro Lauf und startet nur, wenn mindestens 2 $ Monatsguthaben da sind.

## Grundregeln

- **Nichts geht ohne Freigabe online.** Der Server postet nur freigegebene Beiträge zum Termin.
- **Schlüssel gehören in den Schlüsselbund**, nie in `.env`, nie in einen Chat, nie in Git. Der Befehl `security add-generic-password ... -w` fragt den Wert interaktiv ab, er landet nicht in der Shell-Historie.
- **Keine automatischen Antworten oder Direktnachrichten** an deine Leser, keine Links in Beitrag oder Bio.
