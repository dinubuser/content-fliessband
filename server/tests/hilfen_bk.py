"""Hilfen für die Server-Tests: falsches Telegram, Uhr, Beiträge, Knopfdrücke, Textnachrichten."""
import io
import json
import urllib.error
import urllib.parse

from briefkasten.facebook import FacebookFehler
from briefkasten.telegram import TelegramFehler

MEDIEN = {"version": 1, "medien": ["https://example.com/wp-content/uploads/2026/10/v.mp4"],
          "cover": "https://example.com/wp-content/uploads/2026/10/c.jpg", "caption": "Caption 1"}
TERMINE = {1: "2026-10-27T19:00", 2: "2026-10-28T19:00", 3: "2026-10-29T19:00", 4: "2026-10-31T19:00"}


class FalschesTelegram:
    """aufrufe: (methode, felder). updates: Inhalt für getUpdates. scheitern_bei: Methode, die scheitert."""

    def __init__(self):
        self.aufrufe, self.updates, self.scheitern_bei, self._id = [], [], None, 500

    def __call__(self, methode, felder, zeitlimit=30):
        if methode == self.scheitern_bei:
            raise TelegramFehler(f"Telegram {methode}: nicht erreichbar")
        self.aufrufe.append((methode, felder))
        if methode == "getUpdates":
            return [u for u in self.updates if u["update_id"] >= felder["offset"]]
        if methode == "sendMessage":
            self._id += 1
            return {"message_id": self._id}
        return True

    def methoden(self):
        return [m for m, _ in self.aufrufe]

    def gesendet(self):
        return [f["text"] for m, f in self.aufrufe if m == "sendMessage"]

    def bearbeitet(self):
        return [f for m, f in self.aufrufe if m == "editMessageText"]

    def antworten(self):
        return [f["text"] for m, f in self.aufrufe if m == "answerCallbackQuery"]


class Uhr:
    def __init__(self, zeit):
        self.zeit = zeit

    def __call__(self):
        return self.zeit


def daten(nr=1, **ueber):
    d = {"id": f"2026-KW44-thema-{nr}", "woche": "2026-KW44", "version": 1, "titel": f"Thema {nr}",
         "format": "reel" if nr in (1, 3) else "karussell", "termin": TERMINE[nr], "neubauten": 0}
    d.update(ueber)
    return d


def knopf(b, art, update_id=10, chat=42, version=None):
    return {"update_id": update_id, "callback_query": {
        "id": f"q{update_id}", "data": f"{art}:{b['nr']}:{b['version'] if version is None else version}",
        "message": {"message_id": b["nachricht_id"], "chat": {"id": chat}}}}


def woche_knopf(art, woche="2026-KW44", update_id=10):
    return {"update_id": update_id, "callback_query": {
        "id": f"q{update_id}", "data": f"{art}:{woche}", "message": {"message_id": 1, "chat": {"id": 42}}}}


def text(t, update_id=20, antwort_auf=None, chat=42):
    m = {"message_id": 1000 + update_id, "chat": {"id": chat, "type": "private"}, "text": t}
    if antwort_auf is not None:
        m["reply_to_message"] = {"message_id": antwort_auf}
    return {"update_id": update_id, "message": m}


class Antworten:
    """Ersatz für den urllib-Öffner: antworten = Liste von dict (HTTP 200) oder (code, dict) für HTTPError.
    anfragen: (methode, pfad, felder ohne access_token)."""

    def __init__(self, *antworten):
        self.antworten, self.anfragen = list(antworten), []

    def __call__(self, req, timeout=None):
        url = urllib.parse.urlsplit(req.full_url)
        felder = dict(urllib.parse.parse_qsl(req.data.decode() if req.data else url.query))
        felder.pop("access_token", None)
        self.anfragen.append((req.get_method(), url.path, felder))
        a = self.antworten.pop(0)
        if isinstance(a, tuple):
            code, koerper = a
            raise urllib.error.HTTPError(req.full_url, code, "Fehler", {}, io.BytesIO(json.dumps(koerper).encode()))
        return io.BytesIO(json.dumps(a).encode())


