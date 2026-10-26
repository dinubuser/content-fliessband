from datetime import datetime

from hilfen_bk import daten, knopf, text, woche_knopf

from briefkasten.ablauf import ZONE


def _knoepfe(felder):
    return [k["text"] for reihe in felder["reply_markup"]["inline_keyboard"] for k in reihe]


def _arten(ablauf):
    return [e["art"] for e in ablauf.s.ereignisse(0, ["freigegeben", "zurueckgenommen", "aendern", "verworfen",
                                                        "verpasst", "nachricht"])]


def test_freigeben(ablauf, tg, vier):
    ablauf.verarbeite(knopf(vier[0], "f"))
    b = ablauf.s.beitrag(vier[0]["id"])
    assert b["status"] == "freigegeben" and _arten(ablauf) == ["freigegeben"]
    e = ablauf.s.ereignisse(0, ["freigegeben"])[0]
    assert (e["beitrag"], e["woche"], e["version"]) == (b["id"], "2026-KW44", 1)
    nachricht, uebersicht = tg.bearbeitet()
    assert nachricht["message_id"] == 501 and nachricht["text"].endswith("✅ Freigegeben, geht Di 27.10. um 19:00 online")
    assert _knoepfe(nachricht) == ["↩️ Zurücknehmen"]
    assert uebersicht["message_id"] == 505 and "«Thema 1»: ✅ freigegeben" in uebersicht["text"]
    assert tg.antworten() == ["✅ Freigegeben"]
    assert ablauf.s.lies("update_id") == 10


def test_doppelter_tipp_aendert_nichts(ablauf, tg, vier):
    ablauf.verarbeite(knopf(vier[0], "f", update_id=10))
    ablauf.verarbeite(knopf(vier[0], "f", update_id=11))
    assert _arten(ablauf) == ["freigegeben"]
    assert tg.antworten() == ["✅ Freigegeben", "Schon entschieden"]


def test_zuruecknehmen_bis_zum_termin(ablauf, tg, vier, uhr):
    ablauf.verarbeite(knopf(vier[0], "f", update_id=10))
    ablauf.verarbeite(knopf(vier[0], "z", update_id=11))
    assert ablauf.s.beitrag(vier[0]["id"])["status"] == "offen"
    assert _arten(ablauf) == ["freigegeben", "zurueckgenommen"]
    assert _knoepfe(tg.bearbeitet()[-2]) == ["✅ Freigeben", "✏️ Ändern", "❌ Verwerfen"]
    ablauf.verarbeite(knopf(vier[1], "f", update_id=12))
    uhr.zeit = datetime(2026, 10, 28, 19, 0, tzinfo=ZONE)
    ablauf.verarbeite(knopf(vier[1], "z", update_id=13))
    assert ablauf.s.beitrag(vier[1]["id"])["status"] == "freigegeben"
    assert tg.antworten()[-1] == "Termin vorbei, geht nicht mehr"


def test_veralteter_und_fremder_knopf(ablauf, tg, vier):
    ablauf.verarbeite(knopf(vier[0], "f", version=2, update_id=10))
    ablauf.verarbeite(knopf(vier[0], "f", chat=7, update_id=11))
    ablauf.verarbeite({"update_id": 12, "callback_query": {"id": "q", "data": "x:y",
                                                           "message": {"message_id": 1, "chat": {"id": 42}}}})
    assert _arten(ablauf) == []
    assert tg.antworten() == ["Veraltet, bitte die neue Nachricht nehmen", "", "Unbekannter Knopf"]
    assert ablauf.s.lies("update_id") == 12


def test_verwerfen_mit_rueckfrage(ablauf, tg, vier):
    ablauf.verarbeite(knopf(vier[3], "v", update_id=10))
    frage = tg.bearbeitet()[-1]
    assert frage["text"].endswith("Wirklich verwerfen? Ich baue dann ein Reserve-Thema.")
    assert _knoepfe(frage) == ["Ja, verwerfen", "Nein"] and _arten(ablauf) == []
    ablauf.verarbeite(knopf(vier[3], "vn", update_id=11))
    assert _knoepfe(tg.bearbeitet()[-1]) == ["✅ Freigeben", "✏️ Ändern", "❌ Verwerfen"]
    ablauf.verarbeite(knopf(vier[3], "v", update_id=12))
    ablauf.verarbeite(knopf(vier[3], "vj", update_id=13))
    assert ablauf.s.beitrag(vier[3]["id"])["status"] == "verworfen" and _arten(ablauf) == ["verworfen"]
    assert tg.bearbeitet()[-2]["text"].endswith("❌ verworfen\nReserve folgt.")
    assert tg.antworten()[-1] == "❌ Verworfen, Reserve folgt"


