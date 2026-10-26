from datetime import datetime

from hilfen_bk import knopf

from briefkasten.ablauf import ZONE


def test_verpasst_nach_termin(ablauf, tg, vier, uhr):
    ablauf.verarbeite(knopf(vier[1], "f", update_id=10))
    tg.aufrufe.clear()
    uhr.zeit = datetime(2026, 10, 28, 19, 0, tzinfo=ZONE)
    ablauf.zeitgeber()
    ablauf.zeitgeber()
    assert [b["status"] for b in ablauf.s.beitraege("2026-KW44")] == ["verpasst", "freigegeben", "offen", "offen"]
    assert [e["art"] for e in ablauf.s.ereignisse(0, ["verpasst"])] == ["verpasst"]
    assert tg.gesendet() == ["⏰ «Thema 1» (Di 27.10., 19:00) war bis zum Termin nicht freigegeben und wird "
                             "nicht gepostet."]
    assert tg.bearbeitet()[0]["text"].endswith("⏰ verpasst")


def test_wartende_aenderung_verpasst_auch(ablauf, vier, uhr):
    ablauf.s.setze(vier[0]["id"], status="aendern_wartet")
    uhr.zeit = datetime(2026, 10, 27, 19, 0, tzinfo=ZONE)
    ablauf.zeitgeber()
    assert ablauf.s.beitrag(vier[0]["id"])["status"] == "verpasst"


def test_verpasst_vergisst_notiz_anfragen(ablauf, tg, vier, uhr):
    ablauf.verarbeite(knopf(vier[0], "a", update_id=10))
    ablauf.verarbeite(knopf(vier[1], "a", update_id=11))
    uhr.zeit = datetime(2026, 10, 27, 19, 0, tzinfo=ZONE)
    ablauf.zeitgeber()
    assert [a["beitrag"] for a in ablauf.s.lies("notiz_anfragen")] == [vier[1]["nr"]]


def test_telegram_fehler_bricht_zeitgeber_nicht_ab_und_meldung_folgt(ablauf, tg, vier, uhr):
    uhr.zeit = datetime(2026, 10, 28, 19, 0, tzinfo=ZONE)
    tg.scheitern_bei = "sendMessage"
    ablauf.zeitgeber()
    assert [b["status"] for b in ablauf.s.beitraege("2026-KW44")] == ["verpasst", "verpasst", "offen", "offen"]
    assert len(ablauf.s.ereignisse(0, ["verpasst"])) == 2
    assert tg.gesendet() == []
    tg.scheitern_bei = "editMessageText"
    ablauf.zeitgeber()
    assert [t.split(" (")[0] for t in tg.gesendet()] == ["⏰ «Thema 1»", "⏰ «Thema 2»"]
    tg.scheitern_bei = None
    ablauf.zeitgeber()
    assert len(tg.gesendet()) == 2
    assert len(ablauf.s.ereignisse(0, ["verpasst"])) == 2


def test_erinnerung_montag_8_uhr_einmal(ablauf, tg, vier, uhr):
    ablauf.verarbeite(knopf(vier[0], "f", update_id=10))
    tg.aufrufe.clear()
    for zeit in (datetime(2026, 10, 25, 20, 0), datetime(2026, 10, 26, 7, 59)):
        uhr.zeit = zeit.replace(tzinfo=ZONE)
        ablauf.zeitgeber()
    assert tg.gesendet() == []
    uhr.zeit = datetime(2026, 10, 26, 8, 0, tzinfo=ZONE)
    ablauf.zeitgeber()
    ablauf.zeitgeber()
    assert len(tg.gesendet()) == 1
    erinnerung = tg.gesendet()[0]
    assert erinnerung.startswith("Erinnerung: Diese Beiträge sind noch nicht freigegeben.")
    assert "«Thema 1»" not in erinnerung and "«Thema 2»: offen" in erinnerung


