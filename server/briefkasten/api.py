"""HTTP-Schnittstelle für den Mac. Nur über Tailscale erreichbar, jede Anfrage ausser /gesund braucht
«Authorization: Bearer <API_SCHLUESSEL>». Antworten sind JSON."""
import hmac
import json
import logging
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from briefkasten.instagram import InstagramFehler
from briefkasten.telegram import TelegramFehler

LOG = logging.getLogger("briefkasten.api")
MAX_KOERPER = 64 * 1024
MAX_ZAHL = 2**63 - 1   # SQLite-Ganzzahl
MAX_TAGE = 90


def _zahl(wert, name: str) -> int:
    if isinstance(wert, bool) or not isinstance(wert, int) or not 0 <= wert <= MAX_ZAHL:
        raise ValueError(f"{name}: ganze Zahl >= 0 erwartet")
    return wert


def _tage(wert: str) -> int:
    tage = int(wert)   # ValueError → 400
    if not 1 <= tage <= MAX_TAGE:
        raise ValueError(f"tage: 1 bis {MAX_TAGE} erwartet")
    return tage


def _zahlen(ablauf, abfrage: str) -> dict:
    return ablauf.poster.zahlen(_tage(parse_qs(abfrage).get("tage", ["28"])[0]))


def baue_server(ablauf, schluessel: str, adresse: tuple[str, int]) -> ThreadingHTTPServer:
    if not schluessel:
        raise ValueError("API_SCHLUESSEL fehlt")
    erwartet = f"Bearer {schluessel}".encode()

    class Handler(BaseHTTPRequestHandler):
        timeout = 30   # hängende Verbindungen blockieren keinen Thread ewig

        def log_message(self, *args):
            pass   # keine Zugriffszeilen im Journal

        def _antworte(self, code: int, daten) -> None:
            roh = json.dumps(daten, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(roh)))
            self.end_headers()
            self.wfile.write(roh)

        def _erlaubt(self) -> bool:
            return hmac.compare_digest(self.headers.get("Authorization", "").encode(), erwartet)

        def _koerper(self) -> dict:
            laenge = int(self.headers.get("Content-Length") or 0)
            if laenge < 0 or laenge > MAX_KOERPER:
                raise ValueError("Länge der Anfrage ungültig")
            daten = json.loads(self.rfile.read(laenge) or b"{}")
            if not isinstance(daten, dict):
                raise ValueError("JSON-Objekt erwartet")
            return daten

        def _fuehre(self, arbeit) -> None:
            try:
                self._antworte(200, arbeit())
            except (ValueError, KeyError, TypeError) as e:
                self._antworte(400, {"fehler": str(e)})
            except TelegramFehler as e:
                self._antworte(502, {"fehler": str(e)})
            except InstagramFehler as e:
                self._antworte(503 if e.ungueltig else 502, {"fehler": str(e)})
            except Exception as e:   # nie Traceback oder Details an den Mac (Token-Schutz)
                LOG.error("Interner Fehler: %s", type(e).__name__)
                self._antworte(500, {"fehler": "interner Fehler"})

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/gesund":
                return self._antworte(200, {"ok": True})
            if not self._erlaubt():
                return self._antworte(401, {"fehler": "Schlüssel fehlt oder falsch"})
            if url.path == "/ereignisse":
                q = parse_qs(url.query)
                return self._fuehre(lambda: {"ereignisse": ablauf.ereignisse(
                    _zahl(int(q.get("nach", ["0"])[0]), "nach"), q.get("arten", [""])[0].split(","))})
            if url.path == "/poster" and ablauf.poster is not None:
                return self._fuehre(ablauf.poster.stand)
            if url.path == "/facebook" and ablauf.poster is not None:
                return self._fuehre(ablauf.poster.fb_stand)
            if url.path == "/zahlen" and ablauf.poster is not None:
                return self._fuehre(lambda: _zahlen(ablauf, url.query))
            if url.path == "/kommentare" and ablauf.kommentare is not None:
                return self._fuehre(ablauf.kommentare.stand)
            self._antworte(404, {"fehler": "unbekannte Adresse"})

        def do_POST(self):
            if not self._erlaubt():
                return self._antworte(401, {"fehler": "Schlüssel fehlt oder falsch"})
            teile = [unquote(t) for t in urlparse(self.path).path.strip("/").split("/")]
            if teile == ["beitraege"]:
                return self._fuehre(lambda: ablauf.melde_beitrag(self._koerper()))
            if len(teile) == 3 and teile[0] == "wochen" and teile[2] == "fertig":
                return self._fuehre(lambda: ablauf.woche_fertig(teile[1]) or {"ok": True})
            if len(teile) == 3 and teile[0] == "beitraege" and teile[2] == "fehler":
                return self._fuehre(lambda: ablauf.neubau_gescheitert(teile[1], str(self._koerper()["grund"]))
                                    or {"ok": True})
            if teile == ["fragen"]:
                return self._fuehre(lambda: ablauf.fragen_offen(str(self._koerper()["bis"])) or {"ok": True})
            if len(teile) == 3 and teile[0] == "beitraege" and teile[2] == "medien" and ablauf.poster is not None:
                return self._fuehre(lambda: ablauf.poster.medien(teile[1], self._koerper()))
            if teile == ["kommentare"] and ablauf.kommentare is not None:
                return self._fuehre(lambda: ablauf.kommentare.schalter(self._koerper()["an"]))
            if teile == ["poster"] and ablauf.poster is not None:
                return self._fuehre(lambda: ablauf.poster.schalter(self._koerper()["an"]))
            if teile == ["facebook"] and ablauf.poster is not None:
                return self._fuehre(lambda: ablauf.poster.fb_schalter(self._koerper()["an"]))
            if teile == ["umstellen"]:
                return self._fuehre(lambda: {"update_id": ablauf.umstellen(_zahl(self._koerper()["update_id"], "update_id"))})
            self._antworte(404, {"fehler": "unbekannte Adresse"})

    class Server(ThreadingHTTPServer):
        def handle_error(self, request, client_address):
            LOG.error("Verbindungsfehler: %s", type(sys.exc_info()[1]).__name__)   # kein Traceback

    return Server(adresse, Handler)
