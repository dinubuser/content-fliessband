from pathlib import Path

import pytest

from lib.reel_modell import Aufnahme, Wort
from lib.zeitplan import NACHLAUF, PAUSE, LaengeFehler, gruppiere, laenge_status, plane


def test_plane_setzt_pausen_und_nachlauf():
    a = [Aufnahme(1, Path("a"), 2.0), Aufnahme(2, Path("b"), 3.0)]
    plan = plane(a)
    assert [(p.start, p.dauer) for p in plan.szenen] == [(0.0, 2.35), (2.35, 3.8)]
    assert plan.gesamt == pytest.approx(6.15)


def test_untertitel_gruppen_brechen_nach_satzende_und_anzahl():
    ws = [Wort("Keine", 0, .3), Wort("Zeit?", .3, .6), Wort("Ich", .7, .8), Wort("lerne", .8, 1.0),
          Wort("nun", 1.0, 1.3), Wort("jeden", 1.3, 1.5), Wort("Abend", 1.5, 1.7), Wort("weiter.", 1.7, 2.0)]
    g = gruppiere(ws, max_woerter=5, max_zeichen=28, brueche=".?!:;", versatz=10.0, ende=12.5)
    assert [[w.wort for w in x.woerter] for x in g] == [["Keine", "Zeit?"],
                                                         ["Ich", "lerne", "nun", "jeden", "Abend"],
                                                         ["weiter."]]
    assert g[0].start == 10.0 and g[0].ende == pytest.approx(10.7)
    assert g[1].woerter[0].start == pytest.approx(10.7)
    assert g[-1].ende == 12.5


def test_untertitel_gruppen_brechen_nach_zeichen():
    ws = [Wort(t, i, i + 1) for i, t in enumerate(["Donaudampfschiff", "fahrtsgesellschaft", "fährt"])]
    g = gruppiere(ws, max_woerter=5, max_zeichen=28, brueche=".", versatz=0.0, ende=4.0)
    assert [len(x.woerter) for x in g] == [1, 2]


def test_hook_gruppen_hoechstens_drei_woerter():
    ws = [Wort(t, i * .2, i * .2 + .2) for i, t in enumerate("Keine Zeit und kein Geld übrig?".split())]
    g = gruppiere(ws, max_woerter=3, max_zeichen=18, brueche=".?!:;,", versatz=0.0, ende=2.0)
    assert [len(x.woerter) for x in g] == [3, 3]


def test_laenge_status():
    assert laenge_status(59.9) == "ok"
    assert laenge_status(70.0) == "lang"
    with pytest.raises(LaengeFehler, match="95 s"):
        laenge_status(95.0)


@pytest.mark.parametrize("schluss", ["Zeit?»", 'Zeit?"', "Zeit?“", "Zeit?)"])
def test_gruppen_brechen_auch_vor_schliessenden_anfuehrungszeichen(schluss):
    ws = [Wort("«Keine", 0, .3), Wort(schluss, .3, .6), Wort("Ich", .7, .8), Wort("lerne.", .8, 1.0)]
    g = gruppiere(ws, max_woerter=3, max_zeichen=18, brueche=".?!:;,", versatz=0.0, ende=2.0)
    assert [[w.wort for w in x.woerter] for x in g] == [["«Keine", schluss], ["Ich", "lerne."]]


def test_gruppen_brechen_nach_klammer_mit_punkt():
    ws = [Wort("(so.)", 0, .3), Wort("Ende.)", .3, .6), Wort("Neu", .7, .9)]
    g = gruppiere(ws, max_woerter=5, max_zeichen=28, brueche=".?!", versatz=0.0, ende=2.0)
    assert [[w.wort for w in x.woerter] for x in g] == [["(so.)"], ["Ende.)"], ["Neu"]]


def test_plane_ohne_luecken_zwischen_szenen():
    # Krumme Dauern: einzeln gerundet entstünden ±1 ms Lücken oder Überlappungen
    dauern = [1.0004, 2.3336, 0.1235, 3.33349, 1.99951, 0.0005, 2.71828, 1.41421, 0.66666, 4.44449,
              0.12345, 3.14159, 2.22251, 0.9995, 1.2345]
    a = [Aufnahme(i + 1, Path(f"s{i}"), d) for i, d in enumerate(dauern)]
    plan = plane(a)
    sz = plan.szenen
    assert sz[0].start == 0.0
    for vorher, nachher in zip(sz, sz[1:]):
        assert round(vorher.start + vorher.dauer, 3) == nachher.start
        assert vorher.start + vorher.dauer == pytest.approx(nachher.start, abs=1e-9)
    assert round(sz[-1].start + sz[-1].dauer, 3) == plan.gesamt
    assert plan.gesamt == round(sum(dauern) + PAUSE * (len(dauern) - 1) + NACHLAUF, 3)
    for z in sz:
        assert z.start == round(z.start, 3) and z.dauer == round(z.dauer, 3)
