import json
from datetime import date, datetime

import pytest

from lib import manifest, reel_bauer
from lib.manifest import ManifestFehler
from lib.medien import MedienFehler
from lib.musik import MusikFehler
from lib.pruefungen import SATZZEICHEN, lade_aussprache
from lib.reel_bauer import baue_reel, manifest_eintrag
from lib.reel_bilder import ZuLangFehler
from lib.reel_leser import LeserFehler
from lib.reel_renderer import RenderFehler
from lib.stimme import StimmFehler
from lib.zeitplan import LaengeFehler

TERMIN = datetime(2026, 10, 25, 19, 0)


@pytest.mark.langsam
def test_baut_reel_mit_manifest(tmp_path, reel_quelle, falsche_elevenlabs):
    ziel, eintrag = baue_reel(reel_quelle, termin=TERMIN, basis=tmp_path, anfrage=falsche_elevenlabs)
    assert ziel == tmp_path / "wochen" / "2026-KW43" / "reel-beispiel"
    for name in ["reel.mp4", "cover.png", "caption.txt", "stimme/szene-01.mp3"]:
        assert (ziel / name).exists(), name
    assert not (ziel / "_komposition").exists()
    daten = json.loads((ziel.parent / "manifest.json").read_text(encoding="utf-8"))
    b = daten["beitraege"][0]
    assert b == eintrag
    assert b["id"] == "2026-KW43-reel-beispiel"
    assert b["format"] == "reel"
    assert b["medien"] == ["reel.mp4"] and b["cover"] == "cover.png"
    assert b["ki_stimme"] is True
    assert b["pruefungen"]["laenge"] == "ok"
    # Trading-Reel: Risikohinweis immer auf dem Bild (letzte Szene)
    assert "szene" in b["pruefungen"]["risikohinweis_ergaenzt"]
    assert b["status"] == "entwurf"
    assert b["dauer_s"] > 0


@pytest.mark.langsam
def test_zweiter_lauf_nutzt_zwischenspeicher_und_ersetzt(tmp_path, reel_quelle, falsche_elevenlabs):
    baue_reel(reel_quelle, termin=TERMIN, basis=tmp_path, anfrage=falsche_elevenlabs)
    n = len(falsche_elevenlabs.aufrufe)
    ziel, _ = baue_reel(reel_quelle, termin=TERMIN, basis=tmp_path, anfrage=falsche_elevenlabs)
    assert len(falsche_elevenlabs.aufrufe) == n
    daten = json.loads((ziel.parent / "manifest.json").read_text(encoding="utf-8"))
    assert len(daten["beitraege"]) == 1


def test_karussell_mit_gleichem_slug_bleibt(tmp_path):
    woche = tmp_path / "wochen" / "2026-KW43"
    woche.mkdir(parents=True)
    manifest.trage_ein(woche / "manifest.json", "2026-KW43", {"id": "2026-KW43-beispiel", "format": "karussell"})
    manifest.trage_ein(woche / "manifest.json", "2026-KW43",
                       manifest_eintrag("2026-KW43", "beispiel", tmp_path / "q.md", None, {"platzhalter": []}, 10.0))
    daten = json.loads((woche / "manifest.json").read_text(encoding="utf-8"))
    assert [b["id"] for b in daten["beitraege"]] == ["2026-KW43-beispiel", "2026-KW43-reel-beispiel"]


def test_platzhalter_ergibt_braucht_eingabe(tmp_path):
    e = manifest_eintrag("2026-KW43", "x", tmp_path / "q.md", None, {"platzhalter": ["Szene 2: [prüfen]"]}, 10.0)
    assert e["status"] == "braucht_eingabe"


def test_stimmfehler_hinterlaesst_nichts(tmp_path, reel_quelle):
    def kaputt(text):
        raise StimmFehler("ElevenLabs 401: quota_exceeded")
    with pytest.raises(StimmFehler, match="Szene 1"):
        baue_reel(reel_quelle, termin=TERMIN, basis=tmp_path, anfrage=kaputt)
    woche = tmp_path / "wochen" / "2026-KW43"
    assert not (woche / "reel-beispiel").exists()
    assert not (woche / ".tmp-reel-beispiel").exists()


