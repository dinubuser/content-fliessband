import json
import threading
import urllib.error
import urllib.request

import pytest
from hilfen_bk import daten

from briefkasten.api import baue_server

SCHLUESSEL = "test-schluessel"


@pytest.fixture
def adresse(ablauf):
    server = baue_server(ablauf, SCHLUESSEL, ("127.0.0.1", 0))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _rufe(adresse, methode, pfad, koerper=None, schluessel=SCHLUESSEL):
    kopf = {"Content-Type": "application/json"}
    if schluessel:
        kopf["Authorization"] = f"Bearer {schluessel}"
    req = urllib.request.Request(adresse + pfad, method=methode, headers=kopf,
                                 data=json.dumps(koerper).encode() if koerper is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_gesund_ohne_schluessel(adresse):
    assert _rufe(adresse, "GET", "/gesund", schluessel=None) == (200, {"ok": True})


@pytest.mark.parametrize("schluessel", [None, "falsch"])
def test_ohne_richtigen_schluessel(adresse, schluessel):
    assert _rufe(adresse, "POST", "/beitraege", daten(1), schluessel=schluessel)[0] == 401
    assert _rufe(adresse, "GET", "/ereignisse?nach=0&arten=nachricht", schluessel=schluessel)[0] == 401


def test_ablauf_ueber_http(adresse, ablauf, tg):
    code, b = _rufe(adresse, "POST", "/beitraege", daten(1))
    assert code == 200 and b["status"] == "offen" and b["nachricht_id"] == 501
    assert _rufe(adresse, "POST", "/wochen/2026-KW44/fertig", {}) == (200, {"ok": True})
    assert _rufe(adresse, "POST", "/fragen", {"bis": "2026-10-24T22:00"}) == (200, {"ok": True})
    assert _rufe(adresse, "POST", "/umstellen", {"update_id": 41}) == (200, {"update_id": 41})
    ablauf.s.setze(b["id"], status="aendern_wartet")
    assert _rufe(adresse, "POST", f"/beitraege/{b['id']}/fehler", {"grund": "zu lang"}) == (200, {"ok": True})
    ablauf.s.ereignis("2026-10-25T09:00:00+01:00", "freigegeben", beitrag=b["id"], woche="2026-KW44", version=1)
    code, antwort = _rufe(adresse, "GET", "/ereignisse?nach=0&arten=freigegeben,aendern")
    assert code == 200 and [e["art"] for e in antwort["ereignisse"]] == ["freigegeben"]


def test_fehlerfaelle(adresse, tg):
    assert _rufe(adresse, "POST", "/beitraege", daten(1, format="video"))[0] == 400
    assert _rufe(adresse, "POST", "/beitraege/fehlt/fehler", {"grund": "x"})[0] == 400
    assert _rufe(adresse, "GET", "/ereignisse?nach=0&arten=geheim")[0] == 400
    assert _rufe(adresse, "POST", "/gibtsnicht", {})[0] == 404
    tg.scheitern_bei = "sendMessage"
    code, antwort = _rufe(adresse, "POST", "/beitraege", daten(2))
    assert code == 502 and "nicht erreichbar" in antwort["fehler"]


def _roh(adresse, pfad, rohkoerper: bytes, laenge=None):
    import http.client
    host, port = adresse.removeprefix("http://").split(":")
    c = http.client.HTTPConnection(host, int(port), timeout=5)
    c.putrequest("POST", pfad)
    c.putheader("Authorization", f"Bearer {SCHLUESSEL}")
    c.putheader("Content-Length", str(len(rohkoerper) if laenge is None else laenge))
    c.endheaders(rohkoerper)
    r = c.getresponse()
    return r.status, json.loads(r.read())


def test_ungueltige_koerper(adresse):
    assert _roh(adresse, "/beitraege", b"", laenge=-1)[0] == 400
    assert _roh(adresse, "/beitraege", b"{kaputt")[0] == 400
    assert _roh(adresse, "/beitraege", b"[1, 2]")[0] == 400


def test_ungueltige_zahlen(adresse):
    assert _rufe(adresse, "GET", f"/ereignisse?nach={10**30}&arten=nachricht")[0] == 400
    assert _rufe(adresse, "GET", "/ereignisse?nach=-1&arten=nachricht")[0] == 400
    for falsch in (True, 1.5, "7", -3, 10**30):
        assert _rufe(adresse, "POST", "/umstellen", {"update_id": falsch})[0] == 400
    assert _rufe(adresse, "POST", "/umstellen", {"update_id": 0}) == (200, {"update_id": 0})


def test_interner_fehler_ohne_details(adresse, ablauf):
    def kaputt(*a, **k):
        raise RuntimeError("geheim-123")
    ablauf.melde_beitrag = kaputt
    code, antwort = _rufe(adresse, "POST", "/beitraege", daten(1))
    assert code == 500 and antwort == {"fehler": "interner Fehler"}


@pytest.fixture
def api_poster(ablauf):
    from hilfen_bk import FalschesInstagram

    from briefkasten.poster import Poster
    Poster(ablauf, FalschesInstagram())
    server = baue_server(ablauf, SCHLUESSEL, ("127.0.0.1", 0))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    adr = f"http://127.0.0.1:{server.server_address[1]}"
    yield ablauf, lambda methode, pfad, koerper=None: _rufe(adr, methode, pfad, koerper)
    server.shutdown()
    server.server_close()


def test_medien_und_poster(api_poster):
    ablauf, rufe = api_poster
    b = ablauf.melde_beitrag(daten(1))
    code, antwort = rufe("POST", f"/beitraege/{b['id']}/medien",
                         {"version": 1, "medien": ["https://example.com/v.mp4"], "cover": None, "caption": "C"})
    assert code == 200 and antwort["medien"] == ["https://example.com/v.mp4"]
    assert rufe("POST", f"/beitraege/{b['id']}/medien", {"version": 2, "medien": [], "caption": "C"})[0] == 400
    assert rufe("GET", "/poster")[1]["an"] is False
    assert rufe("POST", "/poster", {"an": True})[1]["an"] is True
    assert rufe("POST", "/poster", {"an": "ja"})[0] == 400


def test_ereignisse_gepostet_abrufbar(api_poster):
    _, rufe = api_poster
    assert rufe("GET", "/ereignisse?nach=0&arten=gepostet,ausgelassen") == (200, {"ereignisse": []})


def test_poster_adressen_ohne_poster_unbekannt(adresse):
    assert _rufe(adresse, "GET", "/poster")[0] == 404
    assert _rufe(adresse, "POST", "/poster", {"an": True})[0] == 404


def test_facebook_adressen(ablauf):
    from hilfen_bk import FalschesFacebook, FalschesInstagram

    from briefkasten.poster import Poster
    Poster(ablauf, FalschesInstagram(), FalschesFacebook())
    server = baue_server(ablauf, SCHLUESSEL, ("127.0.0.1", 0))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    adr = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        assert _rufe(adr, "GET", "/facebook") == (200, {"an": False, "schluessel": True, "posts": []})
        assert _rufe(adr, "POST", "/facebook", {"an": True})[1]["an"] is True
        assert _rufe(adr, "POST", "/facebook", {"an": "ja"})[0] == 400
        assert _rufe(adr, "GET", "/facebook", schluessel="falsch")[0] == 401
    finally:
        server.shutdown()
        server.server_close()


def test_facebook_ohne_facebook_400(api_poster):
    _, rufe = api_poster
    code, antwort = rufe("POST", "/facebook", {"an": True})
    assert code == 400 and "nicht eingerichtet" in antwort["fehler"]


def test_zahlen_ueber_http(api_poster):
    ablauf, rufe = api_poster
    ablauf.poster.ig.medien_liste = [{"id": "m1", "timestamp": "2026-10-20T17:00:05+0000", "media_type": "IMAGE"}]
    code, antwort = rufe("GET", "/zahlen?tage=28")
    assert code == 200 and antwort["beitraege"][0]["ig_id"] == "m1"
    assert rufe("GET", "/zahlen")[0] == 200
    assert rufe("GET", "/zahlen?tage=0")[0] == 400
    assert rufe("GET", "/zahlen?tage=91")[0] == 400
    assert rufe("GET", "/zahlen?tage=x")[0] == 400


def test_zahlen_instagram_fehler(api_poster):
    from briefkasten.instagram import InstagramFehler
    ablauf, rufe = api_poster
    ablauf.poster.ig.zahlen_fehler = [InstagramFehler("Instagram-Schlüssel fehlt", ungueltig=True),
                                      InstagramFehler("Instagram nicht erreichbar (URLError)")]
    assert rufe("GET", "/zahlen") == (503, {"fehler": "Instagram-Schlüssel fehlt"})
    assert rufe("GET", "/zahlen") == (502, {"fehler": "Instagram nicht erreichbar (URLError)"})


def test_zahlen_ohne_poster_unbekannt(adresse):
    assert _rufe(adresse, "GET", "/zahlen")[0] == 404


def test_zahlen_antwort_ohne_instagram_schluessel(api_poster, tmp_path):
    from hilfen_bk import Antworten

    from briefkasten.instagram import Instagram, Schluessel
    geheim = "IGgeheim123"
    sl = Schluessel(tmp_path / "instagram.json")
    sl.speichere({"token": geheim, "erstellt": "2026-10-25", "user_id": "1784"})
    ablauf, rufe = api_poster
    ablauf.poster.ig = Instagram(sl, oeffne=Antworten(
        (400, {"error": {"message": f"bad token {geheim}", "code": 190}}),
        (400, {"error": {"message": f"kaputt {geheim}", "code": 1}})))
    code, antwort = rufe("GET", "/zahlen")
    assert code == 503 and geheim not in json.dumps(antwort)
    code, antwort = rufe("GET", "/zahlen")
    assert code == 502 and geheim not in json.dumps(antwort)


def test_kommentare_adressen(ablauf):
    from hilfen_bk import FalschesInstagram

    from briefkasten.kommentare import Kommentare
    Kommentare(ablauf, FalschesInstagram())
    server = baue_server(ablauf, SCHLUESSEL, ("127.0.0.1", 0))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    adr = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        code, stand = _rufe(adr, "GET", "/kommentare")
        assert code == 200 and stand["an"] is False and stand["start"] == 0
        assert _rufe(adr, "POST", "/kommentare", {"an": True})[1]["an"] is True
        assert _rufe(adr, "POST", "/kommentare", {"an": "ja"})[0] == 400
        assert _rufe(adr, "GET", "/kommentare", schluessel="falsch")[0] == 401
    finally:
        server.shutdown()
        server.server_close()


def test_kommentare_ohne_einrichtung_unbekannt(adresse):
    assert _rufe(adresse, "GET", "/kommentare")[0] == 404
    assert _rufe(adresse, "POST", "/kommentare", {"an": True})[0] == 404
