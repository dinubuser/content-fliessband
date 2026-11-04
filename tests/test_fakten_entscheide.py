"""Etappe 10: Faktencheck beim Neubau nach ✏️ Ändern. Offene Funde setzen dort nie einen Marker, damit die
neue Fassung freigebbar bleibt; bei einem Fehler im Neubau gilt der alte Stand von t["fakten"] weiter."""
import pytest

from lib import entscheide
from lib.reel_renderer import RenderFehler
from lib.wochenplan import Wochenplan
from tests.test_entscheide_aendern import REEL1, WOCHE, _e, _lauf, _thema, gesendet  # noqa: F401  (Fixture gesendet)


def _sprechzeile(auftrag: str) -> str:
    """Eine eindeutige Sprechtext-Zeile aus dem Skript im Auftrag (zwischen den -----, ohne Label)."""
    skript = auftrag.split("-----")[1]
    kandidaten = [z.split("Sprechtext: ", 1)[1] for z in skript.splitlines() if z.startswith("Sprechtext: ")]
    kandidaten = [z for z in kandidaten if len(z) >= 8 and skript.count(z) == 1]
    assert kandidaten
    return kandidaten[0]


def test_aendern_prueft_fakten_ohne_marker(gesendet, briefkasten):
    u, a = gesendet
    a.fakten_antwort = lambda auftrag: {"geprueft": 4, "funde": [
        {"stelle": _sprechzeile(auftrag), "urteil": "falsch", "korrektur": "", "quelle": "", "grund": "g"}]}
    briefkasten.ereignis("aendern", beitrag=REEL1, notiz="Hook kürzer")
    assert _lauf(u, a, briefkasten) == 1
    t = _thema(u, "beispiel-reel-eins")
    assert len(t["fakten"]["offen"]) == 1
    assert "[prüfen]" not in open(t["beitrag"], encoding="utf-8").read()
    zeilen = [z for z in u.telegram.texte() if z.startswith("🔎 Faktencheck: 4 Aussagen geprüft, 1 offen:")]
    assert zeilen and zeilen[0].endswith("bitte selbst klären") and "[prüfen]" not in zeilen[0]
    assert _e(u, REEL1)["version"] == 2


@pytest.mark.parametrize("vorher", [{"lief": True, "geprueft": 2, "korrigiert": [], "offen": []}, None])
def test_aendern_fehler_stellt_fakten_wieder_her(gesendet, briefkasten, monkeypatch, vorher):
    u, a = gesendet
    a.fakten_antwort = lambda auftrag: {"geprueft": 4, "funde": [
        {"stelle": _sprechzeile(auftrag), "urteil": "falsch", "korrektur": "", "quelle": "", "grund": "g"}]}
    plan = Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE)
    t = next(t for t in plan.themen if t["slug"] == "beispiel-reel-eins")
    t.pop("fakten", None)
    if vorher is not None:
        t["fakten"] = vorher
    plan.speichere()
    gesehen = []

    def kaputt(thema, *args, **kwargs):
        gesehen.append((thema, thema["fakten"]["geprueft"]))
        raise RenderFehler("Telegram weg")
    monkeypatch.setattr(entscheide, "sende_beitrag", kaputt)
    briefkasten.ereignis("aendern", beitrag=REEL1, notiz="Hook kürzer")
    _lauf(u, a, briefkasten)
    thema, beim_senden = gesehen[0]
    assert beim_senden == 4   # der neue Wert war gesetzt
    if vorher is None:
        assert "fakten" not in thema   # Feld wieder entfernt
    else:
        assert thema["fakten"] == vorher
