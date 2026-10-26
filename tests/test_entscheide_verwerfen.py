import re
from datetime import datetime

import pytest

from lib import entscheide, woche
from lib.freigabe import eintrag, manifest_pfad
from lib.reel_renderer import RenderFehler
from lib.wochenplan import Wochenplan
from tests.test_entscheide_aendern import _ohne_laenge

WOCHE = "2026-KW44"
SONNTAG = datetime(2026, 10, 25, 9, 0)


@pytest.fixture
def gesendet(wochen_umgebung, agentur_attrappe, briefkasten, schnell, schnelles_karussell):
    """Karussell-Texte ohne [Platzhalter] (sonst braucht_eingabe und ohne Knöpfe), ausser platzhalter_weg ist aus."""
    class OhnePlatzhalter(agentur_attrappe):
        platzhalter_weg = True

        def claude(self, agent, auftrag, ausgabe, *args, **kwargs):
            pfad = super().claude(agent, auftrag, ausgabe, *args, **kwargs)
            if self.platzhalter_weg and pfad.suffix == ".md" and "_reel_" not in pfad.name:
                pfad.write_text(re.sub(r"\[[^\]]+\]", "", pfad.read_text(encoding="utf-8")), encoding="utf-8")
            return pfad

    u = wochen_umgebung
    a = OhnePlatzhalter(fragen=0)
    for schritt, jetzt in (("job-vorbereiten", datetime(2026, 10, 23, 22, 0)),
                           ("job-bauen", datetime(2026, 10, 24, 22, 0))):
        assert woche.fuehre_aus(schritt, WOCHE, u.pfade, u.dienste(a, jetzt=jetzt, briefkasten=briefkasten),
                                lambda t: None) == 0
    u.telegram.aufrufe.clear()
    briefkasten.gemeldet.clear()
    return u, a


def _lauf(u, a, briefkasten, log=None):
    return entscheide.entscheide(u.pfade, u.dienste(a, jetzt=SONNTAG, briefkasten=briefkasten),
                                 (log if log is not None else []).append)


def test_verwerfen_baut_reserve(gesendet, briefkasten):
    u, a = gesendet
    briefkasten.ereignis("verworfen", beitrag="2026-KW44-demokonto-woche")
    assert _lauf(u, a, briefkasten) == 1
    e = eintrag(manifest_pfad(u.pfade, WOCHE), WOCHE, "2026-KW44-demokonto-woche")
    assert e["status"] == "verworfen" and e["entschieden"] == "2026-10-25T09:00:00+01:00"
    plan = Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE)
    ersetzt = next(t for t in plan.themen if t["slug"] == "demokonto-woche")
    reserve = next(t for t in plan.aktive() if t["slug"] == "reserve-karussell")
    assert ersetzt["status"] == "ersetzt" and ersetzt["vermerk"] == "Der Betreiber hat verworfen"
    assert (reserve["status"], reserve["termin"], reserve["angemeldet"]) == ("gesendet", "2026-10-31T19:00", 1)
    assert [b["id"] for b in briefkasten.gemeldet] == ["2026-KW44-reserve-karussell"]
    assert u.telegram.methoden() == ["sendMediaGroup", "sendMessage"]
    assert not any(t.startswith("Wochenpaket") for t in u.telegram.texte())


def test_verwerfen_wiederholt_holt_keine_zweite_reserve(gesendet, briefkasten):
    u, a = gesendet
    briefkasten.ereignis("verworfen", beitrag="2026-KW44-demokonto-woche")
    assert _lauf(u, a, briefkasten) == 1
    plan = Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE)
    reserve_vorher = list(plan.daten["reserve"])
    # Abholen gilt «mindestens einmal»: dasselbe Ereignis kommt nochmals
    briefkasten.stand["entscheide"] = 0
    u.telegram.aufrufe.clear()
    log = []
    assert _lauf(u, a, briefkasten, log) == 1
    plan = Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE)
    assert plan.daten["reserve"] == reserve_vorher
    assert u.telegram.aufrufe == []
    assert any("schon verworfen" in z for z in log)


def test_keine_reserve_mehr(gesendet, briefkasten):
    u, a = gesendet
    plan = Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE)
    plan.daten["reserve"] = []
    plan.speichere()
    briefkasten.ereignis("verworfen", beitrag="2026-KW44-demokonto-woche")
    assert _lauf(u, a, briefkasten) == 1
    assert u.telegram.texte() == ["Keine Reserve mehr: «Thema demokonto-woche» fällt diese Woche weg."]
    assert briefkasten.gemeldet == []


def test_reserve_scheitert(gesendet, briefkasten, monkeypatch):
    u, a = gesendet

    def kaputt(*args, **kwargs):
        raise RenderFehler("Chromium abgestürzt")
    monkeypatch.setattr(woche, "baue_karussell", kaputt)
    briefkasten.ereignis("verworfen", beitrag="2026-KW44-demokonto-woche")
    assert _lauf(u, a, briefkasten) == 1
    assert u.telegram.texte() == ["Reserve für «Thema demokonto-woche» gescheitert: Chromium abgestürzt"]


