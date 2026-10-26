"""Poster (Etappe 5): postet freigegebene Beiträge zum Termin auf Instagram. Der Dienst ruft takt() alle 30 s in
einem eigenen Thread auf. Post-Stand in der Tabelle posts (eine Zeile pro Beitrag, gilt für eine Version).
Alles ausser den Instagram-Aufrufen läuft unter der Sperre von Ablauf. Knöpfe kommen über Ablauf._knopf
(Sperre schon gehalten). Ablauf: Vorwarnung Termin − 60 Min, Posten zum Termin, still wiederholen nach 2, 5,
10 Min, dann Meldung mit 🔁 und alle 15 Min weiter bis Termin + 3 h, danach «Verpasst» mit Jetzt posten /
Auslassen. Doppelpost-Schutz: Ist von einem früheren Versuch eine creation_id da, entscheidet deren Stand
(PUBLISHED: schon online, FINISHED: denselben Container veröffentlichen, sonst neu anlegen). Meldungen, auf die der
Betreiber antworten muss (unklar, verpasst), bleiben in meldung_offen vorgemerkt, bis Telegram sie angenommen hat.
Der Poster beachtet nur Termine ab dem ersten Einschalten (poster_seit).
Facebook-Zusatz: Nach dem Instagram-Erfolg postet `_facebook()` denselben Beitrag auf die Facebook-Seite, wenn der
Schalter facebook_an an ist (Stand in den fb_-Spalten)."""
import logging
from datetime import datetime, timedelta

from briefkasten import texte
from briefkasten.ablauf import _zone
from briefkasten.facebook import FacebookFehler
from briefkasten.instagram import InstagramFehler
from briefkasten.telegram import TelegramFehler

LOG = logging.getLogger("briefkasten.poster")
VORWARNUNG = timedelta(minutes=60)
NACHHOLEN = timedelta(hours=3)
PAUSEN = (2, 5, 10)        # Minuten: stille Wiederholungen nach dem 1., 2. und 3. Fehler
TAKT_FEHLER = 15           # Minuten zwischen Versuchen nach der Fehlermeldung
MAX_BILDER = 10
MAX_CAPTION = 2200
ERNEUERN_AB_TAGEN = 50
ERNEUERN_PAUSE = timedelta(hours=1)    # nach einem Fehlversuch frühestens wieder
JETZT_FRIST = timedelta(minutes=30)    # «Jetzt posten» gilt höchstens so lange
FERTIG = ("laeuft", "gepostet", "ausgelassen", "unklar", "verpasst_post")   # kein automatischer Versuch
FB_PAUSEN = (2, 10, 30)                   # Minuten nach dem 1., 2., 3. Fehlversuch, der 4. bringt die Meldung
FB_FRIST = timedelta(hours=24)            # danach kein automatischer Facebook-Versuch mehr (nicht rückwirkend)
FB_SCHLUESSEL_PAUSE = timedelta(hours=1)  # ungültiger Schlüssel: Versuch zählt nicht, später nochmals


def _adresse(u) -> bool:
    return isinstance(u, str) and u.startswith("https://") and len(u) <= 1000


