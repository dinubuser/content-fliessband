import re
from datetime import datetime

import pytest

from lib import woche
from lib.manifest import lade
from lib.wochenplan import Wochenplan

WOCHE = "2026-KW44"
SAMSTAG = datetime(2026, 10, 24, 22, 0)


@pytest.fixture
def ohne_platzhalter(agentur_attrappe):
    """Agentur, deren Karussell-Texte keine [Platzhalter] enthalten (Manifest-Status entwurf statt braucht_eingabe)."""
    class OhnePlatzhalter(agentur_attrappe):
        def claude(self, agent, auftrag, ausgabe, *args, **kwargs):
            pfad = super().claude(agent, auftrag, ausgabe, *args, **kwargs)
            if pfad.suffix == ".md" and "_reel_" not in pfad.name:
                pfad.write_text(re.sub(r"\[[^\]]+\]", "", pfad.read_text(encoding="utf-8")), encoding="utf-8")
            return pfad
    return OhnePlatzhalter


def _gesendete_woche(u, a, briefkasten, log=None):
    """Ganze Woche mit echten Bauern (schnell) bauen und senden, mit Briefkasten."""
    log = log if log is not None else []
    freitag = u.dienste(a, jetzt=datetime(2026, 10, 23, 22, 0), briefkasten=briefkasten)
    assert woche.fuehre_aus("job-vorbereiten", WOCHE, u.pfade, freitag, log.append) == 0
    samstag = u.dienste(a, jetzt=SAMSTAG, briefkasten=briefkasten)
    assert woche.fuehre_aus("job-bauen", WOCHE, u.pfade, samstag, log.append) == 0
    return Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE)


def test_senden_meldet_alle_und_die_woche(wochen_umgebung, agentur_attrappe, ohne_platzhalter, briefkasten, schnell,
                                          schnelles_karussell):
    u = wochen_umgebung
    plan = _gesendete_woche(u, ohne_platzhalter(fragen=0), briefkasten)
    ids = [b["id"] for b in briefkasten.gemeldet]
    assert ids == ["2026-KW44-reel-beispiel-reel-eins", "2026-KW44-notgroschen-beispiel",
                   "2026-KW44-reel-drei-fehler", "2026-KW44-demokonto-woche"]
    assert briefkasten.gemeldet[0] == {"id": "2026-KW44-reel-beispiel-reel-eins", "woche": WOCHE, "version": 1,
                                       "titel": "Thema beispiel-reel-eins", "format": "reel",
                                       "termin": "2026-10-27T19:00", "neubauten": 0, "platzhalter": False}
    assert briefkasten.fertig_wochen == [WOCHE]
    assert [t["angemeldet"] for t in plan.aktive()] == [1, 1, 1, 1]
    assert plan.daten["fertig_gemeldet"] is True
    woche.melde_offene(plan, WOCHE, u.pfade, u.dienste(agentur_attrappe(), briefkasten=briefkasten),
                       lambda t: None)
    assert len(briefkasten.gemeldet) == 4 and briefkasten.fertig_wochen == [WOCHE]


def test_briefkasten_weg_wird_nachgeholt(wochen_umgebung, agentur_attrappe, ohne_platzhalter, briefkasten, schnell,
                                         schnelles_karussell):
    u = wochen_umgebung
    briefkasten.nicht_erreichbar = True
    log = []
    plan = _gesendete_woche(u, ohne_platzhalter(fragen=0), briefkasten, log)
    assert [t["status"] for t in plan.aktive()] == ["gesendet"] * 4
    assert all(not t.get("angemeldet") for t in plan.aktive())
    assert any("Anmelden gescheitert" in z for z in log)
    briefkasten.nicht_erreichbar = False
    woche.melde_offene(plan, WOCHE, u.pfade, u.dienste(agentur_attrappe(), briefkasten=briefkasten),
                       lambda t: None)
    assert len(briefkasten.gemeldet) == 4 and briefkasten.fertig_wochen == [WOCHE]


def test_ohne_briefkasten_keine_anmeldung(wochen_umgebung, ohne_platzhalter, schnell, schnelles_karussell):
    u = wochen_umgebung
    plan = _gesendete_woche(u, ohne_platzhalter(fragen=0), None)
    assert all("angemeldet" not in t for t in plan.aktive())
    manifest = lade(u.pfade.woche(WOCHE) / "manifest.json", WOCHE)
    assert all(b["status"] == "entwurf" for b in manifest["beitraege"])


def test_senden_ohne_uebersicht(wochen_umgebung, agentur_attrappe, ohne_platzhalter, briefkasten, schnell, schnelles_karussell):
    u = wochen_umgebung
    plan = _gesendete_woche(u, ohne_platzhalter(fragen=0), briefkasten)
    plan.setze(plan.aktive()[0], "gebaut")
    u.telegram.aufrufe.clear()
    dienste = u.dienste(agentur_attrappe(), briefkasten=briefkasten)
    assert woche.senden(WOCHE, u.pfade, dienste, lambda t: None, plan=plan, mit_uebersicht=False) == 1
    assert u.telegram.methoden() == ["sendVideo", "sendMessage"]


