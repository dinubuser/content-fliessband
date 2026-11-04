"""Logik des Briefkastens: Beiträge mit Knöpfen, Betreiber-Entscheide als Ereignisse, Übersicht, Zeitgeber.
Öffentliche Methoden laufen hinter einer Sperre: API-Thread, Abhol-Schleife und Zeitgeber teilen alles.
Termine sind Ortszeit ohne Zeitzone ('2026-10-27T19:00')."""
import logging
import os
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from briefkasten import texte
from briefkasten.telegram import TelegramFehler

LOG = logging.getLogger("briefkasten")


def zeitzone() -> ZoneInfo:
    """Zeitzone der Termine aus FLIESSBAND_ZEITZONE, Standard Europe/Zurich."""
    name = os.environ.get("FLIESSBAND_ZEITZONE") or "Europe/Zurich"
    try:
        return ZoneInfo(name)
    except (KeyError, ValueError, OSError):   # ZoneInfoNotFoundError ist ein KeyError
        raise ValueError(f"FLIESSBAND_ZEITZONE '{name}' ist keine bekannte Zeitzone, z.B. Europe/Zurich") from None


ZONE = zeitzone()
FORMATE = ("reel", "karussell")
ENTSCHEIDE = ("freigegeben", "zurueckgenommen", "aendern", "verworfen", "verpasst")
ARTEN = ENTSCHEIDE + ("gepostet", "ausgelassen", "nachricht")
NOTIZ_FENSTER = timedelta(minutes=30)
NOTIZ_ANZEIGE = 500
ERINNERUNG_STUNDE = 8


def _zone(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=ZONE)


def _pruefe_beitrag(d: dict) -> dict:
    try:
        b = {"id": str(d["id"]), "woche": str(d["woche"]), "version": int(d["version"]),
             "titel": str(d["titel"]), "format": d["format"], "termin": str(d["termin"]),
             "neubauten": int(d.get("neubauten", 0)), "platzhalter": d.get("platzhalter", False)}
        datetime.fromisoformat(b["termin"])
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"Beitrag ungültig: {e}") from None
    if b["format"] not in FORMATE or b["version"] < 1 or not b["id"] or not b["titel"]:
        raise ValueError("Beitrag ungültig: format, version, id oder titel")
    if not isinstance(b["platzhalter"], bool):
        raise ValueError("Beitrag ungültig: platzhalter muss true oder false sein")
    return b


