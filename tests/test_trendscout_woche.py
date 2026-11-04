import json

from lib import trendscout
from tests.test_woche_bauen import _plan, _vorbereitet


def test_aus_der_planer_arbeitet_wie_bisher(wochen_umgebung, agentur_attrappe):
    u, a = wochen_umgebung, agentur_attrappe(fragen=0)
    _vorbereitet(u, a, fragen=False)
    assert a.anzahl("trend-scout") == 0
    assert "Trend-Scout" not in (u.pfade.woche("2026-KW44") / "planer-eingabe.md").read_text(encoding="utf-8")
    assert not any("Trend-Scout" in v for v in _plan(u).daten["vermerke"])


def test_an_der_scout_laeuft_vor_dem_planer_und_die_eingabe_nennt_die_themen(wochen_umgebung, agentur_attrappe):
    u, a = wochen_umgebung, agentur_attrappe(fragen=0)
    trendscout.setze(u.pfade.basis, True)
    _vorbereitet(u, a, fragen=False)
    namen = [wer for wer, _ in a.aufrufe]
    assert a.anzahl("trend-scout") == 1
    assert namen.index("trend-scout") < namen.index("trend-agent")   # erst Scout, dann Planer
    eingabe = (u.pfade.woche("2026-KW44") / "planer-eingabe.md").read_text(encoding="utf-8")
    assert "## Trend-Scout" in eingabe and "Prämien 2027 steigen" in eingabe
    planer_auftrag = next(t for wer, t in a.auftraege if wer == "trend-agent" and "Planer-Eingabe" not in t and "themen.json" in t)
    assert "Anregungen aus dem Web" in planer_auftrag
    assert "Trend-Scout: 1 Thema" in _plan(u).daten["vermerke"]


def test_scout_fehler_kippt_die_planung_nicht(wochen_umgebung, agentur_attrappe):
    u, a = wochen_umgebung, agentur_attrappe(fragen=0)
    trendscout.setze(u.pfade.basis, True)
    original = a.claude

    def claude(agent, auftrag, ausgabe, *args, **kwargs):
        if agent == "trend-scout":
            from lib.claude_lauf import ClaudeFehler
            raise ClaudeFehler("trend-scout: keine Antwort innerhalb von 8 Min")
        return original(agent, auftrag, ausgabe, *args, **kwargs)

    a.claude = claude
    _vorbereitet(u, a, fragen=False)
    plan = _plan(u)
    assert plan.vorbereitet and plan.daten["themen"]
    assert any(v.startswith("Trend-Scout übersprungen") for v in plan.daten["vermerke"])
