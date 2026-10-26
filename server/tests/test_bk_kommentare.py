from datetime import timedelta

import pytest

from briefkasten import texte
from briefkasten.instagram import InstagramFehler
from briefkasten.telegram import TelegramFehler
from briefkasten.kommentare import MAX_MELDUNGEN, Kommentare, ist_start


@pytest.mark.parametrize("text", ["START", "start", "Start!", "START 🙌", "START bitte", "Bitte start",
                                  "#start", "start.", "🙌START🙌", "  sTaRt  "])
def test_ist_start(text):
    assert ist_start(text)


@pytest.mark.parametrize("text", ["Neustart", "gestartet", "Startup", "Starter", "Restart", "start_", "start2", "", "sta rt", None])
def test_ist_kein_start(text):
    assert not ist_start(text)


def test_kommentar_meldung():
    assert texte.kommentar_meldung("anna_beispiel", "Reel", "Thema 1") == \
        "💬 @anna_beispiel hat START kommentiert · Reel ‹Thema 1›"
    assert texte.kommentar_meldung(None, "Karussell", "T").startswith("💬 Jemand hat START kommentiert")


def test_profil_tastatur():
    assert texte.profil_tastatur("beispiel.konto") == {
        "inline_keyboard": [[{"text": "Profil öffnen", "url": "https://instagram.com/beispiel.konto"}]]}
    assert texte.profil_tastatur("anna beispiel") is None
    assert texte.profil_tastatur("a/../b") is None
    assert texte.profil_tastatur(None) is None


def test_kommentare_hinweis():
    text = texte.kommentare_hinweis("Instagram HTTP 403: keine Berechtigung")
    assert text.startswith("⚠️ Kommentare lesen geht nicht: Instagram neu verbinden")
    assert "server/instagram.sh" in text and "Instagram HTTP 403: keine Berechtigung" in text


def test_nutzername_ohne_punktnamen():
    assert texte.profil_tastatur("..") is None
    assert texte.profil_tastatur(".anna") is None
    assert texte.profil_tastatur("_anna.b_") is not None


REEL = {"id": "m1", "caption": "Wie ich neben dem Job ein zweites Standbein aufbaue",
        "media_type": "VIDEO", "media_product_type": "REELS", "timestamp": "2026-10-24T17:00:05+0000"}
KARUSSELL = {"id": "m2", "caption": None, "media_type": "CAROUSEL_ALBUM", "media_product_type": "FEED",
             "timestamp": "2026-10-24T17:00:05+0000"}


def _k(id, text, username="anna_beispiel", zeit="2026-10-24T20:00:00+0000"):
    return {"id": id, "text": text, "username": username, "zeit": zeit}


@pytest.fixture
def km(ablauf, ig):
    ig.medien_liste = [REEL]
    return Kommentare(ablauf, ig)


def _ein(km, ig, *vorhanden):
    """Einschalten und den stillen ersten Lauf mit den vorhandenen Kommentaren machen."""
    ig.kommentar_liste["m1"] = list(vorhanden)
    km.schalter(True)
    km.runde()


def _meldungen(tg):
    return [f for m, f in tg.aufrufe if m == "sendMessage"]


def test_haengt_sich_an_den_ablauf(km, ablauf):
    assert ablauf.kommentare is km


def test_aus_liest_nichts(km, ig, tg):
    km.runde()
    assert ig.aufrufe == [] and _meldungen(tg) == []


def test_erster_lauf_still_dann_neue_melden(km, ig, tg, ablauf):
    _ein(km, ig, _k("k1", "START"), _k("k2", "Super Beitrag", "beat.b"))
    assert _meldungen(tg) == []
    assert ablauf.s.kommentar("k1")["gemeldet"] == "still"
    assert ablauf.s.kommentar("k2")["start"] is False
    assert ("medien_seit", (ablauf.jetzt() - timedelta(days=14),)) in ig.aufrufe
    ig.kommentar_liste["m1"].append(_k("k3", "Start bitte 🙌", "beispiel.konto"))
    km.runde()
    m = _meldungen(tg)
    assert [f["text"] for f in m] == [f"💬 @beispiel.konto hat START kommentiert · Reel ‹{REEL['caption'][:40]}›"]
    assert m[0]["reply_markup"] == {"inline_keyboard": [[{"text": "Profil öffnen",
                                                          "url": "https://instagram.com/beispiel.konto"}]]}
    assert m[0]["disable_notification"] is False
    km.runde()
    assert len(_meldungen(tg)) == 1   # nicht doppelt


