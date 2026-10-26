import json
from datetime import date, datetime

import pytest

from lib.bauer import baue_karussell
from lib.manifest import ManifestFehler
from lib.renderer import ZuLangFehler

TERMIN = datetime(2026, 10, 23, 19, 0)


def test_baut_karussell_mit_manifest(tmp_path, karussell_quelle):
    ziel, eintrag = baue_karussell(karussell_quelle, termin=TERMIN, basis=tmp_path)
    assert ziel == tmp_path / "wochen" / "2026-KW43" / "beispiel-thema"
    assert len(list(ziel.glob("slide-*.png"))) == 10
    assert (ziel / "caption.txt").read_text(encoding="utf-8").startswith("Trading lernen")
    daten = json.loads((ziel.parent / "manifest.json").read_text(encoding="utf-8"))
    b = daten["beitraege"][0]
    assert b == eintrag
    assert b["id"] == "2026-KW43-beispiel-thema"
    assert b["format"] == "karussell"
    assert b["termin"] == "2026-10-23T19:00"
    assert b["medien"] == [f"slide-{n:02d}.png" for n in range(1, 11)]
    # Fixture enthält zwei [Platzhalter: …] und ein [prüfen: …]
    assert b["status"] == "braucht_eingabe"
    assert len(b["pruefungen"]["platzhalter"]) == 3
    assert b["pruefungen"]["risikohinweis"] is True


def test_zweiter_lauf_ersetzt(tmp_path, karussell_quelle):
    baue_karussell(karussell_quelle, termin=TERMIN, basis=tmp_path)
    ziel, _ = baue_karussell(karussell_quelle, termin=TERMIN, basis=tmp_path)
    daten = json.loads((ziel.parent / "manifest.json").read_text(encoding="utf-8"))
    assert len(daten["beitraege"]) == 1


def test_ohne_platzhalter_ist_status_entwurf(tmp_path):
    quelle = tmp_path / "2026-10-20_karussell_sauber.md"
    quelle.write_text(
        "## Slides\n\n**Slide 1**\nÜberschrift: Hallo\nText: Kurz.\n\n"
        "**Slide 2**\nÜberschrift: Tschüss\nText: Ende.\n\n## Caption\nSchöner Tag.\n",
        encoding="utf-8",
    )
    _, eintrag = baue_karussell(quelle, basis=tmp_path, heute=date(2026, 10, 20))
    assert eintrag["status"] == "entwurf"
    assert eintrag["termin"] is None


def test_abbruch_hinterlaesst_nichts(tmp_path):
    quelle = tmp_path / "2026-10-20_karussell_zu-lang.md"
    quelle.write_text(
        "## Slides\n\n**Slide 1**\nÜberschrift: Hallo\nText: " + "Wort " * 600 + "\n\n## Caption\nHallo\n",
        encoding="utf-8",
    )
    with pytest.raises(ZuLangFehler):
        baue_karussell(quelle, basis=tmp_path, heute=date(2026, 10, 20))
    woche = tmp_path / "wochen" / "2026-KW43"
    assert not (woche / "zu-lang").exists()
    assert not (woche / ".tmp-zu-lang").exists()
    assert not (woche / "manifest.json").exists()


def test_kaputtes_manifest_bricht_vor_dem_bauen_ab(tmp_path, karussell_quelle):
    woche = tmp_path / "wochen" / "2026-KW43"
    woche.mkdir(parents=True)
    (woche / "manifest.json").write_text("{kaputt", encoding="utf-8")
    with pytest.raises(ManifestFehler):
        baue_karussell(karussell_quelle, termin=TERMIN, basis=tmp_path)
    assert not (woche / "beispiel-thema").exists()
    assert not (woche / ".tmp-beispiel-thema").exists()
    assert (woche / "manifest.json").read_text(encoding="utf-8") == "{kaputt"


def test_bau_ergaenzt_start_satz(tmp_path, karussell_quelle, schnelles_karussell):
    from lib.pruefungen import START_STANDARD
    quelle = tmp_path / "2026-10-20_karussell_ohne-start.md"
    quelle.write_text(karussell_quelle.read_text(encoding="utf-8").replace("START", "Start"), encoding="utf-8")
    ziel, b = baue_karussell(quelle, termin=TERMIN, basis=tmp_path / "fb")
    assert b["pruefungen"]["start_ergaenzt"] is True
    assert START_STANDARD in (ziel / "caption.txt").read_text(encoding="utf-8")
