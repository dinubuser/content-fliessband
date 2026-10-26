from pathlib import Path

from lib import texter
from lib.reel_leser import lese_reel
from lib.umgebung import Pfade
from lib.woche import neue_sprechzeichen

FIXTURES = Path(__file__).parent / "fixtures"


def test_naechste_fassung():
    assert texter.naechste_fassung(Path("/b/2026-10-27_reel_x.md")) == Path("/b/2026-10-27_reel_x_v2.md")
    assert texter.naechste_fassung(Path("/b/2026-10-27_reel_x_v3.md")) == Path("/b/2026-10-27_reel_x_v4.md")


def test_ueberarbeite_schreibt_neue_fassung(tmp_path, agentur_attrappe):
    pfade = Pfade(basis=tmp_path / "fb", agentur=tmp_path / "agentur", skill=tmp_path / "skill")
    alt = tmp_path / "agentur" / "beitraege" / "2026-10-27_reel_drei-fehler_v2.md"
    alt.parent.mkdir(parents=True)
    alt.write_text((FIXTURES / "reel_beispiel.md").read_text(encoding="utf-8"), encoding="utf-8")
    thema = {"format": "reel", "beitrag": str(alt), "antwort": None, "frage": None}
    a = agentur_attrappe()
    neu = texter.ueberarbeite(thema, "Hook zu lang, kürzer", pfade, a.claude)
    assert neu == alt.with_name("2026-10-27_reel_drei-fehler_v3.md") and neu.exists()
    agent, auftrag = a.auftraege[0]
    assert agent == "content-agent"
    assert "«««\nHook zu lang, kürzer\n»»»" in auftrag and f"Beitrag: {alt}" in auftrag
    assert f"genau nach {neu}" in auftrag and "## Szenen fürs Fliessband" in auftrag
    assert alt.read_text(encoding="utf-8") == (FIXTURES / "reel_beispiel.md").read_text(encoding="utf-8")


def test_neue_sprechzeichen_nur_geaenderte_szenen(tmp_path):
    text = (FIXTURES / "reel_beispiel.md").read_text(encoding="utf-8")
    alt = tmp_path / "alt.md"
    alt.write_text(text, encoding="utf-8")
    szene2 = lese_reel(alt).szenen[1].sprechtext
    assert text.count(szene2) == 1
    neu = tmp_path / "neu.md"
    neu.write_text(text.replace(szene2, "Ganz neuer Satz hier."), encoding="utf-8")
    assert neue_sprechzeichen(alt, neu) == len("Ganz neuer Satz hier.")
    assert neue_sprechzeichen(alt, alt) == 0