def test_alle_offenen_freigeben(ablauf, tg, vier):
    ablauf.verarbeite(knopf(vier[3], "vj", update_id=9))
    ablauf.verarbeite(woche_knopf("A", update_id=10))
    frage = tg.bearbeitet()[-1]
    assert frage["message_id"] == 505 and frage["text"].endswith("Wirklich alle 3 offenen Beiträge freigeben?")
    ablauf.verarbeite(woche_knopf("An", update_id=11))
    assert _arten(ablauf) == ["verworfen"]
    ablauf.verarbeite(woche_knopf("Aj", update_id=12))
    assert _arten(ablauf) == ["verworfen", "freigegeben", "freigegeben", "freigegeben"]
    assert [b["status"] for b in ablauf.s.beitraege("2026-KW44")] == ["freigegeben"] * 3 + ["verworfen"]
    assert tg.bearbeitet()[-1]["text"].endswith("Alles entschieden.")
    assert tg.antworten()[-1] == "✅ 3 freigegeben"


def test_aendern_knopf_fragt_mit_antwortfeld(ablauf, tg, vier):
    ablauf.verarbeite(knopf(vier[1], "a", update_id=10))
    methode, f = tg.aufrufe[0]
    assert methode == "sendMessage" and f["reply_markup"]["force_reply"] is True
    assert f["text"] == "Was soll ich bei «Thema 2» ändern? Antworte direkt auf diese Nachricht."
    assert ablauf.s.lies("notiz_anfragen") == [{"beitrag": 2, "version": 1, "nachricht": 506,
                                                 "zeit": "2026-10-24T22:30:00+02:00"}]
    assert tg.antworten() == ["Schreib mir, was ich ändern soll"] and _arten(ablauf) == []


def test_aendern_nach_zwei_neubauten_gesperrt(ablauf, tg, vier):
    b = ablauf.melde_beitrag(daten(1, version=3, neubauten=2))
    ablauf.verarbeite(knopf(b, "a", update_id=10))
    assert tg.antworten()[-1] == "Schon 2-mal neu gebaut, nur noch Freigeben oder Verwerfen"
    assert ablauf.s.lies("notiz_anfragen", []) == []


def test_textnachricht_ohne_anfrage_wird_nachricht(ablauf, vier):
    ablauf.verarbeite(text("1: Glücksspiel, sagt der Kollege.", update_id=30, antwort_auf=600))
    e = ablauf.s.ereignisse(0, ["nachricht"])[0]
    assert e["nachricht"]["update_id"] == 30
    assert e["nachricht"]["message"]["text"] == "1: Glücksspiel, sagt der Kollege."
    assert e["nachricht"]["message"]["reply_to_message"] == {"message_id": 600}
    ablauf.verarbeite(text("fremd", update_id=31, chat=7))
    assert len(ablauf.s.ereignisse(0, ["nachricht"])) == 1
    assert ablauf.s.lies("update_id") == 31


def test_freigeben_nach_termin_gesperrt(ablauf, tg, vier, uhr):
    from briefkasten import texte
    uhr.zeit = datetime(2026, 10, 27, 19, 0, 30, tzinfo=ZONE)
    ablauf.verarbeite(knopf(vier[0], "f", update_id=10))
    assert _arten(ablauf) == [] and ablauf.s.beitrag(vier[0]["id"])["status"] == "offen"
    assert tg.antworten() == [texte.TERMIN_VORBEI]
    assert tg.bearbeitet() == []


def test_alle_freigeben_ueberspringt_beitrag_nach_termin(ablauf, tg, vier, uhr):
    uhr.zeit = datetime(2026, 10, 27, 19, 0, 30, tzinfo=ZONE)
    ablauf.verarbeite(woche_knopf("A", update_id=10))
    assert tg.bearbeitet()[-1]["text"].endswith("Wirklich alle 3 offenen Beiträge freigeben?")
    ablauf.verarbeite(woche_knopf("Aj", update_id=11))
    assert _arten(ablauf) == ["freigegeben"] * 3
    assert [b["status"] for b in ablauf.s.beitraege("2026-KW44")] == ["offen"] + ["freigegeben"] * 3
    assert tg.antworten()[-1] == "✅ 3 freigegeben"


