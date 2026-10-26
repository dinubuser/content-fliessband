import io
import json
import urllib.error
from datetime import datetime

import pytest

from lib.briefkasten import Briefkasten, BriefkastenFehler, http, umstellen
from lib.manifest import schreibe_json


class Antwort(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_http_mit_schluessel_und_fehlern():
    gesehen = []

    def oeffne(req, timeout):
        gesehen.append(req)
        return Antwort(b'{"ok": true}')
    anfrage = http("http://server:8096/", schluessel=lambda: "geheim", oeffne=oeffne)
    assert anfrage("POST", "/beitraege", {"id": "x"}) == {"ok": True}
    req = gesehen[0]
    assert req.full_url == "http://server:8096/beitraege" and req.get_method() == "POST"
    assert req.get_header("Authorization") == "Bearer geheim" and json.loads(req.data) == {"id": "x"}

    def http_fehler(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 400, "x", {}, io.BytesIO(b'{"fehler": "Beitrag ungueltig"}'))
    with pytest.raises(BriefkastenFehler, match="HTTP 400 Beitrag ungueltig") as e:
        http("http://s", schluessel=lambda: "geheim", oeffne=http_fehler)("POST", "/beitraege", {})
    assert "geheim" not in str(e.value) and e.value.code == 400

    def weg(req, timeout):
        raise urllib.error.URLError("keine Route")
    with pytest.raises(BriefkastenFehler, match="nicht erreichbar") as e:
        http("http://s", schluessel=lambda: "geheim", oeffne=weg)("GET", "/gesund")
    assert e.value.code is None


class Aufzeichnung:
    def __init__(self, antworten=None):
        self.aufrufe, self.antworten = [], antworten or {}

    def __call__(self, methode, pfad, daten=None):
        self.aufrufe.append((methode, pfad, daten))
        return self.antworten.get(pfad.split("?")[0], {"ok": True})


def test_briefkasten_aufrufe_und_lesestand(tmp_path):
    assert Briefkasten.lade(tmp_path) is None
    schreibe_json(tmp_path / "briefkasten.json", {"adresse": "http://s", "nachrichten_bis": 0, "entscheide_bis": 4})
    a = Aufzeichnung({"/ereignisse": {"ereignisse": [{"nr": 5}]}})
    bk = Briefkasten.lade(tmp_path, anfrage=a)
    bk.melde({"id": "x"})
    bk.fertig("2026-KW44")
    bk.fehler("2026-KW44-reel-a b", "zu lang")
    bk.fragen_offen(datetime(2026, 10, 24, 22, 0))
    assert bk.ereignisse("entscheide") == [{"nr": 5}]
    bk.merke("entscheide", 5)
    bk.merke("entscheide", 3)
    assert a.aufrufe == [
        ("POST", "/beitraege", {"id": "x"}),
        ("POST", "/wochen/2026-KW44/fertig", {}),
        ("POST", "/beitraege/2026-KW44-reel-a%20b/fehler", {"grund": "zu lang"}),
        ("POST", "/fragen", {"bis": "2026-10-24T22:00"}),
        ("GET", "/ereignisse?nach=4&arten=freigegeben,zurueckgenommen,aendern,verworfen,verpasst,gepostet,ausgelassen", None)]
    assert json.loads((tmp_path / "briefkasten.json").read_text())["entscheide_bis"] == 5
    bk.ereignisse("nachrichten")
    assert a.aufrufe[-1] == ("GET", "/ereignisse?nach=0&arten=nachricht", None)


class Bot:
    def __init__(self):
        self.gesammelt = 0
        self.letzte_update_id = 41

    def sammle(self):
        self.gesammelt += 1
        return 0


def test_umstellen(tmp_path):
    a = Aufzeichnung({"/umstellen": {"update_id": 41}})
    bot = Bot()
    assert umstellen(tmp_path, "http://your-server-ip:8096", bot, anfrage=a) == 41
    assert bot.gesammelt == 1
    assert a.aufrufe == [("GET", "/gesund", None), ("POST", "/umstellen", {"update_id": 41})]
    assert json.loads((tmp_path / "briefkasten.json").read_text()) == {
        "adresse": "http://your-server-ip:8096", "nachrichten_bis": 0, "entscheide_bis": 0}
    with pytest.raises(BriefkastenFehler, match="Schon umgestellt"):
        umstellen(tmp_path, "http://x", bot, anfrage=a)


def test_umstellen_server_weg_aendert_nichts(tmp_path):
    def weg(methode, pfad, daten=None):
        raise BriefkastenFehler("Briefkasten nicht erreichbar (URLError)")
    bot = Bot()
    with pytest.raises(BriefkastenFehler):
        umstellen(tmp_path, "http://x", bot, anfrage=weg)
    assert bot.gesammelt == 0 and not (tmp_path / "briefkasten.json").exists()


def test_kaputter_stand(tmp_path):
    (tmp_path / "briefkasten.json").write_text("{kaputt", encoding="utf-8")
    with pytest.raises(BriefkastenFehler, match="kaputt"):
        Briefkasten.lade(tmp_path, anfrage=Aufzeichnung()).ereignisse("entscheide")


def test_fehlergrund_gekuerzt(tmp_path):
    schreibe_json(tmp_path / "briefkasten.json", {"adresse": "http://s"})
    a = Aufzeichnung()
    Briefkasten.lade(tmp_path, anfrage=a).fehler("x", "a" * 2000)
    assert len(a.aufrufe[0][2]["grund"]) == 500


def test_merke_liest_frisch_unter_sperre(tmp_path):
    schreibe_json(tmp_path / "briefkasten.json", {"adresse": "http://s", "nachrichten_bis": 0, "entscheide_bis": 0})
    alt = Briefkasten.lade(tmp_path, anfrage=Aufzeichnung())
    zweiter = Briefkasten.lade(tmp_path, anfrage=Aufzeichnung())
    alt.merke("entscheide", 7)
    zweiter.merke("nachrichten", 3)
    alt.merke("nachrichten", 2)
    stand = json.loads((tmp_path / "briefkasten.json").read_text())
    assert stand["entscheide_bis"] == 7 and stand["nachrichten_bis"] == 3
    assert (tmp_path / "briefkasten.json.sperre").exists()


def test_umstellen_warnt_bei_anderer_update_id(tmp_path):
    a = Aufzeichnung({"/umstellen": {"update_id": 12}})
    with pytest.raises(BriefkastenFehler, match="update_id 12 statt 41"):
        umstellen(tmp_path, "http://s", Bot(), anfrage=a)
    # Server fragt schon ab: Mac darf nicht mehr selbst abfragen, darum Stand trotzdem geschrieben
    assert (tmp_path / "briefkasten.json").exists()


def test_quote_ohne_schraegstrich(tmp_path):
    schreibe_json(tmp_path / "briefkasten.json", {"adresse": "http://s"})
    a = Aufzeichnung()
    bk = Briefkasten.lade(tmp_path, anfrage=a)
    bk.fehler("a/b", "x")
    bk.fertig("2026/KW44")
    assert a.aufrufe[0][1] == "/beitraege/a%2Fb/fehler" and a.aufrufe[1][1] == "/wochen/2026%2FKW44/fertig"


def test_http_unerwartete_antworten():
    def kaputt(req, timeout):
        return Antwort(b"<html>")
    with pytest.raises(BriefkastenFehler, match="unerwartete Antwort"):
        http("http://s", schluessel=lambda: "k", oeffne=kaputt)("GET", "/gesund")

    def fehler_liste(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 500, "x", {}, io.BytesIO(b'["x"]'))
    with pytest.raises(BriefkastenFehler, match="HTTP 500"):
        http("http://s", schluessel=lambda: "k", oeffne=fehler_liste)("GET", "/gesund")

    class Kaputt(io.BytesIO):
        def read(self, *a):
            raise ConnectionResetError
    def fehler_lesen(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "x", {}, Kaputt())
    with pytest.raises(BriefkastenFehler, match="HTTP 401"):
        http("http://s", schluessel=lambda: "k", oeffne=fehler_lesen)("GET", "/gesund")


def test_medien_poster_und_ereignis_arten(tmp_path):
    from lib.briefkasten import ARTEN, Briefkasten
    from lib.manifest import schreibe_json
    schreibe_json(tmp_path / "briefkasten.json", {"adresse": "http://x", "entscheide_bis": 0, "nachrichten_bis": 0})
    aufrufe = []

    def anfrage(methode, pfad, daten=None):
        aufrufe.append((methode, pfad, daten))
        return {"an": True, "naechste": []} if "poster" in pfad else {"ok": True}
    bk = Briefkasten.lade(tmp_path, anfrage=anfrage)
    bk.medien("2026-KW44-reel-x", {"version": 1, "medien": ["https://example.com/v.mp4"], "cover": None, "caption": "C"})
    assert bk.poster(True) == {"an": True, "naechste": []}
    assert bk.poster_stand()["an"] is True
    assert aufrufe == [
        ("POST", "/beitraege/2026-KW44-reel-x/medien",
         {"version": 1, "medien": ["https://example.com/v.mp4"], "cover": None, "caption": "C"}),
        ("POST", "/poster", {"an": True}),
        ("GET", "/poster", None)]
    assert {"gepostet", "ausgelassen"} <= set(ARTEN["entscheide"])


def test_zahlen(tmp_path):
    aufrufe = []

    def anfrage(methode, pfad, daten=None, zeitlimit=None):
        aufrufe.append((methode, pfad, zeitlimit))
        return {"beitraege": [{"ig_id": "m1"}]}

    bk = Briefkasten(tmp_path / "briefkasten.json", anfrage)
    assert bk.zahlen() == [{"ig_id": "m1"}]
    assert bk.zahlen(14) == [{"ig_id": "m1"}]
    assert aufrufe == [("GET", "/zahlen?tage=28", 180), ("GET", "/zahlen?tage=14", 180)]


def test_http_gibt_zeitlimit_weiter():
    zeiten = []

    def oeffne(req, timeout):
        zeiten.append(timeout)
        return Antwort(b'{}')
    anfrage = http("http://s", schluessel=lambda: "k", oeffne=oeffne)
    anfrage("GET", "/x")
    anfrage("GET", "/zahlen", zeitlimit=180)
    assert zeiten == [20, 180]


def test_kommentare_aufrufe(tmp_path):
    aufrufe = []

    def anfrage(methode, pfad, daten=None):
        aufrufe.append((methode, pfad, daten))
        return {"an": True}

    bk = Briefkasten(tmp_path / "briefkasten.json", anfrage)
    assert bk.kommentare(True) == {"an": True}
    bk.kommentare_stand()
    assert aufrufe == [("POST", "/kommentare", {"an": True}), ("GET", "/kommentare", None)]
