from datetime import datetime, timedelta

import pytest
from hilfen_bk import FalschesInstagram, knopf

from briefkasten.ablauf import ZONE
from briefkasten.facebook import FacebookFehler
from briefkasten.poster import Poster

VIDEO = "https://example.com/wp-content/uploads/2026/10/v.mp4"


def _um(uhr, tag, stunde, minute=0):
    uhr.zeit = datetime(2026, 10, tag, stunde, minute, tzinfo=ZONE)


def test_schalter_und_stand(poster, ablauf, fb, uhr):
    assert poster.fb_stand() == {"an": False, "schluessel": True, "posts": []}
    assert poster.fb_schalter(True)["an"] is True
    assert ablauf.s.lies("facebook_seit") == "2026-10-24T22:30:00+02:00"
    _um(uhr, 25, 9)
    poster.fb_schalter(False)
    poster.fb_schalter(True)
    assert ablauf.s.lies("facebook_seit") == "2026-10-24T22:30:00+02:00"   # bleibt beim ersten Ein
    with pytest.raises(ValueError):
        poster.fb_schalter("ja")
    fb.schluessel.vorhanden = False
    assert poster.fb_stand()["schluessel"] is False


def test_ohne_facebook_nicht_einschaltbar(ablauf):
    p = Poster(ablauf, FalschesInstagram())
    assert p.fb_stand() == {"an": False, "schluessel": False, "posts": []}
    with pytest.raises(ValueError, match="nicht eingerichtet"):
        p.fb_schalter(True)


def test_aus_kein_facebook(poster, frei, fb, uhr, ablauf):
    _um(uhr, 27, 19, 0)
    poster.takt()
    p = ablauf.s.post(frei[0]["id"])
    assert p["post_status"] == "gepostet" and p["fb_status"] is None and fb.aufrufe == []
    assert p["gepostet_id"] is not None


def test_erst_nach_instagram_eingeschaltet_kein_facebook(poster, frei, fb, uhr, ablauf):
    _um(uhr, 27, 19, 0)
    poster.takt()
    poster.fb_schalter(True)
    _um(uhr, 27, 19, 1)
    poster.takt()
    assert fb.aufrufe == [] and ablauf.s.post(frei[0]["id"])["fb_status"] is None


def test_reel_auf_facebook(poster, frei, fb, tg, uhr, ablauf):
    poster.fb_schalter(True)
    _um(uhr, 27, 19, 0)
    poster.takt()
    assert fb.methoden() == ["starte_reel", "lade_reel", "beende_reel", "warte_reel"]
    assert ("lade_reel", ("v1", VIDEO)) in fb.aufrufe and ("beende_reel", ("v1", "Caption 1")) in fb.aufrufe
    p = ablauf.s.post(frei[0]["id"])
    assert (p["fb_status"], p["fb_id"], p["fb_link"], p["fb_beendet"]) == (
        "gepostet", "v1", "https://www.facebook.com/reel/v1", True)
    neu = [f for f in tg.bearbeitet() if f["message_id"] == p["gepostet_id"]]
    assert neu[-1]["text"] == ("✅ Gepostet: «Thema 1»\nhttps://www.instagram.com/p/c1/\n"
                               "Facebook: https://www.facebook.com/reel/v1")
    poster.takt()
    assert fb.methoden().count("starte_reel") == 1
    assert poster.fb_stand()["posts"] == [{"id": frei[0]["id"], "titel": "Thema 1", "termin": "2026-10-27T19:00",
                                           "fb_status": "gepostet", "fb_link": "https://www.facebook.com/reel/v1",
                                           "fb_grund": None}]


def test_karussell_auf_facebook(poster, frei, fb, uhr, ablauf):
    poster.fb_schalter(True)
    ablauf.s.setze(frei[0]["id"], status="ausgelassen")   # Thema 1 aus dem Weg
    _um(uhr, 28, 19, 0)
    poster.takt()
    assert fb.methoden() == ["schon_gepostet", "poste_karussell"]
    assert ("poste_karussell", (("https://example.com/1.jpg", "https://example.com/2.jpg"), "Caption 2")) in fb.aufrufe
    p = ablauf.s.post(frei[1]["id"])
    assert (p["fb_status"], p["fb_link"]) == ("gepostet", "https://www.facebook.com/fb1")