def test_zu_lang_bricht_ab(tmp_path, falsche_elevenlabs):
    quelle = tmp_path / "2026-10-20_reel_lang.md"
    satz = "Das ist ein ziemlich langer Satz mit vielen Wörtern drin. " * 14
    quelle.write_text(f"## Szenen fürs Fliessband\n\n**Szene 1**\nSprechtext: {satz}\nEinblendung: Lang\n\n"
                      "## Caption\nHallo\n", encoding="utf-8")
    with pytest.raises(LaengeFehler):
        baue_reel(quelle, basis=tmp_path, heute=date(2026, 10, 20), anfrage=falsche_elevenlabs)
    assert not (tmp_path / "wochen" / "2026-KW43" / "reel-lang").exists()
    assert not (tmp_path / "wochen" / "2026-KW43" / ".tmp-reel-lang").exists()


# --- Schnelle Tests: Playwright und HyperFrames ersetzt, alles andere echt ---

def _inhalt(ordner):
    return sorted(str(p.relative_to(ordner)) for p in ordner.rglob("*"))


def test_schnell_baut_ordner_ohne_hilfsdateien(tmp_path, reel_quelle, falsche_elevenlabs, schnell):
    ziel, eintrag = baue_reel(reel_quelle, termin=TERMIN, basis=tmp_path, anfrage=falsche_elevenlabs)
    assert _inhalt(ziel) == ["caption.txt", "cover.png", "reel.mp4", "stimme"] + sorted(
        f"stimme/szene-{n:02d}.{e}" for n in range(1, 5) for e in ("json", "mp3"))
    woche = ziel.parent
    assert sorted(p.name for p in woche.iterdir()) == ["manifest.json", "reel-beispiel"]
    assert eintrag["termin"] == "2026-10-25T19:00"
    assert eintrag["quelle"] == str(reel_quelle.resolve())
    caption = (ziel / "caption.txt").read_text(encoding="utf-8")
    assert caption.startswith("Trading lernen") and caption.endswith("\n")
    assert not (tmp_path / "zwischenspeicher").exists()


def test_70_sekunden_ist_lang_ohne_statuswechsel(tmp_path, falsche_elevenlabs, schnell):
    quelle = tmp_path / "2026-10-20_reel_mittel.md"
    satz = "Das ist ein ziemlich langer Satz mit vielen Wörtern drin. " * 10  # rund 580 Zeichen
    quelle.write_text(f"## Szenen fürs Fliessband\n\n**Szene 1**\nSprechtext: {satz}\nEinblendung: Mittel\n\n"
                      "## Caption\nHallo\n", encoding="utf-8")
    _, eintrag = baue_reel(quelle, basis=tmp_path, heute=date(2026, 10, 20), anfrage=falsche_elevenlabs)
    assert 60 < eintrag["dauer_s"] <= 90
    assert eintrag["pruefungen"]["laenge"] == "lang"
    assert eintrag["status"] == "entwurf"


def _wirf(fehler):
    def f(*args, **kwargs):
        raise fehler
    return f


@pytest.mark.parametrize("schritt, fehler", [
    ("erzeuge_bett", MusikFehler("Musikstück kaputt")),
    ("waehle_skalen", ZuLangFehler("Szene 3: Text passt auch bei kleinster Schrift nicht")),
    ("baue_komposition", FileNotFoundError("gsap.min.js fehlt, im Projektordner 'npm install' ausführen")),
    ("pruefe_komposition", RenderFehler("HyperFrames check gescheitert, Protokoll: x.log")),
    ("rendere", RenderFehler("HyperFrames render gescheitert, Protokoll: x.log")),
    ("pruefe_video", MedienFehler("ffprobe kann reel.mp4 nicht lesen")),
    ("pruefe_video", RenderFehler("Länge 12.0 s statt 30.0 s")),
    ("rendere_cover", ZuLangFehler("Titelbild: Hook-Einblendung passt nicht")),
    ("rendere_cover", KeyboardInterrupt()),
])
def test_fehler_laesst_alten_stand_stehen(tmp_path, reel_quelle, falsche_elevenlabs, schnell, schritt, fehler):
    ziel, _ = baue_reel(reel_quelle, termin=TERMIN, basis=tmp_path, anfrage=falsche_elevenlabs)
    vorher = _inhalt(ziel)
    manifest_vorher = (ziel.parent / "manifest.json").read_text(encoding="utf-8")

    schnell.setattr(reel_bauer, schritt, _wirf(fehler))
    with pytest.raises(type(fehler)) as info:
        baue_reel(reel_quelle, termin=TERMIN, basis=tmp_path, anfrage=falsche_elevenlabs)
    assert str(info.value) == str(fehler)  # Meldung unverändert weitergereicht
    assert "\n" not in str(info.value)

    woche = ziel.parent
    assert sorted(p.name for p in woche.iterdir()) == ["manifest.json", "reel-beispiel"]
    assert _inhalt(ziel) == vorher
    assert (woche / "manifest.json").read_text(encoding="utf-8") == manifest_vorher


