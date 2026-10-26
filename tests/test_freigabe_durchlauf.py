"""Durchlauf Mac und Server zusammen: echter Briefkasten (Ablauf, Speicher im RAM, HTTP auf 127.0.0.1) mit
falschem Telegram auf der Server-Seite, echter lib.briefkasten.Briefkasten auf der Mac-Seite."""
import re
import threading
from datetime import datetime

import pytest

from briefkasten.ablauf import ZONE, Ablauf
from briefkasten.api import baue_server
from briefkasten.speicher import Speicher
from lib import entscheide, woche
from lib.briefkasten import Briefkasten, http
from lib.freigabe import eintrag, manifest_pfad
from lib.manifest import schreibe_json
from lib.wochenplan import Wochenplan

WOCHE = "2026-KW44"


class ServerTelegram:
    def __init__(self):
        self.aufrufe, self._id = [], 700

    def __call__(self, methode, felder, zeitlimit=30):
        self.aufrufe.append((methode, felder))
        if methode == "sendMessage":
            self._id += 1
            return {"message_id": self._id}
        return True

    def gesendet(self):
        return [f for m, f in self.aufrufe if m == "sendMessage"]


@pytest.fixture
def server():
    tg = ServerTelegram()
    uhr = [datetime(2026, 10, 23, 22, 0, tzinfo=ZONE)]
    ablauf = Ablauf(Speicher(":memory:"), tg, 42, jetzt=lambda: uhr[0])
    ablauf.umstellen(0)
    http_server = baue_server(ablauf, "s", ("127.0.0.1", 0))
    threading.Thread(target=http_server.serve_forever, daemon=True).start()
    yield ablauf, tg, uhr, f"http://127.0.0.1:{http_server.server_address[1]}"
    http_server.shutdown()
    http_server.server_close()


@pytest.fixture
def ohne_platzhalter(agentur_attrappe):
    """Karussell-Texte ohne [Platzhalter], sonst werden Karussells und Reserve braucht_eingabe (keine Knöpfe)
    und «Ändern» scheitert an der Platzhalter-Prüfung."""
    class OhnePlatzhalter(agentur_attrappe):
        def claude(self, agent, auftrag, ausgabe, *args, **kwargs):
            pfad = super().claude(agent, auftrag, ausgabe, *args, **kwargs)
            if pfad.suffix == ".md" and "_reel_" not in pfad.name:
                pfad.write_text(re.sub(r"\[[^\]]+\]", "", pfad.read_text(encoding="utf-8")), encoding="utf-8")
            return pfad
    return OhnePlatzhalter


def _knopf(ablauf, b, art, update_id):
    ablauf.verarbeite({"update_id": update_id, "callback_query": {
        "id": f"q{update_id}", "data": f"{art}:{b['nr']}:{b['version']}",
        "message": {"message_id": b["nachricht_id"], "chat": {"id": 42}}}})


def _text(ablauf, text, update_id, antwort_auf):
    ablauf.verarbeite({"update_id": update_id, "message": {
        "message_id": 900 + update_id, "chat": {"id": 42, "type": "private"}, "text": text,
        "reply_to_message": {"message_id": antwort_auf}}})


def test_woche_mit_freigabe_aendern_verwerfen(server, wochen_umgebung, ohne_platzhalter, schnell,
                                              schnelles_karussell):
    ablauf, tg, uhr, adresse = server
    u = wochen_umgebung
    schreibe_json(u.pfade.daten / "briefkasten.json", {"adresse": adresse, "nachrichten_bis": 0, "entscheide_bis": 0})
    bk = Briefkasten.lade(u.pfade.daten, anfrage=http(adresse, schluessel=lambda: "s"))
    a = ohne_platzhalter(fragen=1)
    log = []

    # Freitag: Frage geht raus, die Frist wird beim Server gemeldet
    freitag = u.dienste(a, jetzt=datetime(2026, 10, 23, 22, 0), briefkasten=bk)
    assert woche.fuehre_aus("job-vorbereiten", WOCHE, u.pfade, freitag, log.append) == 0
    assert ablauf.s.lies("fragen_bis") == "2026-10-24T22:00"
    frage_id = Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE).themen[0]["frage_nachricht"]

    # Betreiber antwortet: Der Server legt die Nachricht ab, der Samstags-Bau holt sie dort
    _text(ablauf, "Glücksspiel, sagt der Kollege.", 1, frage_id)
    uhr[0] = datetime(2026, 10, 24, 22, 0, tzinfo=ZONE)
    samstag = u.dienste(a, jetzt=datetime(2026, 10, 24, 22, 0), briefkasten=bk)
    assert woche.fuehre_aus("job-bauen", WOCHE, u.pfade, samstag, log.append) == 0
    assert "getUpdates" not in u.telegram.methoden()
    content = [t for agent, t in a.auftraege if agent == "content-agent"]
    assert "Glücksspiel, sagt der Kollege." in content[0]

    # Server: 4 Knopf-Nachrichten und die Übersicht
    bs = ablauf.s.beitraege(WOCHE)
    assert len(bs) == 4 and all(b["status"] == "offen" and b["nachricht_id"] for b in bs)
    assert tg.gesendet()[-1]["text"].startswith("Freigabe 2026-KW44")

    # Sonntag: Betreiber gibt 1 frei, will 2 ändern, verwirft 4
    uhr[0] = datetime(2026, 10, 25, 9, 0, tzinfo=ZONE)
    _knopf(ablauf, bs[0], "f", 2)
    _knopf(ablauf, bs[1], "a", 3)
    _text(ablauf, "Slide 3 kürzer", 4, ablauf.s.lies("notiz_anfragen")[0]["nachricht"])
    _knopf(ablauf, bs[3], "vj", 5)

    sonntag = u.dienste(a, jetzt=datetime(2026, 10, 25, 9, 15), briefkasten=bk)
    assert entscheide.entscheide(u.pfade, sonntag, log.append) == 3

    pfad = manifest_pfad(u.pfade, WOCHE)
    assert eintrag(pfad, WOCHE, bs[0]["id"])["status"] == "freigegeben"
    zwei = eintrag(pfad, WOCHE, bs[1]["id"])
    assert (zwei["version"], zwei["notizen"][0]["text"]) == (2, "Slide 3 kürzer")
    assert eintrag(pfad, WOCHE, bs[3]["id"])["status"] == "verworfen"

    nach = {b["id"]: b for b in ablauf.s.beitraege(WOCHE)}
    assert (nach[bs[1]["id"]]["version"], nach[bs[1]["id"]]["status"]) == (2, "offen")
    assert nach["2026-KW44-reserve-karussell"]["status"] == "offen"
    assert len(nach) == 5
    assert entscheide.entscheide(u.pfade, sonntag, log.append) == 0
    assert not [z for z in log if z.startswith("Fehler")]


