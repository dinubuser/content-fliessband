"""Telegram-Bot-API für den Briefkasten (JSON über urllib). Der Token steht nur in der URL und erscheint nie
in einer Fehlermeldung."""
import http.client
import json
import socket
import urllib.error
import urllib.request

API = "https://api.telegram.org"


class TelegramFehler(Exception):
    def __init__(self, text: str, warten: float | None = None):
        super().__init__(text)
        self.warten = warten


def verbinde_ipv4(adresse, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None):
    """Nur IPv4: Auf dem Server ist IPv6 nach aussen tot, jeder Versuch hängt bis zum Zeitlimit."""
    host, port = adresse
    ziel = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)[0][4]
    return socket.create_connection(ziel, timeout, source_address)


class _HTTPSIPv4(http.client.HTTPSConnection):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._create_connection = verbinde_ipv4


class _HTTPSHandlerIPv4(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_HTTPSIPv4, req, context=self._context)


oeffne_ipv4 = urllib.request.build_opener(_HTTPSHandlerIPv4()).open


def telegram(token: str, oeffne=oeffne_ipv4):
    """Liefert anfrage(methode, felder, zeitlimit=30) → result."""
    def anfrage(methode: str, felder: dict, zeitlimit: int = 30):
        req = urllib.request.Request(f"{API}/bot{token}/{methode}", data=json.dumps(felder).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        try:
            with oeffne(req, timeout=zeitlimit) as r:
                koerper = json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                koerper = json.loads(e.read())
            except (ValueError, OSError, http.client.HTTPException):
                koerper = {}
            if not isinstance(koerper, dict):
                koerper = {}
            parameter = koerper.get("parameters")
            warten = parameter.get("retry_after") if isinstance(parameter, dict) else None
            text = f"Telegram {methode}: HTTP {e.code} {koerper.get('description', '')}".strip()
            raise TelegramFehler(text, warten) from None
        except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as e:
            raise TelegramFehler(f"Telegram {methode}: nicht erreichbar ({type(e).__name__})") from None
        if not isinstance(koerper, dict):
            raise TelegramFehler(f"Telegram {methode}: unerwartete Antwort")
        if not koerper.get("ok"):
            raise TelegramFehler(f"Telegram {methode}: {koerper.get('description', 'unbekannter Fehler')}")
        return koerper["result"]
    return anfrage