def test_fehler_nach_stimme_behaelt_aufnahmen(tmp_path, reel_quelle, falsche_elevenlabs, schnell):
    """Scheitert der Render, kostet der nächste Lauf kein ElevenLabs-Guthaben."""
    gut = reel_bauer.rendere
    schnell.setattr(reel_bauer, "rendere", _wirf(RenderFehler("HyperFrames render gescheitert")))
    with pytest.raises(RenderFehler):
        baue_reel(reel_quelle, termin=TERMIN, basis=tmp_path, anfrage=falsche_elevenlabs)
    woche = tmp_path / "wochen" / "2026-KW43"
    assert not woche.exists() or sorted(p.name for p in woche.iterdir()) == []
    n = len(falsche_elevenlabs.aufrufe)
    assert n == 4

    schnell.setattr(reel_bauer, "rendere", gut)
    ziel, _ = baue_reel(reel_quelle, termin=TERMIN, basis=tmp_path, anfrage=falsche_elevenlabs)
    assert len(falsche_elevenlabs.aufrufe) == n
    assert (ziel / "stimme" / "szene-04.mp3").exists()
    # Nach Erfolg liegt der gerettete Zwischenspeicher wieder im Reel-Ordner, nicht mehr daneben
    assert not (tmp_path / "zwischenspeicher" / "2026-KW43-reel-beispiel").exists()


def test_zu_lang_zweiter_lauf_ohne_neue_anfragen(tmp_path, falsche_elevenlabs):
    quelle = tmp_path / "2026-10-20_reel_lang.md"
    satz = "Das ist ein ziemlich langer Satz mit vielen Wörtern drin. " * 14
    quelle.write_text(f"## Szenen fürs Fliessband\n\n**Szene 1**\nSprechtext: {satz}\nEinblendung: Lang\n\n"
                      "## Caption\nHallo\n", encoding="utf-8")
    for _ in range(2):
        with pytest.raises(LaengeFehler):
            baue_reel(quelle, basis=tmp_path, heute=date(2026, 10, 20), anfrage=falsche_elevenlabs)
    assert len(falsche_elevenlabs.aufrufe) == 1


def test_kaputtes_manifest_bricht_vor_der_stimme_ab(tmp_path, reel_quelle, falsche_elevenlabs):
    woche = tmp_path / "wochen" / "2026-KW43"
    woche.mkdir(parents=True)
    (woche / "manifest.json").write_text("{kaputt", encoding="utf-8")
    with pytest.raises(ManifestFehler):
        baue_reel(reel_quelle, termin=TERMIN, basis=tmp_path, anfrage=falsche_elevenlabs)
    assert falsche_elevenlabs.aufrufe == []
    assert sorted(p.name for p in woche.iterdir()) == ["manifest.json"]


def test_formatfehler_bricht_vor_der_stimme_ab(tmp_path, falsche_elevenlabs):
    quelle = tmp_path / "2026-10-20_reel_leer.md"
    quelle.write_text("# Nur ein Titel\n", encoding="utf-8")
    with pytest.raises(LeserFehler, match="Szenen fürs Fliessband"):
        baue_reel(quelle, basis=tmp_path, heute=date(2026, 10, 20), anfrage=falsche_elevenlabs)
    assert falsche_elevenlabs.aufrufe == []
    assert not (tmp_path / "wochen").exists()


def test_rettung_scheitert_urspruenglicher_fehler_bleibt(tmp_path, reel_quelle, falsche_elevenlabs, schnell):
    """Scheitert das Retten der Stimme selbst, kommt trotzdem der echte Fehler und tmp ist weg."""
    import shutil
    schnell.setattr(reel_bauer, "rendere", _wirf(RenderFehler("HyperFrames render gescheitert")))
    schnell.setattr(shutil, "move", _wirf(OSError("Platte voll")))
    with pytest.raises(RenderFehler, match="render gescheitert"):
        baue_reel(reel_quelle, termin=TERMIN, basis=tmp_path, anfrage=falsche_elevenlabs)
    woche = tmp_path / "wochen" / "2026-KW43"
    assert not any(p.name.startswith(".tmp-reel-") for p in woche.iterdir())


