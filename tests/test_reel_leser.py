import pytest

from lib.reel_leser import LeserFehler, lese_reel
from lib.reel_modell import Bild


def _schreibe(tmp_path, szenen, caption="Hallo"):
    f = tmp_path / "2026-10-20_reel_test.md"
    f.write_text(f"## Szenen fürs Fliessband\n\n{szenen}\n\n## Caption\n\n{caption}\n", encoding="utf-8")
    return f


def test_liest_beispiel(reel_quelle):
    reel = lese_reel(reel_quelle)
    assert [s.nummer for s in reel.szenen] == [1, 2, 3, 4]
    assert reel.szenen[0].hook is True
    assert all(not s.hook for s in reel.szenen[1:])
    assert reel.szenen[0].einblendung == "Keine Zeit, kein Geld? Kenn ich."
    assert reel.szenen[0].grafik is None
    assert reel.szenen[1].grafik.art == "vergleich"
    assert reel.szenen[1].grafik.teile == ["Übungsgeld", "Haushaltsbudget"]
    assert reel.szenen[2].grafik.teile == ["1'000 Fr. Konto", "max. 10 Fr. pro Trade"]
    assert reel.szenen[3].grafik.art == "liste"
    assert reel.caption.startswith("Trading lernen")
    assert reel.caption.rstrip().endswith("#beispielalltag")
    assert reel.szenen[0].bild is None
    assert reel.szenen[1].bild == Bild("haelt", ["schild-demo"])
    assert reel.szenen[2].bild == Bild("zeigt", ["muenzen"])
    assert reel.szenen[3].bild == Bild("winkt", [])
    assert all(s.bild_hinweise == [] for s in reel.szenen)


def test_fehlender_abschnitt(tmp_path):
    f = tmp_path / "x.md"
    f.write_text("## Caption\nHallo\n", encoding="utf-8")
    with pytest.raises(LeserFehler, match="Szenen fürs Fliessband"):
        lese_reel(f)


def test_fehlender_sprechtext(tmp_path):
    f = _schreibe(tmp_path, "**Szene 1**\nEinblendung: Hallo")
    with pytest.raises(LeserFehler, match="Szene 1: 'Sprechtext:' fehlt"):
        lese_reel(f)


def test_fehlende_einblendung(tmp_path):
    f = _schreibe(tmp_path, "**Szene 1**\nSprechtext: Hallo")
    with pytest.raises(LeserFehler, match="Szene 1: 'Einblendung:' fehlt"):
        lese_reel(f)


def test_einblendung_zu_lang(tmp_path):
    f = _schreibe(tmp_path, "**Szene 1**\nSprechtext: Hallo\nEinblendung: eins zwei drei vier fünf sechs sieben")
    with pytest.raises(LeserFehler, match="Szene 1: Einblendung hat 7 Wörter"):
        lese_reel(f)


def test_unbekannte_grafik(tmp_path):
    f = _schreibe(tmp_path, "**Szene 1**\nSprechtext: Start\nEinblendung: Hi\n\n**Szene 2**\nSprechtext: Hallo\nEinblendung: Hi\nGrafik: torte | a | b")
    with pytest.raises(LeserFehler, match="Szene 2: unbekannte Grafik 'torte'"):
        lese_reel(f)


def test_grafik_falsche_teile(tmp_path):
    f = _schreibe(tmp_path, "**Szene 1**\nSprechtext: Start\nEinblendung: Hi\n\n**Szene 2**\nSprechtext: Hallo\nEinblendung: Hi\nGrafik: liste | a | b | c | d")
    with pytest.raises(LeserFehler, match="Szene 2: Grafik 'liste' braucht 2 bis 3 Teile"):
        lese_reel(f)


def test_szenen_luecke(tmp_path):
    f = _schreibe(tmp_path, "**Szene 1**\nSprechtext: A\nEinblendung: A\n\n**Szene 3**\nSprechtext: B\nEinblendung: B")
    with pytest.raises(LeserFehler, match="Szene 3 folgt auf Szene 1"):
        lese_reel(f)


def test_leere_caption(tmp_path):
    f = _schreibe(tmp_path, "**Szene 1**\nSprechtext: A\nEinblendung: A", caption="")
    with pytest.raises(LeserFehler, match="Caption"):
        lese_reel(f)


def test_unbekanntes_feld(tmp_path):
    f = _schreibe(tmp_path, "**Szene 1**\nSprechtext: Hallo\nEinblendung: Hi\nB-Roll: Kind im Garten")
    with pytest.raises(LeserFehler, match="Szene 1: unbekanntes Feld 'B-Roll:'"):
        lese_reel(f)


