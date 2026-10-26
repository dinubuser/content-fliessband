from datetime import timedelta

from hilfen_bk import daten, knopf, text


def _aendern(ablauf, b, update_id=10):
    ablauf.verarbeite(knopf(b, "a", update_id=update_id))
    return ablauf.s.lies("notiz_anfragen")[-1]["nachricht"]


def test_antwort_auf_frage_ist_notiz(ablauf, tg, vier):
    frage = _aendern(ablauf, vier[1])
    tg.aufrufe.clear()
    ablauf.verarbeite(text("Hook zu lang, kürzer bitte", update_id=20, antwort_auf=frage))
    e = ablauf.s.ereignisse(0, ["aendern"])[0]
    assert (e["beitrag"], e["version"], e["notiz"]) == (vier[1]["id"], 1, "Hook zu lang, kürzer bitte")
    assert ablauf.s.beitrag(vier[1]["id"])["status"] == "aendern_wartet"
    assert ablauf.s.lies("notiz_anfragen") == []
    knopf_nachricht = tg.bearbeitet()[0]
    assert knopf_nachricht["text"].endswith("✏️ wird geändert\nNotiz: Hook zu lang, kürzer bitte")
    assert knopf_nachricht["reply_markup"] == {"inline_keyboard": []}
    assert tg.gesendet() == ["Notiert. Ich baue «Thema 2» neu, sobald der Mac wach ist."]
    assert ablauf.s.ereignisse(0, ["nachricht"]) == []


def test_ohne_antwort_bezug_innerhalb_30_minuten(ablauf, vier, uhr):
    _aendern(ablauf, vier[1])
    uhr.zeit += timedelta(minutes=29)
    ablauf.verarbeite(text("Zahl stimmt nicht", update_id=20))
    assert ablauf.s.ereignisse(0, ["aendern"])[0]["notiz"] == "Zahl stimmt nicht"


def test_ohne_antwort_bezug_zu_spaet_oder_fragen_offen(ablauf, vier, uhr):
    _aendern(ablauf, vier[1])
    uhr.zeit += timedelta(minutes=31)
    ablauf.verarbeite(text("zu spät", update_id=20))
    ablauf.fragen_offen((uhr.zeit + timedelta(hours=1)).replace(tzinfo=None).isoformat(timespec="minutes"))
    _aendern(ablauf, vier[2], update_id=21)
    ablauf.verarbeite(text("Antwort auf Freitags-Frage", update_id=22))
    assert ablauf.s.ereignisse(0, ["aendern"]) == []
    assert [e["nachricht"]["message"]["text"] for e in ablauf.s.ereignisse(0, ["nachricht"])] == [
        "zu spät", "Antwort auf Freitags-Frage"]


def test_antwort_auf_andere_nachricht_ist_keine_notiz(ablauf, vier):
    _aendern(ablauf, vier[1])
    ablauf.verarbeite(text("1: Glücksspiel", update_id=20, antwort_auf=123))
    ablauf.verarbeite(text("/start", update_id=21))
    assert ablauf.s.ereignisse(0, ["aendern"]) == []
    assert len(ablauf.s.ereignisse(0, ["nachricht"])) == 2


def test_leere_notiz_fragt_nochmals(ablauf, tg, vier):
    frage = _aendern(ablauf, vier[1])
    ablauf.verarbeite(text("👍", update_id=20, antwort_auf=frage))
    assert tg.gesendet()[-1] == "Ich brauche einen Satz, was ich ändern soll. Antworte nochmals auf meine Frage."
    assert ablauf.s.ereignisse(0, ["aendern", "nachricht"]) == []
    ablauf.verarbeite(text("Kürzer", update_id=21, antwort_auf=frage))
    assert ablauf.s.ereignisse(0, ["aendern"])[0]["notiz"] == "Kürzer"


def test_notiz_zu_veralteter_version(ablauf, vier):
    frage = _aendern(ablauf, vier[1])
    ablauf.melde_beitrag(daten(2, version=2, neubauten=1))
    ablauf.verarbeite(text("Kürzer", update_id=20, antwort_auf=frage))
    assert ablauf.s.ereignisse(0, ["aendern"]) == []
    assert ablauf.s.ereignisse(0, ["nachricht"])[0]["nachricht"]["message"]["text"] == "Kürzer"


# --- Nachträge aus den Prüfungen ---

def test_notiz_nach_termin_wird_nicht_angenommen(ablauf, tg, vier, uhr):
    frage = _aendern(ablauf, vier[0])
    uhr.zeit = uhr.zeit.replace(month=10, day=27, hour=19, minute=0)   # Termin Beitrag 1 erreicht
    tg.aufrufe.clear()
    ablauf.verarbeite(text("Kürzer", update_id=20, antwort_auf=frage))
    assert ablauf.s.ereignisse(0, ["aendern"]) == []
    assert ablauf.s.ereignisse(0, ["nachricht"])[0]["nachricht"]["message"]["text"] == "Kürzer"
    assert ablauf.s.beitrag(vier[0]["id"])["status"] == "offen"
    assert ablauf.s.lies("notiz_anfragen") == []
    assert tg.gesendet() == ["Termin vorbei, dieser Beitrag wird nicht gepostet."]


def test_anzeige_fehler_laesst_zustand_ganz(ablauf, tg, vier):
    frage = _aendern(ablauf, vier[1])
    tg.scheitern_bei = "editMessageText"
    ablauf.verarbeite(text("Kürzer", update_id=20, antwort_auf=frage))
    assert ablauf.s.beitrag(vier[1]["id"])["status"] == "aendern_wartet"
    assert ablauf.s.ereignisse(0, ["aendern"])[0]["notiz"] == "Kürzer"
    assert ablauf.s.lies("notiz_anfragen") == []
    assert tg.gesendet()[-1] == "Notiert. Ich baue «Thema 2» neu, sobald der Mac wach ist."


