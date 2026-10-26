import json
import os
from datetime import datetime

import pytest

from lib import woche
from lib.notiz import NotizFehler
from lib.woche import Protokoll, SchrittFehler, Sperre, SperreBelegt
from lib.wochenplan import Wochenplan

WOCHE = "2026-KW44"


def _plan(u, w=WOCHE):
    return Wochenplan.lade(u.pfade.plan(w), w)


def test_vorbereiten_plant_und_fragt(wochen_umgebung, agentur_attrappe):
    u = wochen_umgebung
    a = agentur_attrappe(konkurrenz=True)
    woche.vorbereiten(WOCHE, u.pfade, u.dienste(a), lambda t: None)
    plan = _plan(u)
    assert plan.daten["schritte"]["vorbereitet"] == "2026-10-23T22:00"
    assert [t["slug"] for t in plan.themen] == ["beispiel-reel-eins", "notgroschen-beispiel", "drei-fehler",
                                                "demokonto-woche"]
    assert [r["slug"] for r in plan.daten["reserve"]] == ["reserve-reel", "reserve-karussell"]
    assert [t["status"] for t in plan.themen] == ["frage_gesendet", "geplant", "geplant", "geplant"]
    assert plan.themen[0]["frage_nachricht"] == 101
    assert plan.themen[2]["vorlage"]["url"] == "https://www.instagram.com/reel/A1/"
    assert plan.daten["ausreisser"][0]["faktor"] == 5.3
    assert u.telegram.texte() == [
        "Frage 1/1 (Reel Di 27.10.): Welche Sätze hörst du im Alltag, wenn du Trading erwähnst?\n\n"
        "Tipp bei dieser Nachricht auf «Antworten» und schreib deine Antwort bis Samstag 22:00. "
        "Ohne Antwort oder mit «Ersatz» nehme ich ein anderes Thema."]
    assert a.aufrufe[:2] == [("apify.py", "check"), ("apify.py", "reels")]
    assert "Die Sätze aus dem Teamraum" in (u.pfade.woche(WOCHE) / "planer-eingabe.md").read_text(encoding="utf-8")
    liste = json.loads((u.pfade.daten / "konkurrenz.json").read_text(encoding="utf-8"))
    assert liste["gezaehlt"] == WOCHE
    assert [k["leere_wochen"] for k in liste["accounts"]][:2] == [0, 1]


def test_vorbereiten_ist_wiederholbar(wochen_umgebung, agentur_attrappe):
    u = wochen_umgebung
    a = agentur_attrappe()
    woche.vorbereiten(WOCHE, u.pfade, u.dienste(a), lambda t: None)
    anzahl, nachrichten = len(a.aufrufe), len(u.telegram.aufrufe)
    woche.vorbereiten(WOCHE, u.pfade, u.dienste(a), lambda t: None)
    assert len(a.aufrufe) == anzahl and len(u.telegram.aufrufe) == nachrichten


def test_apify_unter_zwei_dollar(wochen_umgebung, agentur_attrappe):
    u = wochen_umgebung
    a = agentur_attrappe(apify_rest=1.5)
    woche.vorbereiten(WOCHE, u.pfade, u.dienste(a), lambda t: None)
    plan = _plan(u)
    assert a.anzahl("apify.py") == 1
    assert plan.daten["ausreisser"] == []
    assert "Kein Apify-Lauf: Monatsguthaben 1.50 $ unter 2 $" in plan.daten["vermerke"]
    assert plan.vorbereitet


def test_erster_freitag_erneuert_konkurrenz(wochen_umgebung, agentur_attrappe):
    u = wochen_umgebung
    a = agentur_attrappe(woche="2026-KW46")
    woche.vorbereiten("2026-KW46", u.pfade, u.dienste(a, jetzt=datetime(2026, 11, 6, 22, 0)), lambda t: None)
    assert ("trend-agent", "konkurrenz-vorschlag.json") in a.aufrufe
    liste = json.loads((u.pfade.daten / "konkurrenz.json").read_text(encoding="utf-8"))
    assert liste["erneuert"] == "2026-11-06"
    assert [k["name"] for k in liste["accounts"]] == [f"neu.{i}" for i in range(8)]


def test_notiz_fehler_wird_vermerk(wochen_umgebung, agentur_attrappe):
    u = wochen_umgebung

    def kaputt(skript):
        raise NotizFehler("Apple-Notiz nicht lesbar: Not authorized (-1743)")

    woche.vorbereiten(WOCHE, u.pfade, u.dienste(agentur_attrappe(notiz=False), notiz=kaputt), lambda t: None)
    plan = _plan(u)
    assert plan.vorbereitet
    assert "Apple-Notiz nicht gelesen: Apple-Notiz nicht lesbar: Not authorized (-1743)" in plan.daten["vermerke"]


def test_ohne_fragen(wochen_umgebung, agentur_attrappe):
    u = wochen_umgebung
    a = agentur_attrappe(fragen=0)
    woche.vorbereiten(WOCHE, u.pfade, u.dienste(a), lambda t: None, fragen=False)
    assert u.telegram.texte() == []
    planer_auftrag = next(t for agent, t in a.auftraege if agent == "trend-agent")
    assert "keine Fragen an den Betreiber" in planer_auftrag


def test_frage_nicht_gesendet_wird_nachgeholt(wochen_umgebung, agentur_attrappe):
    u = wochen_umgebung
    u.telegram.scheitern_bei = "sendMessage"
    with pytest.raises(SchrittFehler, match="Frage 1 nicht gesendet"):
        woche.vorbereiten(WOCHE, u.pfade, u.dienste(agentur_attrappe()), lambda t: None)
    plan = _plan(u)
    assert plan.vorbereitet and plan.themen[0]["status"] == "geplant"
    u.telegram.scheitern_bei = None
    woche.vorbereiten(WOCHE, u.pfade, u.dienste(agentur_attrappe()), lambda t: None)
    assert _plan(u).themen[0]["status"] == "frage_gesendet"


def test_sperre(tmp_path):
    pfad = tmp_path / "daten" / "sperre-2026-KW44"
    with Sperre(pfad):
        assert pfad.read_text() == str(os.getpid())
        with pytest.raises(SperreBelegt, match="Läuft bereits"):
            with Sperre(pfad):
                pass
    assert not pfad.exists()


def test_verwaiste_sperre_wird_uebernommen(tmp_path):
    pfad = tmp_path / "sperre"
    pfad.write_text("999999")
    with Sperre(pfad):
        assert pfad.read_text() == str(os.getpid())


def test_protokoll(tmp_path):
    ausgabe = []
    log = Protokoll(tmp_path / "logs" / "x.log", ausgabe.append)
    log("Thema 1 gebaut")
    assert ausgabe == ["Thema 1 gebaut"]
    assert (tmp_path / "logs" / "x.log").read_text(encoding="utf-8").strip().endswith(" Thema 1 gebaut")
