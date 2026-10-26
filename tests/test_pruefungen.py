import pytest

from lib.modell import Beitrag, Slide
from lib.pruefungen import RISIKO_STANDARD, START_STANDARD, ergaenze_start, korrigiere_schreibweise, pruefe


def _beitrag(letzter_text="Speichern!", caption="Mehr dazu. Kommentiere START.\n\n#finanzenlernen"):
    return Beitrag(
        slides=[Slide(1, "hook", "Trading lernen", "Los gehts"),
                Slide(2, "schluss", "Speicher dir das", letzter_text)],
        caption=caption,
    )


def test_eszett_wird_ersetzt():
    assert korrigiere_schreibweise("Grüße und Spaß") == ("Grüsse und Spass", 2)


def test_gedankenstrich_im_text_wird_komma():
    assert korrigiere_schreibweise("Erst üben – dann traden") == ("Erst üben, dann traden", 1)


def test_gedankenstrich_zwischen_zahlen_wird_bis():
    assert korrigiere_schreibweise("10–20 Franken") == ("10 bis 20 Franken", 1)


def test_bindestrich_bleibt():
    assert korrigiere_schreibweise("Demo-Konto") == ("Demo-Konto", 0)


def test_fehlender_risikohinweis_wird_ergaenzt():
    b = _beitrag()
    p = pruefe(b)
    assert p["risikohinweis"] is True
    assert p["risikohinweis_ergaenzt"] == ["slide", "caption"]
    assert b.slides[-1].hinweis == RISIKO_STANDARD
    assert b.caption == f"Mehr dazu. Kommentiere START.\n\n{RISIKO_STANDARD}\n\n#finanzenlernen"


def test_vorhandener_risikohinweis_bleibt():
    b = _beitrag(letzter_text="Trading birgt Verlustrisiken.", caption="Das Verlustrisiko ist real.\n\n#x")
    p = pruefe(b)
    assert p["risikohinweis_ergaenzt"] == []
    assert b.slides[-1].hinweis is None


def test_kein_trading_kein_hinweis():
    b = Beitrag(slides=[Slide(1, "hook", "Familienzeit", "Zmorge am Sonntag")], caption="Schöner Sonntag")
    p = pruefe(b)
    assert p["risikohinweis"] is False
    assert p["risikohinweis_ergaenzt"] == []


def test_platzhalter_werden_gefunden():
    b = _beitrag(letzter_text="Trading birgt Verlustrisiken. [prüfen: stimmt das?]",
                 caption="Verlustrisiko. [Platzhalter: DM-Inhalt]")
    p = pruefe(b)
    assert p["platzhalter"] == ["Slide 2: [prüfen: stimmt das?]", "Caption: [Platzhalter: DM-Inhalt]"]


def test_schreibweise_wird_im_beitrag_korrigiert_und_gezaehlt():
    b = Beitrag(slides=[Slide(1, "hook", "Grösse – Maß", "")], caption="Verlustrisiko, Trading")
    p = pruefe(b)
    assert b.slides[0].ueberschrift == "Grösse, Mass"
    assert p["schreibweise_korrekturen"] == 2


def test_aufzaehlungsstrich_am_zeilenanfang_entfaellt():
    assert korrigiere_schreibweise("– Erstens\n– Zweitens") == ("Erstens\nZweitens", 2)


def test_strich_vor_satzzeichen_oder_zeilenende_entfaellt():
    assert korrigiere_schreibweise("Am Ende –.") == ("Am Ende.", 1)
    assert korrigiere_schreibweise("Warte –\nweiter") == ("Warte\nweiter", 1)


def test_strich_frisst_keine_zeilenumbrueche():
    assert korrigiere_schreibweise("Erst – \ndann") == ("Erst\ndann", 1)
    assert korrigiere_schreibweise("a – b\n\nc") == ("a, b\n\nc", 1)


@pytest.mark.parametrize("caption", ["Mehr dazu.\n\n#a #b\n\n", "Mehr dazu.\n\n#a #b  \n \n", "Mehr dazu.\n#a\n#b\n"])
def test_risikosatz_vor_hashtag_block_auch_mit_leerzeilen(caption):
    from lib.pruefungen import _vor_hashtags_einfuegen
    neu = _vor_hashtags_einfuegen(caption, "RISIKO")
    assert neu.startswith("Mehr dazu.\n\nRISIKO\n\n#a")
    assert neu.rstrip().endswith(("#b"))



def test_start_satz_vor_den_hashtags():
    b = _beitrag(caption="Mehr dazu.\n\n#finanzenlernen")
    p = pruefe(b)
    assert p["start_ergaenzt"] is True
    assert b.caption.index(START_STANDARD) < b.caption.index("#finanzenlernen")


def test_start_vorhanden_bleibt():
    b = _beitrag()
    assert pruefe(b)["start_ergaenzt"] is False and START_STANDARD not in b.caption


@pytest.mark.parametrize("caption, ergaenzt", [("Kommentiere START.", False), ("Kommentiere start.", True),
                                               ("Neustart #x", True), ("STARTEN", True)])
def test_ergaenze_start(caption, ergaenzt):
    neu, e = ergaenze_start(caption)
    assert e is ergaenzt and (START_STANDARD in neu) is ergaenzt


def test_start_schluss_fehlt_gemeldet():
    b = _beitrag()   # letzte Slide ohne START, Caption hat es
    assert pruefe(b)["start_schluss_fehlt"] is True
    b = _beitrag(letzter_text="Kommentiere START.")
    assert pruefe(b)["start_schluss_fehlt"] is False