def test_erster_lauf_bleibt_still_bis_er_gelingt(km, ig, tg, ablauf):
    ig.kommentar_liste["m1"] = [_k("k1", "START")]
    ig.kommentar_fehler = [InstagramFehler("Instagram nicht erreichbar (URLError)", netz=True)]
    km.schalter(True)
    km.runde()
    assert ablauf.s.kommentar("k1") is None
    km.runde()
    assert ablauf.s.kommentar("k1")["gemeldet"] == "still" and _meldungen(tg) == []


def test_thema_aus_dem_briefkasten(km, ig, tg, ablauf, vier):
    ablauf.s.neuer_post(vier[0]["id"], 1)
    ablauf.s.setze_post(vier[0]["id"], instagram_id="m1")
    _ein(km, ig)
    ig.kommentar_liste["m1"] = [_k("k1", "START")]
    km.runde()
    assert _meldungen(tg)[-1]["text"] == "💬 @anna_beispiel hat START kommentiert · Reel ‹Thema 1›"


def test_karussell_ohne_caption(km, ig, tg):
    ig.medien_liste = [KARUSSELL]
    km.schalter(True)
    km.runde()
    ig.kommentar_liste["m2"] = [_k("k1", "start!")]
    km.runde()
    assert _meldungen(tg)[-1]["text"] == "💬 @anna_beispiel hat START kommentiert · Karussell ‹ohne Caption›"


def test_eigener_account_zaehlt_nicht(km, ig, tg, ablauf):
    _ein(km, ig)
    ig.kommentar_liste["m1"] = [_k("k1", "START", "example.com")]
    km.runde()
    assert ablauf.s.kommentar("k1")["start"] is False and _meldungen(tg) == []


def test_ohne_username_kein_knopf(km, ig, tg):
    _ein(km, ig)
    ig.kommentar_liste["m1"] = [_k("k1", "START", None)]
    km.runde()
    m = _meldungen(tg)[-1]
    assert m["text"].startswith("💬 Jemand hat START kommentiert") and "reply_markup" not in m


def test_instagram_fehler_bricht_nur_die_runde_ab(km, ig, tg, ablauf):
    _ein(km, ig)
    ig.kommentar_liste["m1"] = [_k("k1", "START")]
    ig.kommentar_fehler = [InstagramFehler("Instagram nicht erreichbar (URLError)", netz=True)]
    km.runde()
    assert ablauf.s.kommentar("k1") is None and _meldungen(tg) == []
    assert km.stand()["problem"] == "Instagram nicht erreichbar (URLError)"
    km.runde()
    assert len(_meldungen(tg)) == 1 and km.stand()["problem"] is None


def test_telegram_fehler_meldet_in_der_naechsten_runde(km, ig, tg, ablauf):
    _ein(km, ig)
    ig.kommentar_liste["m1"] = [_k("k1", "START")]
    tg.scheitern_bei = "sendMessage"
    km.runde()
    assert ablauf.s.kommentar("k1")["gemeldet"] is None
    tg.scheitern_bei = None
    km.runde()
    assert len(_meldungen(tg)) == 1 and ablauf.s.kommentar("k1")["gemeldet"] is not None


def test_hoechstens_20_meldungen_pro_runde(km, ig, tg):
    _ein(km, ig)
    ig.kommentar_liste["m1"] = [_k(f"k{i:02d}", "START", f"person{i}") for i in range(25)]
    km.runde()
    assert len(_meldungen(tg)) == MAX_MELDUNGEN
    km.runde()
    assert len(_meldungen(tg)) == 25