class FalschesInstagram:
    """Ersatz für briefkasten.instagram.Instagram im Poster. fehler: Ausnahmen, die die nächsten Aufrufe von
    bereite_vor werfen (wird abgebaut). veroeffentlichen_fehler: dasselbe für veroeffentliche.
    letzte_liste: Ergebnis von letzte(). grenze: Tagesgrenze erreicht. aufrufe: (methode, argumente).
    status: Container-Stand pro creation_id (bereite_vor setzt FINISHED, veroeffentliche PUBLISHED, unbekannt
    EXPIRED). status_fehler: Ausnahmen, die die nächsten Aufrufe von container_status werfen.
    pruefe_fehler: dasselbe für pruefe (täglicher Schlüssel-Check). medien_liste: Ergebnis von medien_seit.
    werte: Insights pro media_id. zahlen_fehler: Ausnahmen, die die nächsten Aufrufe von medien_seit werfen.
    werte_fehler: Ausnahme pro media_id, die zahlen() wirft.
    kommentar_liste: Ergebnis von kommentare() pro media_id. kommentar_fehler: Ausnahmen, die die nächsten Aufrufe
    von kommentare werfen. eigener: Ergebnis von eigener_name()."""

    def __init__(self, schluessel=None):
        self.aufrufe, self.fehler, self.veroeffentlichen_fehler, self.letzte_liste = [], [], [], []
        self.grenze, self._n, self.schluessel = False, 0, schluessel
        self.status, self.status_fehler, self.pruefe_fehler = {}, [], []
        self.medien_liste, self.werte, self.zahlen_fehler, self.werte_fehler = [], {}, [], {}
        self.kommentar_liste, self.kommentar_fehler, self.eigener = {}, [], "example.com"

    def medien_seit(self, grenze):
        assert grenze.tzinfo is not None
        self.aufrufe.append(("medien_seit", (grenze,)))
        if self.zahlen_fehler:
            raise self.zahlen_fehler.pop(0)
        return self.medien_liste

    def zahlen(self, media_id, reel):
        self.aufrufe.append(("zahlen", (media_id, reel)))
        if media_id in self.werte_fehler:
            raise self.werte_fehler[media_id]
        return self.werte.get(media_id, {})

    def kommentare(self, media_id):
        self.aufrufe.append(("kommentare", (media_id,)))
        if self.kommentar_fehler:
            raise self.kommentar_fehler.pop(0)
        return [dict(k) for k in self.kommentar_liste.get(media_id, [])]

    def eigener_name(self):
        self.aufrufe.append(("eigener_name", ()))
        return self.eigener

    def pruefe(self):
        self.aufrufe.append(("pruefe", ()))
        if self.pruefe_fehler:
            raise self.pruefe_fehler.pop(0)

    def tagesgrenze_erreicht(self):
        self.aufrufe.append(("tagesgrenze", ()))
        return self.grenze

    def bereite_vor(self, format, medien, cover, caption):
        self.aufrufe.append(("bereite_vor", (format, tuple(medien), cover, caption)))
        if self.fehler:
            raise self.fehler.pop(0)
        self._n += 1
        self.status[f"c{self._n}"] = "FINISHED"
        return f"c{self._n}"

    def container_status(self, creation_id):
        self.aufrufe.append(("container_status", (creation_id,)))
        if self.status_fehler:
            raise self.status_fehler.pop(0)
        return self.status.get(creation_id, "EXPIRED")

    def veroeffentliche(self, creation_id):
        self.aufrufe.append(("veroeffentliche", (creation_id,)))
        if self.veroeffentlichen_fehler:
            raise self.veroeffentlichen_fehler.pop(0)
        self.status[creation_id] = "PUBLISHED"
        return {"instagram_id": f"m-{creation_id}", "permalink": f"https://www.instagram.com/p/{creation_id}/"}

    def letzte(self, anzahl=10):
        self.aufrufe.append(("letzte", (anzahl,)))
        return self.letzte_liste

    konto_werte = {"follower": 412, "aufrufe_30t": 4812, "aufrufe_tage": {}, "link": "https://www.instagram.com/dein.konto/"}
    konto_fehler = None

    def konto(self, tage, heute):
        self.aufrufe.append(("konto", (tage, heute)))
        if self.konto_fehler:
            raise self.konto_fehler
        return dict(self.konto_werte)

    def methoden(self):
        return [m for m, _ in self.aufrufe]


class FalschesFacebook:
    """Ersatz für briefkasten.facebook.Facebook im Poster. fehler: Ausnahmen, die die nächsten Aufrufe von
    poste_karussell bzw. starte_reel werfen (wird abgebaut), beende_fehler: dasselbe für beende_reel. stand: reel_stand pro video_id (starte_reel setzt
    «offen», beende_reel «fertig», unbekannt «fehler»). treffer: Ergebnis von schon_gepostet.
    aufrufe: (methode, argumente)."""

    class _Schluessel:
        def __init__(self):
            self.vorhanden = True

        def da(self):
            return self.vorhanden

    def __init__(self):
        self.aufrufe, self.fehler, self.stand, self.treffer, self._n = [], [], {}, None, 0
        self.beende_fehler = []
        self.schluessel = self._Schluessel()

    def _fehler(self):
        if self.fehler:
            raise self.fehler.pop(0)

    def schon_gepostet(self, caption, seit):
        assert seit.tzinfo is not None
        self.aufrufe.append(("schon_gepostet", (caption,)))
        return self.treffer

    def poste_karussell(self, medien, caption):
        self.aufrufe.append(("poste_karussell", (tuple(medien), caption)))
        self._fehler()
        self._n += 1
        return {"id": f"fb{self._n}", "link": f"https://www.facebook.com/fb{self._n}"}

    def starte_reel(self):
        self.aufrufe.append(("starte_reel", ()))
        self._fehler()
        self._n += 1
        self.stand[f"v{self._n}"] = "offen"
        return f"v{self._n}"

    def lade_reel(self, video_id, video_url):
        self.aufrufe.append(("lade_reel", (video_id, video_url)))

    def beende_reel(self, video_id, caption):
        self.aufrufe.append(("beende_reel", (video_id, caption)))
        if self.beende_fehler:   # Facebook hat evtl. angenommen, die Antwort kam aber nie an: Stand bleibt «offen»
            raise self.beende_fehler.pop(0)
        self.stand[video_id] = "fertig"

    def reel_stand(self, video_id):
        self.aufrufe.append(("reel_stand", (video_id,)))
        return self.stand.get(video_id, "fehler")

    def warte_reel(self, video_id):
        self.aufrufe.append(("warte_reel", (video_id,)))
        if self.stand.get(video_id) != "fertig":
            raise FacebookFehler("Facebook hat das Reel nicht innert 10 Minuten veröffentlicht")

    def link(self, video_id):
        return f"https://www.facebook.com/reel/{video_id}"

    konto_werte = {"follower": 156, "aufrufe_30t": 2140, "aufrufe_tage": {}, "link": "https://www.facebook.com/dein.konto"}

    def konto(self, tage, heute):
        self.aufrufe.append(("konto", (tage, heute)))
        return dict(self.konto_werte)

    def methoden(self):
        return [m for m, _ in self.aufrufe]
