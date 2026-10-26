import pytest

from lib import freigabe
from lib.manifest import ManifestFehler, lade, trage_ein
from lib.umgebung import Pfade

WOCHE = "2026-KW44"


def _thema(**ueber):
    t = {"nr": 1, "format": "reel", "slug": "drei-fehler", "termin": "2026-10-27T19:00",
         "thema": "Drei Fehler, die ich beim Trading-Start gemacht habe und heute anders mache"}
    t.update(ueber)
    return t


def test_beitrag_id_wie_die_bauer():
    assert freigabe.beitrag_id(WOCHE, _thema()) == "2026-KW44-reel-drei-fehler"
    assert freigabe.beitrag_id(WOCHE, _thema(format="karussell")) == "2026-KW44-drei-fehler"


def test_titel_kuerzt_an_wortgrenze():
    assert freigabe.titel_von(_thema(thema="Kurz und gut")) == "Kurz und gut"
    titel = freigabe.titel_von(_thema())
    assert len(titel) <= 60 and titel.endswith("…") and titel.startswith("Drei Fehler, die ich beim")
    assert not titel[:-1].endswith(" ")


def test_eintrag_mit_standardwerten_und_aendern(tmp_path):
    pfad = Pfade(basis=tmp_path).woche(WOCHE) / "manifest.json"
    assert freigabe.manifest_pfad(Pfade(basis=tmp_path), WOCHE) == pfad
    trage_ein(pfad, WOCHE, {"id": "a", "status": "entwurf", "caption": "caption.txt"})
    e = freigabe.eintrag(pfad, WOCHE, "a")
    assert (e["version"], e["neubauten"], e["notizen"], e["entschieden"]) == (1, 0, [], None)
    e["notizen"].append("nicht gespeichert")
    assert freigabe.eintrag(pfad, WOCHE, "a")["notizen"] == []
    neu = freigabe.aendere(pfad, WOCHE, "a", status="freigegeben", entschieden="2026-10-25T09:00:00+01:00")
    assert neu["status"] == "freigegeben" and neu["caption"] == "caption.txt"
    assert lade(pfad, WOCHE)["beitraege"][0]["entschieden"] == "2026-10-25T09:00:00+01:00"
    with pytest.raises(ManifestFehler):
        freigabe.aendere(pfad, WOCHE, "a", status="erledigt")
    with pytest.raises(ManifestFehler):
        freigabe.eintrag(pfad, WOCHE, "fehlt")
    with pytest.raises(ManifestFehler):
        freigabe.aendere(pfad, WOCHE, "fehlt", status="verworfen")


def test_anmeldung():
    e = {"id": "2026-KW44-reel-drei-fehler", "version": 2, "neubauten": 1}
    assert freigabe.anmeldung(WOCHE, _thema(thema="Drei Fehler"), e) == {
        "id": "2026-KW44-reel-drei-fehler", "woche": WOCHE, "version": 2, "titel": "Drei Fehler",
        "format": "reel", "termin": "2026-10-27T19:00", "neubauten": 1, "platzhalter": False}
    mit = {**e, "status": "braucht_eingabe"}
    assert freigabe.anmeldung(WOCHE, _thema(thema="Drei Fehler"), mit)["platzhalter"] is True
    assert freigabe.anmeldung(WOCHE, _thema(), {**e, "status": "entwurf"})["platzhalter"] is False


def test_braucht_eingabe_nie_freigegeben(tmp_path):
    """braucht_eingabe ist ein bestehender Status: verwerfen, verpassen und (nach Neubau) entwurf gehen,
    freigegeben nie."""
    pfad = Pfade(basis=tmp_path).woche(WOCHE) / "manifest.json"
    for id in ("a", "b", "c", "d"):
        trage_ein(pfad, WOCHE, {"id": id, "status": "braucht_eingabe"})
    assert "braucht_eingabe" in freigabe.STATUS
    with pytest.raises(ManifestFehler, match="Platzhalter"):
        freigabe.aendere(pfad, WOCHE, "a", status="freigegeben", entschieden="2026-10-25T09:00:00+01:00")
    assert freigabe.eintrag(pfad, WOCHE, "a")["status"] == "braucht_eingabe"
    assert freigabe.aendere(pfad, WOCHE, "b", status="verworfen")["status"] == "verworfen"
    assert freigabe.aendere(pfad, WOCHE, "c", status="verpasst")["status"] == "verpasst"
    assert freigabe.aendere(pfad, WOCHE, "d", status="entwurf", version=2)["status"] == "entwurf"
    assert freigabe.aendere(pfad, WOCHE, "d", status="freigegeben")["status"] == "freigegeben"
