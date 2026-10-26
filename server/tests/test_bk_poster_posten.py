from datetime import datetime

from hilfen_bk import knopf

from briefkasten.ablauf import ZONE
from briefkasten.instagram import InstagramFehler

VIDEO = "https://example.com/wp-content/uploads/2026/10/v.mp4"
COVER = "https://example.com/wp-content/uploads/2026/10/c.jpg"


def _um(uhr, tag, stunde, minute=0):
    uhr.zeit = datetime(2026, 10, tag, stunde, minute, tzinfo=ZONE)


def test_posten_zum_termin(poster, frei, ig, tg, uhr, ablauf):
    _um(uhr, 27, 18, 59)
    poster.takt()
    assert "bereite_vor" not in ig.methoden()
    _um(uhr, 27, 19, 0)
    poster.takt()
    assert ("bereite_vor", ("reel", (VIDEO,), COVER, "Caption 1")) in ig.aufrufe
    p = ablauf.s.post(frei[0]["id"])
    assert (p["post_status"], p["instagram_id"], p["permalink"]) == ("gepostet", "m-c1", "https://www.instagram.com/p/c1/")
    assert ablauf.s.beitrag(frei[0]["id"])["status"] == "gepostet"
    e = ablauf.s.ereignisse(0, ["gepostet"])
    assert len(e) == 1 and e[0]["nachricht"] == {"instagram_id": "m-c1", "permalink": "https://www.instagram.com/p/c1/"}
    assert "✅ Gepostet: «Thema 1»\nhttps://www.instagram.com/p/c1/" in tg.gesendet()
    assert any(f["text"].endswith("📲 gepostet") for f in tg.bearbeitet())
    poster.takt()
    assert ig.methoden().count("veroeffentliche") == 1


def test_poster_aus_postet_nicht(poster, frei, ig, uhr):
    poster.schalter(False)
    _um(uhr, 27, 19, 0)
    poster.takt()
    assert ig.aufrufe == []


def test_nicht_freigegeben_postet_nicht(poster, vier, ig, uhr):
    poster.medien(vier[0]["id"], {"version": 1, "medien": ["https://example.com/v.mp4"], "cover": None, "caption": "C"})
    _um(uhr, 27, 19, 0)
    poster.takt()
    assert ig.aufrufe == []


def test_fehler_still_wiederholen_dann_meldung(poster, frei, ig, tg, uhr, ablauf):
    ig.fehler = [InstagramFehler("Instagram nicht erreichbar (URLError)") for _ in range(5)]
    for minute in (0, 2, 7, 17):
        _um(uhr, 27, 19, minute)
        poster.takt()
        _um(uhr, 27, 19, minute + 1)
        poster.takt()   # zu früh für den nächsten Versuch
    assert ig.methoden().count("bereite_vor") == 4
    p = ablauf.s.post(frei[0]["id"])
    assert (p["post_status"], p["versuche"], p["naechster_versuch"]) == ("fehler", 4, "2026-10-27T19:32:00+01:00")
    meldungen = [f for m, f in tg.aufrufe if m == "sendMessage"]
    assert [f["text"] for f in meldungen] == ["⚠️ Nicht gepostet: «Thema 1», Grund: Instagram nicht erreichbar (URLError)"]
    assert meldungen[0]["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == f"n:{frei[0]['nr']}:1"
    _um(uhr, 27, 19, 32)
    poster.takt()
    assert ablauf.s.post(frei[0]["id"])["post_status"] == "fehler"
    assert len([1 for m, _ in tg.aufrufe if m == "sendMessage"]) == 1   # keine zweite Meldung
    _um(uhr, 27, 19, 47)
    poster.takt()
    assert ablauf.s.post(frei[0]["id"])["post_status"] == "gepostet"


def test_dateien_fehlen_zaehlt_als_fehler(poster, vier, ablauf, ig, uhr):
    ablauf.verarbeite(knopf(vier[2], "f", update_id=40))
    _um(uhr, 29, 19, 0)
    poster.takt()
    p = ablauf.s.post(vier[2]["id"])
    assert p["post_status"] == "fehler" and p["grund"].startswith("Dateien fehlen")
    assert "bereite_vor" not in ig.methoden()


def test_tagesgrenze(poster, frei, ig, uhr, ablauf):
    ig.grenze = True
    _um(uhr, 27, 19, 0)
    poster.takt()
    assert ablauf.s.post(frei[0]["id"])["grund"] == "Tagesgrenze Instagram erreicht"


def test_nach_drei_stunden_verpasst(poster, frei, ig, tg, uhr, ablauf):
    ig.fehler = [InstagramFehler("weg") for _ in range(30)]
    for minute in range(180):
        _um(uhr, 27, 19 + minute // 60, minute % 60)
        poster.takt()
    tg.aufrufe.clear()
    _um(uhr, 27, 22, 0)
    poster.takt()
    assert ablauf.s.post(frei[0]["id"])["post_status"] == "verpasst_post"
    gesendet = [f for m, f in tg.aufrufe if m == "sendMessage"]
    assert [f["text"] for f in gesendet] == ["⚠️ Verpasst: «Thema 1» (geplant Di 27.10., 19:00). Grund: weg"]
    assert [k["text"] for k in gesendet[0]["reply_markup"]["inline_keyboard"][0]] == ["🔁 Jetzt posten", "❌ Auslassen"]
    assert any(f["reply_markup"] == {"inline_keyboard": []} for f in tg.bearbeitet())   # alte Meldung ohne Knopf
    anzahl = ig.methoden().count("bereite_vor")
    _um(uhr, 27, 23, 0)
    poster.takt()
    assert ig.methoden().count("bereite_vor") == anzahl


def test_poster_aus_ueber_termin_dann_verpasst(poster, frei, ig, tg, uhr, ablauf):
    poster.schalter(False)
    _um(uhr, 27, 22, 0)
    poster.takt()
    assert ablauf.s.post(frei[0]["id"])["post_status"] == "verpasst_post"
    assert tg.gesendet()[-1].endswith("Grund: Poster war ausgeschaltet")
    poster.schalter(True)
    poster.takt()
    assert ig.aufrufe == []


def test_unerwarteter_fehler_haelt_takt_nicht_auf(poster, frei, ig, uhr, ablauf):
    ig.fehler = [RuntimeError("kaputt")]
    _um(uhr, 28, 19, 0)   # Thema 1 ist über 3 h vorbei (Verpasst), Thema 2 ist fällig
    poster.takt()
    assert ablauf.s.post(frei[1]["id"])["grund"] == "interner Fehler (RuntimeError)"
    assert ablauf.s.post(frei[0]["id"])["post_status"] == "verpasst_post"