def test_karussell_schon_auf_der_seite(poster, frei, fb, uhr, ablauf):
    poster.fb_schalter(True)
    ablauf.s.setze(frei[0]["id"], status="ausgelassen")
    fb.treffer = {"id": "alt", "link": "https://www.facebook.com/alt"}
    _um(uhr, 28, 19, 0)
    poster.takt()
    assert "poste_karussell" not in fb.methoden()
    assert ablauf.s.post(frei[1]["id"])["fb_link"] == "https://www.facebook.com/alt"


def _karussell_bereit(poster, frei, ablauf):
    poster.fb_schalter(True)
    ablauf.s.setze(frei[0]["id"], status="ausgelassen")
    return ablauf.s.beitrag(frei[1]["id"])


def _vier_fehlversuche(poster, fb, uhr):
    fb.fehler = [FacebookFehler("weg") for _ in range(4)]
    for minute in (0, 2, 12, 42):
        _um(uhr, 28, 19, minute)
        poster.takt()


def _fb_meldungen(tg):
    return [f for m, f in tg.aufrufe if m == "sendMessage" and f["text"].startswith("⚠️ Facebook nicht")]


def test_fehler_pausen_dann_meldung(poster, frei, fb, tg, uhr, ablauf):
    b = _karussell_bereit(poster, frei, ablauf)
    fb.fehler = [FacebookFehler("weg") for _ in range(4)]
    for minute in (0, 2, 12, 42):
        _um(uhr, 28, 19, minute)
        poster.takt()
        _um(uhr, 28, 19, minute + 1)
        poster.takt()   # zu früh für den nächsten Versuch
    assert fb.methoden().count("poste_karussell") == 4
    p = ablauf.s.post(b["id"])
    assert (p["fb_status"], p["fb_versuche"], p["fb_grund"], p["fb_naechster"]) == ("fehler", 4, "weg", None)
    meldung = _fb_meldungen(tg)
    assert [f["text"] for f in meldung] == [
        "⚠️ Facebook nicht gepostet: «Thema 2», Grund: weg\nAuf Instagram ist der Beitrag online."]
    assert [k["callback_data"] for k in meldung[0]["reply_markup"]["inline_keyboard"][0]] == [
        f"fn:{b['nr']}:1", f"fl:{b['nr']}:1"]
    _um(uhr, 28, 21, 0)
    poster.takt()
    assert fb.methoden().count("poste_karussell") == 4   # kein automatischer Versuch mehr


def test_nochmals_knopf(poster, frei, fb, tg, uhr, ablauf):
    b = _karussell_bereit(poster, frei, ablauf)
    _vier_fehlversuche(poster, fb, uhr)
    meldung_id = ablauf.s.post(b["id"])["fb_meldung_id"]
    ablauf.verarbeite(knopf(b, "fn", update_id=60))
    assert "🔁 Ich versuche es gleich nochmals" in tg.antworten()
    assert ablauf.s.post(b["id"])["fb_status"] == "offen"
    poster.takt()
    assert ablauf.s.post(b["id"])["fb_status"] == "gepostet"
    assert any(f["message_id"] == meldung_id and f["text"] == "✅ Facebook nachgeholt: «Thema 2»"
               for f in tg.bearbeitet())
    ablauf.verarbeite(knopf(b, "fn", update_id=61))
    assert tg.antworten()[-1] == "Schon auf Facebook"


def test_auslassen_knopf(poster, frei, fb, tg, uhr, ablauf):
    b = _karussell_bereit(poster, frei, ablauf)
    _vier_fehlversuche(poster, fb, uhr)
    ablauf.verarbeite(knopf(b, "fl", update_id=60))
    assert tg.antworten()[-1] == "⏭ Facebook ausgelassen"
    assert ablauf.s.post(b["id"])["fb_status"] == "ausgelassen"
    assert tg.bearbeitet()[-1]["text"].endswith("⏭ Facebook ausgelassen")
    poster.takt()
    assert fb.methoden().count("poste_karussell") == 4


def test_nochmals_bei_ausgeschaltetem_facebook(poster, frei, fb, tg, uhr, ablauf):
    b = _karussell_bereit(poster, frei, ablauf)
    _vier_fehlversuche(poster, fb, uhr)
    poster.fb_schalter(False)
    ablauf.verarbeite(knopf(b, "fn", update_id=60))
    assert tg.antworten()[-1] == "Facebook ist aus, zuerst «fliessband facebook ein»"
    assert ablauf.s.post(b["id"])["fb_status"] == "fehler"


