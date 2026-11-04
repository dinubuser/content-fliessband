"""Instagram-Login-API (graph.instagram.com) für den Poster. Der Schlüssel liegt in /var/lib/fliessband/instagram.json
({"token", "erstellt" (ISO-Datum), "user_id"}, Rechte 600), geht nur als Parameter an Instagram und erscheint nie
in Fehlern oder Logs. Verbindung nur über IPv4 (siehe briefkasten.telegram)."""
import http.client
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

from briefkasten.konto import stempel, summe
from briefkasten.telegram import oeffne_ipv4

API = "https://graph.instagram.com"
VERSION = "v26.0"
WARTEN = 5           # Sekunden zwischen zwei Abfragen des Container-Stands
MAX_WARTEN = 600     # höchstens 10 Minuten auf die Verarbeitung warten
ZEITLIMIT = 60
MAX_GRUND = 300
METRIKEN = ("views", "reach", "shares", "saved", "comments", "likes", "total_interactions")
METRIKEN_REEL = ("ig_reels_avg_watch_time", "reels_skip_rate")
MAX_SEITEN = 5       # 5 × 50 Beiträge reichen für 4 Wochen weit
MAX_KOMMENTAR_SEITEN = 10   # 10 × 50 Kommentare pro Beitrag


class InstagramFehler(Exception):
    def __init__(self, text: str, ungueltig: bool = False, netz: bool = False, berechtigung: bool = False):
        super().__init__(text)
        self.ungueltig = ungueltig         # Schlüssel fehlt, abgelaufen oder ungültig (Code 190)
        self.netz = netz                   # Instagram nicht erreichbar (kein HTTP-Fehler von Instagram)
        self.berechtigung = berechtigung   # Schlüssel ohne nötige Berechtigung (Code 10 oder 200 bis 299)


