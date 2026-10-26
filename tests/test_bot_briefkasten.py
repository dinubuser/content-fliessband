import json
from datetime import datetime

from lib import woche
from lib.bot import Bot
from lib.manifest import schreibe_json
from lib.wochenplan import Wochenplan

WOCHE = "2026-KW44"


def _nachricht(update_id, text, chat=42, antwort_auf=None):
    m = {"message_id": 800 + update_id, "chat": {"id": chat, "type": "private"}, "text": text}
    if antwort_auf:
        m["reply_to_message"] = {"message_id": antwort_auf}
    return {"update_id": update_id, "message": m}


def test_sammle_ueber_briefkasten(tmp_path, telegram, briefkasten):
    schreibe_json(tmp_path / "bot.json", {"chat_id": 42, "letzte_update_id": 3})
    bot = Bot(tmp_path / "bot.json", anfrage=telegram, briefkasten=briefkasten)
    briefkasten.ereignis("nachricht", nachricht=_nachricht(7, "1: Glücksspiel", antwort_auf=101), woche=None)
    briefkasten.ereignis("freigegeben", beitrag="x")
    briefkasten.ereignis("nachricht", nachricht=_nachricht(8, "fremd", chat=9), woche=None)
    assert bot.sammle() == 1
    assert telegram.aufrufe == []
    eingang = json.loads((tmp_path / "bot-eingang.json").read_text(encoding="utf-8"))["nachrichten"]
    assert [e["update_id"] for e in eingang] == [7]
    assert briefkasten.stand == {"entscheide": 0, "nachrichten": 3}
    assert bot.sammle() == 0
    nachrichten, hoechste = bot.neue_nachrichten()
    assert [m["text"] for m in nachrichten] == ["1: Glücksspiel"] and hoechste == 7
    assert bot.letzte_update_id == 3


def test_sammle_ohne_briefkasten_wie_bisher(tmp_path, telegram):
    schreibe_json(tmp_path / "bot.json", {"chat_id": 42, "letzte_update_id": 0})
    telegram.updates = [_nachricht(5, "Hallo")]
    bot = Bot(tmp_path / "bot.json", anfrage=telegram)
    assert bot.sammle() == 1 and bot.letzte_update_id == 5
    assert telegram.methoden() == ["getUpdates", "getUpdates"]


def test_antwort_frist():
    assert woche.antwort_frist(datetime(2026, 10, 23, 22, 0)) == datetime(2026, 10, 24, 22, 0)
    assert woche.antwort_frist(datetime(2026, 10, 24, 9, 0)) == datetime(2026, 10, 24, 22, 0)


def test_fragen_werden_beim_briefkasten_gemeldet(wochen_umgebung, agentur_attrappe, briefkasten):
    u = wochen_umgebung
    dienste = u.dienste(agentur_attrappe(), jetzt=datetime(2026, 10, 23, 22, 0), briefkasten=briefkasten)
    woche.vorbereiten(WOCHE, u.pfade, dienste, lambda t: None)
    assert briefkasten.fragen == [datetime(2026, 10, 24, 22, 0)]


def test_fragen_melden_scheitert_nur_als_vermerk(wochen_umgebung, agentur_attrappe, briefkasten):
    u = wochen_umgebung
    briefkasten.nicht_erreichbar = True
    dienste = u.dienste(agentur_attrappe(), jetzt=datetime(2026, 10, 23, 22, 0), briefkasten=briefkasten)
    woche.vorbereiten(WOCHE, u.pfade, dienste, lambda t: None)
    plan = Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE)
    assert plan.themen[0]["status"] == "frage_gesendet"
    assert any(v.startswith("Briefkasten: Fragen nicht gemeldet") for v in plan.daten["vermerke"])


def test_sammle_briefkasten_laesst_bestaetigte_weg(tmp_path, telegram, briefkasten):
    """Mindestens einmal: Kommt eine schon bestätigte Nachricht nochmals, fällt sie weg (mit Log), merke läuft weiter."""
    schreibe_json(tmp_path / "bot.json", {"chat_id": 42, "letzte_update_id": 7})
    zeilen = []
    bot = Bot(tmp_path / "bot.json", anfrage=telegram, briefkasten=briefkasten, log=zeilen.append)
    briefkasten.ereignis("nachricht", nachricht=_nachricht(7, "schon bestätigt"), woche=None)
    briefkasten.ereignis("nachricht", nachricht=_nachricht(9, "neu"), woche=None)
    assert bot.sammle() == 1
    eingang = json.loads((tmp_path / "bot-eingang.json").read_text(encoding="utf-8"))["nachrichten"]
    assert [e["update_id"] for e in eingang] == [9]
    assert briefkasten.stand["nachrichten"] == 2
    assert zeilen == ["Briefkasten: 1 Nachricht schon bestätigt oder doppelt, verworfen"]


def test_bauen_briefkasten_weg_nimmt_lokalen_eingang(wochen_umgebung, agentur_attrappe, briefkasten, monkeypatch):
    """Samstag, Server nicht erreichbar: Der Bau läuft mit dem lokalen Eingang weiter (statt abzubrechen),
    mit Vermerk im Plan und Log. Telegram fragt der Mac auch dann nie selbst ab (409)."""
    u = wochen_umgebung
    a = agentur_attrappe()
    woche.vorbereiten(WOCHE, u.pfade, u.dienste(a, briefkasten=briefkasten), lambda t: None)
    plan = Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE)
    frage = plan.themen[0]["frage_nachricht"]
    schreibe_json(u.pfade.daten / "bot-eingang.json",
                  {"nachrichten": [_nachricht(7, "Glücksspiel", antwort_auf=frage)]})
    briefkasten.nicht_erreichbar = True
    monkeypatch.setattr(woche, "baue_offene", lambda *args, **kw: False)   # nur das Lesen der Antworten prüfen
    zeilen = []
    woche.bauen(WOCHE, u.pfade, u.dienste(a, jetzt=datetime(2026, 10, 24, 22, 0), briefkasten=briefkasten),
                zeilen.append)
    plan = Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE)
    assert plan.themen[0]["antwort"] == "Glücksspiel"
    vermerk = ("Briefkasten nicht erreichbar, Antworten evtl. unvollständig "
               "(Briefkasten nicht erreichbar (URLError))")
    assert vermerk in plan.daten["vermerke"]
    assert any(vermerk in z for z in zeilen)
    assert "getUpdates" not in u.telegram.methoden()


def test_bauen_telegram_weg_bricht_weiter_ab(wochen_umgebung, agentur_attrappe):
    """Etappe 3 ohne Briefkasten: BotFehler beim Lesen der Antworten beendet den Schritt wie bisher."""
    import pytest
    from lib.bot import BotFehler
    from lib.woche import SchrittFehler
    u = wochen_umgebung
    a = agentur_attrappe()
    woche.vorbereiten(WOCHE, u.pfade, u.dienste(a), lambda t: None)
    dienste = u.dienste(a, jetzt=datetime(2026, 10, 24, 22, 0))

    def weg():
        raise BotFehler("Telegram nicht erreichbar")
    dienste.bot.neue_nachrichten = weg
    with pytest.raises(SchrittFehler, match="Antworten nicht lesbar: Telegram nicht erreichbar"):
        woche.bauen(WOCHE, u.pfade, dienste, lambda t: None)


def test_briefkasten_fehler_ist_schritt_fehler():
    from lib.briefkasten import BriefkastenFehler
    assert BriefkastenFehler in woche.SCHRITT_FEHLER
