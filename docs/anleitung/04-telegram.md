# 4. Telegram

Ziel: Das Fliessband schickt dir die Beiträge in Telegram und nimmt deine Freigabe per Knopf entgegen. Du hast einen eigenen Bot, sein Token liegt im Schlüsselbund, und das Fliessband kennt deine Chat-ID. Prüfung: `./fliessband einrichten` zeigt Schritt 4 als `[OK]`.

Stand der Klickwege: November 2026, nicht von null getestet.

## Bot anlegen

1. Öffne in Telegram den Chat mit **@BotFather**.
2. Schreibe `/newbot` und folge den Fragen (Name und Benutzername des Bots).
3. BotFather schickt dir ein **Token**. Es ist der Schlüssel zu deinem Bot. Teile es mit niemandem.

## Token in den Schlüsselbund

```bash
security add-generic-password -s fliessband-telegram -a fliessband -w
```

Der Befehl fragt das Token interaktiv ab. Es landet nicht in der Shell-Historie.

## Bot mit dem Fliessband verbinden

1. Öffne in Telegram deinen neuen Bot und schreibe ihm im **privaten Chat** `/start`.
2. Danach im Terminal:

```bash
./fliessband bot einrichten
```

Das Fliessband speichert deine Chat-ID in `daten/bot.json` und schickt dir eine Bestätigung in Telegram. Nur dein privater Chat ist erlaubt.

Dieser Befehl gilt **nur vor der Umstellung des Briefkastens** (Kapitel 6). Danach fragt der Server Telegram ab, und das Fliessband meldet «Briefkasten schon umgestellt».

## Prüfen

```bash
./fliessband einrichten
```

Schritt 4 ist `[OK]`, wenn das Token im Schlüsselbund liegt und `daten/bot.json` eine Chat-ID enthält.

## Wenn es nicht klappt

- «Keine /start-Nachricht gefunden»: Schreibe dem Bot noch einmal `/start`, und zwar im privaten Chat mit ihm, nicht in einer Gruppe. Dann den Befehl wiederholen.
- «Telegram-Token fehlt im Schlüsselbund»: Der Dienstname muss genau `fliessband-telegram` heissen.
