import http.client
import json
import os
import subprocess

import pytest

from lib import stimme
from lib.reel_modell import Szene
from lib.stimme import StimmFehler, vertone, woerter_aus_alignment


def _szenen():
    return [Szene(1, True, "Eine Glace, bitte.", "Glace"),
            Szene(2, False, "Schreib DEMO!", "DEMO")]


def test_woerter_aus_alignment():
    al = {"characters": list("Hi du"),
          "character_start_times_seconds": [0.0, 0.1, 0.2, 0.3, 0.4],
          "character_end_times_seconds": [0.1, 0.2, 0.3, 0.4, 0.5]}
    assert woerter_aus_alignment(al) == [("Hi", 0.0, 0.2), ("du", 0.3, 0.5)]


def test_vertone_mit_aussprache_und_originalwoertern(tmp_path, falsche_elevenlabs):
    aufnahmen = vertone(_szenen(), tmp_path / "stimme", {"Glace": "Eis", "DEMO": "Demo"},
                        anfrage=falsche_elevenlabs)
    assert falsche_elevenlabs.aufrufe == ["Eine Eis, bitte.", "Schreib Demo!"]
    assert [w.wort for w in aufnahmen[0].woerter] == ["Eine", "Glace,", "bitte."]
    assert [w.wort for w in aufnahmen[1].woerter] == ["Schreib", "DEMO!"]
    assert aufnahmen[0].datei == tmp_path / "stimme" / "szene-01.mp3"
    assert aufnahmen[0].dauer > 0
    assert aufnahmen[0].woerter[0].start < aufnahmen[0].woerter[1].start


def test_gleicher_text_keine_neue_anfrage(tmp_path, falsche_elevenlabs):
    vertone(_szenen(), tmp_path / "stimme", {}, anfrage=falsche_elevenlabs)
    vertone(_szenen(), tmp_path / "stimme", {}, anfrage=falsche_elevenlabs)
    assert len(falsche_elevenlabs.aufrufe) == 2


def test_geaenderter_text_nur_diese_szene_neu(tmp_path, falsche_elevenlabs):
    vertone(_szenen(), tmp_path / "stimme", {}, anfrage=falsche_elevenlabs)
    neu = _szenen()
    neu[1].sprechtext = "Schreib Hallo!"
    vertone(neu, tmp_path / "stimme", {}, anfrage=falsche_elevenlabs)
    assert falsche_elevenlabs.aufrufe[-1] == "Schreib Hallo!"
    assert len(falsche_elevenlabs.aufrufe) == 3


def test_api_fehler_nennt_szene(tmp_path):
    def kaputt(text):
        raise StimmFehler("ElevenLabs 401: quota_exceeded")
    with pytest.raises(StimmFehler, match="Szene 1: ElevenLabs 401"):
        vertone(_szenen(), tmp_path / "stimme", {}, anfrage=kaputt)


def test_wortzahl_passt_nicht(tmp_path, falsche_elevenlabs):
    def anders(text):
        return falsche_elevenlabs(text + " extra")
    with pytest.raises(StimmFehler, match="Szene 1: Wortzahl"):
        vertone(_szenen(), tmp_path / "stimme", {}, anfrage=anders)


def test_untertitel_zeigen_aktuellen_sprechtext(tmp_path, falsche_elevenlabs):
    liste = {"DEMO": "Demo"}
    vertone(_szenen(), tmp_path / "stimme", liste, anfrage=falsche_elevenlabs)
    neu = _szenen()
    neu[1].sprechtext = "Schreib Demo!"
    aufnahmen = vertone(neu, tmp_path / "stimme", liste, anfrage=falsche_elevenlabs)
    assert len(falsche_elevenlabs.aufrufe) == 2
    assert [w.wort for w in aufnahmen[1].woerter] == ["Schreib", "Demo!"]
    daten = json.loads((tmp_path / "stimme" / "szene-02.json").read_text(encoding="utf-8"))
    assert "woerter" not in daten
    assert all(len(z) == 2 for z in daten["zeiten"])


@pytest.mark.parametrize("inhalt", ["{kaputt", "[]", '{"schluessel": "x"}', "SCHLUESSEL_FALSCHE_ZEITEN",
                                    "SCHLUESSEL_OHNE_ZEITEN"])
def test_kaputter_speicher_gibt_neue_anfrage(tmp_path, falsche_elevenlabs, inhalt):
    ordner = tmp_path / "stimme"
    vertone(_szenen(), ordner, {}, anfrage=falsche_elevenlabs)
    json_pfad = ordner / "szene-01.json"
    schluessel = json.loads(json_pfad.read_text(encoding="utf-8"))["schluessel"]
    if inhalt == "SCHLUESSEL_FALSCHE_ZEITEN":
        inhalt = json.dumps({"schluessel": schluessel, "zeiten": [[0.1, 0.2]]})
    elif inhalt == "SCHLUESSEL_OHNE_ZEITEN":
        inhalt = json.dumps({"schluessel": schluessel, "woerter": [["Eine", 0.1, 0.2]]})
    json_pfad.write_text(inhalt, encoding="utf-8")
    aufnahmen = vertone(_szenen(), ordner, {}, anfrage=falsche_elevenlabs)
    assert len(falsche_elevenlabs.aufrufe) == 3
    assert [w.wort for w in aufnahmen[0].woerter] == ["Eine", "Glace,", "bitte."]


