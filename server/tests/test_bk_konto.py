from datetime import date

import pytest

from briefkasten.konto import sammle, summe, tage_aus


class Gut:
    def konto(self, tage, heute):
        return {"follower": 1, "tage": tage, "heute": heute.isoformat()}


class Kaputt:
    def konto(self, tage, heute):
        raise RuntimeError("weg")


def test_sammle_ein_fehler_stoppt_die_anderen_nicht():
    d = sammle({"a": Kaputt(), "b": Gut()}, 3, date(2026, 10, 28))
    assert d["konten"]["a"] == {"fehler": "weg"}
    assert d["konten"]["b"] == {"follower": 1, "tage": 3, "heute": "2026-10-28"}
    assert d["stand"].startswith("20")


def test_summe_total_value_und_tageswerte():
    assert summe({"data": [{"name": "views", "total_value": {"value": 7}}]}, "views") == 7
    assert summe({"data": [{"name": "x", "values": [{"value": 2}, {"value": 3}]}]}, "x") == 5
    assert summe({"data": []}, "views") is None


def test_tage_aus():
    assert tage_aus("") == 3 and tage_aus("tage=30") == 30
    for falsch in ("tage=0", "tage=31", "tage=x"):
        with pytest.raises(ValueError):
            tage_aus(falsch)
