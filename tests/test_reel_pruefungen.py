from pathlib import Path

import pytest

from lib.pruefungen import (RISIKO_STANDARD, START_STANDARD, AusspracheFehler, lade_aussprache,
                            pruefe_reel, sprechbar)
from lib.reel_modell import Grafik, Reel, Szene


def _reel(caption="Hallo\n\n#tag", sprechtext="Mach mit."):
    s1 = Szene(1, True, "Trading ist spannend.", "Trading spannend")
    s2 = Szene(2, False, sprechtext, "Mach mit", grafik=Grafik("liste", ["a", "b"]))
    return Reel([s1, s2], caption)


def test_risikohinweis_ergaenzt_caption_und_szene():
    r = _reel()
    p = pruefe_reel(r)
    assert p["risikohinweis"] is True
    assert p["risikohinweis_ergaenzt"] == ["szene", "caption"]
    assert r.szenen[-1].hinweis == RISIKO_STANDARD
    assert RISIKO_STANDARD in r.caption
    assert r.caption.rstrip().endswith("#tag")


def test_risikohinweis_auf_bild_immer_auch_wenn_gesprochen():
    r = _reel(caption="Trading birgt Verlustrisiken. Kommentiere START.",
              sprechtext="Du kannst Geld verlieren, das Risiko ist echt.")
    p = pruefe_reel(r)
    assert p["risikohinweis_ergaenzt"] == ["szene"]
    assert r.szenen[-1].hinweis == RISIKO_STANDARD
    assert r.caption == "Trading birgt Verlustrisiken. Kommentiere START."


def test_risikolos_gilt_nicht_als_hinweis():
    r = _reel(caption="Trading birgt Verlustrisiken.", sprechtext="Das ist risikolos, kein Zeitverlust.")
    pruefe_reel(r)
    assert r.szenen[-1].hinweis == RISIKO_STANDARD


def test_platzhalter_in_allen_feldern():
    r = _reel(caption="Hallo [prüfen]")
    r.szenen[0].sprechtext = "Ich [Platzhalter: Wendepunkt] lerne."
    r.szenen[1].grafik = Grafik("zahl", ["[Zahl]", "b"])
    p = pruefe_reel(r)
    assert p["platzhalter"] == ["Szene 1: [Platzhalter: Wendepunkt]", "Szene 2: [Zahl]", "Caption: [prüfen]"]


def test_schreibweise_in_allen_feldern():
    r = _reel()
    r.szenen[0].sprechtext = "Grösse – Maß"
    r.szenen[0].einblendung = "Maß"
    r.szenen[1].grafik = Grafik("vergleich", ["Spaß", "b"])
    p = pruefe_reel(r)
    assert r.szenen[0].sprechtext == "Grösse, Mass"
    assert r.szenen[0].einblendung == "Mass"
    assert r.szenen[1].grafik.teile[0] == "Spass"
    assert p["schreibweise_korrekturen"] == 4


def test_lade_aussprache(tmp_path):
    f = tmp_path / "aussprache.txt"
    f.write_text("# Kommentar\nGlace → Eis\n\nDM → Direktnachricht\n", encoding="utf-8")
    assert lade_aussprache(f) == {"Glace": "Eis", "DM": "Direktnachricht"}


def test_aussprache_mehrere_woerter_verboten(tmp_path):
    f = tmp_path / "aussprache.txt"
    f.write_text("DM → Direkte Nachricht\n", encoding="utf-8")
    with pytest.raises(AusspracheFehler, match="Zeile 1"):
        lade_aussprache(f)


def test_sprechbar_ersetzt_wortweise_und_behaelt_satzzeichen():
    liste = {"Glace": "Eis", "DEMO": "Demo"}
    assert sprechbar("Eine Glace, bitte. Schreib DEMO!", liste) == "Eine Eis, bitte. Schreib Demo!"
    assert sprechbar("Glacestand", liste) == "Glacestand"


def test_mitgelieferte_liste_ist_gueltig():
    liste = lade_aussprache(Path(__file__).parent.parent / "aussprache.txt")
    assert liste["Glace"] == "Eis"


@pytest.mark.parametrize("zeile", ["Glace, → Eis", "Glace → Eis.", "(DM) → Direktnachricht"])
def test_aussprache_satzzeichen_am_rand_verboten(tmp_path, zeile):
    f = tmp_path / "aussprache.txt"
    f.write_text(f"# Kommentar\n{zeile}\n", encoding="utf-8")
    with pytest.raises(AusspracheFehler, match="Zeile 2"):
        lade_aussprache(f)


def test_aussprache_satzzeichen_innen_erlaubt(tmp_path):
    f = tmp_path / "aussprache.txt"
    f.write_text("E-Mail → Imehl\n", encoding="utf-8")
    assert lade_aussprache(f) == {"E-Mail": "Imehl"}


def test_bild_hinweise_gesammelt():
    r = Reel([Szene(1, True, "Hallo", "Hallo"),
              Szene(2, False, "a", "b", bild_hinweise=["Szene 2: Haltung 'tanzt' unbekannt, Figur steht"]),
              Szene(3, False, "c", "d", bild_hinweise=["Szene 3: keine Zeile 'Bild:', Figur steht"])], "Caption")
    p = pruefe_reel(r)
    assert p["bild_hinweise"] == ["Szene 2: Haltung 'tanzt' unbekannt, Figur steht",
                                  "Szene 3: keine Zeile 'Bild:', Figur steht"]



def test_reel_start_satz_ergaenzt():
    r = _reel()
    p = pruefe_reel(r)
    assert p["start_ergaenzt"] is True and START_STANDARD in r.caption
    assert r.caption.rstrip().endswith("#tag")


def test_reel_start_schluss_fehlt_gemeldet():
    assert pruefe_reel(_reel())["start_schluss_fehlt"] is True
    assert pruefe_reel(_reel(sprechtext="Kommentiere START."))["start_schluss_fehlt"] is False
