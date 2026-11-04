"""Verbindung zum Briefkasten auf dem Server (Etappe 4): Beiträge anmelden, Entscheide und Nachrichten abholen.
Adresse und Lesestand stehen in daten/briefkasten.json. Fehlt die Datei, ist nicht umgestellt und der Mac fragt
Telegram selbst ab wie in Etappe 3. Der API-Schlüssel liegt im Schlüsselbund (Dienst <Präfix>-briefkasten, Standard fliessband-briefkasten)
und erscheint nie in Meldungen oder Logs."""
import fcntl
import functools
import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Callable

from lib.konfig import schluessel_dienst
from lib.manifest import schreibe_json
from lib.netzgrund import netzgrund

KONTO = "fliessband"   # so legt server/zugang.sh den Schlüssel an
DATEI = "briefkasten.json"
ENTSCHEIDE = ("freigegeben", "zurueckgenommen", "aendern", "verworfen", "verpasst", "gepostet", "ausgelassen")
ARTEN = {"entscheide": ENTSCHEIDE, "nachrichten": ("nachricht",)}
ZEITLIMIT = 20
ZEITLIMIT_ZAHLEN = 180   # GET /zahlen holt Insights je Beitrag bei Instagram, das dauert
MAX_GRUND = 500


class BriefkastenFehler(Exception):
    """code: HTTP-Code der Antwort oder None (nicht erreichbar, kaputte Antwort, Schlüssel fehlt)."""

    def __init__(self, text: str, code: int | None = None):
        super().__init__(text)
        self.code = code


