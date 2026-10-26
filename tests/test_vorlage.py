from lib.modell import Slide
from lib.vorlage import baue_html


def test_hook_hat_balken_und_wischen():
    h = baue_html(Slide(1, "hook", "Kein Geld?", "Text"), 10, 1.0)
    assert 'class="balken"' in h
    assert "wischen →" in h
    assert "@dein.konto" in h


def test_schritt_zeigt_nummer_und_position():
    h = baue_html(Slide(6, "schritt", "Wie viel darf weg?", "", schritt=4), 10, 1.0)
    assert '<div class="nummer">4</div>' in h
    assert "6 / 10" in h


def test_text_wird_escaped():
    h = baue_html(Slide(2, "text", "A < B & C", ""), 10, 1.0)
    assert "A &lt; B &amp; C" in h


def test_hervorhebung():
    h = baue_html(Slide(1, "hook", "Genau ==richtig== an", ""), 10, 1.0)
    assert '<span class="hl">richtig</span>' in h


def test_hinweis_wird_angezeigt():
    h = baue_html(Slide(10, "schluss", "Ende", "", hinweis="Trading birgt Verlustrisiken."), 10, 1.0)
    assert '<div class="hinweis">Trading birgt Verlustrisiken.</div>' in h


def test_skala_wird_gesetzt():
    assert "--s:0.8" in baue_html(Slide(2, "text", "X", ""), 10, 0.8)


def test_css_wird_als_datei_url_eingebunden():
    assert 'href="file://' in baue_html(Slide(2, "text", "X", ""), 10, 1.0)
