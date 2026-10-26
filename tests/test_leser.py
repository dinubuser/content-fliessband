import pytest

from lib.leser import LeserFehler, lese_beitrag


def test_liest_alle_zehn_slides(karussell_quelle):
    b = lese_beitrag(karussell_quelle)
    assert [s.nummer for s in b.slides] == list(range(1, 11))


def test_slide_typen(karussell_quelle):
    b = lese_beitrag(karussell_quelle)
    assert [s.typ for s in b.slides] == ["hook", "text"] + ["schritt"] * 6 + ["text", "schluss"]


def test_schritt_nummer_wird_abgetrennt(karussell_quelle):
    s3 = lese_beitrag(karussell_quelle).slides[2]
    assert s3.schritt == 1
    assert s3.ueberschrift == "Zuerst der Notgroschen"


def test_hook_text(karussell_quelle):
    s1 = lese_beitrag(karussell_quelle).slides[0]
    assert s1.ueberschrift.startswith("Kein Geld zum Verlieren?")
    assert s1.text.startswith("Das Auto streikt")


def test_caption_ohne_trennlinie_mit_hashtags(karussell_quelle):
    c = lese_beitrag(karussell_quelle).caption
    assert c.startswith("Trading lernen, ohne das Haushaltsbudget")
    assert c.endswith("#geld")
    assert "---" not in c


def test_aenderungsprotokoll_wird_ignoriert(karussell_quelle):
    b = lese_beitrag(karussell_quelle)
    assert all("Änderung" not in s.ueberschrift for s in b.slides)


def test_fehlender_slides_abschnitt(tmp_path):
    f = tmp_path / "x.md"
    f.write_text("# Titel\n\n## Caption\nHallo\n", encoding="utf-8")
    with pytest.raises(LeserFehler, match="## Slides"):
        lese_beitrag(f)


def test_slide_ohne_ueberschrift(tmp_path):
    f = tmp_path / "x.md"
    f.write_text("## Slides\n\n**Slide 1 (Hook)**\nText: nur Text\n\n## Caption\nHallo\n", encoding="utf-8")
    with pytest.raises(LeserFehler, match="Slide 1"):
        lese_beitrag(f)


def test_fehlende_caption(tmp_path):
    f = tmp_path / "x.md"
    f.write_text("## Slides\n\n**Slide 1**\nÜberschrift: Hallo\n", encoding="utf-8")
    with pytest.raises(LeserFehler, match="## Caption"):
        lese_beitrag(f)


def _slides_quelle(tmp_path, slide1_text):
    q = tmp_path / "b.md"
    q.write_text(
        "## Slides\n\n**Slide 1**\nÜberschrift: Hallo\n" + slide1_text + "\n\n"
        "**Slide 2**\nÜberschrift: Ende\nText: Schluss.\n\n## Caption\nCap\n",
        encoding="utf-8",
    )
    return q


def test_zweiter_absatz_geht_nicht_verloren(tmp_path):
    q = _slides_quelle(tmp_path, "Text: Absatz eins.\n\nAbsatz zwei.")
    assert lese_beitrag(q).slides[0].text == "Absatz eins.\n\nAbsatz zwei."


def test_leerzeile_am_ende_fuegt_keinen_absatz_an(tmp_path):
    q = _slides_quelle(tmp_path, "Text: Eins.\nZwei.\n\n---\n")
    assert lese_beitrag(q).slides[0].text == "Eins.\nZwei."


def test_abschnitt_mit_zusatz_in_klammern():
    from lib.leser import abschnitt
    zeilen = ["## Caption (unverändert aus V2)", "Hallo", "## Andere", "x"]
    assert abschnitt(zeilen, "Caption") == ["Hallo"]
    assert abschnitt(["## Captions", "x"], "Caption") is None
    assert abschnitt(["## Caption", "y"], "Caption") == ["y"]


def test_caption_im_codeblock_ohne_hinweis(tmp_path):
    f = tmp_path / "k.md"
    f.write_text("## Slides\n\n**Slide 1**\nÜberschrift: Hallo\nText: x\n\n"
                 "## Caption\n\n```\nZeile eins.\n\n#tag\n```\n\nHinweis: nicht ändern.\n", encoding="utf-8")
    assert lese_beitrag(f).caption == "Zeile eins.\n\n#tag"
