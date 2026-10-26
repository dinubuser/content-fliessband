"""Etappe 9: START-Kommentare unter den eigenen Instagram-Beiträgen finden und Betreiber in Telegram melden.
Der Dienst ruft runde() alle 5 Minuten in einem eigenen Thread auf. Gelesen werden die Beiträge der letzten
14 Tage. Jeder Kommentar wird einmal gespeichert (Tabelle kommentare), jeder START-Kommentar einmal gemeldet.
Der erste Lauf nach dem allerersten Einschalten speichert nur (kein Schwall alter Meldungen). Eigene Kommentare
zählen nicht. Ein Fehler bricht nur die Runde ab. Fehlt die Berechtigung oder ist der Schlüssel ungültig, kommt
höchstens einmal pro Tag ein Hinweis. Kein automatisches Antworten, keine Direktnachrichten."""
import logging
import re
from datetime import timedelta

from briefkasten import texte
from briefkasten.instagram import InstagramFehler
from briefkasten.telegram import TelegramFehler

LOG = logging.getLogger("briefkasten.kommentare")
START = re.compile(r"\bstart\b", re.IGNORECASE)
TAGE = 14              # Beiträge der letzten 14 Tage
MAX_MELDUNGEN = 20     # pro Runde, der Rest folgt in der nächsten
MAX_TITEL = 40         # Zeichen Caption als Titel, wenn der Beitrag nicht vom Fliessband stammt
ART = {"REELS": "Reel", "CAROUSEL_ALBUM": "Karussell"}


def ist_start(text) -> bool:
    """START in jeder Schreibweise als ganzes Wort, Satzzeichen und Emojis egal.
    Neustart, gestartet, Startup und Restart zählen nicht."""
    return isinstance(text, str) and bool(START.search(text))


def _art_und_titel(m: dict | None) -> tuple[str, str]:
    """Ohne Beitrag im Briefkasten: Art aus Instagram, Titel = erste 40 Zeichen der Caption."""
    if m is None:
        return "Beitrag", "unbekannter Beitrag"
    art = ART.get(m.get("media_product_type")) or ART.get(m.get("media_type")) or "Beitrag"
    caption = " ".join(str(m.get("caption") or "").split())
    return art, caption[:MAX_TITEL] or "ohne Caption"


