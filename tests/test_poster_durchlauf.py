"""Durchlauf Etappe 5 Mac und Server zusammen: Samstag senden und hochladen, Freigabe per Knopf, ein Karussell
wird verworfen (seine Dateien verschwinden aus der Mediathek), Vorwarnung, Posten zum Termin, der Mac übernimmt
«gepostet», die gepostete Version bleibt in der Mediathek. Echter Briefkasten (Ablauf, Poster, Speicher im RAM,
HTTP auf 127.0.0.1) mit falschem Telegram und falschem Instagram, echter lib.briefkasten.Briefkasten auf der
Mac-Seite, falsche Mediathek."""
import re
import sys
import threading
from datetime import datetime
from pathlib import Path

import pytest

from briefkasten.ablauf import ZONE, Ablauf
from briefkasten.api import baue_server
from briefkasten.poster import Poster
from briefkasten.speicher import Speicher
from lib import entscheide, woche
from lib.briefkasten import Briefkasten, http
from lib.freigabe import eintrag, manifest_pfad
from lib.manifest import schreibe_json

sys.path.append(str(Path(__file__).resolve().parents[1] / "server" / "tests"))
from hilfen_bk import FalschesInstagram  # noqa: E402

WOCHE = "2026-KW44"
REEL1 = "2026-KW44-reel-beispiel-reel-eins"
KARUSSELL2 = "2026-KW44-notgroschen-beispiel"
RESERVE = "2026-KW44-reserve-karussell"


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
        return [f["text"] for m, f in self.aufrufe if m == "sendMessage"]


@pytest.fixture
def server():
    tg, ig = ServerTelegram(), FalschesInstagram()
    uhr = [datetime(2026, 10, 23, 22, 0, tzinfo=ZONE)]
    ablauf = Ablauf(Speicher(":memory:"), tg, 42, jetzt=lambda: uhr[0])
    ablauf.umstellen(0)
    poster = Poster(ablauf, ig)
    http_server = baue_server(ablauf, "s", ("127.0.0.1", 0))
    threading.Thread(target=http_server.serve_forever, daemon=True).start()
    yield ablauf, poster, ig, tg, uhr, f"http://127.0.0.1:{http_server.server_address[1]}"
    http_server.shutdown()
    http_server.server_close()


@pytest.fixture
def ohne_platzhalter(agentur_attrappe):
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