def test_folgezeile_wird_angehaengt(tmp_path):
    f = _schreibe(tmp_path, "**Szene 1**\nSprechtext: Start\nEinblendung: Hi\n\n**Szene 2**\nSprechtext: Hallo du,\nwie geht es dir?\n"
                            "Einblendung: Hi\nGrafik: liste | a\n| b")
    s = lese_reel(f).szenen[1]
    assert s.sprechtext == "Hallo du, wie geht es dir?"
    assert s.grafik.teile == ["a", "b"]


def test_folgezeile_zaehlt_fuer_einblendung(tmp_path):
    f = _schreibe(tmp_path, "**Szene 1**\nSprechtext: Hallo\nEinblendung: eins zwei drei\nvier fünf sechs sieben")
    with pytest.raises(LeserFehler, match="Szene 1: Einblendung hat 7 Wörter"):
        lese_reel(f)


def test_zeile_ohne_feld(tmp_path):
    f = _schreibe(tmp_path, "**Szene 1**\nirgendwas\nSprechtext: Hallo\nEinblendung: Hi")
    with pytest.raises(LeserFehler, match="Szene 1: Zeile ohne Feld: 'irgendwas'"):
        lese_reel(f)


def test_feld_doppelt(tmp_path):
    f = _schreibe(tmp_path, "**Szene 1**\nSprechtext: Hallo\nEinblendung: Hi\nSprechtext: Nochmal")
    with pytest.raises(LeserFehler, match="Szene 1: 'Sprechtext:' doppelt"):
        lese_reel(f)


@pytest.mark.parametrize("kopf", ["**Szene 2:**", "Szene 2", "### Szene 2", "**Szene zwei**"])
def test_szenen_kopf_nicht_erkannt(tmp_path, kopf):
    f = _schreibe(tmp_path, f"**Szene 1**\nSprechtext: A\nEinblendung: A\n\n{kopf}\nSprechtext: B\nEinblendung: B")
    with pytest.raises(LeserFehler, match=r"Szenen-Kopf nicht erkannt: '.*' \(erwartet \*\*Szene N\*\*"):
        lese_reel(f)


def test_grafik_leerer_teil(tmp_path):
    f = _schreibe(tmp_path, "**Szene 1**\nSprechtext: Start\nEinblendung: Hi\n\n**Szene 2**\nSprechtext: Hallo\nEinblendung: Hi\nGrafik: liste | a | | b")
    with pytest.raises(LeserFehler, match="Szene 2: Grafik hat einen leeren Teil"):
        lese_reel(f)


def test_caption_mit_zusatz_in_klammern(tmp_path):
    f = tmp_path / "x.md"
    f.write_text("## Szenen fürs Fliessband\n\n**Szene 1**\nSprechtext: A\nEinblendung: A\n\n"
                 "## Caption (unverändert aus V2)\n\nHallo\n", encoding="utf-8")
    assert lese_reel(f).caption == "Hallo"


def test_caption_im_codeblock_ohne_hinweis(tmp_path):
    f = _schreibe(tmp_path, "**Szene 1**\nSprechtext: Hallo.\nEinblendung: Hi",
                  "```\nZeile eins.\n\n#tag\n```\n\nHinweis: Caption bewusst nicht geändert.\n\n---")
    assert lese_reel(f).caption == "Zeile eins.\n\n#tag"


def test_caption_ohne_codeblock_bleibt(tmp_path):
    f = _schreibe(tmp_path, "**Szene 1**\nSprechtext: Hallo.\nEinblendung: Hi", "Zeile eins.\n\n---\n#tag")
    assert lese_reel(f).caption == "Zeile eins.\n\n#tag"


def test_grafik_auf_hook_ist_fehler(tmp_path):
    f = _schreibe(tmp_path, "**Szene 1**\nSprechtext: Hallo.\nEinblendung: Hi\nGrafik: zahl | 1 | 2")
    with pytest.raises(LeserFehler, match="Szene 1: der Hook zeigt keine Grafik, bitte 'Grafik:' entfernen"):
        lese_reel(f)


HOOK = "**Szene 1**\nSprechtext: Hallo\nEinblendung: Hallo\n\n"


def test_bild_gueltig(tmp_path):
    f = _schreibe(tmp_path, HOOK + "**Szene 2**\nSprechtext: a\nEinblendung: b\nBild: zeigt | waage | Notgroschen")
    s = lese_reel(f).szenen[1]
    assert s.bild == Bild("zeigt", ["waage", "notgroschen"])
    assert s.bild_hinweise == []


