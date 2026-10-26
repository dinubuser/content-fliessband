from datetime import datetime

import pytest
from hilfen_bk import MEDIEN, FalschesFacebook, FalschesInstagram, FalschesTelegram, Uhr, daten, knopf

from briefkasten.ablauf import ZONE, Ablauf
from briefkasten.poster import Poster
from briefkasten.speicher import Speicher


@pytest.fixture
def tg():
    return FalschesTelegram()


@pytest.fixture
def uhr():
    """Samstag 24.10.2026 22:30 Ortszeit (Paket ist gerade gesendet)."""
    return Uhr(datetime(2026, 10, 24, 22, 30, tzinfo=ZONE))


@pytest.fixture
def ablauf(tg, uhr):
    return Ablauf(Speicher(":memory:"), tg, 42, jetzt=uhr)


@pytest.fixture
def vier(ablauf, tg):
    """4 angemeldete Beiträge (Nachrichten 501 bis 504) und die Übersicht (505). Telegram-Aufrufe geleert."""
    bs = [ablauf.melde_beitrag(daten(nr)) for nr in (1, 2, 3, 4)]
    ablauf.woche_fertig("2026-KW44")
    tg.aufrufe.clear()
    return bs


@pytest.fixture
def ig():
    return FalschesInstagram()


@pytest.fixture
def fb():
    return FalschesFacebook()


@pytest.fixture
def poster(ablauf, ig, fb):
    p = Poster(ablauf, ig, fb)
    p.schalter(True)
    return p


@pytest.fixture
def frei(ablauf, tg, vier, poster):
    """Beitrag 1 (Reel, Di 27.10. 19:00) und 2 (Karussell, Mi 28.10. 19:00) am Sa 24.10. 22:30 freigegeben,
    beide mit Medien. Telegram-Aufrufe geleert. Liefert alle 4 Beiträge frisch aus dem Speicher."""
    for i, b in enumerate(vier[:2]):
        ablauf.verarbeite(knopf(b, "f", update_id=10 + i))
    poster.medien(vier[0]["id"], MEDIEN)
    poster.medien(vier[1]["id"], {"version": 1, "medien": ["https://example.com/1.jpg", "https://example.com/2.jpg"],
                                  "cover": None, "caption": "Caption 2"})
    tg.aufrufe.clear()
    return [ablauf.s.beitrag(b["id"]) for b in vier]