def test_erinnerung_folgt_wenn_telegram_erst_scheitert(ablauf, tg, vier, uhr):
    uhr.zeit = datetime(2026, 10, 26, 8, 0, tzinfo=ZONE)
    tg.scheitern_bei = "sendMessage"
    ablauf.zeitgeber()
    assert not ablauf.s.lies("erinnert-2026-W44")
    tg.scheitern_bei = None
    uhr.zeit = datetime(2026, 10, 26, 8, 1, tzinfo=ZONE)
    ablauf.zeitgeber()
    assert len(tg.gesendet()) == 1 and ablauf.s.lies("erinnert-2026-W44") is True


def test_keine_erinnerung_wenn_nichts_offen(ablauf, tg, vier, uhr):
    for b in vier:
        ablauf.s.setze(b["id"], status="freigegeben")
    uhr.zeit = datetime(2026, 10, 26, 9, 0, tzinfo=ZONE)
    ablauf.zeitgeber()
    assert tg.gesendet() == [] and ablauf.s.lies("erinnert-2026-W44") is True


def test_abholen_erst_nach_umstellen(ablauf, tg, vier):
    tg.updates = [knopf(vier[0], "f", update_id=6), knopf(vier[1], "f", update_id=7)]
    assert ablauf.abholen() is None and "getUpdates" not in tg.methoden()
    ablauf.umstellen(5)
    assert ablauf.abholen(zeitlimit=50) == 2
    abfrage = next(f for m, f in tg.aufrufe if m == "getUpdates")
    assert abfrage == {"offset": 6, "timeout": 50, "allowed_updates": ["message", "callback_query"]}
    assert ablauf.s.lies("update_id") == 7
    assert len(ablauf.s.ereignisse(0, ["freigegeben"])) == 2


def test_abholen_wartet_bei_telegram_laenger_als_long_polling(ablauf, vier):
    zeitlimits = []

    def tg(methode, felder, zeitlimit=30):
        zeitlimits.append((felder["timeout"], zeitlimit))
        return []

    ablauf.tg = tg
    ablauf.umstellen(5)
    assert ablauf.abholen() == 0
    (telegram_timeout, http_zeitlimit), = zeitlimits
    assert telegram_timeout <= 30 and http_zeitlimit >= telegram_timeout + 20


def test_abholen_haelt_die_sperre_nicht_waehrend_getupdates(ablauf, vier):
    frei = []

    def tg(methode, felder, zeitlimit=30):
        frei.append(not ablauf.sperre._is_owned())
        return []

    ablauf.tg = tg
    ablauf.umstellen(5)
    ablauf.abholen()
    assert frei == [True]


def test_update_zaehlt_auch_wenn_telegram_beim_bearbeiten_scheitert(ablauf, tg, vier):
    ablauf.umstellen(5)
    tg.updates = [knopf(vier[0], "f", update_id=6)]
    tg.scheitern_bei = "editMessageText"
    assert ablauf.abholen() == 1
    assert ablauf.s.lies("update_id") == 6
    assert ablauf.s.beitrag(vier[0]["id"])["status"] == "freigegeben"
    assert tg.antworten() == ["✅ Freigegeben"]


def test_platzhalter_wie_offen_verpasst_und_erinnert(ablauf, tg, vier, uhr):
    from datetime import datetime
    from briefkasten.ablauf import ZONE
    ablauf.s.setze(vier[0]["id"], platzhalter=True)
    ablauf.s.setze(vier[1]["id"], platzhalter=True)
    uhr.zeit = datetime(2026, 10, 27, 19, 0, tzinfo=ZONE)   # Di: Termin 1 erreicht, kein Montag
    ablauf.zeitgeber()
    assert ablauf.s.beitrag(vier[0]["id"])["status"] == "verpasst"
    ablauf.s.schreibe("erinnert-2026-W44", None)
    uhr.zeit = datetime(2026, 10, 26, 8, 0, tzinfo=ZONE)    # Mo 08:00
    tg.aufrufe.clear()
    ablauf.zeitgeber()
    assert "«Thema 2»: offen, ⚠️ hat noch Platzhalter" in tg.gesendet()[0]
