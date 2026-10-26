"""Vertont jede Szene mit der ElevenLabs-Stimme des Betreibers und speichert Wortzeiten.

Der API-Key kommt aus dem macOS-Schlüsselbund (Dienst elevenlabs-api) und wird nie ausgegeben.
Gleicher Text + gleiche Stimme = keine neue Anfrage (Zwischenspeicher im Ordner stimme/).
"""
import base64
import binascii
import functools
import http.client
import hashlib
import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from lib.konfig import wert
from lib.medien import dauer
from lib.pruefungen import sprechbar
from lib.reel_modell import Aufnahme, Szene, Wort

VOICE_ID = wert("ELEVENLABS_VOICE_ID", "your-elevenlabs-voice-id")   # Stimme aus .env, siehe .env.example
MODELL = "eleven_multilingual_v2"
# Seit Etappe 7 lebendiger (Kurs-Anleitung «Reel Pipeline»): tiefere Stability, etwas Style, Speaker-Boost
EINSTELLUNGEN = {"stability": 0.35, "similarity_boost": 0.8, "style": 0.15, "use_speaker_boost": True, "speed": 1.05}
URL = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/with-timestamps?output_format=mp3_44100_128"


class StimmFehler(Exception):
    pass


ENV_DATEI = Path(__file__).resolve().parent.parent / ".env.local"  # ELEVENLABS_API_KEY, seit 2026-10-24


def _key_aus_env_datei() -> str:
    if not ENV_DATEI.exists():
        return ""
    for zeile in ENV_DATEI.read_text().splitlines():
        name, _, wert = zeile.strip().partition("=")
        if name.strip() == "ELEVENLABS_API_KEY":
            return wert.strip().strip('"').strip("'")
    return ""


