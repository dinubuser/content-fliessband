"""Schlüsselbund-Namen sind einstellbar (FLIESSBAND_KEYCHAIN_PREFIX), damit ein zweites Fliessband auf demselben Mac
(zum Beispiel ein Test von null) die Einträge des ersten nie liest oder überschreibt."""
import re
from pathlib import Path

import pytest

from lib import bot, briefkasten, konfig, mediathek, stimme

SERVER = Path(__file__).resolve().parent.parent / "server"


class Treffer:
    returncode, stdout = 0, "geheim\n"


def _fange(monkeypatch, modul):
    aufrufe = []
    monkeypatch.setattr(modul.subprocess, "run", lambda args, **k: aufrufe.append(list(args)) or Treffer())
    return aufrufe


def test_standardnamen_bleiben(monkeypatch):
    monkeypatch.delenv("FLIESSBAND_KEYCHAIN_PREFIX", raising=False)
    assert [konfig.schluessel_dienst(a) for a in ("telegram", "briefkasten", "wp", "facebook-app")] == [
        "fliessband-telegram", "fliessband-briefkasten", "fliessband-wp", "fliessband-facebook-app"]


@pytest.mark.parametrize("praefix,erwartet", [("fbtest", "fbtest-telegram"), ("  fbtest  ", "fbtest-telegram"), ("", "fliessband-telegram")])
def test_eigener_praefix(monkeypatch, praefix, erwartet):
    monkeypatch.setenv("FLIESSBAND_KEYCHAIN_PREFIX", praefix)
    assert konfig.schluessel_dienst("telegram") == erwartet


def test_telegram_token_nutzt_den_praefix(monkeypatch):
    monkeypatch.setenv("FLIESSBAND_KEYCHAIN_PREFIX", "fbtest")
    bot._token.cache_clear()
    aufrufe = _fange(monkeypatch, bot)
    assert bot._token() == "geheim"
    assert aufrufe[0] == ["security", "find-generic-password", "-s", "fbtest-telegram", "-w"]
    bot._token.cache_clear()


def test_briefkasten_schluessel_nutzt_den_praefix(monkeypatch):
    monkeypatch.setenv("FLIESSBAND_KEYCHAIN_PREFIX", "fbtest")
    briefkasten._schluessel.cache_clear()
    aufrufe = _fange(monkeypatch, briefkasten)
    briefkasten._schluessel()
    assert aufrufe[0][:4] == ["security", "find-generic-password", "-s", "fbtest-briefkasten"]
    briefkasten._schluessel.cache_clear()


def test_wordpress_passwort_nutzt_den_praefix_ausser_der_dienst_ist_gesetzt(monkeypatch):
    monkeypatch.delenv("FLIESSBAND_WP_DIENST", raising=False)
    monkeypatch.setenv("FLIESSBAND_KEYCHAIN_PREFIX", "fbtest")
    mediathek._passwort.cache_clear()
    aufrufe = _fange(monkeypatch, mediathek)
    mediathek._passwort()
    assert "fbtest-wp" in aufrufe[0]
    mediathek._passwort.cache_clear()
    monkeypatch.setenv("FLIESSBAND_WP_DIENST", "mein-wp")
    mediathek._passwort()
    assert "mein-wp" in aufrufe[1]
    mediathek._passwort.cache_clear()


def test_elevenlabs_dienst_ist_einstellbar(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.setattr(stimme, "_key_aus_env_datei", lambda: "")
    stimme._api_key.cache_clear()
    aufrufe = _fange(monkeypatch, stimme)
    stimme._api_key()
    assert aufrufe[0] == ["security", "find-generic-password", "-s", "elevenlabs-api", "-w"]
    stimme._api_key.cache_clear()
    monkeypatch.setenv("FLIESSBAND_ELEVENLABS_DIENST", "mein-elevenlabs")
    stimme._api_key()
    assert aufrufe[1] == ["security", "find-generic-password", "-s", "mein-elevenlabs", "-w"]
    stimme._api_key.cache_clear()


@pytest.mark.parametrize("skript", ["zugang.sh", "facebook.sh"])
def test_server_skripte_haben_keine_festen_schluesselbund_namen(skript):
    """Die Skripte rufen security mit dem Präfix auf, nie mit einem festen fliessband-… Namen."""
    text = (SERVER / skript).read_text(encoding="utf-8")
    befehle = [z for z in text.splitlines() if "generic-password" in z and not z.lstrip().startswith("#")]
    assert befehle
    for z in befehle:
        assert not re.search(r"-s\s+fliessband-", z), z
        assert "FLIESSBAND_KEYCHAIN_PREFIX" in text