@pytest.mark.parametrize("fehler, wo", [
    (InstagramFehler("Instagram HTTP 403: keine Berechtigung", berechtigung=True), "kommentare"),
    (InstagramFehler("Instagram-Schlüssel fehlt", ungueltig=True), "medien_seit"),
])
def test_hinweis_einmal_pro_tag(km, ig, tg, uhr, fehler, wo):
    km.schalter(True)
    if wo == "kommentare":
        ig.kommentar_fehler = [fehler] * 3
    else:
        ig.zahlen_fehler = [fehler] * 3   # FalschesInstagram: zahlen_fehler gilt für medien_seit
    km.runde()
    km.runde()
    assert [f["text"] for f in _meldungen(tg)] == [texte.kommentare_hinweis(str(fehler))]
    uhr.zeit += timedelta(days=1)
    km.runde()
    assert len(_meldungen(tg)) == 2


def test_netzfehler_ohne_hinweis(km, ig, tg):
    km.schalter(True)
    ig.kommentar_fehler = [InstagramFehler("Instagram nicht erreichbar (URLError)", netz=True)]
    km.runde()
    assert _meldungen(tg) == []


def test_schalter_und_stand(km, ablauf):
    with pytest.raises(ValueError):
        km.schalter("ja")
    assert km.stand() == {"an": False, "seit": None, "kommentare": 0, "start": 0, "abgelehnt": 0,
                          "letzte_runde": None, "problem": None}
    stand = km.schalter(True)
    assert stand["an"] is True and stand["seit"] == "2026-10-24T22:30:00+02:00"
    assert ablauf.s.lies("kommentare_still") is True
    km.schalter(False)
    km.schalter(True)
    assert km.stand()["seit"] == "2026-10-24T22:30:00+02:00"
    km.runde()
    assert km.stand()["letzte_runde"] == "2026-10-24T22:30:00+02:00"


def test_wieder_einschalten_meldet_aus_der_pause(km, ig, tg):
    _ein(km, ig)
    km.schalter(False)
    ig.kommentar_liste["m1"] = [_k("k1", "START")]
    km.runde()   # aus: liest nichts
    assert _meldungen(tg) == []
    km.schalter(True)
    km.runde()
    assert len(_meldungen(tg)) == 1


def test_fehler_bei_einem_beitrag_blockiert_nicht_die_anderen(km, ig, tg, ablauf):
    ig.medien_liste = [REEL, KARUSSELL]
    km.schalter(True)
    km.runde()
    ig.kommentar_liste["m2"] = [_k("k1", "START")]
    orig = ig.kommentare

    def kommentare(media_id):
        if media_id == "m1":
            raise InstagramFehler("Instagram HTTP 400: Medium gelöscht")
        return orig(media_id)
    ig.kommentare = kommentare
    km.runde()
    assert len(_meldungen(tg)) == 1 and km.stand()["problem"] is None


def test_netzfehler_bei_einem_beitrag_bricht_die_runde_ab(km, ig, tg, ablauf):
    _ein(km, ig)
    ig.kommentar_liste["m1"] = [_k("k1", "START")]
    ig.kommentar_fehler = [InstagramFehler("Instagram nicht erreichbar (URLError)", netz=True)]
    km.runde()
    assert ablauf.s.kommentar("k1") is None


def test_ausgeschaltet_zwischen_lesen_und_speichern(km, ig, tg, ablauf):
    _ein(km, ig)
    ig.kommentar_liste["m1"] = [_k("k1", "START")]
    orig = ig.kommentare

    def kommentare(media_id):
        km.schalter(False)
        return orig(media_id)
    ig.kommentare = kommentare
    km.runde()
    assert ablauf.s.kommentar("k1") is None and _meldungen(tg) == []


def test_leerer_eigener_name_wird_nicht_gemerkt(km, ig, tg, ablauf):
    _ein(km, ig)
    ig.eigener = None
    km.runde()
    ig.eigener = "example.com"
    ig.kommentar_liste["m1"] = [_k("k1", "START", "example.com")]
    km.runde()
    assert ablauf.s.kommentar("k1")["start"] is False and _meldungen(tg) == []