def _knoepfe(felder):
    return [k["text"] for reihe in felder["reply_markup"]["inline_keyboard"] for k in reihe]


def test_platzhalter_erst_aendern_dann_freigeben(server, wochen_umgebung, agentur_attrappe, schnell,
                                                 schnelles_karussell):
    """Karussell mit [Platzhalter] (braucht_eingabe): Knöpfe ohne Freigeben. Betreiber füllt die Platzhalter per Ändern,
    die neue Fassung (_v2, ohne Platzhalter) wird entwurf und bekommt den Freigeben-Knopf."""
    class FuelltPlatzhalter(agentur_attrappe):
        def claude(self, agent, auftrag, ausgabe, *args, **kwargs):
            pfad = super().claude(agent, auftrag, ausgabe, *args, **kwargs)
            if pfad.suffix == ".md" and re.search(r"_v\d+$", pfad.stem):
                pfad.write_text(re.sub(r"\[[^\]]+\]", "3000 Fr.", pfad.read_text(encoding="utf-8")),
                                encoding="utf-8")
            return pfad

    ablauf, tg, uhr, adresse = server
    u = wochen_umgebung
    schreibe_json(u.pfade.daten / "briefkasten.json", {"adresse": adresse, "nachrichten_bis": 0, "entscheide_bis": 0})
    bk = Briefkasten.lade(u.pfade.daten, anfrage=http(adresse, schluessel=lambda: "s"))
    a = FuelltPlatzhalter(fragen=0)
    log = []
    for schritt, jetzt in (("job-vorbereiten", datetime(2026, 10, 23, 22, 0)),
                           ("job-bauen", datetime(2026, 10, 24, 22, 0))):
        uhr[0] = jetzt.replace(tzinfo=ZONE)
        assert woche.fuehre_aus(schritt, WOCHE, u.pfade, u.dienste(a, jetzt=jetzt, briefkasten=bk), log.append) == 0

    id = "2026-KW44-notgroschen-beispiel"
    pfad = manifest_pfad(u.pfade, WOCHE)
    assert eintrag(pfad, WOCHE, id)["status"] == "braucht_eingabe"
    b = ablauf.s.beitrag(id)
    assert b["platzhalter"] is True and b["status"] == "offen"
    karte = tg.gesendet()[b["nachricht_id"] - 701]   # Nachrichten-IDs ab 701, eine pro sendMessage
    assert karte["text"].endswith("⚠️ Hat noch Platzhalter, bitte per ✏️ Ändern ergänzen.")
    assert _knoepfe(karte) == ["✏️ Ändern", "❌ Verwerfen"]
    assert "✅ Alle offenen freigeben" in _knoepfe(tg.gesendet()[-1])   # Übersicht: die Reels gehen noch

    # Sonntag: Freigeben geht nicht (alter Knopf), Ändern mit Notiz
    uhr[0] = datetime(2026, 10, 25, 9, 0, tzinfo=ZONE)
    _knopf(ablauf, b, "f", 2)
    assert ablauf.s.beitrag(id)["status"] == "offen" and ablauf.s.ereignisse(0, ["freigegeben"]) == []
    _knopf(ablauf, b, "a", 3)
    _text(ablauf, "Betrag ist 3000 Fr.", 4, ablauf.s.lies("notiz_anfragen")[0]["nachricht"])
    sonntag = u.dienste(a, jetzt=datetime(2026, 10, 25, 9, 15), briefkasten=bk)
    assert entscheide.entscheide(u.pfade, sonntag, log.append) == 1

    e = eintrag(pfad, WOCHE, id)
    assert (e["status"], e["version"], e["neubauten"]) == ("entwurf", 2, 1)
    neu = ablauf.s.beitrag(id)
    assert (neu["version"], neu["status"], neu["platzhalter"]) == (2, "offen", False)
    assert _knoepfe(tg.gesendet()[-1]) == ["✅ Freigeben", "✏️ Ändern", "❌ Verwerfen"]

    # Jetzt freigeben
    _knopf(ablauf, neu, "f", 5)
    assert entscheide.entscheide(u.pfade, sonntag, log.append) == 1
    assert eintrag(pfad, WOCHE, id)["status"] == "freigegeben"
