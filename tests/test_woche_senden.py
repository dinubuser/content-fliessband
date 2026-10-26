from datetime import datetime
from pathlib import Path

import pytest

from lib import woche
from lib.bot import BotFehler
from lib.kalender import termine
from lib.woche import SchrittFehler, senden, status_text, uebersicht
from lib.wochenplan import Wochenplan, arbeitsfelder

WOCHE = "2026-KW44"


def _gebauter_plan(u) -> Wochenplan:
    """4 gebaute Themen mit Ordnern (Reel: reel.mp4, Karussell: 2 Slides) und je einem guten Test."""
    plan = Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE)
    for t in termine(WOCHE):
        slug = f"thema-{t['nr']}"
        ordner = u.pfade.woche(WOCHE) / (f"reel-{slug}" if t["format"] == "reel" else slug)
        ordner.mkdir(parents=True)
        if t["format"] == "reel":
            (ordner / "reel.mp4").write_bytes(b"mp4")
        else:
            for n in (1, 2):
                (ordner / f"slide-{n:02d}.png").write_bytes(b"png")
        (ordner / "caption.txt").write_text(f"Caption {t['nr']}\n", encoding="utf-8")
        beitrag = f"/agentur/beitraege/{slug}.md"
        thema = arbeitsfelder({"nr": t["nr"], "format": t["format"], "termin": t["termin"], "slug": slug,
                               "thema": f"Thema {t['nr']}", "quelle": {"art": "ideen", "detail": "x"},
                               "vorlage": None, "weiterschick": "x", "hook_idee": "x", "frage": None})
        thema.update(status="gebaut", beitrag=beitrag, ordner=str(ordner),
                     test=[{"runde": 1, "wegwisch": 0.3, "teilen": 0.1, "speichern": 0.1, "urteil": "gut",
                            "datei": beitrag}])
        plan.themen.append(thema)
    plan.schritt_fertig("vorbereitet", datetime(2026, 10, 23, 22, 0))
    return plan


def _lade(u):
    return Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE)


def test_senden_reihenfolge_und_wiederholbar(wochen_umgebung, agentur_attrappe):
    u = wochen_umgebung
    _gebauter_plan(u)
    assert senden(WOCHE, u.pfade, u.dienste(agentur_attrappe()), lambda t: None) == 4
    assert u.telegram.methoden() == ["sendMessage", "sendVideo", "sendMessage", "sendMediaGroup", "sendMessage",
                                     "sendVideo", "sendMessage", "sendMediaGroup", "sendMessage"]
    texte = u.telegram.texte()
    assert texte[0].startswith("Wochenpaket 2026-KW44 (Di 27.10. bis Sa 31.10.)")
    assert texte[1] == "Caption 1"
    plan = _lade(u)
    assert [t["status"] for t in plan.aktive()] == ["gesendet"] * 4
    assert plan.daten["schritte"]["gesendet"] == "2026-10-23T22:00"
    assert senden(WOCHE, u.pfade, u.dienste(agentur_attrappe()), lambda t: None) == 0
    assert len(u.telegram.aufrufe) == 9


def test_senden_nach_fehler_schickt_nur_offenes(wochen_umgebung, agentur_attrappe):
    u = wochen_umgebung
    _gebauter_plan(u)
    u.telegram.scheitern_bei = "sendMediaGroup"
    with pytest.raises(BotFehler):
        senden(WOCHE, u.pfade, u.dienste(agentur_attrappe()), lambda t: None)
    assert [t["status"] for t in _lade(u).aktive()] == ["gesendet", "gebaut", "gebaut", "gebaut"]
    u.telegram.scheitern_bei = None
    assert senden(WOCHE, u.pfade, u.dienste(agentur_attrappe()), lambda t: None) == 3
    assert u.telegram.methoden().count("sendVideo") == 2
    assert [t["status"] for t in _lade(u).aktive()] == ["gesendet"] * 4


def test_grosses_reel_wird_verkleinert(wochen_umgebung, agentur_attrappe, monkeypatch):
    u = wochen_umgebung
    _gebauter_plan(u)
    monkeypatch.setattr(woche, "VERSAND_GRENZE", 2)

    def klein(quelle, ziel):
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_bytes(b"k")
        return ziel
    monkeypatch.setattr(woche, "verkleinere", klein)
    senden(WOCHE, u.pfade, u.dienste(agentur_attrappe()), lambda t: None)
    videos = [d["video"] for m, _, d in u.telegram.aufrufe if m == "sendVideo"]
    assert videos[0] == u.pfade.basis / "zwischenspeicher" / "versand" / "2026-KW44-thema-1.mp4"
    assert (u.pfade.woche(WOCHE) / "reel-thema-1" / "reel.mp4").read_bytes() == b"mp4"


def test_senden_ohne_vorbereitung(wochen_umgebung, agentur_attrappe):
    u = wochen_umgebung
    with pytest.raises(SchrittFehler, match="nicht vorbereitet"):
        senden(WOCHE, u.pfade, u.dienste(agentur_attrappe()), lambda t: None)


