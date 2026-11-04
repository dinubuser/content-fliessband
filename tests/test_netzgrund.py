"""Netzgrund: Der Grund eines Netzfehlers steht als festes deutsches Wort in der Meldung (nie der rohe Fehlertext)."""
import errno
import http.client
import socket
import ssl
import urllib.error
import urllib.request

import pytest

from lib import bot
from lib.bot import BotFehler, telegram_anfrage
from lib.briefkasten import BriefkastenFehler, http as briefkasten_http
from lib.mediathek import Mediathek, MediathekFehler
from lib.netzgrund import netzgrund


@pytest.mark.parametrize("fehler, erwartet", [
    (urllib.error.URLError(TimeoutError()), "Zeitüberschreitung"),
    (TimeoutError("timed out"), "Zeitüberschreitung"),
    (socket.timeout("timed out"), "Zeitüberschreitung"),
    (urllib.error.URLError(socket.gaierror(8, "nodename nor servname provided")), "Name nicht aufgelöst"),
    (urllib.error.URLError("nodename nor servname provided"), "Name nicht aufgelöst"),
    (urllib.error.URLError(ConnectionRefusedError(61, "Connection refused")), "Verbindung abgelehnt"),
    (ConnectionResetError(54, "reset"), "Verbindung zurückgesetzt"),
    (http.client.RemoteDisconnected("Remote end closed connection"), "Verbindung zurückgesetzt"),
    (urllib.error.URLError(OSError(errno.ENETUNREACH, "Network is unreachable")), "Netz nicht erreichbar"),
    (urllib.error.URLError(OSError(errno.EHOSTUNREACH, "No route to host")), "Host nicht erreichbar"),
    (urllib.error.URLError(ssl.SSLError(1, "handshake failure")), "TLS-Fehler"),
    (urllib.error.URLError("irgendein neuer Text"), "unbekannt"),
    (ValueError("123456:GEHEIM"), "unbekannt"),
])
def test_grund_als_festes_wort(fehler, erwartet):
    assert netzgrund(fehler) == erwartet


def test_kein_roher_text_mit_geheimnis():
    for f in (ValueError("123456:GEHEIM"), urllib.error.URLError("https://api.telegram.org/bot123456:GEHEIM/x"),
              OSError(5, "123456:GEHEIM")):
        assert "GEHEIM" not in netzgrund(f)


def test_briefkasten_meldung_nennt_den_grund():
    def oeffne(req, timeout):
        raise urllib.error.URLError(TimeoutError())
    anfrage = briefkasten_http("http://127.0.0.1:1", schluessel=lambda: "x", oeffne=oeffne)
    with pytest.raises(BriefkastenFehler) as info:
        anfrage("GET", "/poster")
    assert str(info.value) == "Briefkasten nicht erreichbar (URLError: Zeitüberschreitung)"


def test_briefkasten_netz_unerreichbar():
    def oeffne(req, timeout):
        raise urllib.error.URLError(OSError(errno.ENETUNREACH, "Network is unreachable"))
    anfrage = briefkasten_http("http://127.0.0.1:1", schluessel=lambda: "x", oeffne=oeffne)
    with pytest.raises(BriefkastenFehler, match=r"nicht erreichbar \(URLError: Netz nicht erreichbar\)"):
        anfrage("GET", "/poster")


def test_telegram_meldung_nennt_den_grund_ohne_token(monkeypatch):
    monkeypatch.setattr(bot, "_token", lambda: "123456:GEHEIM")

    def urlopen(req, timeout):
        raise urllib.error.URLError(socket.gaierror(8, "https://api.telegram.org/bot123456:GEHEIM/getUpdates"))
    monkeypatch.setattr(bot.urllib.request, "urlopen", urlopen)
    with pytest.raises(BotFehler) as info:
        telegram_anfrage("getUpdates", {"offset": 1})
    assert str(info.value) == "Telegram nicht erreichbar (URLError: Name nicht aufgelöst)"
    assert "GEHEIM" not in str(info.value)


def test_mediathek_meldung_nennt_den_grund():
    def oeffne(req, timeout):
        raise urllib.error.URLError(ConnectionRefusedError(61, "refused"))
    m = Mediathek(passwort=lambda: "pw", oeffne=oeffne, adresse="https://example.invalid")
    with pytest.raises(MediathekFehler, match=r"nicht erreichbar \(URLError: Verbindung abgelehnt\)"):
        m._rufe(urllib.request.Request("https://example.invalid/wp-json/x"))