def test_senden_laeuft_ohne_sperre(km, ig, tg, ablauf):
    _ein(km, ig)
    ig.kommentar_liste["m1"] = [_k("k1", "START")]
    frei = []
    orig = ablauf._sende
    ablauf._sende = lambda *a, **kw: (frei.append(ablauf.sperre.acquire(blocking=False)),
                                      ablauf.sperre.release() if frei[-1] else None, orig(*a, **kw))[2]
    km.runde()
    assert frei == [True]


def test_abgelehnte_meldung_geht_ohne_knopf_nochmals(km, ig, tg, ablauf):
    _ein(km, ig)
    orig = tg.__call__

    def tg2(methode, felder, zeitlimit=30):
        if methode == "sendMessage" and "reply_markup" in felder:
            raise TelegramFehler("Telegram sendMessage: HTTP 400 Bad Request: BUTTON_URL_INVALID")
        return orig(methode, felder, zeitlimit)
    ablauf.tg = tg2
    ig.kommentar_liste["m1"] = [_k("k1", "START")]
    km.runde()
    m = _meldungen(tg)
    assert len(m) == 1 and "reply_markup" not in m[0]
    assert ablauf.s.kommentar("k1")["gemeldet"] not in (None, "abgelehnt")


def test_dauerhaft_abgelehnt_staut_nicht(km, ig, tg, ablauf):
    _ein(km, ig)
    orig = tg.__call__

    def tg2(methode, felder, zeitlimit=30):
        if methode == "sendMessage" and "@boese" in felder["text"]:
            raise TelegramFehler("Telegram sendMessage: HTTP 400 Bad Request")
        return orig(methode, felder, zeitlimit)
    ablauf.tg = tg2
    ig.kommentar_liste["m1"] = [_k("k1", "START", "boese", "2026-10-24T20:00:00+0000"),
                                _k("k2", "START", "nett", "2026-10-24T21:00:00+0000")]
    km.runde()
    assert ablauf.s.kommentar("k1")["gemeldet"] == "abgelehnt" and km.stand()["abgelehnt"] == 1
    assert len(_meldungen(tg)) == 1 and ablauf.s.kommentar("k2")["gemeldet"] not in (None, "abgelehnt")
    km.runde()
    assert len(_meldungen(tg)) == 1


@pytest.mark.parametrize("text", ["Telegram sendMessage: HTTP 429 Too Many Requests", "Telegram sendMessage: HTTP 502 Bad Gateway"])
def test_429_und_5xx_bleiben_fuer_die_naechste_runde(km, ig, tg, ablauf, text):
    _ein(km, ig)
    orig = tg.__call__
    ablauf.tg = lambda m, f, z=30: (_ for _ in ()).throw(TelegramFehler(text)) if m == "sendMessage" else orig(m, f, z)
    ig.kommentar_liste["m1"] = [_k("k1", "START")]
    km.runde()
    assert ablauf.s.kommentar("k1")["gemeldet"] is None


@pytest.mark.parametrize("text", ["Telegram sendMessage: HTTP 403 Forbidden: bot was blocked",
                                  "Telegram sendMessage: HTTP 401 Unauthorized",
                                  "Telegram sendMessage: HTTP 404 Not Found", "Telegram sendMessage: unbekannt"])
def test_403_und_co_markieren_nichts_als_abgelehnt(km, ig, tg, ablauf, text):
    _ein(km, ig)
    orig = tg.__call__
    ablauf.tg = lambda m, f, z=30: (_ for _ in ()).throw(TelegramFehler(text)) if m == "sendMessage" else orig(m, f, z)
    ig.kommentar_liste["m1"] = [_k(f"k{i}", "START", f"p{i}") for i in range(3)]
    km.runde()
    assert [ablauf.s.kommentar(f"k{i}")["gemeldet"] for i in range(3)] == [None] * 3
    assert km.stand()["abgelehnt"] == 0
