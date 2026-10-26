from datetime import datetime

from PIL import Image

from lib.bauer import baue_karussell


def test_schnelles_karussell_baut_ohne_browser(tmp_path, karussell_quelle, schnelles_karussell):
    ziel, eintrag = baue_karussell(karussell_quelle, termin=datetime(2026, 10, 28, 19, 0), basis=tmp_path)
    assert len(eintrag["medien"]) == 10
    with Image.open(ziel / "slide-10.png") as bild:   # echtes PNG, lässt sich als JPEG umwandeln (Etappe 5)
        assert bild.format == "PNG"


def test_telegram_vergibt_nachrichten_ids(telegram):
    assert telegram("sendMessage", {"chat_id": 42, "text": "a"}) == {"message_id": 101}
    assert telegram("sendMessage", {"chat_id": 42, "text": "b"}) == {"message_id": 102}
    assert telegram.texte() == ["a", "b"]


def test_agentur_schreibt_reel_oder_karussell(tmp_path, agentur_attrappe):
    a = agentur_attrappe()
    reel = a.claude("content-agent", "x", tmp_path / "2026-10-27_reel_a.md")
    karussell = a.claude("content-agent", "x", tmp_path / "2026-10-28_karussell_b.md")
    assert "## Szenen fürs Fliessband" in reel.read_text(encoding="utf-8")
    assert "## Slides" in karussell.read_text(encoding="utf-8")
    assert a.anzahl("content-agent") == 2
