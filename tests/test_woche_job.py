import os
from datetime import datetime

import pytest

from lib import lernen, woche
from lib.woche import SchrittFehler, fuehre_aus
from lib.wochenplan import Wochenplan

WOCHE = "2026-KW44"
FREITAG, SAMSTAG = datetime(2026, 10, 23, 22, 0), datetime(2026, 10, 24, 22, 30)
SONNTAG = datetime(2026, 10, 25, 14, 0)


@pytest.fixture
def schritte(monkeypatch):
    aufrufe = []
    monkeypatch.setattr(woche, "vorbereiten", lambda w, p, d, log, fragen=True: aufrufe.append(("vorbereiten", fragen)))
    monkeypatch.setattr(woche, "bauen", lambda w, p, d, log: aufrufe.append(("bauen", None)))
    return aufrufe


def _plan(u):
    return Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE)


def _job(u, a, schritt, jetzt):
    return fuehre_aus(f"job-{schritt}", WOCHE, u.pfade, u.dienste(a, jetzt=jetzt), lambda t: None)


def test_job_ausserhalb_des_fensters(wochen_umgebung, agentur_attrappe, schritte):
    u = wochen_umgebung
    assert _job(u, agentur_attrappe(), "bauen", datetime(2026, 10, 21, 22, 0)) == 0
    assert schritte == [] and u.telegram.aufrufe == []


def test_job_vorbereiten_im_fenster(wochen_umgebung, agentur_attrappe, schritte):
    assert _job(wochen_umgebung, agentur_attrappe(), "vorbereiten", FREITAG) == 0
    assert schritte == [("vorbereiten", True)]


def test_job_bauen_holt_vorbereiten_ohne_fragen_nach(wochen_umgebung, agentur_attrappe, schritte):
    assert _job(wochen_umgebung, agentur_attrappe(), "bauen", SAMSTAG) == 0
    assert schritte == [("vorbereiten", False), ("bauen", None)]


def test_job_bauen_wenn_vorbereitet(wochen_umgebung, agentur_attrappe, schritte):
    _plan(wochen_umgebung).schritt_fertig("vorbereitet", FREITAG)
    _job(wochen_umgebung, agentur_attrappe(), "bauen", SAMSTAG)
    assert schritte == [("bauen", None)]


def test_ausfall_wird_einmal_gemeldet(wochen_umgebung, agentur_attrappe, schritte):
    u = wochen_umgebung
    _job(u, agentur_attrappe(), "bauen", SONNTAG)
    _job(u, agentur_attrappe(), "vorbereiten", SONNTAG)
    assert u.telegram.texte() == ["Paket KW44 ausgefallen: kein Lauf bis So 12:00 (Mac aus oder im Ruhezustand?)"]
    assert _plan(u).daten["ausfall_gemeldet"] is True
    assert schritte == []


def test_ausfall_nennt_den_fehler(wochen_umgebung, agentur_attrappe, schritte):
    u = wochen_umgebung
    plan = _plan(u)
    plan.schritt_fertig("vorbereitet", FREITAG)
    plan.vermerke("bauen gescheitert: Claude nicht erreichbar")
    _job(u, agentur_attrappe(), "bauen", datetime(2026, 10, 25, 12, 30))
    assert u.telegram.texte() == ["Paket KW44 ausgefallen: bauen gescheitert: Claude nicht erreichbar"]


def test_kein_ausfall_wenn_etwas_gebaut(wochen_umgebung, agentur_attrappe, schritte):
    u = wochen_umgebung
    plan = _plan(u)
    plan.daten["themen"] = [{"nr": 1, "status": "gesendet"}]
    plan.speichere()
    _job(u, agentur_attrappe(), "bauen", SONNTAG)
    assert u.telegram.texte() == []