class Schluessel:
    def __init__(self, pfad):
        self.pfad = Path(pfad)

    def lade(self) -> dict:
        try:
            d = json.loads(self.pfad.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise InstagramFehler("Instagram-Schlüssel fehlt", ungueltig=True) from None
        if not isinstance(d, dict) or not all(d.get(k) for k in ("token", "erstellt", "user_id")):
            raise InstagramFehler("Instagram-Schlüssel unvollständig", ungueltig=True)
        return d

    def speichere(self, d: dict) -> None:
        neu = self.pfad.with_name(self.pfad.name + ".neu")
        fd = os.open(neu, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.chmod(neu, 0o600)
        os.replace(neu, self.pfad)

    def alter_tage(self, heute: date) -> int:
        return (heute - date.fromisoformat(str(self.lade()["erstellt"])[:10])).days


class Instagram:
    def __init__(self, schluessel: Schluessel, oeffne=oeffne_ipv4, schlafe=time.sleep, uhr=time.monotonic):
        self.schluessel, self.oeffne, self.schlafe, self.uhr = schluessel, oeffne, schlafe, uhr

    def _rufe(self, methode: str, pfad: str, felder: dict | None = None, mit_version: bool = True) -> dict:
        token = self.schluessel.lade()["token"]
        kodiert = urllib.parse.urlencode(dict(felder or {}, access_token=token))
        basis = f"{API}/{VERSION}" if mit_version else API
        if methode == "GET":
            req = urllib.request.Request(f"{basis}{pfad}?{kodiert}")
        else:
            req = urllib.request.Request(f"{basis}{pfad}", data=kodiert.encode(), method="POST")
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
            text = str(fehler.get("message", "")).replace(token, "…")[:MAX_GRUND]
            code = fehler.get("code")
            raise InstagramFehler(f"Instagram HTTP {e.code}: {text}".strip(), ungueltig=code == 190,
                                  berechtigung=isinstance(code, int) and (code == 10 or 200 <= code <= 299)) from None
        except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as e:
            raise InstagramFehler(f"Instagram nicht erreichbar ({type(e).__name__})", netz=True) from None
        if not isinstance(koerper, dict):
            raise InstagramFehler("Instagram: unerwartete Antwort")
        return koerper

    @staticmethod
    def _id(d: dict) -> str:
        if not d.get("id"):
            raise InstagramFehler("Instagram: Antwort ohne id")
        return str(d["id"])

    def _user(self) -> str:
        return str(self.schluessel.lade()["user_id"])

    def _warte(self, container: str) -> None:
        start = self.uhr()
        while True:
            d = self._rufe("GET", f"/{container}", {"fields": "status_code,status"})
            code = d.get("status_code")
            if code in ("FINISHED", "PUBLISHED"):
                return
            if code in ("ERROR", "EXPIRED"):
                grund = str(d.get("status", ""))[:MAX_GRUND]
                raise InstagramFehler(f"Instagram konnte die Datei nicht verarbeiten ({grund})")
            if self.uhr() - start >= MAX_WARTEN:
                raise InstagramFehler("Instagram hat die Datei nicht innert 10 Minuten verarbeitet")
            self.schlafe(WARTEN)

    def container_status(self, creation_id: str) -> str:
        """Stand eines Containers (FINISHED, PUBLISHED, IN_PROGRESS, ERROR, EXPIRED). Schutz vor Doppelposts:
        PUBLISHED heisst, der Beitrag ist schon online."""
        return str(self._rufe("GET", f"/{creation_id}", {"fields": "status_code"}).get("status_code") or "")

    def tagesgrenze_erreicht(self) -> bool:
        d = self._rufe("GET", f"/{self._user()}/content_publishing_limit", {"fields": "quota_usage,config"})
        eintrag = (d.get("data") or [{}])[0]
        gesamt = (eintrag.get("config") or {}).get("quota_total") or 0
        return bool(gesamt) and (eintrag.get("quota_usage") or 0) >= gesamt

    def bereite_vor(self, format: str, medien: list[str], cover: str | None, caption: str) -> str:
        """Container anlegen und warten, bis Instagram die Dateien verarbeitet hat. Liefert die creation_id."""
        u = self._user()
        if format == "karussell":
            kinder = [self._id(self._rufe("POST", f"/{u}/media", {"image_url": m, "is_carousel_item": "true"}))
                      for m in medien]
            for k in kinder:
                self._warte(k)
            container = self._id(self._rufe("POST", f"/{u}/media", {
                "media_type": "CAROUSEL", "children": ",".join(kinder), "caption": caption}))
        else:
            felder = {"media_type": "REELS", "video_url": medien[0]}
            if cover:
                felder["cover_url"] = cover
            felder.update(caption=caption, share_to_feed="true")
            container = self._id(self._rufe("POST", f"/{u}/media", felder))
        self._warte(container)
        return container

    def veroeffentliche(self, creation_id: str) -> dict:
        media = self._id(self._rufe("POST", f"/{self._user()}/media_publish", {"creation_id": creation_id}))
        try:
            link = self._rufe("GET", f"/{media}", {"fields": "permalink"}).get("permalink")
        except InstagramFehler:
            link = None   # online ist er trotzdem, nur der Link fehlt in der Meldung
        return {"instagram_id": media, "permalink": link}

    def letzte(self, anzahl: int = 10) -> list[dict]:
        d = self._rufe("GET", f"/{self._user()}/media", {"fields": "id,caption,timestamp,permalink", "limit": anzahl})
        return d.get("data") or []

    def medien_seit(self, grenze: datetime) -> list[dict]:
        """Beiträge des Accounts ab `grenze` (mit Zeitzone), neueste zuerst. Folgt den Seiten, bis ein Beitrag
        älter als die Grenze ist."""
        felder = {"fields": "id,caption,media_type,media_product_type,timestamp,permalink", "limit": 50}
        medien = []
        for _ in range(MAX_SEITEN):
            d = self._rufe("GET", f"/{self._user()}/media", felder)
            for m in d.get("data") or []:
                try:
                    zeit = datetime.strptime(str(m["timestamp"]), "%Y-%m-%dT%H:%M:%S%z")
                    m["id"]
                except (KeyError, TypeError, ValueError):
                    continue   # Eintrag ohne id oder gültigen Zeitstempel
                if zeit < grenze:
                    return medien
                medien.append(m)
            seiten = d.get("paging") or {}
            weiter = (seiten.get("cursors") or {}).get("after")
            if not weiter or not seiten.get("next"):
                return medien
            felder = dict(felder, after=weiter)
        return medien

    @staticmethod
    def _werte(d: dict) -> dict:
        werte = {}
        for e in d.get("data") or []:
            if not isinstance(e, dict) or not e.get("name"):
                continue
            erster = (e.get("values") or [None])[0]
            if e.get("values"):
                werte[e["name"]] = erster.get("value") if isinstance(erster, dict) else None
            else:
                gesamt = e.get("total_value")
                werte[e["name"]] = gesamt.get("value") if isinstance(gesamt, dict) else None
        return werte

    def zahlen(self, media_id: str, reel: bool) -> dict:
        """Insights eines Beitrags. Reel-Werte nur bei Reels. Scheitert der Sammelaufruf (z.B. eine Metrik fehlt
        für diesen Beitrag), wird jede Metrik einzeln geholt. Fehlende Werte: None. Ungültiger Schlüssel: wirft."""
        metriken = METRIKEN + (METRIKEN_REEL if reel else ())
        try:
            gefunden = self._werte(self._rufe("GET", f"/{media_id}/insights", {"metric": ",".join(metriken)}))
        except InstagramFehler as e:
            if e.ungueltig or e.netz:
                raise
            gefunden = {}
            for m in metriken:
                try:
                    gefunden.update(self._werte(self._rufe("GET", f"/{media_id}/insights", {"metric": m})))
                except InstagramFehler as einzel:
                    if einzel.ungueltig or einzel.netz:
                        raise
        return {m: gefunden.get(m) for m in metriken}

    def kommentare(self, media_id: str) -> list[dict]:
        """Kommentare direkt unter einem Beitrag (keine Antworten auf Kommentare), je {id, text, username, zeit}.
        Folgt den Seiten. Einträge ohne id fallen weg. Der Name steht mal unter username, mal unter from."""
        felder = {"fields": "id,text,username,from,timestamp", "limit": 50}
        liste = []
        # Bewusst nach MAX_KOMMENTAR_SEITEN Seiten abgeschnitten (neueste zuerst): ältere Kommentare sind längst gelesen.
        for _ in range(MAX_KOMMENTAR_SEITEN):
            d = self._rufe("GET", f"/{media_id}/comments", felder)
            for k in d.get("data") or []:
                if not isinstance(k, dict) or not k.get("id"):
                    continue
                von = k.get("from") if isinstance(k.get("from"), dict) else {}
                name = k.get("username") or von.get("username")
                liste.append({"id": str(k["id"]), "text": str(k.get("text") or ""),
                              "username": str(name) if name else None, "zeit": k.get("timestamp")})
            seiten = d.get("paging") or {}
            weiter = (seiten.get("cursors") or {}).get("after")
            if not weiter or not seiten.get("next"):
                return liste
            felder = dict(felder, after=weiter)
        return liste

    def eigener_name(self) -> str | None:
        """Name des eigenen Accounts (eigene Kommentare zählen nicht als START)."""
        name = self._rufe("GET", "/me", {"fields": "username"}).get("username")
        return str(name) if name else None

    def kommentare_lesbar(self) -> bool | None:
        """True: Kommentare des neuesten Beitrags lesbar. False: Berechtigung fehlt. None: noch kein Beitrag."""
        d = self._rufe("GET", f"/{self._user()}/media", {"fields": "id", "limit": 1})
        medien = [m for m in d.get("data") or [] if isinstance(m, dict) and m.get("id")]
        if not medien:
            return None
        try:
            self._rufe("GET", f"/{medien[0]['id']}/comments", {"fields": "id", "limit": 1})
        except InstagramFehler as e:
            if e.berechtigung:
                return False
            raise
        return True

    def pruefe(self, kommentare: bool = False) -> dict:
        """Täglicher Check: Ist der Schlüssel bei Instagram noch gültig und gehört er zum gespeicherten Konto
        (server/instagram.sh speichert die user_id derselben Abfrage)? Wirft InstagramFehler (ungültig bei Code 190
        oder anderem Konto). kommentare=True (Etappe 9): meldet zusätzlich, ob Kommentare lesbar sind."""
        user = self._rufe("GET", "/me", {"fields": "user_id"}).get("user_id")
        if not user:
            raise InstagramFehler("Instagram: Antwort ohne user_id")
        if str(user) != self._user():
            raise InstagramFehler("Schlüssel gehört zu einem anderen Konto", ungueltig=True)
        return {"kommentare": self.kommentare_lesbar()} if kommentare else {}

    def erneuere(self, heute: date) -> None:
        d = self.schluessel.lade()
        neu = self._rufe("GET", "/refresh_access_token", {"grant_type": "ig_refresh_token"}, mit_version=False)
        if not neu.get("access_token"):
            raise InstagramFehler("Instagram: kein neuer Schlüssel erhalten")
        self.schluessel.speichere(dict(d, token=neu["access_token"], erstellt=heute.isoformat()))

    def konto(self, tage: int, heute: date) -> dict:
        """Follower, Aufrufe der letzten 30 Tage und Aufrufe je Tag für die `tage` Tage vor heute (Social-Kacheln)."""
        user = self._user()
        profil = self._rufe("GET", f"/{user}", {"fields": "followers_count,username"})

        def aufrufe(von: date, bis: date):
            return summe(self._rufe("GET", f"/{user}/insights", {
                "metric": "views", "period": "day", "metric_type": "total_value",
                "since": stempel(von), "until": stempel(bis)}), "views")

        je_tag = {}
        for n in range(1, tage + 1):
            tag = heute - timedelta(days=n)
            wert = aufrufe(tag, tag + timedelta(days=1))
            if wert is not None:
                je_tag[tag.isoformat()] = wert
        return {"follower": profil.get("followers_count"),
                "aufrufe_30t": aufrufe(heute - timedelta(days=30), heute),
                "aufrufe_tage": je_tag,
                "link": f"https://www.instagram.com/{profil['username']}/" if profil.get("username") else None}
