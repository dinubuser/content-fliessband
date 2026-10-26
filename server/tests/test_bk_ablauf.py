import pytest
from hilfen_bk import daten

from briefkasten.telegram import TelegramFehler


def _knoepfe(felder):
    return [k["text"] for reihe in felder["reply_markup"]["inline_keyboard"] for k in reihe]


def test_melde_beitrag_schickt_knopf_nachricht(ablauf, tg):
    b = ablauf.melde_beitrag(daten(1))
    assert b["status"] == "offen" and b["nachricht_id"] == 501 and b["nr"] == 1
    methode, f = tg.aufrufe[0]
    assert methode == "sendMessage" and f["chat_id"] == 42 and f["disable_notification"] is True
    assert f["text"] == "Di 27.10., 19:00 · Reel\n«Thema 1»"
    assert _knoepfe(f) == ["✅ Freigeben", "✏️ Ändern", "❌ Verwerfen"]


def test_melde_beitrag_gleiche_version_nur_einmal(ablauf, tg):
    ablauf.melde_beitrag(daten(1))
    assert ablauf.melde_beitrag(daten(1))["nachricht_id"] == 501
    assert tg.methoden() == ["sendMessage"]


def test_melde_nach_gescheitertem_senden_schickt_nochmals(ablauf, tg):
    tg.scheitern_bei = "sendMessage"
    with pytest.raises(TelegramFehler):
        ablauf.melde_beitrag(daten(1))
    tg.scheitern_bei = None
    assert ablauf.melde_beitrag(daten(1))["nachricht_id"] == 501


def test_neue_version_ersetzt_alte_nachricht(ablauf, tg):
    alt = ablauf.melde_beitrag(daten(1))
    neu = ablauf.melde_beitrag(daten(1, version=2, neubauten=1))
    assert (neu["nr"], neu["version"], neu["nachricht_id"], neu["status"]) == (alt["nr"], 2, 502, "offen")
    alte = tg.bearbeitet()[0]
    assert alte["message_id"] == 501 and alte["text"].endswith("Ersetzt durch Version 2, siehe neue Nachricht.")
    assert alte["reply_markup"] == {"inline_keyboard": []}
    assert tg.gesendet()[-1].startswith("Di 27.10., 19:00 · Reel · Version 2")


def test_aeltere_version_aendert_nichts(ablauf, tg):
    ablauf.melde_beitrag(daten(1, version=2))
    assert ablauf.melde_beitrag(daten(1))["version"] == 2
    assert tg.methoden() == ["sendMessage"]


@pytest.mark.parametrize("feld, wert", [("format", "video"), ("version", 0), ("termin", "morgen"),
                                        ("titel", ""), ("id", "")])
def test_ungueltiger_beitrag(ablauf, feld, wert):
    with pytest.raises(ValueError):
        ablauf.melde_beitrag(daten(1, **{feld: wert}))


def test_woche_fertig_schickt_uebersicht_einmal(ablauf, tg):
    for nr in (1, 2, 3, 4):
        ablauf.melde_beitrag(daten(nr))
    ablauf.woche_fertig("2026-KW44")
    ablauf.woche_fertig("2026-KW44")
    assert tg.methoden().count("sendMessage") == 5
    uebersicht = tg.aufrufe[4][1]
    assert uebersicht["text"].startswith("Freigabe 2026-KW44\nDi 27.10., 19:00 · Reel «Thema 1»: offen")
    assert _knoepfe(uebersicht) == ["✅ Alle offenen freigeben"]
    assert ablauf.s.lies("uebersicht-2026-KW44") == 505
    assert tg.bearbeitet()[-1]["message_id"] == 505


def test_woche_fertig_ohne_beitraege(ablauf):
    with pytest.raises(ValueError):
        ablauf.woche_fertig("2026-KW44")


def test_neubau_gescheitert_stellt_knoepfe_her(ablauf, tg):
    b = ablauf.melde_beitrag(daten(1))
    ablauf.s.setze(b["id"], status="aendern_wartet")
    ablauf.neubau_gescheitert(b["id"], "Szene 2 zu lang")
    assert ablauf.s.beitrag(b["id"])["status"] == "offen"
    assert tg.gesendet()[-1] == "Neubau von «Thema 1» gescheitert: Szene 2 zu lang\nDie bisherige Version gilt weiter."
    assert _knoepfe(tg.bearbeitet()[-1]) == ["✅ Freigeben", "✏️ Ändern", "❌ Verwerfen"]
    with pytest.raises(ValueError):
        ablauf.neubau_gescheitert("fehlt", "x")


def test_neubau_gescheitert_anzeige_fehler_kein_abbruch(ablauf, tg):
    """Status ist schon offen: ein Telegram-Fehler beim Neuzeichnen der Knöpfe/Übersicht löst kein 502 aus."""
    b = ablauf.melde_beitrag(daten(1))
    ablauf.s.setze(b["id"], status="aendern_wartet")
    tg.scheitern_bei = "editMessageText"
    ablauf.neubau_gescheitert(b["id"], "Szene 2 zu lang")
    assert ablauf.s.beitrag(b["id"])["status"] == "offen"
    assert tg.gesendet()[-1].startswith("Neubau von «Thema 1» gescheitert")