def test_fuehre_aus_meldet_fehler(wochen_umgebung, agentur_attrappe, monkeypatch):
    u = wochen_umgebung

    def kaputt(w, p, d, log):
        raise SchrittFehler("Claude nicht erreichbar\nZeile zwei")
    monkeypatch.setattr(woche, "bauen", kaputt)
    log = []
    assert fuehre_aus("bauen", WOCHE, u.pfade, u.dienste(agentur_attrappe()), log.append) == 1
    assert log[-1] == "Fehler: Claude nicht erreichbar Zeile zwei"
    assert u.telegram.texte() == ["Fliessband 2026-KW44: bauen gescheitert. Claude nicht erreichbar Zeile zwei"]
    assert "bauen gescheitert: Claude nicht erreichbar Zeile zwei" in _plan(u).daten["vermerke"]
    assert not (u.pfade.daten / f"sperre-{WOCHE}").exists()


def test_fuehre_aus_ohne_telegram(wochen_umgebung, agentur_attrappe, monkeypatch):
    u = wochen_umgebung
    u.telegram.scheitern_bei = "sendMessage"

    def kaputt(w, p, d, log):
        raise SchrittFehler("kein Netz")
    monkeypatch.setattr(woche, "bauen", kaputt)
    assert fuehre_aus("bauen", WOCHE, u.pfade, u.dienste(agentur_attrappe()), lambda t: None) == 1


def test_fuehre_aus_sperre(wochen_umgebung, agentur_attrappe, schritte):
    u = wochen_umgebung
    sperre = u.pfade.daten / f"sperre-{WOCHE}"
    sperre.write_text(str(os.getpid()))
    log = []
    assert fuehre_aus("bauen", WOCHE, u.pfade, u.dienste(agentur_attrappe()), log.append) == 0
    assert schritte == [] and log[0].startswith("Läuft bereits")
    assert sperre.exists()


def test_programmierfehler_wird_nicht_verschluckt(wochen_umgebung, agentur_attrappe, monkeypatch):
    u = wochen_umgebung

    def bug(w, p, d, log):
        raise RuntimeError("Bug")
    monkeypatch.setattr(woche, "bauen", bug)
    with pytest.raises(RuntimeError, match="Bug"):
        fuehre_aus("bauen", WOCHE, u.pfade, u.dienste(agentur_attrappe()), lambda t: None)
    assert not (u.pfade.daten / f"sperre-{WOCHE}").exists()


def test_job_ausserhalb_des_fensters_liest_den_plan_nicht(wochen_umgebung, agentur_attrappe, schritte):
    u = wochen_umgebung
    u.pfade.plan(WOCHE).parent.mkdir(parents=True, exist_ok=True)
    u.pfade.plan(WOCHE).write_text("{kaputt", encoding="utf-8")
    assert _job(u, agentur_attrappe(), "bauen", datetime(2026, 10, 21, 22, 0)) == 0
    assert u.telegram.aufrufe == []


def test_job_vorbereiten_im_bauen_fenster_baut_gleich(wochen_umgebung, agentur_attrappe, schritte):
    # Mac schlief Fr und Sa 22:00: launchd holt beide Jobs gleichzeitig nach, nur einer bekommt die Sperre
    assert _job(wochen_umgebung, agentur_attrappe(), "vorbereiten", SAMSTAG) == 0
    assert schritte == [("vorbereiten", False), ("bauen", None)]


FREITAG_ABEND = datetime(2026, 10, 23, 20, 30)


@pytest.fixture
def lern_aufrufe():
    aufrufe = []

    def lauf(pfade, dienste, w, log, probe=False):
        aufrufe.append((w, probe))
        lernen.schreibe_stand(pfade, w, dienste.jetzt(), "ok")
        return "ok"

    return aufrufe, lauf


def _mit_lernen(u, a, jetzt, lauf):
    d = u.dienste(a, jetzt=jetzt)
    d.lernen = lauf
    return d


def test_job_lernen_im_fenster(wochen_umgebung, agentur_attrappe, lern_aufrufe, schritte):
    aufrufe, lauf = lern_aufrufe
    d = _mit_lernen(wochen_umgebung, agentur_attrappe(), FREITAG_ABEND, lauf)
    assert fuehre_aus("job-lernen", WOCHE, wochen_umgebung.pfade, d, lambda t: None) == 0
    assert aufrufe == [(WOCHE, False)] and schritte == []
    assert fuehre_aus("job-lernen", WOCHE, wochen_umgebung.pfade, d, lambda t: None) == 0
    assert aufrufe == [(WOCHE, False)]   # schon gelaufen


