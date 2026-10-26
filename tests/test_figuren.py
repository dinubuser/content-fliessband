import re
import xml.etree.ElementTree as ET

import numpy as np
import pytest
from PIL import Image
from playwright.sync_api import sync_playwright

from lib import figuren
from lib.figuren import BEWEGUNGEN, ORDNER
from lib.reel_modell import Bild, Szene

HALTUNGEN = ["steht", "zeigt", "denkt", "laptop", "jubelt", "schulterzucken", "haelt", "winkt"]
GEGENSTAENDE = ["waage", "uhr", "spartopf", "muenzen", "kurve-hoch", "kurve-runter", "kalender", "laptop",
                "handy", "haus", "herz", "gluehbirne", "stopp", "haekchen", "kreuz", "fragezeichen",
                "ausrufezeichen", "buch", "ziel", "schild-demo", "notgroschen", "kaffee", "mond", "sonne",
                "familie-herz", "geschenk", "pfeil", "lupe", "schloss", "rakete"]
VIEWBOX = {"haltungen": "0 0 200 300", "gegenstaende": "0 0 200 200"}


def _ids(text):
    return set(re.findall(r'\sid="([^"]+)"', text))


def test_namen_wie_in_der_spec():
    assert figuren.haltungen() == HALTUNGEN
    assert figuren.gegenstaende() == GEGENSTAENDE


def test_jede_datei_hat_einen_eintrag_und_umgekehrt():
    k = figuren.katalog()
    for art in ("haltungen", "gegenstaende"):
        dateien = {p.relative_to(ORDNER).as_posix() for p in (ORDNER / art).glob("*.svg")}
        eintraege = {e["datei"] for e in k[art].values()}
        assert dateien == eintraege, art


@pytest.mark.parametrize("art", ["haltungen", "gegenstaende"])
def test_eintraege_und_svgs_gueltig(art):
    for name, e in figuren.katalog()[art].items():
        assert e["bewegung"] in BEWEGUNGEN, name
        assert re.fullmatch(r"\d+ \d+", e["ursprung"]), name
        text = (ORDNER / e["datei"]).read_text(encoding="utf-8")
        wurzel = ET.fromstring(text)
        assert wurzel.tag.endswith("svg") and wurzel.get("viewBox") == VIEWBOX[art], name
        for verboten in ("url(#", "<style", "<script"):
            assert verboten not in text, (name, verboten)
        ids = _ids(text)
        assert set(e["teile"]) <= ids, (name, set(e["teile"]) - ids)
        if art == "haltungen":
            assert {"koerper", "kopf"} <= ids, name
        else:
            assert e["teile"], name  # jeder Gegenstand bewegt mindestens ein Teil


def test_namen_text():
    t = figuren.namen_text()
    assert "Haltungen: steht, zeigt," in t
    assert "Gegenstände: waage, uhr," in t and "rakete" in t


def test_svg_inline_ohne_ids():
    s = figuren.svg_inline("haltungen", "zeigt")
    assert s.startswith("<svg") and ' id="' not in s
    assert 'data-teil="arm"' in s and 'data-teil="koerper"' in s


def test_figur_html_ohne_grafik():
    h = figuren.figur_html(Bild("zeigt", ["waage", "notgroschen"]), mit_grafik=False)
    assert h.startswith('<div class="figur">')
    assert '<div class="haltung">' in h
    assert 'class="gegenstand platz-1"' in h and 'class="gegenstand platz-2"' in h
    assert 'data-teil="balken"' in h and 'data-teil="muenze"' in h


def test_figur_neben_grafik_klein_zeigt_ohne_gegenstaende():
    h = figuren.figur_html(Bild("jubelt", ["waage"]), mit_grafik=True)
    assert h.startswith('<div class="figur klein">')
    assert 'data-teil="arm"' in h          # Haltung «zeigt»
    assert "platz-1" not in h
    d = figuren.figur_daten(Bild("jubelt", ["waage"]), mit_grafik=True)
    assert d == {"haltung": {"name": "zeigt", "bewegung": "zeigen", "teile": ["arm"], "ursprung": "126 122"},
                 "gegenstaende": []}


def test_figur_daten():
    d = figuren.figur_daten(Bild("steht", ["uhr"]), mit_grafik=False)
    assert d["haltung"]["bewegung"] == "atmen"
    assert d["gegenstaende"] == [{"name": "uhr", "bewegung": "drehen", "teile": ["zeiger"], "ursprung": "100 100"}]


def test_hat_figur():
    assert figuren.hat_figur(Szene(2, False, "a", "b", bild=Bild("steht", [])))
    assert not figuren.hat_figur(Szene(2, False, "a", "b"))
    assert not figuren.hat_figur(Szene(1, True, "a", "b", bild=Bild("steht", [])))


