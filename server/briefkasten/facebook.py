"""Facebook-Seite (graph.facebook.com) für den Poster (Facebook-Zusatz). Der Seiten-Schlüssel liegt in
/var/lib/fliessband/facebook.json ({"token", "page_id", "erstellt" (ISO-Datum)}, Rechte 600), geht nur als Parameter
oder Kopfzeile an Meta und erscheint nie in Fehlern oder Logs. Verbindung nur über IPv4 (siehe briefkasten.telegram).
Karussell: Bilder unveröffentlicht hochladen, dann ein Beitrag mit allen Bildern. Reel: Start, Datei selbst
hochladen, Fertig, dann Stand abfragen."""
import http.client
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from briefkasten.telegram import oeffne_ipv4

API = "https://graph.facebook.com"
RUPLOAD = "https://rupload.facebook.com/video-upload"
VERSION = "v26.0"
SEITE = "https://www.facebook.com"
WARTEN = 5           # Sekunden zwischen zwei Abfragen des Reel-Stands
MAX_WARTEN = 600     # höchstens 10 Minuten auf die Verarbeitung warten
ZEITLIMIT = 60
DOWNLOAD_ZEITLIMIT = 120
MAX_VIDEO = 1024 ** 3   # 1 GB
MAX_GRUND = 300


class FacebookFehler(Exception):
    def __init__(self, text: str, ungueltig: bool = False):
        super().__init__(text)
        self.ungueltig = ungueltig   # Schlüssel fehlt, abgelaufen oder ungültig (Code 190)