def test_bild_unbekannte_haltung_wird_steht(tmp_path):
    f = _schreibe(tmp_path, HOOK + "**Szene 2**\nSprechtext: a\nEinblendung: b\nBild: tanzt | uhr")
    s = lese_reel(f).szenen[1]
    assert s.bild == Bild("steht", ["uhr"])
    assert s.bild_hinweise == ["Szene 2: Haltung 'tanzt' unbekannt, Figur steht"]


def test_bild_unbekannter_gegenstand_weggelassen(tmp_path):
    f = _schreibe(tmp_path, HOOK + "**Szene 2**\nSprechtext: a\nEinblendung: b\nBild: denkt | einhorn | uhr")
    s = lese_reel(f).szenen[1]
    assert s.bild == Bild("denkt", ["uhr"])
    assert s.bild_hinweise == ["Szene 2: Gegenstand 'einhorn' unbekannt, weggelassen"]


def test_bild_mehr_als_zwei_gegenstaende(tmp_path):
    f = _schreibe(tmp_path, HOOK + "**Szene 2**\nSprechtext: a\nEinblendung: b\nBild: steht | uhr | herz | mond")
    s = lese_reel(f).szenen[1]
    assert s.bild == Bild("steht", ["uhr", "herz"])
    assert s.bild_hinweise == ["Szene 2: 3 Gegenstände, nur die ersten 2 gezeigt"]


def test_bild_fehlt(tmp_path):
    f = _schreibe(tmp_path, HOOK + "**Szene 2**\nSprechtext: a\nEinblendung: b")
    s = lese_reel(f).szenen[1]
    assert s.bild == Bild("steht", [])
    assert s.bild_hinweise == ["Szene 2: keine Zeile 'Bild:', Figur steht"]


def test_bild_leer(tmp_path):
    f = _schreibe(tmp_path, HOOK + "**Szene 2**\nSprechtext: a\nEinblendung: b\nBild:")
    s = lese_reel(f).szenen[1]
    assert s.bild == Bild("steht", [])
    assert s.bild_hinweise == ["Szene 2: Haltung fehlt, Figur steht"]


def test_bild_doppelt_erste_gilt(tmp_path):
    f = _schreibe(tmp_path, HOOK + "**Szene 2**\nSprechtext: a\nEinblendung: b\nBild: winkt\nBild: jubelt")
    s = lese_reel(f).szenen[1]
    assert s.bild == Bild("winkt", [])
    assert s.bild_hinweise == ["Szene 2: 'Bild:' doppelt, erste genommen"]


def test_bild_im_hook_ignoriert(tmp_path):
    f = _schreibe(tmp_path, "**Szene 1**\nSprechtext: Hallo\nEinblendung: Hallo\nBild: winkt | uhr")
    s = lese_reel(f).szenen[0]
    assert s.bild is None and s.bild_hinweise == []


def test_bild_label_gross_klein(tmp_path):
    f = _schreibe(tmp_path, HOOK + "**Szene 2**\nSprechtext: a\nEinblendung: b\nbild: zeigt | uhr")
    s = lese_reel(f).szenen[1]
    assert s.bild == Bild("zeigt", ["uhr"])
    assert s.bild_hinweise == []


def test_andere_felder_bleiben_gross_klein_strikt(tmp_path):
    f = _schreibe(tmp_path, HOOK + "**Szene 2**\nsprechtext: a\nEinblendung: b")
    with pytest.raises(LeserFehler, match="unbekanntes Feld"):
        lese_reel(f)


def test_bild_doppelter_gegenstand(tmp_path):
    f = _schreibe(tmp_path, HOOK + "**Szene 2**\nSprechtext: a\nEinblendung: b\nBild: zeigt | uhr | uhr")
    s = lese_reel(f).szenen[1]
    assert s.bild == Bild("zeigt", ["uhr"])
    assert s.bild_hinweise == ["Szene 2: Gegenstand 'uhr' doppelt, weggelassen"]


def test_bild_namen_normalisiert(tmp_path):
    f = _schreibe(tmp_path, HOOK + "**Szene 2**\nSprechtext: a\nEinblendung: b\nBild: Hält | Münzen | schild  demo")
    s = lese_reel(f).szenen[1]
    assert s.bild == Bild("haelt", ["muenzen", "schild-demo"])
    assert s.bild_hinweise == []


def test_bild_trenner_komma_und_schraegstrich(tmp_path):
    f = _schreibe(tmp_path, HOOK + "**Szene 2**\nSprechtext: a\nEinblendung: b\nBild: zeigt, uhr / herz")
    s = lese_reel(f).szenen[1]
    assert s.bild == Bild("zeigt", ["uhr", "herz"])
    assert s.bild_hinweise == []
