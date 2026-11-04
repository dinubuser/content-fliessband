"""Posttage und Postzeit sind einstellbar (FLIESSBAND_POSTTAGE, FLIESSBAND_POSTZEIT). Standard: Di Mi Do Sa 19:00."""
import pytest

from lib import kalender
from lib.kalender import KalenderFehler, termine


def _tage(t):
    return [(x["nr"], x["format"], x["termin"][:10]) for x in t]


def test_standard_ohne_einstellung_bleibt_gleich(monkeypatch):
    monkeypatch.delenv("FLIESSBAND_POSTTAGE", raising=False)
    monkeypatch.delenv("FLIESSBAND_POSTZEIT", raising=False)
    assert _tage(termine("2026-KW46")) == [(1, "reel", "2026-11-10"), (2, "karussell", "2026-11-11"),
                                          (3, "reel", "2026-11-12"), (4, "karussell", "2026-11-14")]
    assert kalender.postzeit_text() == "19:00"


def test_eigene_postzeit(monkeypatch):
    monkeypatch.setenv("FLIESSBAND_POSTZEIT", "18:30")
    assert all(x["termin"].endswith("T18:30") for x in termine("2026-KW46"))
    assert all(x["termin"].endswith("T18:30") for x in termine("2026-KW46", plaetze=6))
    assert kalender.postzeit_text() == "18:30"


@pytest.mark.parametrize("zeit", ["25:00", "19", "abends", "19:60", "7:5x"])
def test_ungueltige_postzeit(monkeypatch, zeit):
    monkeypatch.setenv("FLIESSBAND_POSTZEIT", zeit)
    with pytest.raises(KalenderFehler, match="FLIESSBAND_POSTZEIT"):
        termine("2026-KW46")


def test_eigene_posttage_vierer_plan(monkeypatch):
    monkeypatch.setenv("FLIESSBAND_POSTTAGE", "1,3,5,7")   # Mo Mi Fr So
    t = termine("2026-KW46")
    assert _tage(t) == [(1, "reel", "2026-11-09"), (2, "karussell", "2026-11-11"),
                        (3, "reel", "2026-11-13"), (4, "karussell", "2026-11-15")]
    # die Längen hängen an der Reihenfolge der Reels, nicht am Wochentag
    assert [x.get("laenge") for x in t] == [kalender.reel_laenge("2026-KW46", 1), None,
                                            kalender.reel_laenge("2026-KW46", 3), None]


def test_posttage_mit_leerzeichen(monkeypatch):
    monkeypatch.setenv("FLIESSBAND_POSTTAGE", " 2, 3 ,4, 6 ")
    assert _tage(termine("2026-KW46"))[0][2] == "2026-11-10"


@pytest.mark.parametrize("tage", ["2,3,4", "2,3,4,6,7", "2,2,3,4", "4,3,2,1", "0,2,3,4", "2,3,4,8", "a,b,c,d", "2;3;4;6"])
def test_ungueltige_posttage(monkeypatch, tage):
    monkeypatch.setenv("FLIESSBAND_POSTTAGE", tage)
    with pytest.raises(KalenderFehler, match="FLIESSBAND_POSTTAGE"):
        termine("2026-KW46")


def test_sechs_plaetze_mit_freien_montagen_und_freitagen(monkeypatch):
    monkeypatch.setenv("FLIESSBAND_POSTTAGE", "2,3,4,7")   # Di Mi Do So
    t = termine("2026-KW46", plaetze=6)
    assert _tage(t) == [(1, "karussell", "2026-11-09"), (2, "reel", "2026-11-10"), (3, "karussell", "2026-11-11"),
                        (4, "reel", "2026-11-12"), (5, "reel", "2026-11-13"), (6, "karussell", "2026-11-15")]
    assert [x.get("laenge") for x in t] == [None, "kurz", None, "mittel", "kurz", None]


@pytest.mark.parametrize("tage", ["1,2,3,4", "2,3,4,5"])
def test_sechs_plaetze_brauchen_freien_montag_und_freitag(monkeypatch, tage):
    monkeypatch.setenv("FLIESSBAND_POSTTAGE", tage)
    assert len(termine("2026-KW46")) == 4   # vier Plätze gehen
    with pytest.raises(KalenderFehler, match="Montag und Freitag"):
        termine("2026-KW46", plaetze=6)


def test_setze_plaetze_6_wird_bei_konflikt_nicht_gespeichert(monkeypatch, tmp_path):
    monkeypatch.setenv("FLIESSBAND_POSTTAGE", "1,3,4,6")
    with pytest.raises(KalenderFehler, match="Montag und Freitag"):
        kalender.setze_plaetze(tmp_path, 6)
    assert kalender.plaetze(tmp_path) == 4
    kalender.setze_plaetze(tmp_path, 4)   # vier gehen immer
