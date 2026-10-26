import json
import subprocess

import pytest

from lib import guthaben
from lib.guthaben import GuthabenFehler, apify_rest, elevenlabs_abo, elevenlabs_rest
from lib.stimme import StimmFehler


def test_elevenlabs_rest():
    assert elevenlabs_rest(lambda: {"character_count": 25400, "character_limit": 40000, "tier": "starter"}) == 14600


def test_elevenlabs_kaputte_antwort():
    with pytest.raises(GuthabenFehler, match="character_limit"):
        elevenlabs_rest(lambda: {"tier": "starter"})


def test_elevenlabs_ohne_key(monkeypatch):
    def fehlt():
        raise StimmFehler("ElevenLabs-Key fehlt im Schlüsselbund (Dienst elevenlabs-api)")
    monkeypatch.setattr(guthaben, "_api_key", fehlt)
    with pytest.raises(GuthabenFehler, match="Schlüsselbund"):
        elevenlabs_abo()


def _werkzeug(rc, stdout, stderr=""):
    aufrufe = []

    def w(name, argumente, zeitlimit):
        aufrufe.append((name, argumente))
        return subprocess.CompletedProcess([name], rc, stdout, stderr)
    w.aufrufe = aufrufe
    return w


def test_apify_rest():
    w = _werkzeug(0, json.dumps({"konto": "betreiber", "verbleibend_usd": 4.12}))
    assert apify_rest(w) == 4.12
    assert w.aufrufe == [("apify.py", ["check", "--json"])]


def test_apify_check_scheitert():
    w = _werkzeug(2, "", "Fehler: Der Apify-Schlüssel wird nicht akzeptiert.")
    with pytest.raises(GuthabenFehler, match="nicht akzeptiert"):
        apify_rest(w)


def test_apify_ohne_wert():
    with pytest.raises(GuthabenFehler, match="kein Monatsguthaben"):
        apify_rest(_werkzeug(0, json.dumps({"verbleibend_usd": None})))
