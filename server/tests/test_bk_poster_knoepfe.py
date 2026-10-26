from datetime import datetime

from hilfen_bk import knopf

from briefkasten import texte
from briefkasten.ablauf import ZONE
from briefkasten.instagram import InstagramFehler


def _um(uhr, tag, stunde, minute=0):
    uhr.zeit = datetime(2026, 10, tag, stunde, minute, tzinfo=ZONE)


def _vorwarnung(poster, uhr):
    _um(uhr, 27, 18, 0)
    poster.takt()


def _b(ablauf, frei, i=0):
    return ablauf.s.beitrag(frei[i]["id"])


def test_stopp_vor_dem_termin(poster, frei, ablauf, ig, tg, uhr):
    _vorwarnung(poster, uhr)
    ablauf.verarbeite(knopf(_b(ablauf, frei), "s", update_id=50))
    assert tg.antworten()[-1] == "⏸ Gestoppt"
    assert _b(ablauf, frei)["status"] == "offen"
    assert [e["art"] for e in ablauf.s.ereignisse(0, ["zurueckgenommen"])] == ["zurueckgenommen"]
    assert tg.bearbeitet()[-1]["text"] == "⏰ Um 19:00 geht «Thema 1» online.\n⏸ Gestoppt, geht nicht online."
    _um(uhr, 27, 19, 0)
    poster.takt()
    assert "bereite_vor" not in ig.methoden()


def test_stopp_nach_dem_posten(poster, frei, ablauf, tg, uhr):
    _vorwarnung(poster, uhr)
    _um(uhr, 27, 19, 0)
    poster.takt()
    ablauf.verarbeite(knopf(_b(ablauf, frei), "s", update_id=51))
    assert tg.antworten()[-1] == "Schon online"


def test_stopp_waehrend_wiederholungen(poster, frei, ablauf, ig, tg, uhr):
    _vorwarnung(poster, uhr)
    ig.fehler = [InstagramFehler("weg")]
    _um(uhr, 27, 19, 0)
    poster.takt()
    ablauf.verarbeite(knopf(_b(ablauf, frei), "s", update_id=52))
    assert _b(ablauf, frei)["status"] == "ausgelassen"
    assert ablauf.s.post(frei[0]["id"])["post_status"] == "ausgelassen"
    assert [e["art"] for e in ablauf.s.ereignisse(0, ["ausgelassen"])] == ["ausgelassen"]
    _um(uhr, 27, 19, 5)
    poster.takt()
    assert ig.methoden().count("bereite_vor") == 1


def test_stopp_ohne_freigabe_und_veraltet(poster, frei, ablauf, tg, uhr):
    _vorwarnung(poster, uhr)
    ablauf.verarbeite(knopf(_b(ablauf, frei), "z", update_id=53))
    ablauf.verarbeite(knopf(_b(ablauf, frei), "s", update_id=54))
    assert tg.antworten()[-1] == "Nichts zu stoppen"
    ablauf.verarbeite(knopf(_b(ablauf, frei), "s", update_id=55, version=9))
    assert tg.antworten()[-1] == "Veraltet, bitte die neue Nachricht nehmen"


def test_nochmals_versuchen(poster, frei, ablauf, ig, tg, uhr):
    ig.fehler = [InstagramFehler("weg") for _ in range(4)]
    for minute in (0, 2, 7, 17):
        _um(uhr, 27, 19, minute)
        poster.takt()
    _um(uhr, 27, 19, 20)
    ablauf.verarbeite(knopf(_b(ablauf, frei), "n", update_id=56))
    assert tg.antworten()[-1] == "🔁 Ich versuche es gleich nochmals"
    poster.takt()
    assert ablauf.s.post(frei[0]["id"])["post_status"] == "gepostet"
    ablauf.verarbeite(knopf(_b(ablauf, frei), "n", update_id=57))
    assert tg.antworten()[-1] == "Schon online"