@functools.lru_cache(maxsize=1)
def _api_key() -> str:
    """Zuerst .env.local im Projekt (neuer Schlüssel), sonst wie bisher der Schlüsselbund."""
    key = os.environ.get("ELEVENLABS_API_KEY") or _key_aus_env_datei()
    if key:
        return key
    r = subprocess.run(["security", "find-generic-password", "-s", "elevenlabs-api", "-w"],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        raise StimmFehler("ElevenLabs-Key fehlt (.env.local oder Schlüsselbund elevenlabs-api)")
    return r.stdout.strip()


def elevenlabs_anfrage(text: str) -> dict:
    """Echte Anfrage. Liefert das JSON mit audio_base64 und alignment."""
    body = json.dumps({"text": text, "model_id": MODELL, "language_code": "de",
                       "voice_settings": EINSTELLUNGEN}).encode()
    req = urllib.request.Request(URL, data=body, method="POST",
                                 headers={"xi-api-key": _api_key(), "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise StimmFehler(f"ElevenLabs {e.code}: {e.read().decode(errors='replace')[:200]}") from None
    except urllib.error.URLError as e:
        raise StimmFehler(f"ElevenLabs nicht erreichbar: {e.reason}") from None
    except TimeoutError:
        raise StimmFehler("ElevenLabs antwortet nicht (Zeitüberschreitung)") from None
    except json.JSONDecodeError:
        raise StimmFehler("ElevenLabs-Antwort ist kein gültiges JSON") from None
    except (http.client.HTTPException, OSError) as e:
        raise StimmFehler(f"ElevenLabs-Verbindung unterbrochen: {type(e).__name__}") from None


def woerter_aus_alignment(al: dict) -> list[tuple[str, float, float]]:
    """Zeichen-Zeitstempel zu (wort, start, ende) zusammenfassen."""
    woerter, cur, start, ende = [], "", None, None
    for ch, s, e in zip(al["characters"], al["character_start_times_seconds"],
                        al["character_end_times_seconds"]):
        if ch.isspace():
            if cur:
                woerter.append((cur, round(start, 3), round(ende, 3)))
            cur, start = "", None
            continue
        if start is None:
            start = s
        cur += ch
        ende = e
    if cur:
        woerter.append((cur, round(start, 3), round(ende, 3)))
    return woerter


def _schluessel(text: str) -> str:
    roh = json.dumps({"text": text, "voice": VOICE_ID, "modell": MODELL, "einstellungen": EINSTELLUNGEN},
                     sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(roh.encode()).hexdigest()


def _aus_speicher(json_pfad: Path, mp3: Path, schluessel: str, anzahl: int) -> list | None:
    """Gespeicherte [start, ende]-Paare, wenn sie zu Schlüssel und Wortzahl passen. Kaputtes = None."""
    if not (json_pfad.exists() and mp3.exists()):
        return None
    try:
        daten = json.loads(json_pfad.read_text(encoding="utf-8"))
        if daten["schluessel"] != schluessel:
            return None
        zeiten = [(float(a), float(e)) for a, e in daten["zeiten"]]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return zeiten if len(zeiten) == anzahl else None


def _zeiten_aus_antwort(nummer: int, antwort: dict, anzahl: int) -> tuple[bytes, list]:
    """Prüft die API-Antwort. Liefert (mp3-Bytes, [(start, ende)]) oder StimmFehler mit Szene."""
    al = None
    if isinstance(antwort, dict):
        al = antwort.get("alignment") or antwort.get("normalized_alignment")
    if not isinstance(al, dict):
        raise StimmFehler(f"Szene {nummer}: Antwort ohne Zeitstempel (alignment)")
    try:
        spalten = [al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]]
        if len({len(s) for s in spalten}) != 1:
            raise StimmFehler(f"Szene {nummer}: Zeitstempel der Antwort sind unterschiedlich lang")
        roh = woerter_aus_alignment(al)
    except (KeyError, TypeError):
        raise StimmFehler(f"Szene {nummer}: Zeitstempel der Antwort unvollständig") from None
    try:
        audio = base64.b64decode(antwort.get("audio_base64") or "", validate=True)
    except (binascii.Error, TypeError, ValueError):
        audio = b""
    if not audio:
        raise StimmFehler(f"Szene {nummer}: Antwort ohne Ton (audio_base64)")
    if len(roh) != anzahl:
        raise StimmFehler(f"Szene {nummer}: Wortzahl der Aufnahme ({len(roh)}) passt nicht "
                          f"zum Sprechtext ({anzahl})")
    return audio, [(a, e) for _, a, e in roh]


def _sicher_schreiben(pfad: Path, inhalt: bytes) -> None:
    """Erst in eine Hilfsdatei, dann in einem Schritt ersetzen."""
    hilf = pfad.with_name(pfad.name + ".tmp")
    hilf.write_bytes(inhalt)
    os.replace(hilf, pfad)


def vertone(szenen: list[Szene], ordner: Path, aussprache: dict[str, str],
            anfrage: Callable[[str], dict] = elevenlabs_anfrage) -> list[Aufnahme]:
    ordner.mkdir(parents=True, exist_ok=True)
    aufnahmen = []
    for s in szenen:
        gesprochen = sprechbar(s.sprechtext, aussprache)
        original = s.sprechtext.split()
        mp3 = ordner / f"szene-{s.nummer:02d}.mp3"
        json_pfad = ordner / f"szene-{s.nummer:02d}.json"
        schluessel = _schluessel(gesprochen)

        zeiten = _aus_speicher(json_pfad, mp3, schluessel, len(original))
        if zeiten is None:
            try:
                antwort = anfrage(gesprochen)
            except StimmFehler as e:
                raise StimmFehler(f"Szene {s.nummer}: {e}") from None
            audio, zeiten = _zeiten_aus_antwort(s.nummer, antwort, len(original))
            # Alte Zeiten zuerst weg: bricht es danach ab, passt kein Speicher zur neuen mp3
            json_pfad.unlink(missing_ok=True)
            _sicher_schreiben(mp3, audio)
            daten = {"schluessel": schluessel, "gesprochen": gesprochen, "zeiten": [[a, e] for a, e in zeiten]}
            _sicher_schreiben(json_pfad, json.dumps(daten, ensure_ascii=False, indent=1).encode("utf-8"))

        # Zeiten aus der Aufnahme, Wörter immer aus dem aktuellen Sprechtext (für die Untertitel)
        aufnahmen.append(Aufnahme(nummer=s.nummer, datei=mp3, dauer=dauer(mp3),
                                  woerter=[Wort(w, a, e) for w, (a, e) in zip(original, zeiten)]))
    return aufnahmen
