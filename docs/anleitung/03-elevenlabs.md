# 3. Stimme (ElevenLabs)

Ziel: Die Reels bekommen eine KI-Stimme. Du hast ein ElevenLabs-Konto, einen API-Schlüssel im Schlüsselbund und eine Stimmen-ID in `.env`. Prüfung: `./fliessband einrichten` zeigt Schritt 3 als `[OK]`.

Stand der Klickwege: November 2026, nicht von null getestet. Bei Abweichungen gilt die Anleitung von ElevenLabs.

## Konto und Stimme

1. Lege auf elevenlabs.io ein Konto an und wähle einen Plan mit genug Zeichen im Monat. Ein Reel braucht ungefähr 500 bis 800 Zeichen (70 bis 105 Wörter Sprechtext, je nach Länge). Rechne mit zwei Reels pro Woche, mit dem Schalter «6 Plätze» mit drei.
2. Wähle oder erstelle eine Stimme, die **Deutsch** spricht. Die Reels nutzen das Modell `eleven_multilingual_v2`. Eine eigene geklonte Stimme ist möglich, brauchst du aber nicht.
3. Kopiere die **Voice-ID** der Stimme (in ElevenLabs bei der Stimme, in den Details).
4. Erstelle einen **API-Schlüssel** (in den Kontoeinstellungen unter API Keys).

## In die Konfiguration

Die Voice-ID ist nicht geheim und kommt in `.env`:

```
ELEVENLABS_VOICE_ID=die-id-deiner-stimme
```

Der API-Schlüssel ist geheim und kommt **nicht** in `.env`. Standardweg ist der Schlüsselbund:

```bash
security add-generic-password -s elevenlabs-api -a "$USER" -w
```

Der Befehl fragt den Schlüssel interaktiv ab. Alternativ geht `ELEVENLABS_API_KEY` in der Umgebung oder in der Datei `.env.local` im Projektordner (nie in `.env`). Das Fliessband sucht in dieser Reihenfolge: Umgebung, `.env.local`, Schlüsselbund.

## Aussprache

Eine KI-Stimme spricht manche Wörter falsch. Das Fliessband hat dafür einen Aussprache-Check: Er schlägt Ersatzwörter vor, und bestätigte Einträge landen in `daten/aussprache-auto.txt`. Eigene Wörter trägst du in `aussprache.txt` ein, Format `Wort → Ersatz`. Der Eintrag in `aussprache.txt` gewinnt bei gleichem Wort. Hörst du beim ersten Reel ein falsch gesprochenes Wort, trage es dort ein.

## Prüfen

```bash
./fliessband einrichten
```

Schritt 3 ist `[OK]`, wenn die Voice-ID gesetzt ist und der Schlüssel da ist (Umgebung, `.env.local` oder Schlüsselbund). Der Assistent prüft nur, ob etwas da ist, und prüft den Schlüssel nicht bei ElevenLabs. Ob er stimmt, zeigt der erste Lauf (Kapitel 9). Das Fliessband prüft vor dem Bau das Restguthaben der Zeichen und meldet, wenn es nicht reicht.

## Wenn es nicht klappt

- «ELEVENLABS_VOICE_ID fehlt oder ist noch ein Platzhalter»: In `.env` steht noch `your-elevenlabs-voice-id`.
- Beim Bau «ElevenLabs-Key fehlt»: Der Schlüssel liegt unter einem anderen Namen im Schlüsselbund. Der Dienstname muss genau `elevenlabs-api` heissen.
