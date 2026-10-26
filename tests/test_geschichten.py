from datetime import date

from lib import geschichten


def test_merke_legt_an_und_haengt_an(tmp_path):
    pfad = tmp_path / "agentur" / "geschichten.md"
    geschichten.merke(pfad, date(2026, 10, 24), "Welche Sätze hörst du im Alltag?", "Glücksspiel, sagt er.\n")
    geschichten.merke(pfad, date(2026, 10, 31), "Was sagt Tom  zum Sparen?", "Sie will ein Velo.\nUnd zwar rot.")
    text = pfad.read_text(encoding="utf-8")
    assert text.startswith("# Geschichten des Betreibers\n")
    assert "\n## 2026-10-24: Welche Sätze hörst du im Alltag?\n\nGlücksspiel, sagt er.\n" in text
    assert text.endswith("\n## 2026-10-31: Was sagt Tom zum Sparen?\n\nSie will ein Velo.\nUnd zwar rot.\n")
    assert text.count("# Geschichten des Betreibers") == 1


def test_merke_ueberschreibt_nie(tmp_path):
    pfad = tmp_path / "geschichten.md"
    pfad.write_text("# Von Hand\n\nAlter Inhalt.\n", encoding="utf-8")
    geschichten.merke(pfad, date(2026, 10, 24), "Frage?", "Antwort.")
    text = pfad.read_text(encoding="utf-8")
    assert text.startswith("# Von Hand\n\nAlter Inhalt.\n") and "## 2026-10-24: Frage?" in text


def test_kopfzeile_bei_leerer_datei(tmp_path):
    pfad = tmp_path / "geschichten.md"
    pfad.write_text("", encoding="utf-8")
    geschichten.merke(pfad, date(2026, 10, 24), "Frage?", "Antwort.")
    assert pfad.read_text(encoding="utf-8").startswith("# Geschichten des Betreibers\n")


def test_lies_letzte_eintraege(tmp_path):
    pfad = tmp_path / "geschichten.md"
    for i in range(32):
        geschichten.merke(pfad, date(2026, 10, 1), f"Frage {i}?", f"Antwort {i}\n## keine Überschrift {i}")
    eintraege = geschichten.lies(pfad)
    assert len(eintraege) == geschichten.MAX_EINTRAEGE == 30
    assert eintraege[0] == {"datum": "2026-10-01", "frage": "Frage 2?",
                            "antwort": "Antwort 2\n## keine Überschrift 2"}
    assert eintraege[-1]["frage"] == "Frage 31?"


def test_lies_ohne_datei(tmp_path):
    assert geschichten.lies(tmp_path / "fehlt.md") == []