def test_job_lernen_ausserhalb_des_fensters(wochen_umgebung, agentur_attrappe, lern_aufrufe):
    aufrufe, lauf = lern_aufrufe
    d = _mit_lernen(wochen_umgebung, agentur_attrappe(), datetime(2026, 10, 22, 20, 0), lauf)
    assert fuehre_aus("job-lernen", WOCHE, wochen_umgebung.pfade, d, lambda t: None) == 0
    assert aufrufe == [] and wochen_umgebung.telegram.aufrufe == []


def test_job_lernen_meldet_nie_ausfall(wochen_umgebung, agentur_attrappe, lern_aufrufe):
    aufrufe, lauf = lern_aufrufe
    d = _mit_lernen(wochen_umgebung, agentur_attrappe(), SONNTAG, lauf)
    assert fuehre_aus("job-lernen", WOCHE, wochen_umgebung.pfade, d, lambda t: None) == 0
    assert aufrufe == [] and wochen_umgebung.telegram.aufrufe == []


def test_vorbereiten_holt_lernen_nach(wochen_umgebung, agentur_attrappe, lern_aufrufe, schritte):
    aufrufe, lauf = lern_aufrufe
    d = _mit_lernen(wochen_umgebung, agentur_attrappe(), FREITAG, lauf)
    assert fuehre_aus("job-vorbereiten", WOCHE, wochen_umgebung.pfade, d, lambda t: None) == 0
    assert aufrufe == [(WOCHE, False)] and schritte == [("vorbereiten", True)]
    assert fuehre_aus("job-vorbereiten", WOCHE, wochen_umgebung.pfade, d, lambda t: None) == 0
    assert aufrufe == [(WOCHE, False)]


def test_bauen_holt_lernen_vor_vorbereiten_nach(wochen_umgebung, agentur_attrappe, lern_aufrufe, schritte):
    aufrufe, lauf = lern_aufrufe
    d = _mit_lernen(wochen_umgebung, agentur_attrappe(), SAMSTAG, lauf)
    assert fuehre_aus("job-bauen", WOCHE, wochen_umgebung.pfade, d, lambda t: None) == 0
    assert aufrufe == [(WOCHE, False)] and schritte == [("vorbereiten", False), ("bauen", None)]


def test_ohne_lernen_dienst_keine_lern_schleife(wochen_umgebung, agentur_attrappe, schritte):
    assert _job(wochen_umgebung, agentur_attrappe(), "vorbereiten", FREITAG) == 0
    assert schritte == [("vorbereiten", True)]


def test_befehl_lernen_und_probe(wochen_umgebung, agentur_attrappe, monkeypatch):
    aufrufe = []
    monkeypatch.setattr(lernen, "lauf", lambda p, d, w, log, probe=False: aufrufe.append(probe) or (
        "Text" if probe else "fehler"))
    d = wochen_umgebung.dienste(agentur_attrappe(), jetzt=FREITAG)
    assert fuehre_aus("lernen", WOCHE, wochen_umgebung.pfade, d, lambda t: None) == 1
    assert fuehre_aus("lernen-probe", WOCHE, wochen_umgebung.pfade, d, lambda t: None) == 0
    assert aufrufe == [False, True]


@pytest.mark.parametrize("jetzt, laeuft", [
    (datetime(2026, 10, 23, 21, 29), True), (datetime(2026, 10, 23, 21, 30), False),
    (datetime(2026, 10, 23, 21, 56), False), (datetime(2026, 10, 24, 10, 0), False)])
def test_job_lernen_nur_bis_2130(wochen_umgebung, agentur_attrappe, lern_aufrufe, jetzt, laeuft):
    aufrufe, lauf = lern_aufrufe
    d = _mit_lernen(wochen_umgebung, agentur_attrappe(), jetzt, lauf)
    assert fuehre_aus("job-lernen", WOCHE, wochen_umgebung.pfade, d, lambda t: None) == 0
    assert aufrufe == ([(WOCHE, False)] if laeuft else [])