class Poster:
    def __init__(self, ablauf, instagram, facebook=None):
        self.a, self.ig, self.fb, self.s = ablauf, instagram, facebook, ablauf.s
        ablauf.poster = self

    # --- Hilfen ---

    def _jetzt(self) -> datetime:
        return self.a.jetzt()

    def _an(self) -> bool:
        return bool(self.s.lies("poster_an", False))

    def _termin(self, b: dict) -> datetime:
        return self.a._termin(b)

    def _seit(self) -> datetime | None:
        """Erstes Einschalten. Ältere Termine fasst der Poster nie an, ohne Einschalten gar keine."""
        seit = self.s.lies("poster_seit")
        return _zone(datetime.fromisoformat(seit)) if seit else None

    def _beachtet(self, b: dict, seit: datetime | None) -> bool:
        return b["status"] == "freigegeben" and seit is not None and self._termin(b) >= seit

    def _post_fuer(self, b: dict) -> dict:
        """Post-Zeile für die aktuelle Version (neu, wenn keine oder eine für eine alte Version da ist)."""
        p = self.s.post(b["id"])
        if p is None or p["version"] != b["version"]:
            p = self.s.neuer_post(b["id"], b["version"])
        return p

    def _bearbeite_sicher(self, nachricht_id, text: str, tastatur: dict | None = None) -> None:
        try:
            self.a._bearbeite(nachricht_id, text, tastatur)
        except TelegramFehler as e:
            LOG.warning("Nachricht %s nicht bearbeitet: %s", nachricht_id, str(e))

    def _sende_sicher(self, text: str, tastatur: dict | None = None, laut: bool = True) -> int | None:
        try:
            return self.a._sende(text, tastatur, laut=laut)
        except TelegramFehler as e:
            LOG.warning("Poster-Meldung nicht gesendet: %s", str(e))
            return None

    # --- Schnittstelle zum Mac ---

    def medien(self, id: str, d: dict) -> dict:
        """Adressen der hochgeladenen Dateien, Cover und Caption für die aktuelle Version annehmen."""
        try:
            version, medien, cover, caption = int(d["version"]), d["medien"], d.get("cover"), d["caption"]
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"Medien ungültig: {e}") from None
        if not isinstance(medien, list) or not 1 <= len(medien) <= MAX_BILDER or not all(map(_adresse, medien)):
            raise ValueError("Medien ungültig: 1 bis 10 https-Adressen erwartet")
        if cover is not None and not _adresse(cover):
            raise ValueError("Medien ungültig: cover muss eine https-Adresse sein")
        if not isinstance(caption, str) or len(caption) > MAX_CAPTION:
            raise ValueError("Medien ungültig: caption fehlt oder ist zu lang")
        with self.a.sperre:
            b = self.s.beitrag(id)
            if b is None:
                raise ValueError(f"unbekannter Beitrag {id}")
            if version != b["version"]:
                raise ValueError(f"veraltete Version {version}, aktuell {b['version']}")
            if b["format"] == "karussell" and len(medien) < 2:
                raise ValueError("Medien ungültig: ein Karussell braucht mindestens 2 Bilder")
            if b["format"] == "reel" and len(medien) != 1:
                raise ValueError("Medien ungültig: ein Reel braucht genau 1 Video")
            p = self.s.post(id)
            if p is not None and p["post_status"] in ("laeuft", "gepostet", "unklar"):
                return p   # läuft, ist online oder vielleicht online: nie ersetzen
            p = self._post_fuer(b)
            fehlten = not p["medien"]
            p = self.s.setze_post(id, medien=medien, cover=cover, caption=caption)
            if fehlten and p["vorwarnung_id"] and p["post_status"] == "vorgewarnt":
                # Vorwarnung warnte vor fehlenden Dateien: Warnung entfernen, Stopp bleibt
                self._bearbeite_sicher(p["vorwarnung_id"], texte.vorwarnung(b), texte.vorwarnung_tastatur(b))
            return p

    def schalter(self, an: bool) -> dict:
        if not isinstance(an, bool):
            raise ValueError("an muss true oder false sein")
        with self.a.sperre:
            self.s.schreibe("poster_an", an)
            if an and self.s.lies("poster_seit") is None:
                self.s.schreibe("poster_seit", self.a._zeit())
        return self.stand()

    def stand(self) -> dict:
        with self.a.sperre:
            jetzt = self._jetzt()
            naechste = []
            for b in self.s.beitraege():
                if b["status"] != "freigegeben":
                    continue
                p = self.s.post(b["id"])
                aktuell = p is not None and p["version"] == b["version"]
                wartet = aktuell and p["post_status"] in ("unklar", "verpasst_post")   # Betreiber muss entscheiden
                try:
                    vorbei = self._termin(b) + NACHHOLEN <= jetzt
                except ValueError:
                    continue
                if vorbei and not wartet:
                    continue
                naechste.append({"id": b["id"], "titel": b["titel"], "format": b["format"], "termin": b["termin"],
                                 "post_status": p["post_status"] if aktuell else "geplant",
                                 "dateien": bool(aktuell and p["medien"])})
            an = self._an()
        try:
            tage = self.ig.schluessel.alter_tage(jetzt.date()) if self.ig.schluessel else None
        except Exception:   # Schlüssel fehlt oder kaputt: nur kein Alter anzeigen
            tage = None
        return {"an": an, "schluessel_tage": tage, "naechste": naechste}

    # --- Facebook-Zusatz: Schalter und Stand ---

    def _fb_an(self) -> bool:
        return self.fb is not None and bool(self.s.lies("facebook_an", False))

    def fb_schalter(self, an: bool) -> dict:
        if not isinstance(an, bool):
            raise ValueError("an muss true oder false sein")
        if self.fb is None:
            raise ValueError("Facebook ist auf diesem Server nicht eingerichtet")
        with self.a.sperre:
            self.s.schreibe("facebook_an", an)
            if an and self.s.lies("facebook_seit") is None:
                self.s.schreibe("facebook_seit", self.a._zeit())
        return self.fb_stand()

    def fb_stand(self) -> dict:
        with self.a.sperre:
            an, posts = self._fb_an(), []
            for p in self.s.posts():
                if p["fb_status"] is None:
                    continue
                b = self.s.beitrag(p["id"])
                posts.append({"id": p["id"], "titel": b["titel"] if b else p["id"],
                              "termin": b["termin"] if b else "", "fb_status": p["fb_status"],
                              "fb_link": p["fb_link"], "fb_grund": p["fb_grund"]})
        posts.sort(key=lambda x: x["termin"])
        return {"an": an, "schluessel": bool(self.fb is not None and self.fb.schluessel.da()), "posts": posts[-10:]}

    # --- Knöpfe (aus Ablauf._knopf, Sperre gehalten). Rückgabe: kurzer Hinweis oben im Chat ---

    def zahlen(self, tage: int) -> dict:
        """Für die Lern-Schleife (Etappe 6): alle Instagram-Beiträge der letzten `tage` Tage mit ihren Insights.
        Etappe 9: dazu start_kommentare (Anzahl START-Kommentare aus der Tabelle kommentare). Instagram ohne
        Sperre, die Datenbank nur kurz unter der Sperre."""
        beitraege = []
        for m in self.ig.medien_seit(self._jetzt() - timedelta(days=tage)):
            reel = m.get("media_product_type") == "REELS"
            art = "reel" if reel else "karussell" if m.get("media_type") == "CAROUSEL_ALBUM" else "bild"
            try:
                werte = self.ig.zahlen(str(m["id"]), reel)
            except InstagramFehler as e:
                if e.ungueltig or e.netz:
                    raise   # betrifft alle Beiträge: ganze Antwort scheitert
                werte = None   # nur dieser Beitrag (z.B. gelöscht)
            beitraege.append({"ig_id": str(m["id"]), "zeit": m.get("timestamp"), "art": art, "link": m.get("permalink"),
                              "caption_anfang": (m.get("caption") or "")[:80], "werte": werte})
        with self.a.sperre:
            start = self.s.start_anzahl()
        for b in beitraege:
            b["start_kommentare"] = start.get(b["ig_id"], 0)
        return {"beitraege": beitraege}

    def stopp(self, b: dict) -> str:
        p = self.s.post(b["id"])
        if b["status"] == "gepostet":
            return "Schon online"
        if p is not None and p["post_status"] == "laeuft":
            return "Wird gerade gepostet, zu spät"
        if b["status"] != "freigegeben":
            if p is not None and p["vorwarnung_id"]:
                self._bearbeite_sicher(p["vorwarnung_id"], texte.vorwarnung(b))
            return "Nichts zu stoppen"
        if self._termin(b) > self._jetzt():
            antwort = self.a._zuruecknehmen(b)   # ruft zurueckgenommen(b): Post und Meldungen zurücksetzen
            if not antwort.startswith("↩️"):
                return antwort
        else:
            self._auslassen(b)
            self._meldungen_gestoppt(b, p)
        return "⏸ Gestoppt"

    def zurueckgenommen(self, b: dict) -> None:
        """Haken aus Ablauf._zuruecknehmen (Sperre gehalten), auch für ⏸ Stopp vor dem Termin: der Post geht
        wieder auf Anfang, bei neuer, früh genug erfolgter Freigabe kommt eine neue Vorwarnung."""
        p = self.s.post(b["id"])
        if p is None:
            return
        self.s.setze_post(b["id"], post_status="geplant", vorwarnung_id=None, meldung_offen=None)
        self._meldungen_gestoppt(b, p)

    def _meldungen_gestoppt(self, b: dict, p: dict) -> None:
        """Vorwarnung und Fehlermeldung zeigen «Gestoppt» und verlieren ihre Knöpfe."""
        if p["vorwarnung_id"]:
            self._bearbeite_sicher(p["vorwarnung_id"], texte.vorwarnung(b) + "\n⏸ Gestoppt, geht nicht online.")
        if p["meldung_id"]:
            self._bearbeite_sicher(p["meldung_id"], texte.nicht_gepostet(b, p["grund"] or "gestoppt"))

    def nochmals(self, b: dict) -> str:
        if b["status"] == "gepostet":
            return "Schon online"
        p = self.s.post(b["id"])
        if b["status"] != "freigegeben" or p is None or p["post_status"] != "fehler":
            return "Nichts zu wiederholen"
        if not self._an():
            return "Poster ist aus, zuerst «fliessband poster ein»"
        self.s.setze_post(b["id"], naechster_versuch=None, nochmals=True)
        return "🔁 Ich versuche es gleich nochmals"

    def jetzt_posten(self, b: dict) -> str:
        if b["status"] == "gepostet":
            return "Schon online"
        p = self.s.post(b["id"])
        if b["status"] != "freigegeben" or p is None or p["post_status"] not in ("verpasst_post", "unklar"):
            return "Geht nicht mehr"
        if not self._an():
            return "Poster ist aus, zuerst «fliessband poster ein»"
        bis = (self._jetzt() + JETZT_FRIST).isoformat(timespec="seconds")
        self.s.setze_post(b["id"], post_status="geplant", manuell=True, manuell_bis=bis, naechster_versuch=None,
                          meldung_offen=None)
        if p["meldung_id"]:
            self._bearbeite_sicher(p["meldung_id"], self._meldungstext(b, p) + "\n🔁 Wird gepostet")
        return "🔁 Wird jetzt gepostet"

    def auslassen(self, b: dict) -> str:
        p = self.s.post(b["id"])
        if b["status"] != "freigegeben" or p is None or p["post_status"] not in ("verpasst_post", "unklar"):
            return "Schon online" if b["status"] == "gepostet" else "Geht nicht mehr"
        self._auslassen(b)
        if p["meldung_id"]:
            self._bearbeite_sicher(p["meldung_id"], self._meldungstext(b, p) + "\n⏭ Ausgelassen")
        return "⏭ Ausgelassen"

    @staticmethod
    def _meldungstext(b: dict, p: dict) -> str:
        return texte.unklar(b) if p["post_status"] == "unklar" else texte.verpasst_post(b, p["grund"] or "unklar")

    def _auslassen(self, b: dict) -> None:
        self._post_fuer(b)
        self.s.setze_post(b["id"], post_status="ausgelassen", naechster_versuch=None, meldung_offen=None,
                          manuell=False, manuell_bis=None)
        b = self.s.setze(b["id"], status="ausgelassen")
        self.a._ereignis("ausgelassen", b)
        self.a._zeige_sicher(b)
        self.a._uebersicht_sicher(b["woche"])

    # --- Dienststart und Schlüssel ---

    def beim_start(self) -> None:
        """Einmal beim Dienststart, bevor die Threads laufen: Posts, die beim Absturz «laeuft» waren, klären.
        Ohne creation_id kam es nie zum Veröffentlichen: sofort neu versuchen. Mit creation_id entscheidet der
        Container-Stand: PUBLISHED gepostet, FINISHED denselben Container veröffentlichen, sonst neu anlegen.
        Ist der Stand nicht abfragbar: «unklar», kein automatischer Versuch, Betreiber entscheidet."""
        with self.a.sperre:
            offen = [(self.s.beitrag(p["id"]), p) for p in self.s.posts() if p["post_status"] == "laeuft"]
        for b, p in offen:
            if p["creation_id"] is None:
                with self.a.sperre:
                    self.s.setze_post(p["id"], post_status="fehler", naechster_versuch=None)
                continue
            treffer = None
            try:
                code = self.ig.container_status(p["creation_id"])
            except InstagramFehler as e:
                LOG.warning("Container-Stand %s: %s", p["id"], str(e))
                code = None
            except Exception as e:   # Dienststart nie abbrechen, nie Details ins Log (Token-Schutz)
                LOG.error("Container-Stand %s: %s", p["id"], type(e).__name__)
                code = None
            if code == "PUBLISHED":
                treffer = self._abgleich_sicher(b, p)
            with self.a.sperre:
                if code == "PUBLISHED":
                    self._erfolg(b, treffer)
                elif code == "FINISHED":
                    self.s.setze_post(p["id"], post_status="fehler", naechster_versuch=None)
                elif code is None:
                    self.s.setze_post(p["id"], post_status="unklar", grund="unklar nach Neustart",
                                      meldung_offen="unklar", manuell=False, manuell_bis=None)
                    self._melde(p["id"])
                else:
                    self.s.setze_post(p["id"], post_status="fehler", creation_id=None, naechster_versuch=None)
        with self.a.sperre:
            for p in self.s.posts():
                if p["fb_status"] == "laeuft":   # Absturz mitten im Facebook-Post: _fb_reel bzw. Abgleich klärt
                    self.s.setze_post(p["id"], fb_status="offen", fb_naechster=None)

    def _schluessel_pflegen(self) -> None:
        """Einmal pro Tag: Schlüssel ab 50 Tagen erneuern und bei Instagram prüfen (ein ungültiger Schlüssel fällt
        so vor dem Termin auf). Fehlt er oder scheitert Erneuern oder Prüfen: Meldung (höchstens einmal pro Tag),
        nächster Versuch frühestens nach einer Stunde. Instagram-Aufrufe ohne Sperre."""
        if self.ig.schluessel is None:
            return
        jetzt = self._jetzt()
        heute = jetzt.date()
        with self.a.sperre:
            if self.s.lies("schluessel_geprueft") == heute.isoformat():
                return
            versuch = self.s.lies("schluessel_versuch")
            if versuch and jetzt < _zone(datetime.fromisoformat(versuch)) + ERNEUERN_PAUSE:
                return
        try:
            if self.ig.schluessel.alter_tage(heute) >= ERNEUERN_AB_TAGEN:
                self.ig.erneuere(heute)
            self.ig.pruefe()
        except InstagramFehler as e:
            with self.a.sperre:
                self.s.schreibe("schluessel_versuch", jetzt.isoformat(timespec="seconds"))
                if e.ungueltig or str(e).startswith("Instagram HTTP"):   # Netzausfall: still neu versuchen
                    self._schluessel_problem(str(e))
            return
        except Exception as e:   # nie Details ins Log (Token-Schutz)
            LOG.error("Schlüssel pflegen: %s", type(e).__name__)
            with self.a.sperre:
                self.s.schreibe("schluessel_versuch", jetzt.isoformat(timespec="seconds"))
            return
        with self.a.sperre:
            self.s.schreibe("schluessel_geprueft", heute.isoformat())

    # --- Zeitgeber ---

    def takt(self) -> None:
        """Ein Durchgang: vorwarnen, 3-h-Grenze, Frist von «Jetzt posten», vorgemerkte Meldungen, fällige Posts,
        Facebook, Schlüssel pflegen. Fehler eines Beitrags halten die anderen nicht auf."""
        with self.a.sperre:
            self._vorwarnen()
            self._grenze()
            self._frist()
            self._melde_offene()
            faellig = self._faellige()
        for b, p in faellig:
            self._poste(b, p)
        self._facebook()
        self._schluessel_pflegen()

    def _vorwarnen(self) -> None:
        """60 Minuten vor dem Termin, nur wenn früher freigegeben. Scheitert Telegram: nächster Takt."""
        if not self._an():
            return
        jetzt, seit = self._jetzt(), self._seit()
        for b in self.s.beitraege():
            try:
                if not self._beachtet(b, seit):
                    continue
                termin = self._termin(b)
                if not termin - VORWARNUNG <= jetzt < termin:
                    continue
                p = self._post_fuer(b)
                if p["vorwarnung_id"] or p["post_status"] not in ("geplant", "vorgewarnt"):
                    continue
                freigabe = self.s.letzte_freigabe(b["id"], b["version"])
                if freigabe is None or _zone(datetime.fromisoformat(freigabe)) > termin - VORWARNUNG:
                    continue   # zu spät freigegeben: ohne Vorwarnung posten
                nachricht = self._sende_sicher(texte.vorwarnung(b, dateien_fehlen=not p["medien"]),
                                               texte.vorwarnung_tastatur(b))
                if nachricht is not None:
                    self.s.setze_post(b["id"], vorwarnung_id=nachricht, post_status="vorgewarnt")
            except Exception as e:   # ein kaputter Beitrag hält die anderen nicht auf
                LOG.error("Vorwarnung %s: %s", b.get("id"), type(e).__name__)

    def _faellige(self) -> list[tuple[dict, dict]]:
        """Freigegebene Beiträge, deren Versuch jetzt dran ist. Sofort als «laeuft» markiert."""
        jetzt, seit, faellig = self._jetzt(), self._seit(), []
        if not self._an():
            return faellig
        for b in self.s.beitraege():
            try:
                if not self._beachtet(b, seit):
                    continue
                p = self._post_fuer(b)
                if p["post_status"] in FERTIG:
                    continue
                termin = self._termin(b)
                if jetzt < termin or (jetzt >= termin + NACHHOLEN and not p["manuell"]):
                    continue
                bis = p["manuell_bis"]
                if p["manuell"] and (not bis or jetzt >= _zone(datetime.fromisoformat(bis))):
                    continue   # Frist von «Jetzt posten» vorbei: nie später posten
                if p["naechster_versuch"] and jetzt < _zone(datetime.fromisoformat(p["naechster_versuch"])):
                    continue
                faellig.append((b, self.s.setze_post(b["id"], post_status="laeuft")))
            except Exception as e:
                LOG.error("Fällige %s: %s", b.get("id"), type(e).__name__)
        return faellig

    def _frist(self) -> None:
        """«Jetzt posten» ist nicht innert 30 Minuten gelungen (z.B. Poster aus): wieder Verpasst mit Knöpfen."""
        jetzt = self._jetzt()
        for p in self.s.posts():
            try:
                if not p["manuell"] or p["post_status"] not in ("geplant", "fehler"):
                    continue
                if p["manuell_bis"] and jetzt < _zone(datetime.fromisoformat(p["manuell_bis"])):
                    continue
                self.s.setze_post(p["id"], post_status="verpasst_post", manuell=False, manuell_bis=None,
                                  grund=texte.FRIST_VORBEI, naechster_versuch=None, meldung_offen="verpasst")
                self._melde(p["id"])
            except Exception as e:
                LOG.error("Frist %s: %s", p.get("id"), type(e).__name__)

    def _poste(self, b: dict, p: dict) -> None:
        """Ohne Sperre (Instagram). Ist von einem früheren Versuch eine creation_id da, zuerst deren Stand
        abfragen: PUBLISHED gilt als gepostet, FINISHED wird nochmals veröffentlicht (kein neuer Container),
        sonst neu anlegen. Scheitert die Abfrage selbst: Fehler mit normaler Wiederholung."""
        try:
            creation = p["creation_id"]
            if creation:
                code = self.ig.container_status(creation)
                if code == "PUBLISHED":
                    treffer = self._abgleich_sicher(b, p)
                    with self.a.sperre:
                        self._erfolg(b, treffer)
                    return
                if code != "FINISHED":
                    creation = None
                    with self.a.sperre:
                        self.s.setze_post(b["id"], creation_id=None)
            if creation is None and (p["version"] != b["version"] or not p["medien"]):
                raise InstagramFehler("Dateien fehlen (der Mac hat sie noch nicht hochgeladen)")
            if self.ig.tagesgrenze_erreicht():
                raise InstagramFehler("Tagesgrenze Instagram erreicht")
            if creation is None:
                creation = self.ig.bereite_vor(b["format"], p["medien"], p["cover"], p["caption"])
                with self.a.sperre:
                    self.s.setze_post(b["id"], creation_id=creation)
            ergebnis = self.ig.veroeffentliche(creation)
        except InstagramFehler as e:
            with self.a.sperre:
                self._fehler(b, str(e), e.ungueltig)
            return
        except Exception as e:   # nie den Thread verlieren, nie Details ins Log (Token-Schutz)
            LOG.error("Posten %s: %s", b["id"], type(e).__name__)
            with self.a.sperre:
                self._fehler(b, f"interner Fehler ({type(e).__name__})", False)
            return
        with self.a.sperre:
            self._erfolg(b, ergebnis)

    def _abgleich(self, b: dict, p: dict) -> dict | None:
        """Unter den letzten 10 eigenen Beiträgen einen mit gleicher Caption ab Termin − 5 Min suchen (nur für
        instagram_id und Link, der Container-Stand sagt schon, dass er online ist). Nur Instagram, kein Speicher
        (läuft ohne Sperre)."""
        ab = self._termin(b) - timedelta(minutes=5)
        for m in self.ig.letzte(10):
            try:
                zeit = datetime.strptime(m.get("timestamp", ""), "%Y-%m-%dT%H:%M:%S%z")
            except ValueError:
                continue
            if (m.get("caption") or "").strip() == (p["caption"] or "").strip() and zeit >= ab:
                return {"instagram_id": str(m["id"]), "permalink": m.get("permalink")}
        return None

    def _abgleich_sicher(self, b: dict, p: dict) -> dict:
        """Wie _abgleich, aber nie ein Fehler: ohne Treffer instagram_id und Link None (online ist er trotzdem)."""
        try:
            treffer = self._abgleich(b, p)
        except InstagramFehler as e:
            LOG.warning("Abgleich %s: %s", p["id"], str(e))
            treffer = None
        except Exception as e:   # nie Details ins Log (Token-Schutz)
            LOG.error("Abgleich %s: %s", p["id"], type(e).__name__)
            treffer = None
        return treffer or {"instagram_id": None, "permalink": None}

    def _erfolg(self, b: dict, ergebnis: dict) -> None:
        jetzt = self.a._zeit()
        p = self.s.setze_post(b["id"], post_status="gepostet", instagram_id=ergebnis["instagram_id"],
                              permalink=ergebnis.get("permalink"), gepostet=jetzt, naechster_versuch=None,
                              meldung_offen=None, manuell=False, manuell_bis=None, nochmals=False)
        b = self.s.setze(b["id"], status="gepostet")
        self.s.ereignis(jetzt, "gepostet", beitrag=b["id"], woche=b["woche"], version=b["version"],
                        nachricht={"instagram_id": p["instagram_id"], "permalink": p["permalink"]})
        self.a._zeige_sicher(b)
        if p["vorwarnung_id"]:
            self._bearbeite_sicher(p["vorwarnung_id"], texte.vorwarnung(b) + "\n✅ Online")
        if p["meldung_id"]:
            self._bearbeite_sicher(p["meldung_id"], texte.gepostet(b, None))
        felder = {"gepostet_id": self._sende_sicher(texte.gepostet(b, p["permalink"]), laut=False)}
        if self._fb_an():
            felder.update(fb_status="offen", fb_versuche=0, fb_naechster=None, fb_grund=None)
        self.s.setze_post(b["id"], **felder)
        self.a._uebersicht_sicher(b["woche"])

    def _fehler(self, b: dict, grund: str, ungueltig: bool) -> None:
        p = self.s.post(b["id"])
        n = p["versuche"] + 1
        if ungueltig:
            self._schluessel_problem(grund)
        if p["manuell"]:
            # «Jetzt posten» gescheitert: wieder Jetzt posten / Auslassen, keine automatischen Versuche.
            # Erst vormerken, dann senden (scheitert Telegram, folgt die Meldung im nächsten Takt).
            self.s.setze_post(b["id"], post_status="verpasst_post", versuche=n, grund=grund, manuell=False,
                              manuell_bis=None, naechster_versuch=None, meldung_offen="jetzt")
            self._melde(b["id"])
            return
        war_nochmals = p["nochmals"]
        pause = PAUSEN[n - 1] if n <= len(PAUSEN) else TAKT_FEHLER
        naechster = (self._jetzt() + timedelta(minutes=pause)).isoformat(timespec="seconds")
        p = self.s.setze_post(b["id"], post_status="fehler", versuche=n, grund=grund, naechster_versuch=naechster,
                              nochmals=False)
        if war_nochmals and p["meldung_id"]:
            # Von Betreiber mit 🔁 ausgelöst: bestehende Meldung nachführen, Knopf bleibt
            self._bearbeite_sicher(p["meldung_id"], texte.nochmals_gescheitert(b, self._jetzt(), grund),
                                   texte.nochmals_tastatur(b))
        elif n > len(PAUSEN) and not p["meldung_id"]:
            nachricht = self._sende_sicher(texte.nicht_gepostet(b, grund), texte.nochmals_tastatur(b))
            if nachricht is not None:
                self.s.setze_post(b["id"], meldung_id=nachricht)

    def _grenze(self) -> None:
        """Termin + 3 h ohne Erfolg: «Verpasst» mit Jetzt posten / Auslassen. Erst Status und Vormerkung
        speichern, dann senden (scheitert Telegram, folgt die Meldung im nächsten Takt)."""
        jetzt, seit = self._jetzt(), self._seit()
        for b in self.s.beitraege():
            try:
                if not self._beachtet(b, seit) or jetzt < self._termin(b) + NACHHOLEN:
                    continue
                p = self._post_fuer(b)
                if p["post_status"] not in ("geplant", "vorgewarnt", "fehler") or p["manuell"]:
                    continue
                if p["grund"]:
                    grund = p["grund"]
                elif not self._an():
                    grund = "Poster war ausgeschaltet"
                else:
                    grund = "Kein Versuch möglich (Server lief nicht)"
                self.s.setze_post(b["id"], post_status="verpasst_post", grund=grund, naechster_versuch=None,
                                  meldung_offen="verpasst")
                if p["vorwarnung_id"]:
                    self._bearbeite_sicher(p["vorwarnung_id"], texte.vorwarnung(b))
                self._melde(b["id"])
            except Exception as e:
                LOG.error("Grenze %s: %s", b.get("id"), type(e).__name__)

    def _melde(self, id: str) -> None:
        """Vorgemerkte Meldung (meldung_offen: unklar, verpasst, jetzt) mit Jetzt posten / Auslassen senden.
        Erst nach Erfolg gilt sie als erledigt, die alte Meldung verliert dann ihren Knopf."""
        p, b = self.s.post(id), self.s.beitrag(id)
        if p is None or not p["meldung_offen"]:
            return
        if (b is None or b["status"] != "freigegeben" or b["version"] != p["version"]
                or p["post_status"] not in ("unklar", "verpasst_post")):
            self.s.setze_post(id, meldung_offen=None)   # inzwischen entschieden: nichts mehr zu melden
            return
        grund = p["grund"] or "unklar"
        if p["meldung_offen"] == "unklar":
            text = texte.unklar(b)
        elif p["meldung_offen"] == "jetzt":
            text = texte.nicht_gepostet(b, grund)
        else:
            text = texte.verpasst_post(b, grund)
        nachricht = self._sende_sicher(text, texte.nachholen_tastatur(b))
        if nachricht is None:
            return
        if p["meldung_id"]:
            self._bearbeite_sicher(p["meldung_id"], texte.nicht_gepostet(b, grund))
        self.s.setze_post(id, meldung_id=nachricht, meldung_offen=None)

    def _melde_offene(self) -> None:
        for p in self.s.posts():
            if not p["meldung_offen"]:
                continue
            try:
                self._melde(p["id"])
            except Exception as e:
                LOG.error("Meldung %s: %s", p["id"], type(e).__name__)

    def _schluessel_problem(self, grund: str) -> None:
        """Höchstens einmal pro Tag melden."""
        heute = self._jetzt().date().isoformat()
        if self.s.lies("schluessel_gemeldet") == heute:
            return
        if self._sende_sicher(texte.schluessel_meldung(grund)) is not None:
            self.s.schreibe("schluessel_gemeldet", heute)

    # --- Facebook-Zusatz: Posten ---

    def _facebook(self) -> None:
        if self.fb is None:
            return
        with self.a.sperre:
            faellig = self._fb_faellige()
        for b, p in faellig:
            try:
                self._fb_poste(b, p)
            except Exception as e:   # ein Beitrag darf die anderen und die Schlüsselpflege nicht aufhalten
                LOG.error("Facebook %s: %s", b["id"], type(e).__name__)

    def _fb_faellige(self) -> list[tuple[dict, dict]]:
        """Offene Facebook-Posts, deren Versuch jetzt dran ist. Sofort als «laeuft» markiert."""
        jetzt, faellig = self._jetzt(), []
        if not self._fb_an():
            return faellig
        for p in self.s.posts():
            try:
                if p["fb_status"] != "offen":
                    continue
                if p["fb_naechster"] and jetzt < _zone(datetime.fromisoformat(p["fb_naechster"])):
                    continue
                b = self.s.beitrag(p["id"])
                if b is None or b["status"] != "gepostet" or b["version"] != p["version"]:
                    continue
                if (not p["fb_meldung_id"] and p["gepostet"]
                        and jetzt - _zone(datetime.fromisoformat(p["gepostet"])) >= FB_FRIST):
                    # Zu spät für einen automatischen Versuch. Einmal melden; nach «Nochmals» ist fb_meldung_id
                    # gesetzt, dann greift die Frist nicht mehr (bewusste Wahl des Betreibers).
                    alt = f" ({p['fb_grund']})" if p["fb_grund"] else ""
                    self._fb_melde_fehler(b, f"Facebook-Post nicht innert 24 Stunden möglich{alt}")
                    continue
                faellig.append((b, self.s.setze_post(p["id"], fb_status="laeuft")))
            except Exception as e:
                LOG.error("Facebook fällig %s: %s", p.get("id"), type(e).__name__)
        return faellig

    def _fb_poste(self, b: dict, p: dict) -> None:
        """Ohne Sperre (Facebook). Karussell: zuerst auf der Seite nach demselben Text suchen (Doppelpost-Schutz)."""
        try:
            if b["format"] == "karussell":
                seit = _zone(datetime.fromisoformat(p["gepostet"])) - timedelta(minutes=5)
                ergebnis = (self.fb.schon_gepostet(p["caption"], seit)
                            or self.fb.poste_karussell(p["medien"], p["caption"]))
            else:
                ergebnis = self._fb_reel(b, p)
        except FacebookFehler as e:
            with self.a.sperre:
                self._fb_fehler(b, str(e), e.ungueltig)
            return
        except Exception as e:   # nie den Thread verlieren, nie Details ins Log (Token-Schutz)
            LOG.error("Facebook %s: %s", b["id"], type(e).__name__)
            with self.a.sperre:
                self._fb_fehler(b, f"interner Fehler ({type(e).__name__})", False)
            return
        with self.a.sperre:
            self._fb_erfolg(b, ergebnis)

    def _fb_reel(self, b: dict, p: dict) -> dict:
        """Ohne Sperre. Mit fb_id von einem früheren Versuch zuerst dessen Stand: fertig gilt als gepostet, laeuft
        (oder offen, aber «Fertig» schon gemeldet) wird abgewartet, sonst neu anfangen (ein nie veröffentlichtes
        Video bleibt unsichtbar)."""
        vid = p["fb_id"]
        if vid:
            stand = self.fb.reel_stand(vid)
            if stand == "fertig":
                return {"id": vid, "link": self.fb.link(vid)}
            if stand == "laeuft" or (stand == "offen" and p["fb_beendet"]):
                self.fb.warte_reel(vid)
                return {"id": vid, "link": self.fb.link(vid)}
        vid = self.fb.starte_reel()
        with self.a.sperre:
            self.s.setze_post(b["id"], fb_id=vid, fb_beendet=False)
        self.fb.lade_reel(vid, p["medien"][0])
        with self.a.sperre:   # «Abschluss vielleicht gesendet»: scheitert die Antwort, wird abgewartet, nicht neu gestartet
            self.s.setze_post(b["id"], fb_beendet=True)
        try:
            self.fb.beende_reel(vid, p["caption"])
        except FacebookFehler as e:
            if str(e).startswith("Facebook HTTP"):   # Antwort sicher angekommen: abgelehnt, nichts veröffentlicht
                with self.a.sperre:
                    self.s.setze_post(b["id"], fb_beendet=False)
            raise
        self.fb.warte_reel(vid)
        return {"id": vid, "link": self.fb.link(vid)}

    def _fb_erfolg(self, b: dict, ergebnis: dict) -> None:
        p = self.s.setze_post(b["id"], fb_status="gepostet", fb_id=ergebnis["id"], fb_link=ergebnis.get("link"),
                              fb_naechster=None, fb_grund=None)
        if p["gepostet_id"]:
            self._bearbeite_sicher(p["gepostet_id"], texte.gepostet(b, p["permalink"], p["fb_link"] or "online"))
        if p["fb_meldung_id"]:
            self._bearbeite_sicher(p["fb_meldung_id"], texte.fb_nachgeholt(b))

    def _fb_fehler(self, b: dict, grund: str, ungueltig: bool) -> None:
        """Stille Wiederholung nach 2, 10, 30 Min, beim 4. Fehlversuch Meldung mit Nochmals / Auslassen.
        Ungültiger Schlüssel: Versuch zählt nicht, nach 1 h nochmals, Meldung höchstens einmal pro Tag."""
        p, jetzt = self.s.post(b["id"]), self._jetzt()
        if ungueltig:
            self._fb_schluessel_problem(grund)
            self.s.setze_post(b["id"], fb_status="offen", fb_grund=grund,
                              fb_naechster=(jetzt + FB_SCHLUESSEL_PAUSE).isoformat(timespec="seconds"))
            return
        n = p["fb_versuche"] + 1
        if n <= len(FB_PAUSEN):
            naechster = (jetzt + timedelta(minutes=FB_PAUSEN[n - 1])).isoformat(timespec="seconds")
            self.s.setze_post(b["id"], fb_status="offen", fb_versuche=n, fb_grund=grund, fb_naechster=naechster)
            return
        self._fb_melde_fehler(b, grund, n)

    def _fb_melde_fehler(self, b: dict, grund: str, versuche: int | None = None) -> None:
        """Status «fehler» und Meldung mit Nochmals / Auslassen (bestehende Meldung wird bearbeitet)."""
        felder = {"fb_status": "fehler", "fb_grund": grund, "fb_naechster": None}
        if versuche is not None:
            felder["fb_versuche"] = versuche
        p = self.s.setze_post(b["id"], **felder)
        if p["fb_meldung_id"]:
            self._bearbeite_sicher(p["fb_meldung_id"], texte.fb_nicht_gepostet(b, grund), texte.fb_tastatur(b))
            return
        nachricht = self._sende_sicher(texte.fb_nicht_gepostet(b, grund), texte.fb_tastatur(b))
        if nachricht is not None:
            self.s.setze_post(b["id"], fb_meldung_id=nachricht)

    def _fb_schluessel_problem(self, grund: str) -> None:
        heute = self._jetzt().date().isoformat()
        if self.s.lies("fb_schluessel_gemeldet") == heute:
            return
        if self._sende_sicher(texte.fb_schluessel_meldung(grund)) is not None:
            self.s.schreibe("fb_schluessel_gemeldet", heute)

    # --- Facebook-Zusatz: Knöpfe (aus Ablauf._knopf, Sperre gehalten) ---

    def fb_nochmals(self, b: dict) -> str:
        p = self.s.post(b["id"])
        if p is not None and p["fb_status"] == "gepostet":
            return "Schon auf Facebook"
        if p is None or p["fb_status"] != "fehler":
            return "Nichts zu wiederholen"
        if not self._fb_an():
            return "Facebook ist aus, zuerst «fliessband facebook ein»"
        self.s.setze_post(b["id"], fb_status="offen", fb_versuche=0, fb_naechster=None, fb_beendet=False)
        if p["fb_meldung_id"]:
            self._bearbeite_sicher(p["fb_meldung_id"],
                                   texte.fb_nicht_gepostet(b, p["fb_grund"] or "unklar") + "\n🔁 Wird nochmals versucht")
        return "🔁 Ich versuche es gleich nochmals"

    def fb_auslassen(self, b: dict) -> str:
        p = self.s.post(b["id"])
        if p is not None and p["fb_status"] == "gepostet":
            return "Schon auf Facebook"
        if p is None or p["fb_status"] != "fehler":
            return "Geht nicht mehr"
        self.s.setze_post(b["id"], fb_status="ausgelassen", fb_naechster=None)
        if p["fb_meldung_id"]:
            self._bearbeite_sicher(p["fb_meldung_id"],
                                   texte.fb_nicht_gepostet(b, p["fb_grund"] or "unklar") + "\n⏭ Facebook ausgelassen")
        return "⏭ Facebook ausgelassen"