def test_braucht_eingabe_mit_platzhalter_angemeldet(wochen_umgebung, agentur_attrappe, briefkasten, schnell,
                                                 schnelles_karussell):
    """Karussell mit [Platzhalter] (Manifest braucht_eingabe): wird mit Merkmal platzhalter angemeldet (nur Ändern
    und Verwerfen in Telegram), die übrigen ohne."""
    u = wochen_umgebung
    plan = _gesendete_woche(u, agentur_attrappe(fragen=0), briefkasten)
    assert [t["status"] for t in plan.aktive()] == ["gesendet"] * 4
    assert [(b["id"], b["platzhalter"]) for b in briefkasten.gemeldet] == [
        ("2026-KW44-reel-beispiel-reel-eins", False), ("2026-KW44-notgroschen-beispiel", True),
        ("2026-KW44-reel-drei-fehler", False), ("2026-KW44-demokonto-woche", True)]
    assert [t.get("angemeldet") for t in plan.aktive()] == [1, 1, 1, 1]
    assert briefkasten.fertig_wochen == [WOCHE]


def _ohne_knoepfe_gesendet(u, a):
    """Gesendete Woche ohne Briefkasten (nichts angemeldet), danach alle Beiträge verworfen (bekommen keine
    Knöpfe mehr; braucht_eingabe wird seit 2026-10-23 mit Merkmal platzhalter angemeldet)."""
    from lib.manifest import schreibe_json
    plan = _gesendete_woche(u, a, None)
    pfad = u.pfade.woche(WOCHE) / "manifest.json"
    daten = lade(pfad, WOCHE)
    for b in daten["beitraege"]:
        b["status"] = "verworfen"
    schreibe_json(pfad, daten)
    return plan


def test_fertig_nur_mit_angemeldeten_beitraegen(wochen_umgebung, agentur_attrappe, ohne_platzhalter, briefkasten,
                                                schnell, schnelles_karussell):
    """Ohne einen einzigen angemeldeten Beitrag lehnt der Server «fertig» mit 400 ab. Dann nicht aufrufen, nur
    als gemeldet merken (sonst versucht es jeder Lauf neu und meldet nach 8 Läufen «Briefkasten gestört»)."""
    u = wochen_umgebung
    plan = _ohne_knoepfe_gesendet(u, ohne_platzhalter(fragen=0))
    briefkasten.nicht_erreichbar = True   # jeder Aufruf schlüge fehl
    fehler = []
    dienste = u.dienste(agentur_attrappe(), jetzt=SAMSTAG, briefkasten=briefkasten)
    assert woche.melde_offene(plan, WOCHE, u.pfade, dienste, lambda t: None, fehler=fehler) is True
    assert fehler == [] and briefkasten.fertig_wochen == [] and briefkasten.gemeldet == []
    assert Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE).daten["fertig_gemeldet"] is True



def test_termin_vorbei_wird_nicht_angemeldet(wochen_umgebung, agentur_attrappe, ohne_platzhalter, briefkasten,
                                             schnell, schnelles_karussell):
    """Beitrag mit erreichtem Termin: keine Knöpfe mehr (der Server setzte ihn ohnehin auf verpasst), zählt
    aber als erledigt für «fertig»."""
    u = wochen_umgebung
    plan = _gesendete_woche(u, ohne_platzhalter(fragen=0), None)
    dienste = u.dienste(agentur_attrappe(), jetzt=datetime(2026, 10, 27, 19, 0), briefkasten=briefkasten)
    zeilen = []
    assert woche.melde_offene(plan, WOCHE, u.pfade, dienste, zeilen.append) is True
    assert [b["id"] for b in briefkasten.gemeldet] == ["2026-KW44-notgroschen-beispiel", "2026-KW44-reel-drei-fehler",
                                                       "2026-KW44-demokonto-woche"]
    assert briefkasten.fertig_wochen == [WOCHE]
    assert any("Termin vorbei" in z for z in zeilen)


def test_zu_viele_hashtags_keine_knoepfe(wochen_umgebung, ohne_platzhalter, briefkasten, schnell, schnelles_karussell):
    from pathlib import Path
    u = wochen_umgebung
    plan = _gesendete_woche(u, ohne_platzhalter(fragen=0), None)
    t = plan.aktive()[1]
    (Path(t["ordner"]) / "caption.txt").write_text(" ".join(f"#t{i}" for i in range(31)), encoding="utf-8")
    log = []
    dienste = u.dienste(ohne_platzhalter(fragen=0), jetzt=SAMSTAG, briefkasten=briefkasten)
    woche.melde_offene(plan, WOCHE, u.pfade, dienste, log.append)
    assert t["slug"] not in " ".join(b["id"] for b in briefkasten.gemeldet)
    assert any("zu viele Hashtags" in x for x in u.telegram.texte())
    u.telegram.aufrufe.clear()
    woche.melde_offene(plan, WOCHE, u.pfade, dienste, log.append)
    assert not any("zu viele Hashtags" in x for x in u.telegram.texte())   # nur einmal
