import json
from datetime import datetime

import pytest

from lib.wochenplan import PlanFehler, Wochenplan, arbeitsfelder, haenge_an, neu

WOCHE = "2026-KW44"


def _thema(nr, format, slug, frage=None):
    termin = None if nr is None else f"2026-10-{26 + nr}T19:00"
    return arbeitsfelder({"nr": nr, "format": format, "termin": termin, "slug": slug, "thema": f"Thema {slug}",
                          "quelle": {"art": "ideen", "detail": "x"}, "vorlage": None,
                          "weiterschick": "an den Kollegen", "hook_idee": "Hook", "frage": frage})


def _plan(tmp_path, themen=(), reserve=()):
    plan = Wochenplan.lade(tmp_path / "plan.json", WOCHE)
    plan.daten["themen"] = list(themen)
    plan.daten["reserve"] = list(reserve)
    plan.speichere()
    return plan


def test_neuer_plan_ohne_datei(tmp_path):
    plan = Wochenplan.lade(tmp_path / "plan.json", WOCHE)
    assert plan.daten == neu(WOCHE)
    assert plan.daten["schritte"] == {"vorbereitet": None, "gebaut": None, "gesendet": None}
    assert not plan.vorbereitet
    assert not (tmp_path / "plan.json").exists()


def test_arbeitsfelder():
    t = _thema(1, "reel", "a")
    assert (t["status"], t["antwort"], t["beitrag"], t["test"], t["vermerk"]) == ("geplant", None, None, [], "")
    assert t["frage_nachricht"] is None and t["ordner"] is None


def test_speichern_und_laden(tmp_path):
    _plan(tmp_path, [_thema(1, "reel", "a")])
    assert not (tmp_path / "plan.json.tmp").exists()
    assert Wochenplan.lade(tmp_path / "plan.json", WOCHE).themen[0]["slug"] == "a"


def test_kaputtes_json(tmp_path):
    (tmp_path / "plan.json").write_text("{kaputt", encoding="utf-8")
    with pytest.raises(PlanFehler, match="kein gültiges JSON"):
        Wochenplan.lade(tmp_path / "plan.json", WOCHE)


def test_falsche_woche(tmp_path):
    (tmp_path / "plan.json").write_text(json.dumps(neu("2026-KW43")), encoding="utf-8")
    with pytest.raises(PlanFehler, match="2026-KW43"):
        Wochenplan.lade(tmp_path / "plan.json", WOCHE)


def test_setze_speichert_und_prueft(tmp_path):
    plan = _plan(tmp_path, [_thema(1, "reel", "a")])
    plan.setze(plan.themen[0], "fehlgeschlagen", "kaputt")
    gespeichert = Wochenplan.lade(tmp_path / "plan.json", WOCHE).themen[0]
    assert (gespeichert["status"], gespeichert["vermerk"]) == ("fehlgeschlagen", "kaputt")
    with pytest.raises(PlanFehler, match="unbekannter Zustand"):
        plan.setze(plan.themen[0], "fertig")


def test_aktive_ohne_ersetzte_nach_nummer(tmp_path):
    a, b = _thema(2, "karussell", "b"), _thema(1, "reel", "a")
    b["status"] = "ersetzt"
    ersatz = dict(_thema(1, "reel", "c"), status="bereit")
    plan = _plan(tmp_path, [a, b, ersatz])
    assert [t["slug"] for t in plan.aktive()] == ["c", "b"]


def test_vermerke_ohne_doppel(tmp_path):
    plan = _plan(tmp_path)
    plan.vermerke("Kein Apify-Lauf")
    plan.vermerke("Kein Apify-Lauf")
    assert Wochenplan.lade(tmp_path / "plan.json", WOCHE).daten["vermerke"] == ["Kein Apify-Lauf"]


def test_schritt_fertig(tmp_path):
    plan = _plan(tmp_path)
    plan.schritt_fertig("vorbereitet", datetime(2026, 10, 23, 22, 14))
    assert plan.daten["schritte"]["vorbereitet"] == "2026-10-23T22:14"
    assert plan.vorbereitet


