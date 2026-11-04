# 10. Fehlerbehebung

Fange immer hier an:

```bash
./fliessband einrichten --online
```

Der Assistent nennt den ersten offenen Schritt und das passende Kapitel.

## Wo du nachsiehst

| Was | Wo |
|---|---|
| Start und Ende der Jobs | `logs/launchd.log` |
| Ein Schritt in einer Woche | `logs/woche-<woche>-<schritt>.log` |
| Freigaben aus Telegram | `logs/entscheide.log` |
| Faktencheck | `logs/fakten.log` |
| Trend-Scout | `logs/trendscout.log` |
| Stand der Woche | `./fliessband woche status` |
| Vermerke zur Woche (zum Beispiel «Apple-Notiz nicht gelesen») | stehen im Plan der Woche (`wochen/<Woche>/plan.json`, Feld `vermerke`) |
| Der Dienst auf dem Server | `ssh ... systemctl status fliessband-briefkasten` |

## Häufige Meldungen

| Meldung | Ursache und Weg |
|---|---|
| «Telegram-Token fehlt im Schlüsselbund» | Kapitel 4: Dienstname genau `fliessband-telegram` |
| «Keine /start-Nachricht gefunden» | Kapitel 4: dem Bot im privaten Chat `/start` schreiben |
| «ElevenLabs-Key fehlt» | Kapitel 3: Schlüssel im Schlüsselbund, in `.env.local` oder in der Umgebung |
| «Passwort für ... fehlt im Schlüsselbund» | Kapitel 5: Dienst und Konto müssen zu `.env` passen |
| «Mediathek: HTTP 401» oder «403» | Kapitel 5: Anwendungspasswort oder Benutzer stimmen nicht |
| «Briefkasten nicht erreichbar» | Kapitel 6: Tailscale, Adresse, `FLIESSBAND_HOST`, `systemctl status` |
| «Briefkasten nicht eingerichtet» | Kapitel 6: `./fliessband briefkasten umstellen` |
| «Instagram-Schlüssel fehlt oder ungültig» | Kapitel 7: `server/instagram.sh` |
| Instagram-Schlüssel abgelaufen | Kapitel 7: in der Agentur erneuern, dann `server/instagram.sh` |
| Keine START-Meldungen | Kapitel 7: Meta-App im Modus «Veröffentlicht», Berechtigung, `kommentare ein` |
| «FLIESSBAND_POSTTAGE ... ungültig» | `.env`: vier verschiedene Wochentage, aufsteigend (1 = Montag bis 7 = Sonntag) |
| «6 Plätze pro Woche brauchen einen freien Montag und Freitag» | Posttage ändern oder bei 4 Plätzen bleiben |
| Job meldet «claude: command not found» | Kapitel 8: PATH in `launchd/woche.sh` |

## Notbremsen

Alle Schalter lassen sich jederzeit zurücknehmen. Nichts davon löscht Daten.

```bash
./fliessband poster aus        # nichts mehr posten, Freigaben bleiben
./fliessband facebook aus      # Instagram läuft weiter
./fliessband kommentare aus    # keine START-Meldungen mehr
./fliessband fakten aus        # Faktencheck aus (Notausgang, Beiträge werden ungeprüft gebaut)
./fliessband trends aus        # Trend-Scout aus
./fliessband plaetze 4         # zurück auf vier Beiträge pro Woche
```

Jobs ganz stoppen: siehe Kapitel 8, «Jobs wieder entfernen».

## Hilfe holen

Beschreibe das Problem mit dem Text der Meldung und der Ausgabe von `./fliessband einrichten`. Zeige nie einen Schlüssel, ein Token oder ein Passwort her. Der Assistent zeigt sie ohnehin nie an.