def test_neubau_gescheitert_meldung_weg_wird_wiederholt(ablauf, tg):
    """Kommt die Fehlermeldung selbst nicht an, wirft der Server (502), der Mac wiederholt. Der zweite Aufruf
    wirkt beim Status nicht doppelt und schickt die Meldung genau einmal."""
    b = ablauf.melde_beitrag(daten(1))
    ablauf.s.setze(b["id"], status="aendern_wartet")
    tg.scheitern_bei = "sendMessage"
    with pytest.raises(TelegramFehler):
        ablauf.neubau_gescheitert(b["id"], "Szene 2 zu lang")
    assert ablauf.s.beitrag(b["id"])["status"] == "offen"
    tg.scheitern_bei = None
    vorher = len(tg.gesendet())
    ablauf.neubau_gescheitert(b["id"], "Szene 2 zu lang")
    neu = ablauf.s.beitrag(b["id"])
    assert (neu["status"], neu["version"], neu["nachricht_id"]) == ("offen", 1, b["nachricht_id"])
    assert len(tg.gesendet()) == vorher + 1


def test_umstellen_nur_einmal(ablauf):
    assert ablauf.umstellen(41) == 41
    assert ablauf.umstellen(99) == 41


def test_fragen_offen_und_ereignisse(ablauf):
    ablauf.fragen_offen("2026-10-24T22:00")
    assert ablauf.s.lies("fragen_bis") == "2026-10-24T22:00"
    with pytest.raises(ValueError):
        ablauf.fragen_offen("Samstag")
    with pytest.raises(ValueError):
        ablauf.ereignisse(0, ["geheim"])
    assert ablauf.ereignisse(0, ["freigegeben", "nachricht"]) == []


def test_neue_version_trotz_edit_fehler_der_alten_nachricht(ablauf, tg, caplog):
    ablauf.melde_beitrag(daten(1))
    tg.scheitern_bei = "editMessageText"
    neu = ablauf.melde_beitrag(daten(1, version=2, neubauten=1))
    assert (neu["version"], neu["nachricht_id"], neu["status"]) == (2, 502, "offen")
    f = [f for m, f in tg.aufrufe if m == "sendMessage"][-1]
    assert _knoepfe(f) == ["✅ Freigeben", "✏️ Ändern", "❌ Verwerfen"]
    assert "nicht erreichbar" in caplog.text


def test_melde_beitrag_trotz_uebersicht_fehler(ablauf, tg, vier, caplog):
    tg.scheitern_bei = "editMessageText"
    neu = ablauf.melde_beitrag(daten(1, id="2026-KW44-thema-neu", titel="Neu"))
    assert neu["nachricht_id"] == 506 and neu["status"] == "offen"
    assert "nicht erreichbar" in caplog.text


def test_melde_beitrag_mit_platzhalter(ablauf, tg):
    b = ablauf.melde_beitrag(daten(1, platzhalter=True))
    assert b["platzhalter"] is True
    assert _knoepfe(tg.aufrufe[0][1]) == ["✏️ Ändern", "❌ Verwerfen"]
    assert "Platzhalter" in tg.aufrufe[0][1]["text"]
    assert ablauf.melde_beitrag(daten(2))["platzhalter"] is False


def test_neue_version_ohne_platzhalter_bekommt_freigeben(ablauf, tg):
    alt = ablauf.melde_beitrag(daten(1, platzhalter=True))
    neu = ablauf.melde_beitrag(daten(1, version=2, neubauten=1))
    assert neu["nr"] == alt["nr"] and neu["platzhalter"] is False
    gesendet = [f for m, f in tg.aufrufe if m == "sendMessage"]
    assert _knoepfe(gesendet[-1]) == ["✅ Freigeben", "✏️ Ändern", "❌ Verwerfen"]


@pytest.mark.parametrize("wert", ["ja", 1, None])
def test_platzhalter_muss_bool_sein(ablauf, wert):
    with pytest.raises(ValueError):
        ablauf.melde_beitrag(daten(1, platzhalter=wert))


def test_neubau_gescheitert_behaelt_platzhalter_knoepfe(ablauf, tg):
    b = ablauf.melde_beitrag(daten(1, platzhalter=True))
    ablauf.s.setze(b["id"], status="aendern_wartet")
    ablauf.neubau_gescheitert(b["id"], "Neue Fassung hat noch Platzhalter ([Zahl]), bitte genauer beschreiben")
    neu = ablauf.s.beitrag(b["id"])
    assert (neu["status"], neu["platzhalter"]) == ("offen", True)
    assert _knoepfe(tg.bearbeitet()[0]) == ["✏️ Ändern", "❌ Verwerfen"]
