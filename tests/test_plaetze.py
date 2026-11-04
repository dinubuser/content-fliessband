"""Schalter «Plätze pro Woche»: 4 (Standard) oder 6 (Mo Karussell und Fr Reel dazu)."""
import json
from pathlib import Path

from lib import cli, kalender
from lib.kalender import termine
from lib.planer import auftrag, plane
from lib.umgebung import Pfade


def test_standard_bleibt_vier_termine_wie_bisher():
    t = termine("2026-KW46")
    assert [(x["nr"], x["format"], x["termin"][:10]) for x in t] == [
        (1, "reel", "2026-11-10"), (2, "karussell", "2026-11-11"),
        (3, "reel", "2026-11-12"), (4, "karussell", "2026-11-14")]


def test_sechs_plaetze_chronologisch_nummeriert():
    t = termine("2026-KW46", plaetze=6)
    assert [(x["nr"], x["format"], x["termin"][:10]) for x in t] == [
        (1, "karussell", "2026-11-09"), (2, "reel", "2026-11-10"), (3, "karussell", "2026-11-11"),
        (4, "reel", "2026-11-12"), (5, "reel", "2026-11-13"), (6, "karussell", "2026-11-14")]
    assert sorted(x["termin"] for x in t) == [x["termin"] for x in t]
    assert all(x["termin"].endswith("T19:00") for x in t)


def test_sechs_plaetze_drei_reels_drei_karussells():
    t = termine("2026-KW46", plaetze=6)
    assert sorted(x["format"] for x in t) == ["karussell"] * 3 + ["reel"] * 3


def test_reel_laengen_im_sechser_modus():
    # KW46 ist gerade: Di kurz, Do mittel (wie im Vierer-Modus), das Zusatz-Reel am Freitag immer kurz
    laengen = {x["termin"][:10]: x.get("laenge") for x in termine("2026-KW46", plaetze=6)}
    assert laengen["2026-11-10"] == "kurz"
    assert laengen["2026-11-12"] == "mittel"
    assert laengen["2026-11-13"] == "kurz"
    assert laengen["2026-11-09"] is None


def test_vierer_modus_laengen_unveraendert():
    assert [x.get("laenge") for x in termine("2026-KW45")] == ["mittel", None, "kurz", None]


def test_ungueltige_plaetze_gelten_als_vier(tmp_path):
    assert kalender.plaetze(tmp_path) == 4
    (tmp_path / "daten").mkdir()
    for inhalt in ('{"plaetze": 5}', "kaputt", '{"plaetze": "6"}', "[]"):
        (tmp_path / "daten" / "plaetze.json").write_text(inhalt, encoding="utf-8")
        assert kalender.plaetze(tmp_path) == 4


def test_cli_plaetze_setzen_und_status(tmp_path, capsys):
    assert cli.main(["plaetze", "status", "--basis", str(tmp_path)]) == 0
    assert capsys.readouterr().out == "Plätze pro Woche: 4\n"
    assert cli.main(["plaetze", "6", "--basis", str(tmp_path)]) == 0
    assert capsys.readouterr().out == "Plätze pro Woche: 6\n"
    assert json.loads((tmp_path / "daten" / "plaetze.json").read_text(encoding="utf-8")) == {"plaetze": 6}
    assert kalender.plaetze(tmp_path) == 6
    assert cli.main(["plaetze", "4", "--basis", str(tmp_path)]) == 0
    assert kalender.plaetze(tmp_path) == 4


def test_auftrag_nennt_formate_aus_den_terminen():
    pfade = Pfade(basis=Path("/x"))
    text = auftrag(pfade.basis / "e.md", pfade.basis / "t.json", pfade, termine("2026-KW46", plaetze=6), True)
    assert "6 Beiträge und 2 Reserve-Themen" in text
    assert "Thema 1 Karussell, Thema 2 Reel, Thema 3 Karussell, Thema 4 Reel, Thema 5 Reel, Thema 6 Karussell" in text
    assert "alle 8 verschieden" in text
    assert "Höchstens 2 der 6 Themen" in text


def test_auftrag_vierer_text_bleibt_inhaltlich_gleich():
    pfade = Pfade(basis=Path("/x"))
    text = auftrag(pfade.basis / "e.md", pfade.basis / "t.json", pfade, termine("2026-KW46"), True)
    assert "4 Beiträge und 2 Reserve-Themen" in text
    assert "Thema 1 Reel, Thema 2 Karussell, Thema 3 Reel, Thema 4 Karussell" in text
    assert "alle 6 verschieden" in text
    assert "Höchstens 2 der 4 Themen" in text


def test_plane_nimmt_plaetze_aus_dem_schalter(tmp_path):
    pfade = Pfade(basis=tmp_path)
    (tmp_path / "daten").mkdir()
    (tmp_path / "daten" / "plaetze.json").write_text('{"plaetze": 6}', encoding="utf-8")
    gesehen = {}

    def lauf(agent, text, ausgabe, **mehr):
        gesehen["text"] = text
        raise AssertionError("stop")

    try:
        plane(pfade, "2026-KW46", [], [], lauf)
    except AssertionError:
        pass
    assert "6 Beiträge" in gesehen["text"]