def test_ungueltiges_svg_ist_figurenfehler(monkeypatch, tmp_path):
    (tmp_path / "haltungen").mkdir()
    (tmp_path / "haltungen" / "steht.svg").write_text("<svg><g></svg>", encoding="utf-8")
    (tmp_path / "katalog.json").write_text(
        '{"haltungen":{"steht":{"datei":"haltungen/steht.svg","bewegung":"atmen","teile":[],"ursprung":"100 284"}},'
        '"gegenstaende":{}}', encoding="utf-8")
    monkeypatch.setattr(figuren, "ORDNER", tmp_path)
    figuren.katalog.cache_clear()
    figuren.svg_inline.cache_clear()
    try:
        with pytest.raises(figuren.FigurenFehler, match="steht"):
            figuren.svg_inline("haltungen", "steht")
    finally:
        figuren.katalog.cache_clear()
        figuren.svg_inline.cache_clear()


def test_unbekannte_figur_ist_figurenfehler():
    with pytest.raises(figuren.FigurenFehler, match="unbekannte Figur haltungen/gibtsnicht"):
        figuren.svg_inline("haltungen", "gibtsnicht")
    with pytest.raises(figuren.FigurenFehler, match="unbekannte Figur gegenstaende/x"):
        figuren._bewegung("gegenstaende", "x")


CREME = np.array([0xF8, 0xF6, 0xF2])
RAND = 30  # px um jede Box, die leer bleiben müssen
PALETTE = np.array([[0xF8, 0xF6, 0xF2], [0x0B, 0x11, 0x1E], [0xFA, 0x63, 0x17]])


def test_musterseite_bewegt_schreibt_ordner(tmp_path):
    index = figuren.schreibe_musterseite(tmp_path / "muster")
    h = index.read_text(encoding="utf-8")
    assert (tmp_path / "muster" / "gsap.min.js").exists()
    assert (tmp_path / "muster" / "fonts" / "InterVariable.ttf").exists()
    assert "window.FIGUREN" in h and h.count('class="zelle') == 38


@pytest.mark.langsam
def test_jedes_teil_sichtbar_und_im_rahmen(tmp_path):
    seite_html = tmp_path / "muster.html"
    seite_html.write_text(figuren.musterseite_html(bewegt=False, schrift=figuren.SCHRIFT.as_uri()), encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            seite = browser.new_page(viewport={"width": 1800, "height": 1000})
            seite.goto(seite_html.as_uri())
            seite.evaluate("document.fonts.ready.then(() => true)")
            boxen = seite.evaluate("""() => [...document.querySelectorAll('.box')].map(b => {
                const r = b.getBoundingClientRect();
                return {name: b.parentElement.dataset.name, x: r.x + scrollX, y: r.y + scrollY,
                        w: r.width, h: r.height}; })""")
            seite.screenshot(path=str(tmp_path / "muster.png"), full_page=True)
        finally:
            browser.close()
    bild = np.asarray(Image.open(tmp_path / "muster.png").convert("RGB")).astype(int)
    farbig = np.abs(bild - CREME).max(axis=2) > 24
    assert len(boxen) == 38
    for b in boxen:
        x, y, w, h = (round(b[k]) for k in ("x", "y", "w", "h"))
        innen = farbig[y:y + h, x:x + w]
        aussen = farbig[y - RAND:y + h + RAND, x - RAND:x + w + RAND].sum() - innen.sum()
        assert innen.mean() > 0.03, f"{b['name']}: fast leer ({innen.mean():.3f})"
        assert aussen <= 10, f"{b['name']}: {aussen} Pixel über dem Rand"
        # Nur Palettenfarben: Kantenglättung mischt zwei Palettenfarben, darum Abstand zur Mischlinie prüfen
        teil = bild[y:y + h, x:x + w].reshape(-1, 3)
        abstand = np.full(len(teil), np.inf)
        for i in range(3):
            for j in range(i + 1, 3):
                a, d = PALETTE[i], PALETTE[j] - PALETTE[i]
                t = np.clip(((teil - a) @ d) / (d @ d), 0, 1)
                abstand = np.minimum(abstand, np.linalg.norm(teil - (a + t[:, None] * d), axis=1))
        fremd = (abstand > 30).mean()
        assert fremd < 0.002, f"{b['name']}: {fremd:.4f} Anteil Fremdfarben"


@pytest.mark.langsam
def test_musterseite_bewegt_ohne_js_fehler(tmp_path):
    index = figuren.schreibe_musterseite(tmp_path / "muster")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            seite = browser.new_page(viewport={"width": 1800, "height": 1000})
            fehler = []
            seite.on("pageerror", lambda e: fehler.append(str(e)))
            seite.on("console", lambda m: fehler.append(m.text) if m.type in ("error", "warning") else None)
            seite.goto(index.as_uri())
            stand = seite.evaluate("""() => { tl.pause(); const r = [];
                for (const t of [0, 0.5, 1.5, 3, 5.9]) { tl.seek(t);
                  r.push([...document.querySelectorAll('[data-teil]')].filter(e => e.getAttribute('transform')
                    || e.style.transform).length); }
                return {dauer: tl.duration(), kinder: tl.getChildren().length, bewegt: r}; }""")
        finally:
            browser.close()
    assert fehler == []
    assert stand["dauer"] == pytest.approx(6, abs=0.01)
    assert stand["kinder"] >= 38 + 8
    assert max(stand["bewegt"]) > 0