def test_bestaetigung_scheitert_uebersicht_trotzdem(ablauf, tg, vier):
    frage = _aendern(ablauf, vier[1])
    tg.aufrufe.clear()
    tg.scheitern_bei = "sendMessage"
    ablauf.verarbeite(text("Kürzer", update_id=20, antwort_auf=frage))
    assert ablauf.s.beitrag(vier[1]["id"])["status"] == "aendern_wartet"
    assert [f["message_id"] for f in tg.bearbeitet()] == [vier[1]["nachricht_id"], 505]


def test_aendern_frage_nicht_gesendet_bleibt_offen(ablauf, tg, vier):
    tg.scheitern_bei = "sendMessage"
    ablauf.verarbeite(knopf(vier[1], "a"))
    assert ablauf.s.beitrag(vier[1]["id"])["status"] == "offen"
    assert ablauf.s.lies("notiz_anfragen", []) == []
    assert tg.antworten() == ["Hat nicht geklappt, bitte nochmals tippen"]
    tg.scheitern_bei = None
    ablauf.verarbeite(text("Kürzer", update_id=20))
    assert ablauf.s.ereignisse(0, ["aendern"]) == []
    assert len(ablauf.s.ereignisse(0, ["nachricht"])) == 1


# --- Nachtrag: veraltete Notiz-Anfragen ---

def test_aendern_dann_freigeben_dann_text_ist_nachricht(ablauf, tg, vier):
    _aendern(ablauf, vier[1])
    ablauf.verarbeite(knopf(vier[1], "f", update_id=11))
    assert ablauf.s.lies("notiz_anfragen") == []
    tg.aufrufe.clear()
    ablauf.verarbeite(text("2: Kinder und Geld", update_id=20))
    assert ablauf.s.ereignisse(0, ["aendern"]) == []
    assert ablauf.s.ereignisse(0, ["nachricht"])[0]["nachricht"]["message"]["text"] == "2: Kinder und Geld"
    assert tg.gesendet() == []


def test_alle_freigeben_vergisst_anfragen(ablauf, vier):
    from hilfen_bk import woche_knopf
    _aendern(ablauf, vier[1])
    ablauf.verarbeite(woche_knopf("Aj", update_id=11))
    assert ablauf.s.lies("notiz_anfragen") == []


def test_zwei_offene_anfragen_die_neueste_gewinnt(ablauf, vier):
    _aendern(ablauf, vier[1], update_id=10)
    _aendern(ablauf, vier[2], update_id=11)
    ablauf.verarbeite(text("Kürzer", update_id=20))
    e = ablauf.s.ereignisse(0, ["aendern"])
    assert [x["beitrag"] for x in e] == [vier[2]["id"]]
    assert [a["beitrag"] for a in ablauf.s.lies("notiz_anfragen")] == [vier[1]["nr"]]


def test_antwort_auf_frage_bei_offenen_freitags_fragen_ist_notiz(ablauf, vier, uhr):
    ablauf.fragen_offen((uhr.zeit + timedelta(hours=1)).replace(tzinfo=None).isoformat(timespec="minutes"))
    frage = _aendern(ablauf, vier[1])
    ablauf.verarbeite(text("Kürzer", update_id=20, antwort_auf=frage))
    assert ablauf.s.ereignisse(0, ["aendern"])[0]["notiz"] == "Kürzer"
    assert ablauf.s.ereignisse(0, ["nachricht"]) == []


def test_direkte_antwort_auf_ungueltige_anfrage(ablauf, tg, vier):
    frage = _aendern(ablauf, vier[1])
    ablauf.s.setze(vier[1]["id"], status="freigegeben")   # Anfrage bleibt liegen, z.B. nach einem Absturz
    tg.aufrufe.clear()
    ablauf.verarbeite(text("Kürzer", update_id=20, antwort_auf=frage))
    assert ablauf.s.ereignisse(0, ["aendern"]) == []
    assert ablauf.s.ereignisse(0, ["nachricht"])[0]["nachricht"]["message"]["text"] == "Kürzer"
    assert tg.gesendet() == ["«Thema 2» ist schon freigegeben, die Notiz habe ich nicht übernommen."]
    assert ablauf.s.lies("notiz_anfragen") == []


def test_ohne_bezug_ungueltige_anfrage_ist_still_nachricht(ablauf, tg, vier):
    _aendern(ablauf, vier[1])
    ablauf.s.setze(vier[1]["id"], status="verworfen")
    tg.aufrufe.clear()
    ablauf.verarbeite(text("Kürzer", update_id=20))
    assert ablauf.s.ereignisse(0, ["aendern"]) == []
    assert len(ablauf.s.ereignisse(0, ["nachricht"])) == 1
    assert tg.gesendet() == []


def test_lange_notiz_in_anzeige_gekuerzt(ablauf, tg, vier):
    frage = _aendern(ablauf, vier[1])
    lang = "Kürzer bitte. " * 100
    tg.aufrufe.clear()
    ablauf.verarbeite(text(lang, update_id=20, antwort_auf=frage))
    assert ablauf.s.ereignisse(0, ["aendern"])[0]["notiz"] == lang.strip()
    anzeige = tg.bearbeitet()[0]["text"]
    notiz = anzeige.split("Notiz: ", 1)[1]
    assert len(notiz) == 500 and notiz.endswith("…")
