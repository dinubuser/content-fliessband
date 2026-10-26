import http.client
import io
import json
import urllib.error

import pytest

from briefkasten.telegram import TelegramFehler, telegram

TOKEN = "123:geheim"


class Antwort(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _oeffne(koerper=None, fehler=None):
    gesehen = []

    def oeffne(req, timeout):
        gesehen.append((req, timeout))
        if fehler:
            raise fehler
        return Antwort(json.dumps(koerper).encode())
    return oeffne, gesehen


def test_erfolg_schickt_json_und_liefert_result():
    oeffne, gesehen = _oeffne({"ok": True, "result": {"message_id": 5}})
    anfrage = telegram(TOKEN, oeffne=oeffne)
    assert anfrage("sendMessage", {"chat_id": 42, "text": "Hä?"}) == {"message_id": 5}
    req, timeout = gesehen[0]
    assert req.full_url == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert json.loads(req.data) == {"chat_id": 42, "text": "Hä?"} and timeout == 30
    anfrage("getUpdates", {"offset": 1}, 60)
    assert gesehen[1][1] == 60


def test_http_fehler_mit_wartezeit_ohne_token():
    koerper = io.BytesIO(json.dumps({"ok": False, "description": "Too Many Requests",
                                     "parameters": {"retry_after": 7}}).encode())
    fehler = urllib.error.HTTPError("https://api.telegram.org/bot123:geheim/x", 429, "x", {}, koerper)
    oeffne, _ = _oeffne(fehler=fehler)
    with pytest.raises(TelegramFehler) as e:
        telegram(TOKEN, oeffne=oeffne)("sendMessage", {})
    assert e.value.warten == 7 and "HTTP 429" in str(e.value) and "geheim" not in str(e.value)


@pytest.mark.parametrize("fehler", [urllib.error.URLError("dns"), TimeoutError(), OSError("weg")])
def test_netzfehler(fehler):
    oeffne, _ = _oeffne(fehler=fehler)
    with pytest.raises(TelegramFehler) as e:
        telegram(TOKEN, oeffne=oeffne)("getUpdates", {})
    assert e.value.warten is None and "geheim" not in str(e.value)


def test_ok_false():
    oeffne, _ = _oeffne({"ok": False, "description": "Bad Request: chat not found"})
    with pytest.raises(TelegramFehler, match="chat not found"):
        telegram(TOKEN, oeffne=oeffne)("sendMessage", {})


@pytest.mark.parametrize("fehler", [http.client.IncompleteRead(b""),
                                    http.client.InvalidURL("bot123:geheim/x"),
                                    http.client.BadStatusLine("x")])
def test_http_exception_wird_verpackt(fehler):
    oeffne, _ = _oeffne(fehler=fehler)
    with pytest.raises(TelegramFehler) as e:
        telegram(TOKEN, oeffne=oeffne)("getUpdates", {})
    assert e.value.warten is None and "geheim" not in str(e.value)


def test_http_fehler_mit_nicht_json_koerper():
    fehler = urllib.error.HTTPError("https://x", 502, "x", {}, io.BytesIO(b"<html>Bad Gateway</html>"))
    oeffne, _ = _oeffne(fehler=fehler)
    with pytest.raises(TelegramFehler, match="HTTP 502") as e:
        telegram(TOKEN, oeffne=oeffne)("sendMessage", {})
    assert e.value.warten is None


def test_http_fehler_mit_kaputtem_lesen():
    class Kaputt(io.BytesIO):
        def read(self, *a):
            raise http.client.IncompleteRead(b"")
    fehler = urllib.error.HTTPError("https://x", 500, "x", {}, Kaputt())
    oeffne, _ = _oeffne(fehler=fehler)
    with pytest.raises(TelegramFehler, match="HTTP 500"):
        telegram(TOKEN, oeffne=oeffne)("sendMessage", {})


def test_json_liste_als_antwort():
    oeffne, _ = _oeffne([1, 2])
    with pytest.raises(TelegramFehler, match="unerwartete Antwort"):
        telegram(TOKEN, oeffne=oeffne)("getUpdates", {})


def test_verbindung_nur_ipv4(monkeypatch):
    import socket
    from briefkasten import telegram as modul
    gefragt, verbunden = [], []
    monkeypatch.setattr(socket, "getaddrinfo",
                        lambda host, port, fam, typ: gefragt.append((host, port, fam)) or [(fam, typ, 6, "", ("1.2.3.4", port))])
    monkeypatch.setattr(socket, "create_connection", lambda ziel, timeout, quelle: verbunden.append(ziel) or "sock")
    assert modul.verbinde_ipv4(("api.telegram.org", 443), 5) == "sock"
    assert gefragt == [("api.telegram.org", 443, socket.AF_INET)] and verbunden == [("1.2.3.4", 443)]


def test_standard_oeffner_nutzt_ipv4():
    from briefkasten import telegram as modul
    import inspect
    assert inspect.signature(telegram).parameters["oeffne"].default is modul.oeffne_ipv4
    assert modul._HTTPSIPv4("api.telegram.org")._create_connection is modul.verbinde_ipv4
