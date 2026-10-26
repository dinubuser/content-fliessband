import re
from datetime import datetime

import pytest

from lib import entscheide, woche
from lib.freigabe import eintrag, manifest_pfad
from lib.woche import Sperre
from lib.wochenplan import Wochenplan

WOCHE = "2026-KW44"
SONNTAG = datetime(2026, 10, 25, 9, 0)
REEL1 = "2026-KW44-reel-beispiel-reel-eins"


def _lauf(u, a, briefkasten, log=None):
    return entscheide.entscheide(u.pfade, u.dienste(a, jetzt=SONNTAG, briefkasten=briefkasten),
                                 (log if log is not None else []).append)


def _e(u, id=REEL1):
    return eintrag(manifest_pfad(u.pfade, WOCHE), WOCHE, id)


def test_wochen():
    assert entscheide.wochen(datetime(2026, 10, 25).date()) == ["2026-KW43", "2026-KW44"]
    assert entscheide.wochen(datetime(2026, 10, 27).date()) == ["2026-KW44", "2026-KW45"]


def test_freigegeben_zurueckgenommen_verpasst(gesendet, briefkasten):
    u, a = gesendet
    briefkasten.ereignis("freigegeben", beitrag=REEL1)
    briefkasten.ereignis("freigegeben", beitrag="2026-KW44-demokonto-woche")
    briefkasten.ereignis("zurueckgenommen", beitrag="2026-KW44-demokonto-woche", zeit="2026-10-25T09:05:00+01:00")
    briefkasten.ereignis("verpasst", beitrag="2026-KW44-reel-drei-fehler", zeit="2026-10-29T19:00:00+01:00")
    assert _lauf(u, a, briefkasten) == 4
    assert (_e(u)["status"], _e(u)["entschieden"]) == ("freigegeben", "2026-10-25T09:00:00+01:00")
    demo = _e(u, "2026-KW44-demokonto-woche")
    assert (demo["status"], demo["entschieden"]) == ("entwurf", None)
    assert _e(u, "2026-KW44-reel-drei-fehler")["status"] == "verpasst"
    assert briefkasten.stand["entscheide"] == 4
    assert _lauf(u, a, briefkasten) == 0
    assert briefkasten.gemeldet == [] and u.telegram.aufrufe == []


def test_braucht_eingabe_wird_nie_freigegeben(gesendet, briefkasten):
    """Schutz auf dem Mac: der Server zeigt keinen Freigeben-Knopf, ein Ereignis wird trotzdem nicht umgesetzt."""
    from lib import freigabe
    u, a = gesendet
    freigabe.aendere(manifest_pfad(u.pfade, WOCHE), WOCHE, REEL1, status="braucht_eingabe")
    briefkasten.ereignis("freigegeben", beitrag=REEL1)
    briefkasten.ereignis("zurueckgenommen", beitrag=REEL1)
    log = []
    assert _lauf(u, a, briefkasten, log) == 2
    assert (_e(u)["status"], _e(u)["entschieden"]) == ("braucht_eingabe", None)
    assert sum("Platzhalter, nicht umgesetzt" in z for z in log) == 2
    assert u.telegram.texte() == ["«Thema beispiel-reel-eins» nicht freigegeben, hat noch Platzhalter."]
    assert briefkasten.stand["entscheide"] == 2
    briefkasten.ereignis("verpasst", beitrag=REEL1, zeit="2026-10-27T19:00:00+01:00")
    assert _lauf(u, a, briefkasten) == 1
    assert _e(u)["status"] == "verpasst"


def test_unbekannter_beitrag_wird_uebersprungen(gesendet, briefkasten):
    u, a = gesendet
    briefkasten.ereignis("freigegeben", beitrag="2026-KW44-gibts-nicht")
    log = []
    assert _lauf(u, a, briefkasten, log) == 1
    assert any("übersprungen" in z for z in log) and briefkasten.stand["entscheide"] == 1


def test_gesperrte_woche_wartet(gesendet, briefkasten):
    u, a = gesendet
    briefkasten.ereignis("freigegeben", beitrag=REEL1)
    log = []
    with Sperre(u.pfade.daten / f"sperre-{WOCHE}"):
        assert _lauf(u, a, briefkasten, log) == 0
    assert briefkasten.stand["entscheide"] == 0 and _e(u)["status"] == "entwurf"
    assert any("gesperrt" in z for z in log)
    assert _lauf(u, a, briefkasten) == 1 and _e(u)["status"] == "freigegeben"