def test_rettung_verschachtelt_nicht(tmp_path, reel_quelle, falsche_elevenlabs, schnell):
    """Ein alter Zwischenspeicher wird ersetzt, nicht als gerettet/stimme/ verschachtelt."""
    gerettet = tmp_path / "zwischenspeicher" / "2026-KW43-reel-beispiel"
    (gerettet / "stimme").mkdir(parents=True)
    (gerettet / "stimme" / "alt.txt").write_text("x")
    schnell.setattr(reel_bauer, "rendere", _wirf(RenderFehler("kaputt")))
    with pytest.raises(RenderFehler):
        baue_reel(reel_quelle, termin=TERMIN, basis=tmp_path, anfrage=falsche_elevenlabs)
    assert (gerettet / "szene-01.mp3").exists()
    assert not (gerettet / "stimme").exists()


def test_manifest_eintrag_mit_und_ohne_laenge(tmp_path):
    ohne = manifest_eintrag("2026-KW45", "x", tmp_path / "q.md", None, {"platzhalter": []}, 24.0)
    mit = manifest_eintrag("2026-KW45", "x", tmp_path / "q.md", None, {"platzhalter": []}, 24.0, laenge="kurz")
    assert "laenge" not in ohne
    assert mit["laenge"] == "kurz" and mit["dauer_s"] == 24.0


def _wort(quelle):
    """Ein Wort des ersten Sprechtexts, das nicht auf aussprache.txt steht."""
    from lib.reel_leser import lese_reel
    bekannt = set(lade_aussprache(reel_bauer.PROJEKT / "aussprache.txt"))
    for token in lese_reel(quelle).szenen[0].sprechtext.split():
        kern = SATZZEICHEN.match(token).group(2)
        if kern.isalpha() and kern not in bekannt:
            return kern
    raise AssertionError("kein passendes Wort")


@pytest.mark.langsam
def test_pruefer_ersetzt_fuer_die_stimme_und_merkt(tmp_path, reel_quelle, falsche_elevenlabs):
    wort = _wort(reel_quelle)
    gesehen = []

    def pruefer(szenen, liste):
        gesehen.append(dict(liste))
        return {wort: "Ersatzwort"}, []

    ziel, eintrag = baue_reel(reel_quelle, termin=TERMIN, basis=tmp_path, anfrage=falsche_elevenlabs,
                              aussprache_pruefer=pruefer)
    assert "Glace" in gesehen[0]                                   # aussprache.txt ist geladen
    assert "Ersatzwort" in falsche_elevenlabs.aufrufe[0]
    assert eintrag["pruefungen"]["aussprache_neu"] == [[wort, "Ersatzwort"]]
    assert f"{wort} → Ersatzwort" in (tmp_path / "daten" / "aussprache-auto.txt").read_text(encoding="utf-8")


@pytest.mark.langsam
def test_pruefer_fehler_baut_trotzdem(tmp_path, reel_quelle, falsche_elevenlabs):
    def pruefer(szenen, liste):
        raise RuntimeError("Claude weg")

    ziel, eintrag = baue_reel(reel_quelle, termin=TERMIN, basis=tmp_path, anfrage=falsche_elevenlabs,
                              aussprache_pruefer=pruefer)
    assert (ziel / "reel.mp4").exists()
    assert eintrag["pruefungen"]["aussprache_neu"] == []


def test_ohne_pruefer_kein_feld_und_auto_liste_gilt(tmp_path, reel_quelle, falsche_elevenlabs, schnell):
    wort = _wort(reel_quelle)
    auto = tmp_path / "daten" / "aussprache-auto.txt"
    auto.parent.mkdir(parents=True)
    auto.write_text(f"{wort} → Autowort\n", encoding="utf-8")
    _, eintrag = baue_reel(reel_quelle, termin=TERMIN, basis=tmp_path, anfrage=falsche_elevenlabs)
    assert "aussprache_neu" not in eintrag["pruefungen"]
    assert "Autowort" in falsche_elevenlabs.aufrufe[0]