def test_woche_wird_gepostet(server, wochen_umgebung, ohne_platzhalter, mediathek, schnell, schnelles_karussell):
    ablauf, poster, ig, tg, uhr, adresse = server
    u = wochen_umgebung
    schreibe_json(u.pfade.daten / "briefkasten.json", {"adresse": adresse, "nachrichten_bis": 0, "entscheide_bis": 0})
    bk = Briefkasten.lade(u.pfade.daten, anfrage=http(adresse, schluessel=lambda: "s"))
    a = ohne_platzhalter(fragen=0)
    log = []
    pfad = manifest_pfad(u.pfade, WOCHE)

    def dienste(jetzt):
        return u.dienste(a, jetzt=jetzt, briefkasten=bk, mediathek=mediathek)

    # Freitag: Betreiber schaltet den Poster über die Kommandozeile ein (Mac → HTTP → Server)
    assert bk.poster(True)["an"] is True
    assert ablauf.s.lies("poster_seit") is not None

    for schritt, jetzt in (("job-vorbereiten", datetime(2026, 10, 23, 22, 0)),
                           ("job-bauen", datetime(2026, 10, 24, 22, 0))):
        uhr[0] = jetzt.replace(tzinfo=ZONE)
        assert woche.fuehre_aus(schritt, WOCHE, u.pfade, dienste(jetzt), log.append) == 0

    # Samstag: alle vier Beiträge angemeldet, Dateien in der Mediathek, Adressen beim Server
    bs = {b["id"]: b for b in ablauf.s.beitraege(WOCHE)}
    assert len(bs) == 4
    for id, b in bs.items():
        p = ablauf.s.post(id)
        assert p is not None and p["version"] == 1 and p["medien"], id
        assert eintrag(pfad, WOCHE, id)["medien_gemeldet"] == 1
    reel = ablauf.s.post(REEL1)
    assert reel["medien"] == [f"https://example.com/wp-content/uploads/2026/10/fliessband-{REEL1}-v1-video.mp4"]
    assert reel["cover"].endswith(f"fliessband-{REEL1}-v1-cover.jpg")
    assert reel["caption"]
    karussell = ablauf.s.post(KARUSSELL2)
    assert len(karussell["medien"]) >= 2 and all(m.endswith(".jpg") for m in karussell["medien"])
    stand = bk.poster_stand()
    assert stand["an"] is True and stand["naechste"] == []   # noch nichts freigegeben

    # Sonntag: Betreiber gibt Reel 1 frei und verwirft Karussell 2
    uhr[0] = datetime(2026, 10, 25, 9, 0, tzinfo=ZONE)
    _knopf(ablauf, bs[REEL1], "f", 1)
    _knopf(ablauf, bs[KARUSSELL2], "vj", 2)
    weg = {x["wp_id"] for x in eintrag(pfad, WOCHE, KARUSSELL2)["mediathek"]}
    assert weg and not weg & set(mediathek.geloescht)
    assert entscheide.entscheide(u.pfade, dienste(datetime(2026, 10, 25, 9, 5)), log.append) == 2
    assert eintrag(pfad, WOCHE, REEL1)["status"] == "freigegeben"

    # Verworfenes Karussell: alle Dateien gelöscht und im Manifest vermerkt. Die Reserve ist gebaut, gesendet,
    # angemeldet und hochgeladen.
    k = eintrag(pfad, WOCHE, KARUSSELL2)
    assert k["status"] == "verworfen"
    assert set(mediathek.geloescht) == weg
    assert all(x["geloescht"] for x in k["mediathek"])
    r = eintrag(pfad, WOCHE, RESERVE)
    assert r["medien_gemeldet"] == 1 and ablauf.s.post(RESERVE)["medien"]
    assert ablauf.s.beitrag(RESERVE)["status"] == "offen"

    stand = bk.poster_stand()
    assert [(n["id"], n["post_status"], n["dateien"]) for n in stand["naechste"]] == [(REEL1, "geplant", True)]

    # Dienstag 18:00: Vorwarnung mit ⏸ Stopp
    b = ablauf.s.beitrag(REEL1)
    uhr[0] = datetime(2026, 10, 27, 18, 0, tzinfo=ZONE)
    poster.takt()
    assert tg.gesendet()[-1] == f"⏰ Um 19:00 geht «{b['titel']}» online."
    assert ig.methoden() == []

    # 19:00: Posten mit den Adressen vom Mac
    uhr[0] = datetime(2026, 10, 27, 19, 0, tzinfo=ZONE)
    poster.takt()
    assert tg.gesendet()[-1].startswith(f"✅ Gepostet: «{b['titel']}»")
    vorbereitet = [x for m, x in ig.aufrufe if m == "bereite_vor"]
    assert vorbereitet == [("reel", tuple(reel["medien"]), reel["cover"], reel["caption"])]
    assert ablauf.s.beitrag(REEL1)["status"] == "gepostet"
    uhr[0] = datetime(2026, 10, 27, 19, 1, tzinfo=ZONE)
    poster.takt()
    assert ig.methoden().count("bereite_vor") == 1   # kein zweiter Post

    # Mac: «gepostet» ins Manifest, die gepostete Version bleibt in der Mediathek
    geloescht_vorher = list(mediathek.geloescht)
    entscheide.entscheide(u.pfade, dienste(datetime(2026, 10, 27, 19, 10)), log.append)
    e = eintrag(pfad, WOCHE, REEL1)
    assert (e["status"], e["permalink"], e["instagram_id"]) == ("gepostet", "https://www.instagram.com/p/c1/", "m-c1")
    assert not {x["wp_id"] for x in e["mediathek"]} & set(mediathek.geloescht)
    assert mediathek.geloescht == geloescht_vorher
    assert " · gepostet · https://www.instagram.com/p/c1/" in woche.status_text(
        woche.Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE), {e["id"]: e}, umgestellt=True)
    assert not [z for z in log if z.startswith("Fehler") or "nicht gemeldet" in z or "nicht hochgeladen" in z]