def test_uebersicht(wochen_umgebung):
    plan = _gebauter_plan(wochen_umgebung)
    plan.daten["vermerke"] = ["Kein Apify-Lauf: Monatsguthaben 1.50 $ unter 2 $"]
    plan.themen[1]["vermerk"] = "schwach im Test"
    plan.themen[3]["status"] = "fehlgeschlagen"
    plan.themen.append(dict(plan.themen[0], status="ersetzt", thema="Altes Thema",
                            vermerk="keine Antwort auf die Frage"))
    text = uebersicht(plan)
    assert text.startswith("Wochenpaket 2026-KW44 (Di 27.10. bis Sa 31.10.), nichts ist gepostet.")
    assert "Di 27.10. 19:00 · Reel · Thema 1\n   Quelle: Ideen-Liste · Test gut (Wegwisch 30 %, Teilen 10 %)" in text
    assert "Mi 28.10. 19:00 · Karussell · Thema 2" in text and "   Vermerk: schwach im Test" in text
    assert "Sa 31.10. 19:00 · Karussell · Thema 4\n   Quelle: Ideen-Liste · Test gut (Wegwisch 30 %, Teilen 10 %) · FEHLGESCHLAGEN" in text
    assert "Ersetzt: «Altes Thema» (keine Antwort auf die Frage)" in text
    assert text.endswith("Vermerke:\n- Kein Apify-Lauf: Monatsguthaben 1.50 $ unter 2 $")


def test_status_text(wochen_umgebung):
    text = status_text(_gebauter_plan(wochen_umgebung))
    zeilen = text.splitlines()
    assert zeilen[0] == "Woche 2026-KW44"
    assert zeilen[1] == "vorbereitet: 2026-10-23T22:00 · gebaut: offen · gesendet: offen"
    assert zeilen[2].startswith("1 Di 27.10. reel") and zeilen[2].endswith("gebaut")
    assert len(zeilen) == 6


def test_senden_haelt_schritt_nach_abbruch_fest(wochen_umgebung, agentur_attrappe):
    """Abbruch nach dem letzten Beitrag, vor dem Festhalten: Wiederholung schickt nichts mehr und hält fest."""
    u = wochen_umgebung
    plan = _gebauter_plan(u)
    for t in plan.aktive():
        plan.setze(t, "gesendet")
    assert senden(WOCHE, u.pfade, u.dienste(agentur_attrappe()), lambda t: None) == 0
    assert u.telegram.aufrufe == []
    assert _lade(u).daten["schritte"]["gesendet"] == "2026-10-23T22:00"


def test_senden_alle_fehlgeschlagen_schickt_uebersicht(wochen_umgebung, agentur_attrappe):
    """Nichts gebaut, nichts gesendet: Die Übersicht mit den Fehlschlägen geht trotzdem raus."""
    u = wochen_umgebung
    plan = _gebauter_plan(u)
    for t in plan.aktive():
        plan.setze(t, "fehlgeschlagen")
    assert senden(WOCHE, u.pfade, u.dienste(agentur_attrappe()), lambda t: None) == 0
    assert u.telegram.methoden() == ["sendMessage"]
    assert "FEHLGESCHLAGEN" in u.telegram.texte()[0]
    assert _lade(u).daten["schritte"]["gesendet"] == "2026-10-23T22:00"


def test_karussell_ohne_slides_fehlgeschlagen_ohne_caption(wochen_umgebung, agentur_attrappe):
    """Karussell-Ordner ohne slide-*.png: kein leeres Album, keine Caption, Thema fehlgeschlagen."""
    u = wochen_umgebung
    plan = _gebauter_plan(u)
    ordner = Path(plan.aktive()[1]["ordner"])
    for png in ordner.glob("slide-*.png"):
        png.unlink()
    assert senden(WOCHE, u.pfade, u.dienste(agentur_attrappe()), lambda t: None) == 3
    assert "Caption 2" not in u.telegram.texte()
    assert u.telegram.methoden().count("sendMediaGroup") == 1
    t = _lade(u).aktive()[1]
    assert t["status"] == "fehlgeschlagen"
    assert "keine Slides" in t["vermerk"]
    zeile = "Thema 2\n   Quelle: Ideen-Liste · Test gut (Wegwisch 30 %, Teilen 10 %) · FEHLGESCHLAGEN"
    assert zeile in u.telegram.texte()[0]
    assert _lade(u).daten["schritte"]["gesendet"] == "2026-10-23T22:00"


def test_hinweis_bei_ueberlaenge(wochen_umgebung, agentur_attrappe):
    u = wochen_umgebung
    plan = _gebauter_plan(u)
    plan.themen[0].update(laenge="kurz", dauer_s=41.2)    # Di-Reel zu lang
    plan.themen[2].update(laenge="mittel", dauer_s=44.0)  # Do-Reel im Rahmen
    plan.speichere()
    senden(WOCHE, u.pfade, u.dienste(agentur_attrappe()), lambda t: None)
    texte = u.telegram.texte()
    assert texte[1] == "Caption 1"
    assert texte[2] == "⚠️ Reel ist 41 s lang (Ziel kurz: 20 bis 30 s)."
    assert sum("⚠️ Reel ist" in t for t in texte) == 1


def test_aussprache_zeile_nach_laengenhinweis(wochen_umgebung, agentur_attrappe):
    u = wochen_umgebung
    plan = _gebauter_plan(u)
    plan.themen[0].update(laenge="kurz", dauer_s=41.2, aussprache_neu=[["Trottoir", "Gehweg"]])
    plan.themen[2].update(aussprache_neu=[])
    plan.speichere()
    senden(WOCHE, u.pfade, u.dienste(agentur_attrappe()), lambda t: None)
    texte = u.telegram.texte()
    assert texte[1] == "Caption 1"
    assert texte[2] == "⚠️ Reel ist 41 s lang (Ziel kurz: 20 bis 30 s)."
    assert texte[3] == "🗣 Neu für die Stimme: Trottoir → Gehweg"
    assert sum("🗣" in t for t in texte) == 1