def test_anzeige_fehler_bricht_antwort_nicht_ab(ablauf, tg, vier):
    tg.scheitern_bei = "editMessageText"
    ablauf.verarbeite(knopf(vier[0], "f", update_id=10))
    assert ablauf.s.beitrag(vier[0]["id"])["status"] == "freigegeben" and _arten(ablauf) == ["freigegeben"]
    assert tg.antworten() == ["✅ Freigegeben"]
    tg.scheitern_bei = None
    ablauf.verarbeite(knopf(vier[0], "f", update_id=11))
    neu = tg.bearbeitet()[-1]
    assert neu["message_id"] == 501 and neu["text"].endswith("✅ Freigegeben, geht Di 27.10. um 19:00 online")
    assert tg.antworten()[-1] == "Schon entschieden" and _arten(ablauf) == ["freigegeben"]


def test_nichts_zurueckzunehmen_zeichnet_neu(ablauf, tg, vier):
    ablauf.verarbeite(knopf(vier[0], "z", update_id=10))
    assert tg.bearbeitet()[-1]["message_id"] == 501 and tg.antworten() == ["Nichts zurückzunehmen"]


def test_alle_freigeben_trotz_anzeige_fehler(ablauf, tg, vier):
    tg.scheitern_bei = "editMessageText"
    ablauf.verarbeite(woche_knopf("Aj", update_id=10))
    assert _arten(ablauf) == ["freigegeben"] * 4
    assert [b["status"] for b in ablauf.s.beitraege("2026-KW44")] == ["freigegeben"] * 4
    assert tg.antworten() == ["✅ 4 freigegeben"]


def test_freigeben_bei_platzhalter_gesperrt(ablauf, tg, vier):
    b = ablauf.s.setze(vier[0]["id"], platzhalter=True)
    ablauf.verarbeite(knopf(b, "f"))
    assert ablauf.s.beitrag(b["id"])["status"] == "offen" and _arten(ablauf) == []
    assert tg.antworten() == ["Hat noch Platzhalter, bitte zuerst ändern."]
    assert _knoepfe(tg.bearbeitet()[0]) == ["✏️ Ändern", "❌ Verwerfen"]


def test_alle_freigeben_ueberspringt_platzhalter(ablauf, tg, vier):
    ablauf.s.setze(vier[1]["id"], platzhalter=True)
    ablauf.verarbeite(woche_knopf("A", update_id=10))
    assert "Wirklich alle 3 offenen Beiträge freigeben?" in tg.bearbeitet()[0]["text"]
    ablauf.verarbeite(woche_knopf("Aj", update_id=11))
    status = [ablauf.s.beitrag(b["id"])["status"] for b in vier]
    assert status == ["freigegeben", "offen", "freigegeben", "freigegeben"]
    assert tg.antworten()[-1] == "✅ 3 freigegeben"


def test_nur_platzhalter_offen_alle_freigeben_nichts(ablauf, tg, vier):
    for b in vier:
        ablauf.s.setze(b["id"], platzhalter=True)
    ablauf.verarbeite(woche_knopf("A"))
    assert tg.antworten() == ["Nichts offen"]


def test_aendern_und_verwerfen_bei_platzhalter(ablauf, tg, vier):
    b = ablauf.s.setze(vier[0]["id"], platzhalter=True)
    ablauf.verarbeite(knopf(b, "a", update_id=10))
    assert tg.antworten() == ["Schreib mir, was ich ändern soll"]
    ablauf.verarbeite(knopf(b, "vj", update_id=11))
    assert ablauf.s.beitrag(b["id"])["status"] == "verworfen" and _arten(ablauf) == ["verworfen"]


def test_aendern_nach_zwei_neubauten_mit_platzhalter(ablauf, tg, vier):
    b = ablauf.s.setze(vier[0]["id"], platzhalter=True, neubauten=2)
    ablauf.verarbeite(knopf(b, "a"))
    assert tg.antworten() == ["Schon 2-mal neu gebaut, nur noch Verwerfen"]
