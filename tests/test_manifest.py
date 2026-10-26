import json
from datetime import date, datetime
from pathlib import Path

import pytest

from lib import manifest


def test_woche_aus_heute():
    assert manifest.woche_von(None, date(2026, 10, 20)) == "2026-KW43"


def test_woche_aus_termin():
    assert manifest.woche_von(datetime(2026, 10, 28, 19, 0), date(2026, 10, 20)) == "2026-KW44"


def test_iso_jahr_am_jahreswechsel():
    assert manifest.woche_von(None, date(2027, 1, 1)) == "2026-KW53"


def test_slug():
    assert manifest.slug_von(Path("2026-10-15_karussell_beispiel-thema_v2.md")) == "beispiel-thema"
    assert manifest.slug_von(Path("2026-10-15_reel_notgroschen.md")) == "notgroschen"


def test_eintrag_wird_ersetzt_statt_verdoppelt(tmp_path):
    m = tmp_path / "manifest.json"
    manifest.trage_ein(m, "2026-KW43", {"id": "a", "status": "entwurf"})
    manifest.trage_ein(m, "2026-KW43", {"id": "b", "status": "entwurf"})
    manifest.trage_ein(m, "2026-KW43", {"id": "a", "status": "braucht_eingabe"})
    daten = json.loads(m.read_text(encoding="utf-8"))
    assert daten["woche"] == "2026-KW43"
    assert [(b["id"], b["status"]) for b in daten["beitraege"]] == [("a", "braucht_eingabe"), ("b", "entwurf")]
    assert not (tmp_path / "manifest.json.tmp").exists()


def test_lade_ohne_datei_gibt_leeres_manifest(tmp_path):
    assert manifest.lade(tmp_path / "manifest.json", "2026-KW43") == {"woche": "2026-KW43", "beitraege": []}


def test_lade_kaputtes_json_wirft_manifestfehler(tmp_path):
    m = tmp_path / "manifest.json"
    m.write_text("{kaputt", encoding="utf-8")
    with pytest.raises(manifest.ManifestFehler) as e:
        manifest.lade(m, "2026-KW43")
    assert str(m) in str(e.value)
    with pytest.raises(manifest.ManifestFehler):
        manifest.trage_ein(m, "2026-KW43", {"id": "a"})


def test_schreibe_json_atomar_mit_ordner(tmp_path):
    ziel = tmp_path / "neu" / "daten.json"
    manifest.schreibe_json(ziel, {"ä": [1, 2]})
    assert json.loads(ziel.read_text(encoding="utf-8")) == {"ä": [1, 2]}
    assert "\"ä\"" in ziel.read_text(encoding="utf-8")
    assert not (tmp_path / "neu" / "daten.json.tmp").exists()