class Ablauf:
    def __init__(self, speicher, telegram, chat_id: int, jetzt=lambda: datetime.now(ZONE)):
        self.s, self.tg, self.chat, self.jetzt = speicher, telegram, chat_id, jetzt
        self.sperre = threading.RLock()
        self.poster = None   # Etappe 5: briefkasten.poster.Poster hängt sich hier ein
        self.kommentare = None   # Etappe 9: briefkasten.kommentare.Kommentare hängt sich hier ein

    # --- Hilfen ---

    def _zeit(self) -> str:
        return self.jetzt().isoformat(timespec="seconds")

    def _termin(self, b: dict) -> datetime:
        return _zone(datetime.fromisoformat(b["termin"]))

    def _sende(self, text: str, tastatur: dict | None = None, laut: bool = False) -> int:
        felder = {"chat_id": self.chat, "text": text, "disable_notification": not laut}
        if tastatur is not None:
            felder["reply_markup"] = tastatur
        return self.tg("sendMessage", felder)["message_id"]

    def _bearbeite(self, nachricht_id: int | None, text: str, tastatur: dict | None = None) -> None:
        if nachricht_id is None:
            return
        try:
            self.tg("editMessageText", {"chat_id": self.chat, "message_id": nachricht_id, "text": text,
                                        "reply_markup": tastatur or texte.LEER})
        except TelegramFehler as e:
            if "not modified" not in str(e):
                raise

    def _zeige(self, b: dict, zusatz: str = "") -> None:
        self._bearbeite(b["nachricht_id"], texte.knopf_text(b, zusatz), texte.tastatur(b))

    def _ereignis(self, art: str, b: dict, notiz: str | None = None) -> None:
        self.s.ereignis(self._zeit(), art, beitrag=b["id"], woche=b["woche"], version=b["version"], notiz=notiz)

    def _uebersicht(self, woche: str) -> None:
        nachricht = self.s.lies(f"uebersicht-{woche}")
        bs = self.s.beitraege(woche)
        self._bearbeite(nachricht, texte.uebersicht(woche, bs), texte.uebersicht_tastatur(woche, bs))

    def _vergiss_notiz_anfragen(self, nr: int) -> None:
        anfragen = self.s.lies("notiz_anfragen", [])
        rest = [a for a in anfragen if a["beitrag"] != nr]
        if rest != anfragen:
            self.s.schreibe("notiz_anfragen", rest)

    # --- Schnittstelle zum Mac ---

    def melde_beitrag(self, daten: dict) -> dict:
        """Gesendeten Beitrag anmelden und die Knopf-Nachricht schicken. Gleiche Version mit Nachricht: nichts
        Neues. Neue Version: alte Nachricht wird «ersetzt», Status wieder offen."""
        b = _pruefe_beitrag(daten)
        with self.sperre:
            alt = self.s.beitrag(b["id"])
            if alt and (alt["version"] > b["version"] or (alt["version"] == b["version"] and alt["nachricht_id"])):
                return alt
            if alt and alt["version"] < b["version"]:
                p = self.s.post(alt["id"])
                if alt["status"] in ("gepostet", "ausgelassen") or (
                        p is not None and p["version"] == alt["version"]
                        and p["post_status"] in ("laeuft", "unklar", "gepostet")):
                    raise ValueError(f"Beitrag {alt['id']} wird gerade gepostet oder ist schon entschieden, "
                                     "keine neue Version mehr")
                try:
                    self._bearbeite(alt["nachricht_id"], texte.ersetzt_text(alt, b["version"]))
                except TelegramFehler as e:
                    LOG.warning("Alte Nachricht nicht ersetzt: %s", str(e))
                self._vergiss_notiz_anfragen(alt["nr"])
            neu = self.s.speichere_beitrag(dict(b, status="offen", nachricht_id=None))
            neu = self.s.setze(neu["id"], nachricht_id=self._sende(texte.knopf_text(neu), texte.tastatur(neu)))
            try:
                self._uebersicht(neu["woche"])
            except TelegramFehler as e:
                LOG.warning("Übersicht nicht nachgeführt: %s", str(e))
            return neu

    def woche_fertig(self, woche: str) -> None:
        """Übersicht der Woche schicken (einmal), danach nur noch nachführen."""
        with self.sperre:
            bs = self.s.beitraege(woche)
            if not bs:
                raise ValueError(f"keine Beiträge für {woche}")
            if self.s.lies(f"uebersicht-{woche}") is None:
                nachricht = self._sende(texte.uebersicht(woche, bs), texte.uebersicht_tastatur(woche, bs))
                self.s.schreibe(f"uebersicht-{woche}", nachricht)
            else:
                self._uebersicht(woche)

    def neubau_gescheitert(self, id: str, grund: str) -> None:
        with self.sperre:
            b = self.s.beitrag(id)
            if b is None:
                raise ValueError(f"unbekannter Beitrag {id}")
            if b["status"] == "aendern_wartet":
                b = self.s.setze(id, status="offen")
            # Zustand steht schon (wiederholbar). Anzeige-Fehler nur loggen. Kommt die Meldung selbst nicht an,
            # wirft _sende (502): der Mac merkt sie als nicht gemeldet und wiederholt (Status bleibt offen).
            self._zeige_sicher(b)
            self._sende(f"Neubau von «{b['titel']}» gescheitert: {grund}\nDie bisherige Version gilt weiter.")
            self._uebersicht_sicher(b["woche"])

    def fragen_offen(self, bis: str) -> None:
        """Bis wann Freitags-Fragen offen sind (Textnachrichten ohne Antwort-Bezug gelten dann nicht als Notiz)."""
        datetime.fromisoformat(bis)
        with self.sperre:
            self.s.schreibe("fragen_bis", bis)

    def umstellen(self, update_id: int) -> int:
        """Ab jetzt fragt der Server Telegram ab (nach update_id). Nur beim ersten Mal wirksam."""
        with self.sperre:
            if self.s.lies("update_id") is None:
                self.s.schreibe("update_id", int(update_id))
            return self.s.lies("update_id")

    def ereignisse(self, nach: int, arten) -> list[dict]:
        arten = [a for a in arten if a]
        if not arten or set(arten) - set(ARTEN):
            raise ValueError(f"unbekannte Ereignis-Arten {arten}")
        with self.sperre:
            return self.s.ereignisse(int(nach), arten)

    # --- Telegram: Updates verarbeiten ---

    def verarbeite(self, update: dict) -> None:
        """Ein Telegram-Update (Knopf oder Textnachricht). Scheitert Telegram mitten drin, ist der Entscheid
        schon gespeichert und das Update gilt trotzdem als verarbeitet (sonst entstünde er doppelt)."""
        with self.sperre:
            try:
                if "callback_query" in update:
                    self._knopf(update["callback_query"])
                elif "message" in update:
                    m = update["message"]
                    if (m.get("chat") or {}).get("id") == self.chat and m.get("text"):
                        self._text(m, update["update_id"])
            except TelegramFehler as e:
                LOG.warning("Update %s: %s", update["update_id"], str(e))
            finally:
                self.s.schreibe("update_id", max(update["update_id"], self.s.lies("update_id") or 0))

    def _antworte(self, q: dict, text: str) -> None:
        try:
            self.tg("answerCallbackQuery", {"callback_query_id": q["id"], "text": text})
        except TelegramFehler:
            pass   # nur der kurze Hinweis oben im Chat, der Entscheid ist gespeichert

    def _zeige_sicher(self, b: dict, zusatz: str = "") -> None:
        try:
            self._zeige(b, zusatz)
        except TelegramFehler as e:
            LOG.warning("Beitrag %s nicht neu gezeichnet: %s", b["nr"], str(e))

    def _uebersicht_sicher(self, woche: str) -> None:
        try:
            self._uebersicht(woche)
        except TelegramFehler as e:
            LOG.warning("Übersicht %s nicht nachgeführt: %s", woche, str(e))

    def _vorbei(self, b: dict) -> bool:
        return b["status"] in ("offen", "aendern_wartet") and self._termin(b) <= self.jetzt()

    def _knopf(self, q: dict) -> None:
        if ((q.get("message") or {}).get("chat") or {}).get("id") != self.chat:
            self._antworte(q, "")
            return
        art, _, rest = (q.get("data") or "").partition(":")
        if art in ("A", "Aj", "An"):
            self._antworte(q, self._alle(art, rest))
            return
        aktionen = {"f": self._freigeben, "z": self._zuruecknehmen, "a": self._aendern_fragen,
                    "v": self._verwerfen_fragen, "vj": self._verwerfen, "vn": self._verwerfen_nein}
        if self.poster is not None:
            aktionen.update(s=self.poster.stopp, n=self.poster.nochmals, j=self.poster.jetzt_posten,
                            l=self.poster.auslassen, fn=self.poster.fb_nochmals, fl=self.poster.fb_auslassen)
        aktion = aktionen.get(art)
        try:
            nr, version = (int(x) for x in rest.split(":"))
        except ValueError:
            aktion = None
        b = self.s.beitrag_nr(nr) if aktion else None
        if b is None:
            self._antworte(q, "Unbekannter Knopf")
        elif version != b["version"]:
            self._antworte(q, "Veraltet, bitte die neue Nachricht nehmen")
        elif self._vorbei(b):
            self._antworte(q, texte.TERMIN_VORBEI)   # auf «verpasst» setzt der Zeitgeber
        else:
            self._antworte(q, aktion(b))

    def _freigeben(self, b: dict) -> str:
        if b["status"] != "offen":
            self._zeige_sicher(b)
            return "Schon entschieden"
        if b["platzhalter"]:
            self._zeige_sicher(b)   # alte Nachricht mit Freigeben-Knopf? Knöpfe passend neu zeichnen
            return texte.PLATZHALTER_GESPERRT
        b = self.s.setze(b["id"], status="freigegeben")
        self._ereignis("freigegeben", b)
        self._vergiss_notiz_anfragen(b["nr"])
        self._zeige_sicher(b)
        self._uebersicht_sicher(b["woche"])
        return "✅ Freigegeben"

    def _zuruecknehmen(self, b: dict) -> str:
        if b["status"] != "freigegeben":
            self._zeige_sicher(b)
            return "Nichts zurückzunehmen"
        if self._termin(b) <= self.jetzt():
            return "Termin vorbei, geht nicht mehr"
        b = self.s.setze(b["id"], status="offen")
        self._ereignis("zurueckgenommen", b)
        self._zeige_sicher(b)
        self._uebersicht_sicher(b["woche"])
        if self.poster is not None:
            self.poster.zurueckgenommen(b)
        return "↩️ Zurückgenommen"

    def _aendern_fragen(self, b: dict) -> str:
        if b["status"] != "offen":
            return "Geht nur bei offenen Beiträgen"
        if b["neubauten"] >= texte.MAX_NEUBAUTEN:
            if b["platzhalter"]:
                return "Schon 2-mal neu gebaut, nur noch Verwerfen"
            return "Schon 2-mal neu gebaut, nur noch Freigeben oder Verwerfen"
        try:
            nachricht = self._sende(texte.aendern_frage(b), {"force_reply": True,
                                                              "input_field_placeholder": "Was soll anders sein?"})
        except TelegramFehler as e:
            LOG.warning("Ändern-Frage nicht gesendet: %s", str(e))
            return "Hat nicht geklappt, bitte nochmals tippen"
        anfragen = [a for a in self.s.lies("notiz_anfragen", []) if a["beitrag"] != b["nr"]]
        anfragen.append({"beitrag": b["nr"], "version": b["version"], "nachricht": nachricht, "zeit": self._zeit()})
        self.s.schreibe("notiz_anfragen", anfragen)
        return "Schreib mir, was ich ändern soll"

    def _verwerfen_fragen(self, b: dict) -> str:
        if b["status"] != "offen":
            return "Geht nur bei offenen Beiträgen"
        try:
            self._bearbeite(b["nachricht_id"], texte.knopf_text(b, texte.VERWERFEN_FRAGE),
                            texte.verwerfen_tastatur(b))
        except TelegramFehler as e:
            LOG.warning("Verwerfen-Frage nicht gezeigt: %s", str(e))
            return "Hat nicht geklappt, bitte nochmals tippen"
        return ""

    def _verwerfen(self, b: dict) -> str:
        if b["status"] != "offen":
            self._zeige_sicher(b)
            return "Schon entschieden"
        b = self.s.setze(b["id"], status="verworfen")
        self._ereignis("verworfen", b)
        self._vergiss_notiz_anfragen(b["nr"])
        self._zeige_sicher(b, "Reserve folgt.")
        self._uebersicht_sicher(b["woche"])
        return "❌ Verworfen, Reserve folgt"

    def _verwerfen_nein(self, b: dict) -> str:
        self._zeige_sicher(b)
        return "Nicht verworfen"

    def _alle(self, art: str, woche: str) -> str:
        """Alle offenen Beiträge der Woche freigeben (mit Rückfrage). Beiträge mit erreichtem Termin oder mit
        Platzhaltern bleiben liegen. Erst alle Entscheide speichern, dann die Anzeigen einzeln nachführen."""
        bs = self.s.beitraege(woche)
        offen = [b for b in bs if texte.freigebbar(b) and not self._vorbei(b)]
        if art == "An":
            self._uebersicht_sicher(woche)
            return "Nichts geändert"
        if not offen:
            self._uebersicht_sicher(woche)
            return "Nichts offen"
        if art == "A":
            try:
                self._bearbeite(self.s.lies(f"uebersicht-{woche}"),
                                texte.uebersicht(woche, bs) + "\n\n" + texte.alle_frage(len(offen)),
                                texte.alle_tastatur(woche))
            except TelegramFehler as e:
                LOG.warning("Rückfrage «Alle freigeben» nicht gezeigt: %s", str(e))
                return "Hat nicht geklappt, bitte nochmals tippen"
            return ""
        freigegeben = []
        for b in offen:
            b = self.s.setze(b["id"], status="freigegeben")
            self._ereignis("freigegeben", b)
            self._vergiss_notiz_anfragen(b["nr"])
            freigegeben.append(b)
        for b in freigegeben:
            self._zeige_sicher(b)
        self._uebersicht_sicher(woche)
        return f"✅ {len(freigegeben)} freigegeben"

    def _text(self, m: dict, update_id: int) -> None:
        """Textnachricht vom Betreiber: Notiz zu einem «Ändern» oder sonst Ereignis «nachricht»
        (Antworten auf die Freitags-Fragen). Erst Zustand und Ereignis speichern, dann anzeigen."""
        anfrage = self._notiz_anfrage(m)
        if anfrage is None:
            self.s.ereignis(self._zeit(), "nachricht", nachricht={"update_id": update_id, "message": m})
            return
        text = m["text"].strip()
        if not any(z.isalnum() for z in text):
            self._sende("Ich brauche einen Satz, was ich ändern soll. Antworte nochmals auf meine Frage.")
            return
        self._vergiss_notiz_anfragen(anfrage["beitrag"])
        b = self.s.setze(self.s.beitrag_nr(anfrage["beitrag"])["id"], status="aendern_wartet")
        self._ereignis("aendern", b, notiz=text)
        kurz = text if len(text) <= NOTIZ_ANZEIGE else text[:NOTIZ_ANZEIGE - 1] + "…"
        self._zeige_sicher(b, f"Notiz: {kurz}")
        self._sende_sicher(f"Notiert. Ich baue «{b['titel']}» neu, sobald der Mac wach ist.")
        self._uebersicht_sicher(b["woche"])

    def _sende_sicher(self, text: str) -> None:
        try:
            self._sende(text)
        except TelegramFehler as e:
            LOG.warning("Hinweis nicht gesendet: %s", str(e))

    def _anfrage_beitrag(self, a: dict) -> dict | None:
        """Beitrag zur Notiz-Anfrage, wenn sie noch gilt (offen, gleiche Version, Termin nicht erreicht)."""
        b = self.s.beitrag_nr(a["beitrag"])
        if b is None or b["status"] != "offen" or b["version"] != a["version"] or self._vorbei(b):
            return None
        return b

    def _veraltet_hinweis(self, a: dict) -> str:
        b = self.s.beitrag_nr(a["beitrag"])
        if b is None or b["version"] != a["version"]:
            return "Der Beitrag hat sich inzwischen geändert, die Notiz habe ich nicht übernommen."
        if b["status"] == "offen":
            return texte.TERMIN_VORBEI
        lage = {"freigegeben": "ist schon freigegeben", "aendern_wartet": "wird schon geändert",
                "verworfen": "ist schon verworfen", "verpasst": "hat den Termin verpasst"}.get(b["status"],
                                                                                         "ist schon entschieden")
        return f"«{b['titel']}» {lage}, die Notiz habe ich nicht übernommen."

    def _notiz_anfrage(self, m: dict) -> dict | None:
        """Gültige «Was soll ich ändern?»-Frage, auf die der Text antwortet. Mit Antwort-Bezug zählt genau
        diese Frage (veraltet: Hinweis an den Betreiber, Text wird normale Nachricht). Ohne Antwort-Bezug zählt die
        neueste gültige Frage, wenn sie höchstens 30 Minuten alt ist und keine Freitags-Fragen offen sind."""
        anfragen = self.s.lies("notiz_anfragen", [])
        if not anfragen or m["text"].strip().startswith("/"):
            return None
        bezug = (m.get("reply_to_message") or {}).get("message_id")
        if bezug is not None:
            a = next((a for a in anfragen if a["nachricht"] == bezug), None)
            if a is not None and self._anfrage_beitrag(a) is None:
                self._vergiss_notiz_anfragen(a["beitrag"])
                self._sende_sicher(self._veraltet_hinweis(a))
                return None
            return a
        if self._fragen_offen():
            return None
        grenze = self.jetzt() - NOTIZ_FENSTER
        frische = [a for a in anfragen if _zone(datetime.fromisoformat(a["zeit"])) >= grenze
                   and self._anfrage_beitrag(a) is not None]
        return frische[-1] if frische else None

    def _fragen_offen(self) -> bool:
        bis = self.s.lies("fragen_bis")
        return bis is not None and _zone(datetime.fromisoformat(bis)) > self.jetzt()

    # --- Zeitgeber und Abholen ---

    def zeitgeber(self) -> None:
        """Jede Minute: offene Beiträge nach dem Termin auf «verpasst», Montag ab 08:00 einmal erinnern.
        Erst Status und Ereignisse speichern, dann anzeigen. Die «verpasst»-Meldung bleibt vorgemerkt, bis
        Telegram sie angenommen hat, die Erinnerung gilt erst nach erfolgreichem Senden als erledigt."""
        with self.sperre:
            jetzt = self.jetzt()
            verpasst = []
            for b in self.s.beitraege():
                if self._vorbei(b):
                    b = self.s.setze(b["id"], status="verpasst")
                    self._vergiss_notiz_anfragen(b["nr"])
                    self._ereignis("verpasst", b)
                    verpasst.append(b)
            if verpasst:
                self.s.schreibe("verpasst_melden", self.s.lies("verpasst_melden", [])
                                + [{"beitrag": b["nr"], "version": b["version"]} for b in verpasst])
            for b in verpasst:
                self._zeige_sicher(b)
            self._melde_verpasste()
            for woche in dict.fromkeys(b["woche"] for b in verpasst):
                self._uebersicht_sicher(woche)
            if jetzt.weekday() == 0 and jetzt.hour >= ERINNERUNG_STUNDE:
                self._erinnere(f"erinnert-{jetzt:%G-W%V}", jetzt)

    def _melde_verpasste(self) -> None:
        """Vorgemerkte «verpasst»-Meldungen senden. Was scheitert, bleibt für den nächsten Durchgang."""
        rest = []
        for m in self.s.lies("verpasst_melden", []):
            b = self.s.beitrag_nr(m["beitrag"])
            if b is None or b["status"] != "verpasst" or b["version"] != m["version"]:
                continue
            try:
                self._sende(texte.verpasst_text(b))
            except TelegramFehler as e:
                LOG.warning("Verpasst-Meldung %s nicht gesendet: %s", b["nr"], str(e))
                rest.append(m)
        if rest != self.s.lies("verpasst_melden", []):
            self.s.schreibe("verpasst_melden", rest)

    def _erinnere(self, schluessel: str, jetzt: datetime) -> None:
        if self.s.lies(schluessel):
            return
        offen = [b for b in self.s.beitraege() if b["status"] == "offen" and self._termin(b) > jetzt]
        if offen:
            try:
                self._sende(texte.erinnerung(offen))
            except TelegramFehler as e:
                LOG.warning("Erinnerung nicht gesendet: %s", str(e))
                return
        self.s.schreibe(schluessel, True)

    def abholen(self, zeitlimit: int = 25) -> int | None:
        """Long Polling bei Telegram (zeitlimit = Telegram-timeout in Sekunden, die Verbindung wartet 30 s
        länger). None: noch nicht umgestellt (der Mac fragt Telegram noch selbst ab). getUpdates läuft ohne
        Sperre, damit API und Zeitgeber nicht warten. TelegramFehler gehen an den Aufrufer (Pause dort)."""
        with self.sperre:
            letzte = self.s.lies("update_id")
        if letzte is None:
            return None
        updates = self.tg("getUpdates", {"offset": letzte + 1, "timeout": zeitlimit,
                                         "allowed_updates": ["message", "callback_query"]}, zeitlimit + 30)
        for u in updates:
            self.verarbeite(u)
        return len(updates)