def test_ungueltiger_schluessel(poster, frei, fb, tg, uhr, ablauf):
    b = _karussell_bereit(poster, frei, ablauf)
    fb.fehler = [FacebookFehler("Facebook-Schlüssel fehlt", ungueltig=True) for _ in range(3)]
    _um(uhr, 28, 19, 0)
    poster.takt()
    p = ablauf.s.post(b["id"])
    assert (p["fb_status"], p["fb_versuche"], p["fb_naechster"]) == ("offen", 0, "2026-10-28T20:00:00+01:00")
    _um(uhr, 28, 20, 0)
    poster.takt()
    assert len([t for t in tg.gesendet() if t.startswith("⚠️ Facebook-Schlüssel")]) == 1
    assert _fb_meldungen(tg) == []
    _um(uhr, 29, 9, 0)
    poster.takt()
    assert len([t for t in tg.gesendet() if t.startswith("⚠️ Facebook-Schlüssel")]) == 2   # neuer Tag


def test_neustart_reel_fertig_kein_zweiter_upload(poster, frei, fb, uhr, ablauf):
    poster.fb_schalter(True)
    fb.fehler = [FacebookFehler("weg")]
    _um(uhr, 27, 19, 0)
    poster.takt()   # Instagram online, Facebook 1. Fehlversuch
    ablauf.s.setze_post(frei[0]["id"], fb_status="laeuft", fb_id="v9", fb_beendet=True)
    fb.stand["v9"] = "fertig"
    poster.beim_start()
    assert ablauf.s.post(frei[0]["id"])["fb_status"] == "offen"
    _um(uhr, 27, 19, 5)
    poster.takt()
    assert fb.methoden().count("starte_reel") == 1   # nur der gescheiterte erste Versuch
    assert ablauf.s.post(frei[0]["id"])["fb_link"] == "https://www.facebook.com/reel/v9"


def test_neustart_reel_nicht_beendet_faengt_neu_an(poster, frei, fb, uhr, ablauf):
    poster.fb_schalter(True)
    fb.fehler = [FacebookFehler("weg")]
    _um(uhr, 27, 19, 0)
    poster.takt()
    ablauf.s.setze_post(frei[0]["id"], fb_status="offen", fb_id="v8", fb_beendet=False, fb_naechster=None)
    fb.stand["v8"] = "offen"
    poster.takt()
    assert fb.methoden().count("starte_reel") == 2
    p = ablauf.s.post(frei[0]["id"])
    assert (p["fb_status"], p["fb_id"]) == ("gepostet", "v1")


def test_beende_reel_scheitert_nie_zweites_reel(poster, frei, fb, tg, uhr, ablauf):
    poster.fb_schalter(True)
    fb.beende_fehler = [FacebookFehler("Zeitlimit")]
    for minute in (0, 2, 12, 42):
        _um(uhr, 27, 19, minute)
        poster.takt()
    assert fb.methoden().count("starte_reel") == 1
    p = ablauf.s.post(frei[0]["id"])
    assert (p["fb_status"], p["fb_id"], p["fb_beendet"]) == ("fehler", "v1", True)
    # Nochmals behält die alte fb_id; Stand «offen» heisst: neues Reel
    ablauf.verarbeite(knopf(frei[0], "fn", update_id=70))
    p = ablauf.s.post(frei[0]["id"])
    assert (p["fb_status"], p["fb_id"], p["fb_beendet"]) == ("offen", "v1", False)
    poster.takt()
    assert fb.methoden().count("starte_reel") == 2
    assert ablauf.s.post(frei[0]["id"])["fb_status"] == "gepostet"


def test_nochmals_altes_reel_inzwischen_fertig_kein_zweites(poster, frei, fb, tg, uhr, ablauf):
    poster.fb_schalter(True)
    fb.beende_fehler = [FacebookFehler("Zeitlimit")]
    for minute in (0, 2, 12, 42):
        _um(uhr, 27, 19, minute)
        poster.takt()
    assert ablauf.s.post(frei[0]["id"])["fb_status"] == "fehler"
    fb.stand["v1"] = "fertig"   # Facebook hat das alte Video doch noch veröffentlicht
    ablauf.verarbeite(knopf(frei[0], "fn", update_id=70))
    poster.takt()
    assert fb.methoden().count("starte_reel") == 1
    p = ablauf.s.post(frei[0]["id"])
    assert (p["fb_status"], p["fb_id"], p["fb_link"]) == ("gepostet", "v1", "https://www.facebook.com/reel/v1")


