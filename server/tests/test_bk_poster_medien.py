from datetime import datetime

import pytest
from hilfen_bk import MEDIEN, knopf

from briefkasten.ablauf import ZONE
from briefkasten.poster import Poster


def test_medien_annehmen(poster, vier):
    p = poster.medien(vier[0]["id"], MEDIEN)
    assert (p["version"], p["medien"], p["cover"], p["caption"]) == (1, MEDIEN["medien"], MEDIEN["cover"], "Caption 1")


@pytest.mark.parametrize("falsch", [
    {"version": 2}, {"medien": []}, {"medien": ["http://unsicher.ch/a.jpg"]}, {"medien": ["https://example.com/a"] * 11},
    {"caption": "x" * 2201}, {"cover": 5}])
def test_medien_ungueltig(poster, vier, falsch):
    with pytest.raises(ValueError):
        poster.medien(vier[0]["id"], dict(MEDIEN, **falsch))


def test_medien_unbekannter_beitrag(poster):
    with pytest.raises(ValueError):
        poster.medien("gibt-es-nicht", MEDIEN)


def test_medien_nach_dem_posten_unveraendert(poster, vier, ablauf):
    poster.medien(vier[0]["id"], MEDIEN)
    ablauf.s.setze_post(vier[0]["id"], post_status="gepostet")
    assert poster.medien(vier[0]["id"], dict(MEDIEN, caption="Neu"))["caption"] == "Caption 1"


def test_neue_version_ersetzt_post(poster, vier, ablauf):
    poster.medien(vier[0]["id"], MEDIEN)
    ablauf.s.setze_post(vier[0]["id"], vorwarnung_id=77)
    ablauf.s.setze(vier[0]["id"], version=2)
    p = poster.medien(vier[0]["id"], dict(MEDIEN, version=2))
    assert (p["version"], p["vorwarnung_id"]) == (2, None)


def test_schalter_und_stand(poster, frei):
    assert poster.schalter(False)["an"] is False
    stand = poster.schalter(True)
    assert stand["an"] is True and stand["schluessel_tage"] is None
    assert [(n["titel"], n["post_status"], n["dateien"]) for n in stand["naechste"]] == \
        [("Thema 1", "geplant", True), ("Thema 2", "geplant", True)]


def test_poster_startet_aus(ablauf, ig):
    assert Poster(ablauf, ig).stand()["an"] is False


def test_vorwarnung_60_minuten_vorher_einmal(poster, frei, tg, uhr):
    uhr.zeit = datetime(2026, 10, 27, 17, 59, tzinfo=ZONE)
    poster.takt()
    assert tg.gesendet() == []
    uhr.zeit = datetime(2026, 10, 27, 18, 0, tzinfo=ZONE)
    poster.takt()
    poster.takt()
    sendungen = [f for m, f in tg.aufrufe if m == "sendMessage"]
    assert [s["text"] for s in sendungen] == ["⏰ Um 19:00 geht «Thema 1» online."]
    assert sendungen[0]["disable_notification"] is False
    assert sendungen[0]["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == f"s:{frei[0]['nr']}:1"
    assert poster.s.post(frei[0]["id"])["post_status"] == "vorgewarnt"


def test_keine_vorwarnung_bei_spaeter_freigabe(ablauf, poster, vier, tg, uhr):
    uhr.zeit = datetime(2026, 10, 27, 18, 30, tzinfo=ZONE)
    ablauf.verarbeite(knopf(vier[0], "f", update_id=30))
    poster.medien(vier[0]["id"], MEDIEN)
    tg.aufrufe.clear()
    poster.takt()
    assert tg.gesendet() == []


def test_keine_vorwarnung_wenn_poster_aus(poster, frei, tg, uhr):
    poster.schalter(False)
    uhr.zeit = datetime(2026, 10, 27, 18, 0, tzinfo=ZONE)
    poster.takt()
    assert tg.gesendet() == []


def test_vorwarnung_scheitert_kommt_spaeter(poster, frei, tg, uhr):
    uhr.zeit = datetime(2026, 10, 27, 18, 0, tzinfo=ZONE)
    tg.scheitern_bei = "sendMessage"
    poster.takt()
    tg.scheitern_bei = None
    uhr.zeit = datetime(2026, 10, 27, 18, 1, tzinfo=ZONE)
    poster.takt()
    assert tg.gesendet() == ["⏰ Um 19:00 geht «Thema 1» online."]