def _ohne_alignment(antwort):
    return {"audio_base64": antwort["audio_base64"]}


def _ohne_audio(antwort):
    return {**antwort, "audio_base64": ""}


def _laengen_falsch(antwort):
    al = dict(antwort["alignment"])
    al["character_end_times_seconds"] = al["character_end_times_seconds"][:-1]
    return {**antwort, "alignment": al}


@pytest.mark.parametrize("verderben", [_ohne_alignment, _ohne_audio, _laengen_falsch])
def test_kaputte_antwort_nennt_szene(tmp_path, falsche_elevenlabs, verderben):
    with pytest.raises(StimmFehler, match="Szene 1: "):
        vertone(_szenen(), tmp_path / "stimme", {}, anfrage=lambda t: verderben(falsche_elevenlabs(t)))


def test_abbruch_beim_schreiben_hinterlaesst_keinen_falschen_speicher(tmp_path, falsche_elevenlabs, monkeypatch):
    ordner = tmp_path / "stimme"
    vertone(_szenen(), ordner, {}, anfrage=falsche_elevenlabs)
    neu = _szenen()
    neu[0].sprechtext = "Zwei Glace, bitte."
    echt = os.replace

    def bricht_bei_json(quelle, ziel):
        if str(ziel).endswith(".json"):
            raise OSError("Platte voll")
        echt(quelle, ziel)
    monkeypatch.setattr(stimme.os, "replace", bricht_bei_json)
    with pytest.raises(OSError):
        vertone(neu, ordner, {}, anfrage=falsche_elevenlabs)
    monkeypatch.setattr(stimme.os, "replace", echt)
    # alte Wortzeiten dürfen nicht mehr zur neuen mp3 passen: wieder eine Anfrage
    vertone(_szenen(), ordner, {}, anfrage=falsche_elevenlabs)
    assert len(falsche_elevenlabs.aufrufe) == 4


class _Antwort:
    def __init__(self, inhalt):
        self.inhalt = inhalt

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.inhalt


def test_anfrage_timeout_wird_stimmfehler(monkeypatch):
    monkeypatch.setattr(stimme, "_api_key", lambda: "geheim")

    def langsam(req, timeout):
        raise TimeoutError("timed out")
    monkeypatch.setattr(stimme.urllib.request, "urlopen", langsam)
    with pytest.raises(StimmFehler, match="ElevenLabs"):
        stimme.elevenlabs_anfrage("Hallo")


def test_anfrage_kein_json_wird_stimmfehler(monkeypatch):
    monkeypatch.setattr(stimme, "_api_key", lambda: "geheim")
    monkeypatch.setattr(stimme.urllib.request, "urlopen", lambda req, timeout: _Antwort(b"<html>"))
    with pytest.raises(StimmFehler, match="ElevenLabs"):
        stimme.elevenlabs_anfrage("Hallo")


def test_api_key_nur_einmal_lesen(monkeypatch):
    aufrufe = []

    def falsches_security(*a, **k):
        aufrufe.append(a)
        return subprocess.CompletedProcess(a, 0, stdout="geheim\n", stderr="")
    monkeypatch.setattr(stimme.subprocess, "run", falsches_security)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.setattr(stimme, "ENV_DATEI", stimme.Path("/gibt/es/nicht/.env.local"))
    stimme._api_key.cache_clear()
    try:
        assert stimme._api_key() == "geheim"
        assert stimme._api_key() == "geheim"
        assert len(aufrufe) == 1
    finally:
        stimme._api_key.cache_clear()


def test_api_key_aus_env_datei_vor_schluesselbund(monkeypatch, tmp_path):
    datei = tmp_path / ".env.local"
    datei.write_text('ELEVENLABS_API_KEY="aus-datei"\n')
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.setattr(stimme, "ENV_DATEI", datei)
    monkeypatch.setattr(stimme.subprocess, "run", lambda *a, **k: pytest.fail("Schlüsselbund nicht nötig"))
    stimme._api_key.cache_clear()
    try:
        assert stimme._api_key() == "aus-datei"
    finally:
        stimme._api_key.cache_clear()


@pytest.mark.parametrize("fehler", [http.client.IncompleteRead(b"abc"), ConnectionResetError("reset"), OSError("kaputt")])
def test_anfrage_verbindungsfehler_wird_stimmfehler(monkeypatch, fehler):
    monkeypatch.setattr(stimme, "_api_key", lambda: "geheim")

    def kaputt(req, timeout):
        raise fehler
    monkeypatch.setattr(stimme.urllib.request, "urlopen", kaputt)
    with pytest.raises(StimmFehler, match="ElevenLabs"):
        stimme.elevenlabs_anfrage("Hallo")


def test_anfrage_schickt_neue_stimmwerte(monkeypatch):
    monkeypatch.setattr(stimme, "_api_key", lambda: "geheim")
    gesehen = {}

    class Antwort:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"audio_base64": "", "alignment": {}}'

    def urlopen(req, timeout):
        gesehen["body"] = json.loads(req.data)
        return Antwort()
    monkeypatch.setattr(stimme.urllib.request, "urlopen", urlopen)
    stimme.elevenlabs_anfrage("Hallo")
    assert gesehen["body"]["model_id"] == "eleven_multilingual_v2"
    assert gesehen["body"]["voice_settings"] == {"stability": 0.35, "similarity_boost": 0.8, "style": 0.15,
                                                 "use_speaker_boost": True, "speed": 1.05}