class Kommentare:
    def __init__(self, ablauf, instagram):
        self.a, self.ig, self.s = ablauf, instagram, ablauf.s
        self._eigener = None   # eigener Instagram-Name, einmal pro Dienststart geholt
        ablauf.kommentare = self

    def _an(self) -> bool:
        return bool(self.s.lies("kommentare_an", False))

    # --- Schalter und Stand (Mac: fliessband kommentare ein|aus|status) ---

    def schalter(self, an: bool) -> dict:
        if not isinstance(an, bool):
            raise ValueError("an muss true oder false sein")
        with self.a.sperre:
            self.s.schreibe("kommentare_an", an)
            if an and self.s.lies("kommentare_seit") is None:
                # Allererstes Einschalten: die nächste gelungene Runde speichert die vorhandenen Kommentare nur
                self.s.schreibe("kommentare_seit", self.a._zeit())
                self.s.schreibe("kommentare_still", True)
        return self.stand()

    def stand(self) -> dict:
        with self.a.sperre:
            return {"an": self._an(), "seit": self.s.lies("kommentare_seit"), **self.s.kommentar_zahlen(), "abgelehnt": self.s.abgelehnt_anzahl(),
                    "letzte_runde": self.s.lies("kommentare_runde"), "problem": self.s.lies("kommentare_problem")}

    # --- Runde (alle 5 Minuten) ---

    def runde(self) -> None:
        """Instagram und Telegram ohne Sperre, die Datenbank nur kurz unter der Sperre. Ein Instagram-Fehler
        bricht nur diese Runde ab: nichts gespeichert, die nächste Runde versucht es neu."""
        with self.a.sperre:
            if not self._an():
                return
        try:
            medien, gefunden = self._lies()
        except InstagramFehler as e:
            LOG.warning("Kommentare nicht gelesen: %s", str(e))
            with self.a.sperre:
                self.s.schreibe("kommentare_problem", str(e))
            if e.ungueltig or e.berechtigung:
                self._hinweis(str(e))
            return
        with self.a.sperre:
            if not self._an():   # zwischen Prüfung und Speichern ausgeschaltet
                return
            self._speichere(gefunden)
            self.s.schreibe("kommentare_runde", self.a._zeit())
            self.s.schreibe("kommentare_problem", None)
            offen = [(k, *self._titel(k["media_id"], medien)) for k in self.s.zu_melden()[:MAX_MELDUNGEN]]
        self._melde(offen)

    def _lies(self) -> tuple[dict, list]:
        if not self._eigener:   # leer oder unbekannt wird nicht gemerkt, nächste Runde fragt neu
            self._eigener = (self.ig.eigener_name() or "").lower()
        medien = self.ig.medien_seit(self.a.jetzt() - timedelta(days=TAGE))
        gefunden = []
        for m in medien:
            try:
                gefunden += [(str(m["id"]), k) for k in self.ig.kommentare(str(m["id"]))]
            except InstagramFehler as e:
                if e.ungueltig or e.berechtigung or e.netz:
                    raise
                LOG.warning("Kommentare von Beitrag %s übersprungen: %s", m["id"], str(e))   # z.B. gelöscht
        return {str(m["id"]): m for m in medien}, gefunden

    def _speichere(self, gefunden: list) -> None:
        still = bool(self.s.lies("kommentare_still", False))
        for media_id, k in gefunden:
            eigen = bool(self._eigener) and (k.get("username") or "").lower() == self._eigener
            start = ist_start(k.get("text")) and not eigen
            self.s.neuer_kommentar(dict(k, media_id=media_id, start=start,
                                        gemeldet="still" if still and start else None))
        if still:
            self.s.schreibe("kommentare_still", False)

    def _titel(self, media_id: str, medien: dict) -> tuple[str, str]:
        """Thema aus dem Briefkasten (posts.instagram_id → Beitrag), sonst Art und Caption-Anfang von Instagram."""
        p = self.s.post_mit_instagram(media_id)
        b = self.s.beitrag(p["id"]) if p else None
        if b:
            return texte.FORMAT_NAME[b["format"]], b["titel"]
        return _art_und_titel(medien.get(media_id))

    @staticmethod
    def _abgelehnt(e: TelegramFehler) -> bool:
        """Telegram lehnt diese Nachricht dauerhaft ab (HTTP 400 oder 413; 401/403/404/429/5xx betreffen alle), Wiederholen hilft nicht."""
        m = re.search(r"HTTP (\d{3})", str(e))
        return bool(m) and m.group(1) in ("400", "413")

    def _melde(self, offen: list) -> None:
        """START-Kommentare melden, je einmal (ohne Sperre senden). Netz-, 5xx- und 429-Fehler: Rest bleibt für
        die nächste Runde. Dauerhaft abgelehnt: einmal ohne Knopf, dann als abgelehnt markiert und weiter."""
        for k, art, titel in offen:
            text, tastatur = texte.kommentar_meldung(k["username"], art, titel), texte.profil_tastatur(k["username"])
            wert = None
            for versuch in (tastatur, None) if tastatur else (None,):
                try:
                    self.a._sende(text, versuch, laut=True)
                    wert = self.a._zeit()
                    break
                except TelegramFehler as e:
                    LOG.warning("START-Meldung nicht gesendet: %s", str(e))
                    if not self._abgelehnt(e):
                        return
            if wert is None:
                wert = "abgelehnt"   # auch ohne Knopf abgelehnt: nicht mehr versuchen, Rest nicht aufstauen
                LOG.error("START-Meldung %s dauerhaft abgelehnt, übersprungen", k["id"])
            with self.a.sperre:
                self.s.setze_gemeldet(k["id"], wert)

    def _hinweis(self, grund: str) -> None:
        """Höchstens einmal pro Tag, Senden ohne Sperre."""
        with self.a.sperre:
            heute = self.a.jetzt().date().isoformat()
            if self.s.lies("kommentare_hinweis") == heute:
                return
        try:
            self.a._sende(texte.kommentare_hinweis(grund), laut=True)
        except TelegramFehler as e:
            LOG.warning("Kommentar-Hinweis nicht gesendet: %s", str(e))
            return
        with self.a.sperre:
            self.s.schreibe("kommentare_hinweis", heute)