def test_reserve_mit_platzhaltern_nur_aendern_verwerfen(gesendet, briefkasten):
    u, a = gesendet
    a.platzhalter_weg = False
    briefkasten.ereignis("verworfen", beitrag="2026-KW44-demokonto-woche")
    assert _lauf(u, a, briefkasten) == 1
    assert [(b["id"], b["platzhalter"]) for b in briefkasten.gemeldet] == [("2026-KW44-reserve-karussell", True)]
    assert u.telegram.methoden() == ["sendMediaGroup", "sendMessage", "sendMessage"]
    assert u.telegram.texte()[-1].startswith("Reserve für «Thema demokonto-woche» hat noch Platzhalter (Slide 9:")
    assert u.telegram.texte()[-1].endswith(", bitte per ✏️ Ändern ergänzen.")


def test_bauen_nutzt_baue_offene(wochen_umgebung, agentur_attrappe, monkeypatch):
    aufrufe = []
    monkeypatch.setattr(woche, "baue_offene", lambda plan, pfade, dienste, log: aufrufe.append(1) or False)
    u = wochen_umgebung
    a = agentur_attrappe(fragen=0)
    woche.vorbereiten(WOCHE, u.pfade, u.dienste(a), lambda t: None)
    woche.bauen(WOCHE, u.pfade, u.dienste(a, jetzt=datetime(2026, 10, 24, 22, 0)), lambda t: None)
    assert aufrufe == [1]


def test_termin_zu_nah_keine_reserve(gesendet, briefkasten):
    u, a = gesendet
    plan = Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE)
    reserve_vorher = list(plan.daten["reserve"])
    termin = next(t for t in plan.themen if t["slug"] == "demokonto-woche")["termin"]
    kurz_davor = datetime.fromisoformat(termin) - woche.timedelta(hours=1, minutes=30)
    briefkasten.ereignis("verworfen", beitrag="2026-KW44-demokonto-woche")
    assert entscheide.entscheide(u.pfade, u.dienste(a, jetzt=kurz_davor, briefkasten=briefkasten),
                                 lambda t: None) == 1
    e = eintrag(manifest_pfad(u.pfade, WOCHE), WOCHE, "2026-KW44-demokonto-woche")
    assert e["status"] == "verworfen" and e["umgesetzt_nr"] == 1
    plan = Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE)
    assert plan.daten["reserve"] == reserve_vorher
    assert u.telegram.texte() == ["Termin zu nah, «Thema demokonto-woche» fällt weg, keine Reserve."]
    assert briefkasten.gemeldet == []


def test_absturz_nach_ersetzen_setzt_fort(gesendet, briefkasten, monkeypatch):
    u, a = gesendet

    def absturz(*args, **kwargs):
        raise KeyboardInterrupt
    monkeypatch.setattr(entscheide, "baue_offene", absturz)
    briefkasten.ereignis("verworfen", beitrag="2026-KW44-demokonto-woche")
    with pytest.raises(KeyboardInterrupt):
        _lauf(u, a, briefkasten)
    for sperre in u.pfade.daten.glob("sperre-*"):
        sperre.unlink()
    plan = Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE)
    assert next(t for t in plan.aktive() if t["slug"] == "reserve-karussell")["status"] == "bereit"
    monkeypatch.setattr(entscheide, "baue_offene", woche.baue_offene)
    assert _lauf(u, a, briefkasten) == 1
    plan = Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE)
    reserve = next(t for t in plan.aktive() if t["slug"] == "reserve-karussell")
    assert (reserve["status"], reserve["angemeldet"]) == ("gesendet", 1)
    assert [b["id"] for b in briefkasten.gemeldet] == ["2026-KW44-reserve-karussell"]
    assert u.telegram.methoden() == ["sendMediaGroup", "sendMessage"]


def test_meldung_nennt_ersatz_nach_guthaben_umbau(gesendet, briefkasten, monkeypatch):
    u, a = gesendet

    def umbau(plan, pfade, dienste, log):
        r = next(t for t in plan.aktive() if t["slug"] == "reserve-karussell")
        r["status"] = "ersetzt"
        plan.themen.append(dict(r, slug="noch-eine", status="fehlgeschlagen", vermerk="Guthaben weg"))
        plan.speichere()
        return False
    monkeypatch.setattr(entscheide, "baue_offene", umbau)
    briefkasten.ereignis("verworfen", beitrag="2026-KW44-demokonto-woche")
    assert _lauf(u, a, briefkasten) == 1
    assert u.telegram.texte() == ["Reserve für «Thema demokonto-woche» gescheitert: Guthaben weg"]


def test_verwerfen_reel_alte_daten_ohne_laenge(gesendet, briefkasten):
    u, a = gesendet
    _ohne_laenge(u)
    briefkasten.ereignis("verworfen", beitrag="2026-KW44-reel-beispiel-reel-eins")
    assert _lauf(u, a, briefkasten) == 1
    plan = Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE)
    ersetzt = next(t for t in plan.themen if t["slug"] == "beispiel-reel-eins")
    assert ersetzt["status"] == "ersetzt"
    reserve = next(t for t in plan.aktive() if t["nr"] == ersetzt["nr"])
    assert reserve["slug"] != "beispiel-reel-eins"
    assert reserve["status"] == "gesendet" and reserve["angemeldet"] == 1
    assert len(briefkasten.gemeldet) == 1
