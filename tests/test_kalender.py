from datetime import date, datetime

import pytest

from lib.kalender import (KalenderFehler, fenster, freitag, kurz, laengen_hinweis, pruefe_woche, reel_laenge,
                          termine, zielwoche)


@pytest.mark.parametrize("tag, woche", [
    (date(2026, 10, 23), "2026-KW44"),   # Freitag
    (date(2026, 10, 24), "2026-KW44"),   # Samstag
    (date(2026, 10, 25), "2026-KW44"),   # Sonntag
    (date(2026, 10, 20), "2026-KW44"),   # Dienstag: Woche nach dem kommenden Wochenende
    (date(2026, 12, 25), "2026-KW53"),   # Freitag vor der KW53
    (date(2027, 1, 1), "2027-KW01"),     # Freitag in der KW53 → KW1
    (date(2027, 12, 31), "2028-KW01"),   # Freitag in der KW52 → KW1
])
def test_zielwoche(tag, woche):
    assert zielwoche(tag) == woche


def test_termine_kw44():
    assert termine("2026-KW44") == [
        {"nr": 1, "format": "reel", "termin": "2026-10-27T19:00", "laenge": "kurz"},
        {"nr": 2, "format": "karussell", "termin": "2026-10-28T19:00"},
        {"nr": 3, "format": "reel", "termin": "2026-10-29T19:00", "laenge": "mittel"},
        {"nr": 4, "format": "karussell", "termin": "2026-10-31T19:00"},
    ]


def test_laenge_wechselt_nach_kalenderwoche():
    assert [t.get("laenge") for t in termine("2026-KW45")] == ["mittel", None, "kurz", None]
    assert [t.get("laenge") for t in termine("2026-KW46")] == ["kurz", None, "mittel", None]
    assert reel_laenge("2026-KW45", 1) == "mittel"
    assert reel_laenge("2026-KW45", 3) == "kurz"


def test_laengen_hinweis():
    assert laengen_hinweis("kurz", 35.0) is None
    assert laengen_hinweis("kurz", 41.2) == "⚠️ Reel ist 41 s lang (Ziel kurz: 20 bis 30 s)."
    assert laengen_hinweis("mittel", 50.0) is None
    assert laengen_hinweis("mittel", 51) == "⚠️ Reel ist 51 s lang (Ziel mittel: 30 bis 45 s)."
    assert laengen_hinweis(None, 80.0) is None
    assert laengen_hinweis("kurz", None) is None
    assert laengen_hinweis("unbekannt", 80.0) is None


def test_termine_ueber_den_jahreswechsel():
    assert [t["termin"][:10] for t in termine("2026-KW53")] == ["2026-12-29", "2026-12-30", "2026-12-31", "2027-01-02"]


def test_kurz():
    assert kurz("2026-10-27T19:00") == "Di 27.10."
    assert kurz("2026-10-31T19:00") == "Sa 31.10."


def test_pruefe_woche_gueltig():
    assert pruefe_woche("2026-KW53") == "2026-KW53"


@pytest.mark.parametrize("text", ["2026-44", "2026-KW4", "2026-KW54", "2025-KW53", "KW44"])
def test_pruefe_woche_ungueltig(text):
    with pytest.raises(KalenderFehler):
        pruefe_woche(text)


def test_freitag_des_wochenendes():
    assert freitag(date(2026, 10, 25)) == date(2026, 10, 23)
    assert freitag(date(2026, 11, 7)) == date(2026, 11, 6)


@pytest.mark.parametrize("schritt, jetzt, lage", [
    ("vorbereiten", datetime(2026, 10, 23, 21, 59), "ruhe"),
    ("vorbereiten", datetime(2026, 10, 23, 22, 0), "laufen"),
    ("vorbereiten", datetime(2026, 10, 25, 11, 59), "laufen"),
    ("bauen", datetime(2026, 10, 23, 23, 0), "ruhe"),
    ("bauen", datetime(2026, 10, 24, 22, 0), "laufen"),
    ("bauen", datetime(2026, 10, 25, 12, 0), "ausgefallen"),
    ("vorbereiten", datetime(2026, 10, 25, 23, 59), "ausgefallen"),
    ("bauen", datetime(2026, 10, 26, 0, 1), "ruhe"),
    ("bauen", datetime(2026, 10, 21, 22, 0), "ruhe"),
])
def test_fenster(schritt, jetzt, lage):
    assert fenster(schritt, jetzt) == lage


def test_fenster_lernen():
    assert fenster("lernen", datetime(2026, 10, 30, 19, 59)) == "ruhe"
    assert fenster("lernen", datetime(2026, 10, 30, 20, 0)) == "laufen"
    assert fenster("lernen", datetime(2026, 10, 30, 21, 29)) == "laufen"
    # ab 21:30 ruhe (nie «ausgefallen»): danach holt vorbereiten unter derselben Sperre nach
    for spaet in (datetime(2026, 10, 30, 21, 30), datetime(2026, 10, 30, 21, 56), datetime(2026, 10, 31, 9, 0),
                  datetime(2026, 11, 1, 13, 0)):
        assert fenster("lernen", spaet) == "ruhe"
    assert fenster("vorbereiten", datetime(2026, 10, 30, 22, 0)) == "laufen"
    assert fenster("bauen", datetime(2026, 11, 1, 13, 0)) == "ausgefallen"