def _verpasst(poster, uhr):
    poster.schalter(False)
    _um(uhr, 27, 22, 0)
    poster.takt()
    poster.schalter(True)


def test_jetzt_posten_nach_verpasst(poster, frei, ablauf, tg, uhr):
    _verpasst(poster, uhr)
    _um(uhr, 28, 8, 0)
    ablauf.verarbeite(knopf(_b(ablauf, frei), "j", update_id=58))
    assert tg.antworten()[-1] == "🔁 Wird jetzt gepostet"
    poster.takt()
    assert ablauf.s.post(frei[0]["id"])["post_status"] == "gepostet"


def test_jetzt_posten_scheitert_wieder_knoepfe(poster, frei, ablauf, ig, tg, uhr):
    _verpasst(poster, uhr)
    ig.fehler = [InstagramFehler("weg")]
    ablauf.verarbeite(knopf(_b(ablauf, frei), "j", update_id=59))
    poster.takt()
    p = ablauf.s.post(frei[0]["id"])
    assert (p["post_status"], p["manuell"]) == ("verpasst_post", False)
    letzte = [f for m, f in tg.aufrufe if m == "sendMessage"][-1]
    assert letzte["text"] == "⚠️ Nicht gepostet: «Thema 1», Grund: weg"
    assert [k["text"] for k in letzte["reply_markup"]["inline_keyboard"][0]] == ["🔁 Jetzt posten", "❌ Auslassen"]
    poster.takt()
    assert ig.methoden().count("bereite_vor") == 1


def test_jetzt_posten_bei_poster_aus(poster, frei, ablauf, tg, uhr):
    _verpasst(poster, uhr)
    poster.schalter(False)
    ablauf.verarbeite(knopf(_b(ablauf, frei), "j", update_id=60))
    assert tg.antworten()[-1] == "Poster ist aus, zuerst «fliessband poster ein»"


def test_auslassen(poster, frei, ablauf, tg, uhr):
    _verpasst(poster, uhr)
    ablauf.verarbeite(knopf(_b(ablauf, frei), "l", update_id=61))
    assert tg.antworten()[-1] == "⏭ Ausgelassen"
    assert _b(ablauf, frei)["status"] == "ausgelassen"
    assert [e["art"] for e in ablauf.s.ereignisse(0, ["ausgelassen"])] == ["ausgelassen"]
    ablauf.verarbeite(knopf(_b(ablauf, frei), "j", update_id=62))
    assert tg.antworten()[-1] == "Geht nicht mehr"


def test_zuruecknehmen_setzt_post_wie_stopp_zurueck(poster, frei, ablauf, ig, tg, uhr):
    _vorwarnung(poster, uhr)
    assert ablauf.s.post(frei[0]["id"])["vorwarnung_id"] is not None
    ablauf.verarbeite(knopf(_b(ablauf, frei), "z", update_id=55))
    assert tg.antworten()[-1] == "↩️ Zurückgenommen"
    p = ablauf.s.post(frei[0]["id"])
    assert (p["post_status"], p["vorwarnung_id"]) == ("geplant", None)
    assert tg.bearbeitet()[-1]["text"] == "⏰ Um 19:00 geht «Thema 1» online.\n⏸ Gestoppt, geht nicht online."
    assert tg.bearbeitet()[-1]["reply_markup"] == texte.LEER
    _um(uhr, 27, 17, 30)   # früh genug wieder freigegeben (Uhr nur für den Test zurück)
    ablauf.verarbeite(knopf(_b(ablauf, frei), "f", update_id=56))
    _um(uhr, 27, 18, 1)
    poster.takt()
    assert tg.gesendet().count("⏰ Um 19:00 geht «Thema 1» online.") == 2


def test_zuruecknehmen_ohne_poster_post(ablauf, frei, tg):
    ablauf.poster = None
    ablauf.verarbeite(knopf(ablauf.s.beitrag(frei[0]["id"]), "z", update_id=57))
    assert tg.antworten()[-1] == "↩️ Zurückgenommen"