@functools.lru_cache(maxsize=1)
def _schluessel() -> str:
    dienst = schluessel_dienst("briefkasten")
    r = subprocess.run(["security", "find-generic-password", "-s", dienst, "-a", KONTO, "-w"], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        raise BriefkastenFehler(f"API-Schlüssel fehlt im Schlüsselbund (Dienst {dienst})")
    return r.stdout.strip()


def http(adresse: str, schluessel: Callable[[], str] = _schluessel, oeffne=urllib.request.urlopen) -> Callable:
    """anfrage(methode, pfad, daten=None, zeitlimit=ZEITLIMIT) → JSON-Antwort des Briefkastens. Keine Wiederholungen,
    HTTP-Fehler (z.B. 401 falscher Schlüssel) werden als BriefkastenFehler gemeldet, ohne Schlüssel."""
    def anfrage(methode: str, pfad: str, daten: dict | None = None, zeitlimit: float = ZEITLIMIT):
        ohne_abfrage = pfad.split("?")[0]
        req = urllib.request.Request(
            adresse.rstrip("/") + pfad, method=methode,
            data=json.dumps(daten).encode("utf-8") if daten is not None else None,
            headers={"Authorization": f"Bearer {schluessel()}", "Content-Type": "application/json"})
        try:
            with oeffne(req, timeout=zeitlimit) as r:
                roh = r.read()
        except urllib.error.HTTPError as e:
            try:
                koerper = json.loads(e.read())
                grund = str(koerper.get("fehler", "")) if isinstance(koerper, dict) else ""
            except Exception:
                grund = ""
            raise BriefkastenFehler(f"Briefkasten {methode} {ohne_abfrage}: HTTP {e.code} {grund[:MAX_GRUND]}".strip(),
                                    code=e.code) from None
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise BriefkastenFehler(f"Briefkasten nicht erreichbar ({type(e).__name__}: {netzgrund(e)})") from None
        try:
            antwort = json.loads(roh or b"{}")
        except ValueError:
            antwort = None
        if not isinstance(antwort, dict):
            raise BriefkastenFehler(f"Briefkasten {methode} {ohne_abfrage}: unerwartete Antwort")
        return antwort
    return anfrage


class Briefkasten:
    def __init__(self, stand: Path, anfrage: Callable | None = None):
        self.stand = Path(stand)
        self._anfrage = anfrage

    @classmethod
    def lade(cls, daten: Path, anfrage: Callable | None = None) -> "Briefkasten | None":
        pfad = Path(daten) / DATEI
        return cls(pfad, anfrage) if pfad.exists() else None

    def _lade(self) -> dict:
        try:
            return json.loads(self.stand.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise BriefkastenFehler(f"{self.stand} ist kaputt oder fehlt") from None

    @property
    def anfrage(self) -> Callable:
        if self._anfrage is None:
            self._anfrage = http(self._lade()["adresse"])
        return self._anfrage

    def melde(self, beitrag: dict) -> dict:
        return self.anfrage("POST", "/beitraege", beitrag)

    def fertig(self, woche: str) -> None:
        self.anfrage("POST", f"/wochen/{urllib.parse.quote(woche, safe='')}/fertig", {})

    def fehler(self, id: str, grund: str) -> None:
        """Nicht automatisch wiederholen: Betreiber bekäme die Meldung sonst doppelt."""
        self.anfrage("POST", f"/beitraege/{urllib.parse.quote(id, safe='')}/fehler", {"grund": grund[:MAX_GRUND]})

    def medien(self, id: str, daten: dict) -> dict:
        """Adressen der hochgeladenen Dateien, Cover und Caption für die aktuelle Version (Etappe 5)."""
        return self.anfrage("POST", f"/beitraege/{urllib.parse.quote(id, safe='')}/medien", daten)

    def poster(self, an: bool) -> dict:
        return self.anfrage("POST", "/poster", {"an": an})

    def poster_stand(self) -> dict:
        return self.anfrage("GET", "/poster")

    def facebook(self, an: bool) -> dict:
        return self.anfrage("POST", "/facebook", {"an": an})

    def facebook_stand(self) -> dict:
        return self.anfrage("GET", "/facebook")

    def kommentare(self, an: bool) -> dict:
        """START-Kommentare in Telegram melden ein/aus (Etappe 9)."""
        return self.anfrage("POST", "/kommentare", {"an": an})

    def kommentare_stand(self) -> dict:
        return self.anfrage("GET", "/kommentare")

    def zahlen(self, tage: int = 28) -> list[dict]:
        """Instagram-Beiträge der letzten `tage` Tage mit Insights (Lern-Schleife, Etappe 6)."""
        return self.anfrage("GET", f"/zahlen?tage={tage}", zeitlimit=ZEITLIMIT_ZAHLEN)["beitraege"]

    def fragen_offen(self, bis: datetime) -> None:
        self.anfrage("POST", "/fragen", {"bis": bis.isoformat(timespec="minutes")})

    def ereignisse(self, art: str) -> list[dict]:
        """Neue Ereignisse seit dem letzten merke(art, …). art: 'entscheide' oder 'nachrichten'."""
        nach = self._lade().get(f"{art}_bis", 0)
        antwort = self.anfrage("GET", f"/ereignisse?nach={nach}&arten={','.join(ARTEN[art])}")
        return antwort["ereignisse"]

    def merke(self, art: str, nr: int) -> None:
        """Lesen, ändern, schreiben unter einer Dateisperre: Samstags-Bau und entscheide laufen evtl. gleichzeitig."""
        with open(self.stand.with_name(self.stand.name + ".sperre"), "a") as sperre:
            fcntl.flock(sperre, fcntl.LOCK_EX)
            try:
                stand = self._lade()
                stand[f"{art}_bis"] = max(nr, stand.get(f"{art}_bis", 0))
                schreibe_json(self.stand, stand)
            finally:
                fcntl.flock(sperre, fcntl.LOCK_UN)


def umstellen(daten: Path, adresse: str, bot, anfrage: Callable | None = None) -> int:
    """Einmalig: Der Mac holt ein letztes Mal bei Telegram ab, danach fragt nur noch der Server Telegram ab.
    Liefert die update_id, ab der der Server abfragt (er beginnt bei der nächsten). Meldet der Server eine
    andere update_id (war schon früher umgestellt), wird der Stand trotzdem geschrieben (der Server fragt
    Telegram schon ab, der Mac darf es nicht mehr) und laut mit BriefkastenFehler gewarnt."""
    pfad = Path(daten) / DATEI
    if pfad.exists():
        raise BriefkastenFehler("Schon umgestellt (daten/briefkasten.json besteht)")
    anfrage = anfrage or http(adresse)
    anfrage("GET", "/gesund")
    bot.sammle()
    gesendet = bot.letzte_update_id
    antwort = anfrage("POST", "/umstellen", {"update_id": gesendet})
    schreibe_json(pfad, {"adresse": adresse, "nachrichten_bis": 0, "entscheide_bis": 0})
    if antwort.get("update_id") != gesendet:
        raise BriefkastenFehler(
            f"Umgestellt, aber der Server fragt ab update_id {antwort.get('update_id')} statt {gesendet} ab "
            "(war schon umgestellt?). Nachrichten dazwischen können fehlen oder doppelt kommen, bitte prüfen.")
    return gesendet