def test_holt_anmeldung_nach(gesendet, briefkasten):
    u, a = gesendet
    plan = Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE)
    plan.aktive()[1]["angemeldet"] = None
    plan.speichere()
    _lauf(u, a, briefkasten)
    assert [b["id"] for b in briefkasten.gemeldet] == ["2026-KW44-notgroschen-beispiel"]


def test_ohne_briefkasten(gesendet):
    u, a = gesendet
    with pytest.raises(entscheide.EntscheidFehler, match="nicht eingerichtet"):
        entscheide.entscheide(u.pfade, u.dienste(a, jetzt=SONNTAG), lambda t: None)


# --- Kaputte Ereignisse und Dauerfehler ---

class _RoherBriefkasten:
    """Liefert die Ereignisse ungefiltert (auch solche ohne nr), merkt sich gemerkte nr."""

    def __init__(self, liste):
        self.liste, self.gemerkt = liste, []

    def ereignisse(self, art):
        return list(self.liste)

    def merke(self, art, nr):
        self.gemerkt.append(nr)


def test_kaputte_ereignisse_werden_uebersprungen(wochen_umgebung, agentur_attrappe):
    u = wochen_umgebung
    zeit = "2026-10-25T09:00:00+01:00"
    bk = _RoherBriefkasten([
        {"nr": 1, "art": "freigegeben", "woche": WOCHE, "version": 1, "zeit": zeit},          # ohne beitrag
        {"nr": 2, "art": "aendern", "beitrag": REEL1, "woche": WOCHE, "version": 1, "zeit": zeit, "notiz": None},
        {"nr": 3, "art": "freigegeben", "beitrag": REEL1, "woche": WOCHE, "zeit": zeit},      # ohne version
        {"art": "freigegeben", "beitrag": REEL1, "woche": WOCHE, "version": 1, "zeit": zeit},  # ohne nr
        {"nr": 4, "art": "freigegeben", "beitrag": REEL1, "woche": None, "version": 1, "zeit": zeit},
    ])
    log = []
    n = entscheide.entscheide(u.pfade, u.dienste(agentur_attrappe(), jetzt=SONNTAG, briefkasten=bk), log.append)
    assert n == 4 and bk.gemerkt == [1, 2, 3, 4]
    assert sum("unvollständig" in z for z in log) == 5
    assert u.telegram.aufrufe == []


def _scheitere(u, a, bk, mal):
    for _ in range(mal):
        with pytest.raises(entscheide.BriefkastenFehler):
            entscheide.entscheide(u.pfade, u.dienste(a, jetzt=SONNTAG, briefkasten=bk), lambda t: None)


def test_dauerfehler_beim_abholen_einmal_gemeldet(wochen_umgebung, agentur_attrappe, briefkasten):
    u, a = wochen_umgebung, agentur_attrappe()
    briefkasten.nicht_erreichbar = True
    _scheitere(u, a, briefkasten, entscheide.SCHWELLE - 1)
    assert u.telegram.aufrufe == []
    _scheitere(u, a, briefkasten, 3)
    assert u.telegram.methoden() == ["sendMessage"]
    text = u.telegram.aufrufe[0][1]["text"]
    assert text.startswith("Briefkasten seit 2 Stunden gestört (Briefkasten nicht erreichbar (URLError))")
    assert "Knöpfe funktionieren, umgesetzt wird erst danach." in text and "–" not in text
    # Erfolg setzt zurück, eine neue Störung wird wieder gemeldet
    briefkasten.nicht_erreichbar = False
    assert _lauf(u, a, briefkasten) == 0
    assert (u.pfade.daten / entscheide.STAND).exists()
    briefkasten.nicht_erreichbar = True
    _scheitere(u, a, briefkasten, entscheide.SCHWELLE)
    assert u.telegram.methoden() == ["sendMessage", "sendMessage"]


def test_dauerfehler_beim_anmelden_gemeldet(gesendet, briefkasten, monkeypatch):
    u, a = gesendet
    plan = Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE)
    plan.aktive()[0]["angemeldet"] = None
    plan.speichere()

    def kaputt(beitrag):
        raise entscheide.BriefkastenFehler("Briefkasten POST /beitraege: HTTP 401 falscher Schlüssel")
    monkeypatch.setattr(briefkasten, "melde", kaputt)
    for _ in range(entscheide.SCHWELLE + 2):
        assert _lauf(u, a, briefkasten) == 0
    texte = [x[1]["text"] for x in u.telegram.aufrufe if x[0] == "sendMessage"]
    assert len(texte) == 1 and "HTTP 401" in texte[0] and texte[0].startswith("Briefkasten seit 2 Stunden")
