import re

import pytest
from PIL import Image

from lib.reel_bilder import (SCHRIFT_FAMILIE, VORLAGE_ORDNER, ZuLangFehler, markiere, rendere_cover, szene_html,
                             waehle_skalen)
from lib.reel_modell import Grafik, Szene


def _s(nummer, einblendung, grafik=None, hook=False):
    return Szene(nummer, hook, "egal", einblendung, grafik)


def test_markiere_ab_vier_buchstaben():
    assert markiere("Kenn ich.", {"kenn", "ich"}) == '<span class="hl">Kenn</span> ich.'


def test_szene_html_vergleich():
    h = szene_html(_s(2, "Schritt 1", Grafik("vergleich", ["Übungsgeld", "Haushaltsbudget"])), 0.9)
    assert 'id="sz-2"' in h and 'style="--s:0.9"' in h
    assert "statt" in h and "Haushaltsbudget" in h


def test_skalen_normal_ist_eins():
    szenen = [_s(1, "Keine Zeit? Kenn ich.", hook=True),
              _s(2, "Schritt 1: Demokonto", Grafik("vergleich", ["Übungsgeld", "Haushaltsbudget"]))]
    assert waehle_skalen(szenen, hook_gruppen={1: ["Keine Zeit?", "Kenn ich."]}) == {1: 1.0, 2: 1.0}


def test_zu_lange_grafik_bricht_mit_szene_ab():
    lang = " ".join(["Donaudampfschifffahrtsgesellschaft"] * 12)
    szenen = [_s(1, "Hallo", hook=True), _s(2, "Kurz", Grafik("liste", [lang, lang, lang]))]
    with pytest.raises(ZuLangFehler, match="Szene 2"):
        waehle_skalen(szenen, hook_gruppen={1: ["Hallo"]})


def test_cover_png(tmp_path):
    png = rendere_cover("Keine Zeit, kein Geld? Kenn ich.", tmp_path / "cover.png")
    with Image.open(png) as bild:
        assert bild.size == (1080, 1920)
    assert not (tmp_path / "_messen.html").exists()


def test_langes_wort_im_hook_wird_verkleinert():
    szenen = [_s(1, "Altersvorsorgeplanung", hook=True)]
    skalen = waehle_skalen(szenen, hook_gruppen={1: ["Altersvorsorgeplanung"]})
    assert 0.5 <= skalen[1] < 0.7


def test_ueberlanges_wort_im_hook_wird_getrennt():
    # Ausgeschriebene Zahlen passen auch bei kleinster Schrift nicht in die Breite (KW44, Thema 1)
    szenen = [_s(1, "x", hook=True)]
    assert waehle_skalen(szenen, hook_gruppen={1: ["Sechsundzwanzigjähriger"]})[1] >= 0.5


def test_langes_wort_in_einblendung_wird_verkleinert():
    skalen = waehle_skalen([_s(1, "Verantwortungsbewusstsein zählt")], hook_gruppen={})
    assert skalen[1] < 1.0


def test_absurdes_wort_bricht_trotzdem_ab():
    wort = "A" * 45
    with pytest.raises(ZuLangFehler, match="Szene 1"):
        waehle_skalen([_s(1, "x", hook=True)], hook_gruppen={1: [wort]})
    with pytest.raises(ZuLangFehler, match="Szene 3"):
        waehle_skalen([_s(3, wort)], hook_gruppen={})


def test_html_escaped_nutzertext():
    roh = '<b>&"x\'</b>'
    h = szene_html(_s(2, roh, Grafik("liste", [roh, "b"])), 1.0)
    assert "<b>" not in h and "&lt;b&gt;&amp;&quot;x&#x27;&lt;/b&gt;" in h
    hook = szene_html(_s(1, "e", hook=True), 1.0, [roh])
    assert "<b>" not in hook and "&lt;b&gt;" in hook
    g = szene_html(_s(2, "e", Grafik("zahl", [roh, "<i>"])), 1.0)
    assert "<i>" not in g and "&lt;i&gt;" in g


def test_stil_nutzt_nur_lokale_schrift():
    # HyperFrames lädt für "Inter" und Ersatznamen wie Helvetica oder Arial Inter von Google Fonts nach.
    # Mit eigenem Familiennamen und ohne benannte Ersatzschriften rendert immer die mitgelieferte Datei.
    css = (VORLAGE_ORDNER / "stil.css").read_text(encoding="utf-8")
    familien = re.findall(r"font-family:\s*([^;]+);", css)
    assert familien, "stil.css setzt keine Schrift"
    for f in familien:
        namen = [n.strip().strip('"\'') for n in f.split(",")]
        assert set(namen) <= {SCHRIFT_FAMILIE, "sans-serif"}, f
    assert f'font-family: "{SCHRIFT_FAMILIE}";' in css


def test_schrift_nicht_geladen_ist_renderfehler():
    from lib.reel_bilder import _laden
    from lib.reel_renderer import RenderFehler

    class Seite:
        def goto(self, url): pass
        def evaluate(self, js, *a): return False
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(RenderFehler, match="Schrift"):
            _laden(Seite(), "<html></html>", pathlib.Path(d))