def test_ersetze_gleiches_format(tmp_path):
    plan = _plan(tmp_path, [_thema(1, "reel", "a", frage="Wie?")],
                 [_thema(None, "reel", "r"), _thema(None, "karussell", "k")])
    ersatz = plan.ersetze(plan.themen[0], "keine Antwort auf die Frage")
    assert (ersatz["slug"], ersatz["nr"], ersatz["termin"], ersatz["format"]) == ("r", 1, "2026-10-27T19:00", "reel")
    assert ersatz["status"] == "bereit"
    assert ersatz["vermerk"] == "Reserve für «Thema a» (keine Antwort auf die Frage)"
    assert (plan.themen[0]["status"], plan.themen[0]["vermerk"]) == ("ersetzt", "keine Antwort auf die Frage")
    assert [r["slug"] for r in plan.daten["reserve"]] == ["k"]
    assert [t["slug"] for t in plan.aktive()] == ["r"]
    assert len(Wochenplan.lade(tmp_path / "plan.json", WOCHE).themen) == 2


def test_ersetze_nimmt_andere_reserve(tmp_path):
    plan = _plan(tmp_path, [_thema(1, "reel", "a")], [_thema(None, "karussell", "k")])
    ersatz = plan.ersetze(plan.themen[0], "keine Antwort auf die Frage")
    assert (ersatz["slug"], ersatz["format"]) == ("k", "reel")
    assert ersatz["vermerk"].endswith(", als reel umgeschrieben")


def test_ersetze_streng_ohne_passende_reserve(tmp_path):
    plan = _plan(tmp_path, [_thema(1, "reel", "a")], [_thema(None, "reel", "r")])
    assert plan.ersetze(plan.themen[0], "Guthaben", format="karussell", andere_erlaubt=False) is None
    assert plan.themen[0]["status"] == "geplant"
    assert len(plan.daten["reserve"]) == 1


def test_ersetze_ohne_reserve(tmp_path):
    plan = _plan(tmp_path, [_thema(1, "reel", "a")])
    assert plan.ersetze(plan.themen[0], "keine Antwort auf die Frage") is None


def test_schreibe_um(tmp_path):
    t = dict(_thema(3, "reel", "a"), status="getestet", beitrag="/x.md", test=[{"runde": 1}])
    plan = _plan(tmp_path, [t])
    plan.schreibe_um(plan.themen[0], "karussell", "ElevenLabs-Guthaben zu klein")
    t = plan.themen[0]
    assert (t["format"], t["status"], t["beitrag"], t["test"]) == ("karussell", "bereit", None, [])
    assert t["vermerk"] == "als karussell neu geschrieben (ElevenLabs-Guthaben zu klein)"


def test_schreibe_um_haengt_vermerk_an(tmp_path):
    t = dict(_thema(3, "reel", "a"), status="getestet", beitrag="/x.md", vermerk="schwach im Test")
    plan = _plan(tmp_path, [t])
    plan.schreibe_um(plan.themen[0], "karussell", "ElevenLabs-Guthaben zu klein")
    assert plan.themen[0]["vermerk"] == "schwach im Test; als karussell neu geschrieben (ElevenLabs-Guthaben zu klein)"


def test_haenge_an():
    assert haenge_an("", "neu") == "neu"
    assert haenge_an("alt", "neu") == "alt; neu"


def test_ersetze_reel_mit_reserve_ist_kurz(tmp_path):
    plan = _plan(tmp_path, [dict(_thema(1, "reel", "a"), laenge="mittel")],
                 [dict(_thema(None, "reel", "r"), laenge="kurz")])
    assert plan.ersetze(plan.themen[0], "verworfen")["laenge"] == "kurz"


def test_ersetze_karussell_als_reel_wird_kurz(tmp_path):
    plan = _plan(tmp_path, [dict(_thema(1, "reel", "a"), laenge="mittel")], [_thema(None, "karussell", "k")])
    ersatz = plan.ersetze(plan.themen[0], "verworfen")
    assert (ersatz["format"], ersatz["laenge"]) == ("reel", "kurz")


def test_ersetze_reel_als_karussell_ohne_laenge(tmp_path):
    plan = _plan(tmp_path, [_thema(2, "karussell", "a")], [dict(_thema(None, "reel", "r"), laenge="kurz")])
    ersatz = plan.ersetze(plan.themen[0], "verworfen")
    assert ersatz["format"] == "karussell" and "laenge" not in ersatz


def test_schreibe_um_setzt_und_entfernt_laenge(tmp_path):
    plan = _plan(tmp_path, [dict(_thema(1, "reel", "a"), laenge="mittel"), _thema(2, "karussell", "b")])
    plan.schreibe_um(plan.themen[0], "karussell", "Guthaben")
    plan.schreibe_um(plan.themen[1], "reel", "Test")
    assert "laenge" not in plan.themen[0]
    assert plan.themen[1]["laenge"] == "kurz"
