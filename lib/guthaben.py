"""Restguthaben abfragen: ElevenLabs-Zeichen im Abo-Monat und Apify-Monatsguthaben.
Die Schlüssel lesen nur lib.stimme (Schlüsselbund) und das Apify-Werkzeug der Agentur, nie ausgeben."""
import json
import urllib.error
import urllib.request
from typing import Callable

from lib.stimme import StimmFehler, _api_key
from lib.umgebung import Werkzeug, letzte_zeile

ELEVENLABS_ABO = "https://api.elevenlabs.io/v1/user/subscription"


class GuthabenFehler(Exception):
    pass


def elevenlabs_abo() -> dict:
    """Echte Abfrage GET /v1/user/subscription (character_count, character_limit)."""
    try:
        req = urllib.request.Request(ELEVENLABS_ABO, headers={"xi-api-key": _api_key()})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except StimmFehler as e:
        raise GuthabenFehler(str(e)) from None
    except urllib.error.HTTPError as e:
        raise GuthabenFehler(f"ElevenLabs {e.code} bei der Guthaben-Abfrage") from None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        raise GuthabenFehler("ElevenLabs-Guthaben nicht abfragbar (Verbindung)") from None


def elevenlabs_rest(abfrage: Callable[[], dict] = elevenlabs_abo) -> int:
    """Verbleibende Zeichen im laufenden Abo-Monat."""
    daten = abfrage()
    try:
        return int(daten["character_limit"]) - int(daten["character_count"])
    except (KeyError, TypeError, ValueError):
        raise GuthabenFehler("ElevenLabs-Antwort ohne character_limit oder character_count") from None


def apify_rest(werkzeug: Werkzeug) -> float:
    """Verbleibendes Apify-Monatsguthaben in $ (über 'apify.py check --json' der Agentur, kostet nichts)."""
    r = werkzeug("apify.py", ["check", "--json"], 60)
    if r.returncode != 0:
        raise GuthabenFehler(f"Apify-Check gescheitert: {letzte_zeile(r.stderr)}")
    try:
        rest = json.loads(r.stdout)["verbleibend_usd"]
    except (json.JSONDecodeError, KeyError, TypeError):
        raise GuthabenFehler("Apify-Check liefert kein verbleibend_usd") from None
    if not isinstance(rest, (int, float)):
        raise GuthabenFehler("Apify meldet kein Monatsguthaben")
    return float(rest)
