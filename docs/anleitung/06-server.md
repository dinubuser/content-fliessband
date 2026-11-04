# 6. Server und Briefkasten

Ziel: Ein kleiner Linux-Server nimmt deine Freigaben aus Telegram entgegen und postet die freigegebenen Beiträge zum Termin, auch wenn dein Mac schläft. Er heisst im Projekt **Briefkasten**. Prüfung: `./fliessband einrichten --online` zeigt Schritt 6 als `[OK]`.

Stand der Klickwege: November 2026, nicht von null getestet. Das ist der aufwendigste Schritt. Plane Zeit ein.

## Was du brauchst

- Einen **Linux-Server** (zum Beispiel ein kleiner VPS) mit **Python 3.10 oder neuer** und **SQLite 3.24 oder neuer**. Das Skript `server/einrichten.sh` prüft beides und bricht mit einer Meldung ab, wenn eines zu alt ist.
- **SSH-Zugang als root** mit einer Schlüsseldatei auf deinem Mac.
- **Tailscale** auf dem Mac und auf dem Server, im selben Tailnet. Der Briefkasten ist nur über Tailscale erreichbar, nicht öffentlich. Installiere Tailscale nach der offiziellen Anleitung (tailscale.com) und notiere die Tailscale-Adresse des Servers (auf dem Server: `tailscale ip -4`).
- `rsync` auf dem Mac (bei macOS dabei).
- Fertig: Kapitel 4 (Telegram, `daten/bot.json` und Token im Schlüsselbund), denn der Server bekommt von dort Token und Chat-ID.

## In die Konfiguration

In `.env` auf dem Mac:

```
FLIESSBAND_SERVER=root@100.x.y.z                  # SSH-Ziel (Tailscale-Adresse oder Name)
FLIESSBAND_SSH_KEY=~/.ssh/dein_schluessel         # Schlüsseldatei für den Server
FLIESSBAND_BRIEFKASTEN_URL=http://100.x.y.z:8096  # Adresse des Briefkastens
```

Ersetze `100.x.y.z` durch die Tailscale-Adresse deines Servers.

## Server einrichten

Die Skripte in `server/` laufen in dieser Reihenfolge. Alle sind wiederholbar.

**1. Server vorbereiten** (Benutzer `fliessband`, Ordner, Python-Umgebung). Vom Mac aus:

```bash
ssh -i ~/.ssh/dein_schluessel root@100.x.y.z 'bash -s' < server/einrichten.sh
```

**2. Optional, empfohlen: den Dienst auf Tailscale beschränken.** Auf dem Server die Datei `/etc/fliessband/konfig.env` anlegen:

```
FLIESSBAND_HOST=100.x.y.z
FLIESSBAND_ZEITZONE=Europe/Zurich
```

`FLIESSBAND_HOST` ist die Adresse, auf der der Dienst lauscht. Ohne diese Datei lauscht er auf `127.0.0.1` und ist vom Mac aus nicht erreichbar. `FLIESSBAND_ZEITZONE` ist die Zeitzone der Termine und muss zu der deines Macs passen (Standard `Europe/Zurich`).

**3. Zugang einrichten** (auf dem Mac). Das Skript legt auf dem Server `/etc/fliessband/geheim.env` an: Telegram-Token aus dem Schlüsselbund, Chat-ID aus `daten/bot.json` und einen neuen Schlüssel zwischen Mac und Server, den es auch im Schlüsselbund speichert. Nichts davon wird angezeigt.

```bash
server/zugang.sh
```

**4. Code auf den Server bringen, Tests dort ausführen, Dienst starten:**

```bash
server/deploy.sh
```

Es startet nur den Dienst `fliessband-briefkasten` neu und berührt weder die Daten noch `geheim.env`. Am Ende steht `active`, wenn der Dienst läuft.

**5. Telegram an den Server übergeben** (einmalig):

```bash
./fliessband briefkasten umstellen
```

Ab jetzt fragt der Server Telegram ab und der Mac nicht mehr. Das Skript meldet, welche Wochen noch angemeldet werden müssen (`./fliessband woche anmelden --woche ...`).

## Prüfen

```bash
./fliessband einrichten --online
```

Schritt 6 ist `[OK]`, wenn die drei Werte in `.env` gesetzt sind, die Schlüsseldatei da ist, der Schlüssel zwischen Mac und Server im Schlüsselbund liegt, der Briefkasten umgestellt ist und der Server antwortet. Ohne `--online` wird der Server nicht abgefragt.

## Wenn es nicht klappt

- `einrichten.sh` meldet «Python ... zu alt» oder «SQLite ... zu alt»: einen neueren Server wählen.
- `deploy.sh` bricht in den Tests ab: Die Tests laufen auf dem Server. Die Meldung zeigt, welcher Test scheitert.
- «Briefkasten nicht erreichbar»: Läuft Tailscale auf beiden Seiten? Stimmt die Adresse in `FLIESSBAND_BRIEFKASTEN_URL`? Hast du `FLIESSBAND_HOST` gesetzt und den Dienst danach neu gestartet (`server/deploy.sh`)? Auf dem Server prüfen: `systemctl status fliessband-briefkasten`.
- `zugang.sh` meldet, `daten/bot.json` fehle: Kapitel 4 zuerst abschliessen.
- Du hast den Schlüssel neu erzeugt (`zugang.sh` noch einmal): Danach `server/deploy.sh`, damit der Dienst neu startet.