def test_beende_reel_http_fehler_startet_neu(poster, frei, fb, uhr, ablauf):
    poster.fb_schalter(True)
    fb.beende_fehler = [FacebookFehler("Facebook HTTP 400: abgelehnt")]
    _um(uhr, 27, 19, 0)
    poster.takt()
    p = ablauf.s.post(frei[0]["id"])
    assert (p["fb_status"], p["fb_versuche"], p["fb_beendet"]) == ("offen", 1, False)
    _um(uhr, 27, 19, 2)
    poster.takt()
    assert fb.methoden().count("starte_reel") == 2   # sofort neu, nicht 10 Minuten warten
    assert ablauf.s.post(frei[0]["id"])["fb_status"] == "gepostet"


def test_fehler_bei_einem_beitrag_haelt_nichts_auf(poster, frei, fb, uhr, ablauf, monkeypatch):
    poster.fb_schalter(True)
    gepflegt = []
    monkeypatch.setattr(poster, "_schluessel_pflegen", lambda: gepflegt.append(1))

    def kaputt(b, ergebnis):
        raise RuntimeError("x")
    monkeypatch.setattr(poster, "_fb_erfolg", kaputt)
    _um(uhr, 27, 19, 0)
    poster.takt()
    assert gepflegt == [1]
    assert ablauf.s.post(frei[0]["id"])["post_status"] == "gepostet"


def test_ungueltiger_schluessel_ueber_24_stunden(poster, frei, fb, tg, uhr, ablauf):
    b = _karussell_bereit(poster, frei, ablauf)
    fb.fehler = [FacebookFehler("Facebook-Schlüssel fehlt", ungueltig=True) for _ in range(40)]
    start = datetime(2026, 10, 28, 19, 0, tzinfo=ZONE)
    vorher = 0
    for stunden in range(0, 26):
        uhr.zeit = start + timedelta(hours=stunden)
        if stunden == 24:
            vorher = fb.methoden().count("poste_karussell")
        poster.takt()
    assert fb.methoden().count("poste_karussell") == vorher
    p = ablauf.s.post(b["id"])
    assert (p["fb_status"], p["fb_grund"]) == (
        "fehler", "Facebook-Post nicht innert 24 Stunden möglich (Facebook-Schlüssel fehlt)")
    assert [f["text"] for f in _fb_meldungen(tg)] == [
        "⚠️ Facebook nicht gepostet: «Thema 2», Grund: Facebook-Post nicht innert 24 Stunden möglich (Facebook-Schlüssel fehlt)\n"
        "Auf Instagram ist der Beitrag online."]
    fb.fehler = []
    ablauf.verarbeite(knopf(b, "fn", update_id=80))
    poster.takt()   # Nochmals ist bewusste Wahl des Betreibers: die 24-h-Frist schlägt nicht sofort wieder zu
    assert ablauf.s.post(b["id"])["fb_status"] == "gepostet"


def test_frist_bei_ausgeschaltetem_facebook_still(poster, frei, fb, tg, uhr, ablauf):
    b = _karussell_bereit(poster, frei, ablauf)
    fb.fehler = [FacebookFehler("weg")]
    _um(uhr, 28, 19, 0)
    poster.takt()
    poster.fb_schalter(False)
    _um(uhr, 30, 19, 0)
    poster.takt()
    assert ablauf.s.post(b["id"])["fb_status"] == "offen" and _fb_meldungen(tg) == []


def test_unerwarteter_fehler_instagram_bleibt(poster, frei, fb, uhr, ablauf):
    poster.fb_schalter(True)
    fb.fehler = [RuntimeError("geheim")]
    _um(uhr, 27, 19, 0)
    poster.takt()
    p = ablauf.s.post(frei[0]["id"])
    assert p["post_status"] == "gepostet"
    assert (p["fb_status"], p["fb_grund"]) == ("offen", "interner Fehler (RuntimeError)")


def test_telegram_scheitert_bei_erfolg(poster, frei, fb, tg, uhr, ablauf):
    poster.fb_schalter(True)
    tg.scheitern_bei = "sendMessage"
    _um(uhr, 27, 19, 0)
    poster.takt()
    p = ablauf.s.post(frei[0]["id"])
    assert p["post_status"] == "gepostet" and p["gepostet_id"] is None
    assert p["fb_status"] == "gepostet"
    assert [f for f in tg.bearbeitet() if "Facebook:" in f["text"]] == []
