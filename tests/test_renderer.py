import pytest
from PIL import Image

from lib.leser import lese_beitrag
from lib.modell import Slide
from lib.renderer import ZuLangFehler, rendere_slides


def test_zehn_pngs_in_instagram_groesse(tmp_path, karussell_quelle):
    slides = lese_beitrag(karussell_quelle).slides
    pngs = rendere_slides(slides, tmp_path)
    assert [p.name for p in pngs] == [f"slide-{n:02d}.png" for n in range(1, 11)]
    for p in pngs:
        assert Image.open(p).size == (1080, 1350)
    assert not list(tmp_path.glob("*.html"))


def test_zu_langer_text_bricht_mit_slide_nummer_ab(tmp_path):
    slides = [Slide(1, "hook", "Kurz", ""), Slide(2, "text", "Lang", "Wort " * 600)]
    with pytest.raises(ZuLangFehler, match="Slide 2"):
        rendere_slides(slides, tmp_path)
    assert not list(tmp_path.glob("*.html"))