class FbSchluessel:
    def __init__(self, pfad):
        self.pfad = Path(pfad)

    def lade(self) -> dict:
        try:
            d = json.loads(self.pfad.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise FacebookFehler("Facebook-Schlüssel fehlt", ungueltig=True) from None
        if not isinstance(d, dict) or not all(isinstance(d.get(k), str) and d.get(k)
                                              for k in ("token", "page_id", "erstellt")):
            raise FacebookFehler("Facebook-Schlüssel unvollständig", ungueltig=True)
        return d

    def da(self) -> bool:
        try:
            self.lade()
            return True
        except FacebookFehler:
            return False


def _link(u) -> str | None:
    """Facebook liefert bei Videos oft einen Pfad ohne Domain ('/reel/123/')."""
    if not isinstance(u, str) or not u:
        return None
    return SEITE + u if u.startswith("/") else u


class Facebook:
    def __init__(self, schluessel: FbSchluessel, oeffne=oeffne_ipv4, schlafe=time.sleep, uhr=time.monotonic):
        self.schluessel, self.oeffne, self.schlafe, self.uhr = schluessel, oeffne, schlafe, uhr

    def _oeffne_json(self, req, token: str) -> dict:
        try:
            with self.oeffne(req, timeout=ZEITLIMIT) as r:
                koerper = json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                koerper = json.loads(e.read())
            except (ValueError, OSError, http.client.HTTPException):
                koerper = {}
            fehler = koerper.get("error") if isinstance(koerper, dict) else None
            fehler = fehler if isinstance(fehler, dict) else {}
            debug = koerper.get("debug_info") if isinstance(koerper, dict) else None
            debug = debug if isinstance(debug, dict) else {}
            text = str(fehler.get("message") or fehler.get("error_user_msg") or debug.get("message") or "")
            text = text.replace(token, "…")[:MAX_GRUND]
            raise FacebookFehler(f"Facebook HTTP {e.code}: {text}".strip(),
                                 ungueltig=fehler.get("code") == 190) from None
        except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as e:
            raise FacebookFehler(f"Facebook nicht erreichbar ({type(e).__name__})") from None
        if not isinstance(koerper, dict):
            raise FacebookFehler("Facebook: unerwartete Antwort")
        return koerper

    def _rufe(self, methode: str, pfad: str, felder: dict | None = None) -> dict:
        token = self.schluessel.lade()["token"]
        kodiert = urllib.parse.urlencode(dict(felder or {}, access_token=token))
        if methode == "GET":
            req = urllib.request.Request(f"{API}/{VERSION}{pfad}?{kodiert}")
        else:
            req = urllib.request.Request(f"{API}/{VERSION}{pfad}", data=kodiert.encode(), method="POST")
        return self._oeffne_json(req, token)

    def _seite(self) -> str:
        return self.schluessel.lade()["page_id"]

    @staticmethod
    def _id(d: dict, feld: str = "id") -> str:
        if not d.get(feld):
            raise FacebookFehler(f"Facebook: Antwort ohne {feld}")
        return str(d[feld])

    def starte_reel(self) -> str:
        """Reel anmelden. Liefert die video_id (gleich speichern: Schutz vor einem zweiten Upload)."""
        return self._id(self._rufe("POST", f"/{self._seite()}/video_reels", {"upload_phase": "start"}), "video_id")

    def link(self, objekt_id: str) -> str | None:
        """Öffentlicher Link. Fehlt er, ist der Beitrag trotzdem online: dann None."""
        try:
            return _link(self._rufe("GET", f"/{objekt_id}", {"fields": "permalink_url"}).get("permalink_url"))
        except FacebookFehler:
            return None

    def poste_karussell(self, medien: list[str], caption: str) -> dict:
        s = self._seite()
        fotos = [self._id(self._rufe("POST", f"/{s}/photos", {"url": m, "published": "false"})) for m in medien]
        felder = {"message": caption}
        for i, foto in enumerate(fotos):
            felder[f"attached_media[{i}]"] = json.dumps({"media_fbid": foto})
        post = self._id(self._rufe("POST", f"/{s}/feed", felder))
        return {"id": post, "link": self.link(post)}

    def schon_gepostet(self, caption: str, seit: datetime) -> dict | None:
        """Doppelpost-Schutz: unter den letzten 10 Beiträgen der Seite einen mit gleichem Text ab seit suchen."""
        if seit.tzinfo is None:
            raise ValueError("seit braucht eine Zeitzone")
        d = self._rufe("GET", f"/{self._seite()}/published_posts",
                       {"fields": "id,message,created_time,permalink_url", "limit": 10})
        for m in d.get("data") or []:
            if not m.get("id"):
                continue
            try:
                zeit = datetime.strptime(m.get("created_time", ""), "%Y-%m-%dT%H:%M:%S%z")
            except ValueError:
                continue
            if (m.get("message") or "").strip() == (caption or "").strip() and zeit >= seit:
                return {"id": str(m["id"]), "link": _link(m.get("permalink_url"))}
        return None

    def lade_reel(self, video_id: str, video_url: str) -> None:
        """Der Server lädt die Datei selbst, weil example.com den Abholer von Facebook sperrt: erst von der
        Adresse herunterladen (höchstens MAX_VIDEO), dann die Bytes zu Facebook hochladen."""
        token = self.schluessel.lade()["token"]
        try:
            with self.oeffne(urllib.request.Request(video_url), timeout=DOWNLOAD_ZEITLIMIT) as r:
                daten = r.read(MAX_VIDEO + 1)
        except urllib.error.HTTPError as e:
            raise FacebookFehler(f"Video nicht abrufbar (HTTP {e.code})") from None
        except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as e:
            raise FacebookFehler(f"Video nicht abrufbar ({type(e).__name__})") from None
        if len(daten) > MAX_VIDEO:
            raise FacebookFehler("Video nicht abrufbar (über 1 GB)")
        req = urllib.request.Request(f"{RUPLOAD}/{VERSION}/{video_id}", data=daten, method="POST", headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(len(daten)),
            "Content-Type": "application/octet-stream"})
        if not self._oeffne_json(req, token).get("success"):
            raise FacebookFehler("Facebook hat das Video nicht angenommen")

    def beende_reel(self, video_id: str, caption: str) -> None:
        d = self._rufe("POST", f"/{self._seite()}/video_reels", {
            "upload_phase": "finish", "video_id": video_id, "video_state": "PUBLISHED", "description": caption})
        if not d.get("success"):
            raise FacebookFehler("Facebook hat das Reel nicht veröffentlicht")

    def _reel_status(self, video_id: str) -> tuple[str, str]:
        """(Stand, Grund): Stand wie bei reel_stand, Grund = Fehlermeldung von Facebook (sonst leer, ohne Token)."""
        st = self._rufe("GET", f"/{video_id}", {"fields": "status"}).get("status") or {}
        phasen = [st.get(k) if isinstance(st.get(k), dict) else {}
                  for k in ("uploading_phase", "processing_phase", "publishing_phase")]
        for ph in phasen:
            if ph.get("status") == "error" or ph.get("error"):
                fehler = ph.get("error")
                grund = str(fehler.get("message", "") if isinstance(fehler, dict) else fehler or "")
                token = self.schluessel.lade()["token"]
                return "fehler", grund.replace(token, "…")[:MAX_GRUND]
        if str(st.get("video_status") or "") == "error":
            return "fehler", ""
        publish = str(phasen[2].get("status") or "")
        if publish == "complete":
            return "fertig", ""
        if publish == "in_progress":
            return "laeuft", ""
        return "offen", ""

    def reel_stand(self, video_id: str) -> str:
        """fertig (veröffentlicht), laeuft (wird veröffentlicht), fehler (auch Fehler beim Hochladen oder
        Verarbeiten), offen (Veröffentlichen nicht angestossen oder Video noch in Verarbeitung)."""
        return self._reel_status(video_id)[0]

    def warte_reel(self, video_id: str) -> None:
        """Nach beende_reel: warten, bis das Reel veröffentlicht ist (alle 5 s, höchstens 10 Minuten)."""
        start = self.uhr()
        while True:
            stand, grund = self._reel_status(video_id)
            if stand == "fertig":
                return
            if stand == "fehler":
                raise FacebookFehler("Facebook konnte das Video nicht verarbeiten" + (f" ({grund})" if grund else ""))
            if self.uhr() - start >= MAX_WARTEN:
                raise FacebookFehler("Facebook hat das Reel nicht innert 10 Minuten veröffentlicht")
            self.schlafe(WARTEN)
