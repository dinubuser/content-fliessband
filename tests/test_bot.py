import io
import json
import subprocess
import urllib.error
import urllib.parse
from pathlib import Path

import pytest

from lib import bot
from lib.bot import Bot, BotFehler, multipart, telegram_anfrage, verkleinere
from lib.manifest import schreibe_json


def _bot(tmp_path, telegram, chat=42, letzte=5):
    stand = tmp_path / "daten" / "bot.json"
    schreibe_json(stand, {"chat_id": chat, "letzte_update_id": letzte})
    return Bot(stand, anfrage=telegram)


def test_sende_text_leise(tmp_path, telegram):
    assert _bot(tmp_path, telegram).sende_text("Hallo") == 101
    assert telegram.aufrufe == [("sendMessage", {"chat_id": 42, "text": "Hallo", "disable_notification": True}, {})]


def test_langer_text_wird_an_zeilen_geteilt(tmp_path, telegram):
    text = "\n".join(["x" * 99] * 90)
    _bot(tmp_path, telegram).sende_text(text)
    teile = telegram.texte()
    assert len(teile) == 3 and all(len(t) <= 4000 for t in teile)
    assert "\n".join(teile) == text


def test_nicht_eingerichtet(tmp_path, telegram):
    with pytest.raises(BotFehler, match="bot einrichten"):
        Bot(tmp_path / "fehlt.json", anfrage=telegram).sende_text("x")


def test_video(tmp_path, telegram):
    mp4 = tmp_path / "reel.mp4"
    mp4.write_bytes(b"mp4")
    _bot(tmp_path, telegram).sende_video(mp4)
    assert telegram.aufrufe == [("sendVideo", {"chat_id": 42, "disable_notification": True,
                                               "supports_streaming": True}, {"video": mp4})]


@pytest.mark.parametrize("anzahl, erwartet", [
    (10, ["sendMediaGroup"]),
    (12, ["sendMediaGroup", "sendMediaGroup"]),
    (11, ["sendMediaGroup", "sendPhoto"]),
])
def test_album_in_zehnergruppen(tmp_path, telegram, anzahl, erwartet):
    bilder = []
    for i in range(anzahl):
        p = tmp_path / f"slide-{i + 1:02d}.png"
        p.write_bytes(b"png")
        bilder.append(p)
    _bot(tmp_path, telegram).sende_album(bilder)
    assert telegram.methoden() == erwartet
    _, felder, dateien = telegram.aufrufe[0]
    assert felder["media"][0] == {"type": "photo", "media": "attach://bild0"}
    assert len(felder["media"]) == 10 and dateien["bild9"] == bilder[9]
    assert felder["disable_notification"] is True


def test_einrichten_speichert_chat(tmp_path, telegram):
    telegram.updates = [
        {"update_id": 4, "message": {"message_id": 1, "chat": {"id": 7, "type": "group"}, "text": "/start"}},
        {"update_id": 5, "message": {"message_id": 2, "chat": {"id": 42, "type": "private"}, "text": "/start"}}]
    stand = tmp_path / "daten" / "bot.json"
    assert Bot(stand, anfrage=telegram).einrichten() == 42
    assert json.loads(stand.read_text(encoding="utf-8")) == {"chat_id": 42, "letzte_update_id": 5}
    methode, felder, _ = telegram.aufrufe[-1]
    assert methode == "sendMessage" and felder["chat_id"] == 42


def test_einrichten_ohne_start(tmp_path, telegram):
    with pytest.raises(BotFehler, match="/start"):
        Bot(tmp_path / "bot.json", anfrage=telegram).einrichten()


def test_neue_nachrichten_nur_aus_dem_eigenen_chat(tmp_path, telegram):
    telegram.updates = [
        {"update_id": 5, "message": {"message_id": 9, "chat": {"id": 42}, "text": "alt"}},
        {"update_id": 6, "message": {"message_id": 10, "chat": {"id": 42}, "text": "Antwort"}},
        {"update_id": 7, "message": {"message_id": 11, "chat": {"id": 99}, "text": "fremd"}},
        {"update_id": 8, "message": {"message_id": 12, "chat": {"id": 42}, "photo": []}},
        {"update_id": 9, "edited_message": {"message_id": 10, "chat": {"id": 42}, "text": "geändert"}}]
    b = _bot(tmp_path, telegram)
    nachrichten, hoechste = b.neue_nachrichten()
    assert [n["text"] for n in nachrichten] == ["Antwort"]
    assert hoechste == 9
    assert telegram.aufrufe[0][1]["offset"] == 6
    b.bestaetige(hoechste)
    assert json.loads((tmp_path / "daten" / "bot.json").read_text(encoding="utf-8")) == {
        "chat_id": 42, "letzte_update_id": 9}


def test_multipart(tmp_path):
    mp4 = tmp_path / "reel.mp4"
    mp4.write_bytes(b"\x00\x01video")
    body, typ = multipart({"chat_id": "42"}, {"video": mp4})
    grenze = typ.split("boundary=")[1]
    assert typ.startswith("multipart/form-data; boundary=")
    assert b'name="chat_id"\r\n\r\n42\r\n' in body
    assert b'name="video"; filename="reel.mp4"\r\nContent-Type: video/mp4\r\n\r\n\x00\x01video\r\n' in body
    assert body.endswith(f"--{grenze}--\r\n".encode())


def test_anfrage_zeigt_token_nie(monkeypatch):
    monkeypatch.setattr(bot, "_token", lambda: "123456:GEHEIM")

    def urlopen(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", None,
                                     io.BytesIO(b'{"ok": false, "description": "Unauthorized"}'))
    monkeypatch.setattr(bot.urllib.request, "urlopen", urlopen)
    with pytest.raises(BotFehler) as info:
        telegram_anfrage("sendMessage", {"chat_id": 42, "text": "x"})
    assert "GEHEIM" not in str(info.value)
    assert "401" in str(info.value)


def test_anfrage_ohne_netz(monkeypatch):
    monkeypatch.setattr(bot, "_token", lambda: "123456:GEHEIM")

    def urlopen(req, timeout):
        raise urllib.error.URLError("nodename nor servname provided")
    monkeypatch.setattr(bot.urllib.request, "urlopen", urlopen)
    with pytest.raises(BotFehler, match="nicht erreichbar"):
        telegram_anfrage("getUpdates", {"offset": 1})


def test_anfrage_wandelt_felder(monkeypatch):
    monkeypatch.setattr(bot, "_token", lambda: "123456:GEHEIM")
    gesendet = {}

    def urlopen(req, timeout):
        gesendet["daten"] = req.data
        return io.BytesIO(json.dumps({"ok": True, "result": {"message_id": 7}}).encode())
    monkeypatch.setattr(bot.urllib.request, "urlopen", urlopen)
    antwort = telegram_anfrage("sendMessage", {"chat_id": 42, "text": "Grüezi", "disable_notification": True,
                                               "leer": None})
    assert antwort == {"message_id": 7}
    assert urllib.parse.parse_qs(gesendet["daten"].decode()) == {
        "chat_id": ["42"], "text": ["Grüezi"], "disable_notification": ["true"]}


def _ffmpeg(groessen):
    aufrufe = []

    def f(befehl, **kw):
        aufrufe.append(befehl)
        Path(befehl[-1]).write_bytes(b"x" * groessen[len(aufrufe) - 1])
        return subprocess.CompletedProcess(befehl, 0, "", "")
    f.aufrufe = aufrufe
    return f


def test_verkleinere_laesst_original_stehen(tmp_path):
    quelle = tmp_path / "reel.mp4"
    quelle.write_bytes(b"x" * 100)
    f = _ffmpeg([10])
    ziel = verkleinere(quelle, tmp_path / "versand" / "klein.mp4", ausfuehren=f, grenze=50)
    assert ziel.stat().st_size == 10 and quelle.stat().st_size == 100
    assert f.aufrufe[0][f.aufrufe[0].index("-crf") + 1] == "28"
    assert str(quelle) in f.aufrufe[0]


def test_verkleinere_zu_gross(tmp_path):
    quelle = tmp_path / "reel.mp4"
    quelle.write_bytes(b"x" * 100)
    f = _ffmpeg([80, 60])
    with pytest.raises(BotFehler, match="verkleinert über"):
        verkleinere(quelle, tmp_path / "klein.mp4", ausfuehren=f, grenze=50)
    assert len(f.aufrufe) == 2


# --- Lokaler Eingang: Telegram löscht unbestätigte Updates nach 24 h ---

def _nachricht(update_id, text, chat=42):
    return {"update_id": update_id, "message": {"message_id": 100 + update_id, "chat": {"id": chat}, "text": text}}


def test_nachrichten_bleiben_lokal_nach_bestaetigung_bei_telegram(tmp_path, telegram):
    telegram.updates = [_nachricht(6, "Antwort"), _nachricht(7, "fremd", chat=99)]
    assert _bot(tmp_path, telegram).sammle() == 1
    assert telegram.aufrufe[1][0] == "getUpdates" and telegram.aufrufe[1][1]["offset"] == 8
    telegram.updates = []                      # Telegram hat bestätigte Updates gelöscht
    b = _bot_ohne_neu(tmp_path, telegram)      # neuer Prozess, gleicher Stand
    nachrichten, hoechste = b.neue_nachrichten()
    assert [n["text"] for n in nachrichten] == ["Antwort"] and hoechste == 7
    assert telegram.aufrufe[2][1]["offset"] == 8


def _bot_ohne_neu(tmp_path, telegram):
    return Bot(tmp_path / "daten" / "bot.json", anfrage=telegram)


def test_absturz_vor_bestaetigung_liefert_nachrichten_nochmals(tmp_path, telegram):
    telegram.updates = [_nachricht(6, "eins"), _nachricht(7, "zwei")]
    b = _bot(tmp_path, telegram)
    erste, _ = b.neue_nachrichten()
    zweite, hoechste = _bot_ohne_neu(tmp_path, telegram).neue_nachrichten()
    assert [n["text"] for n in erste] == [n["text"] for n in zweite] == ["eins", "zwei"]
    assert hoechste == 7


def test_bestaetige_entfernt_nur_gelesene(tmp_path, telegram):
    telegram.updates = [_nachricht(6, "eins")]
    b = _bot(tmp_path, telegram)
    nachrichten, hoechste = b.neue_nachrichten()
    telegram.updates.append(_nachricht(8, "später"))
    assert b.sammle() == 1                     # kommt zwischen Lesen und Bestätigen dazu
    b.bestaetige(hoechste)
    nachrichten, hoechste = b.neue_nachrichten()
    assert [n["text"] for n in nachrichten] == ["später"] and hoechste == 8
    b.bestaetige(hoechste)
    assert b.neue_nachrichten() == ([], None)
    eingang = json.loads((tmp_path / "daten" / "bot-eingang.json").read_text(encoding="utf-8"))
    assert eingang == {"nachrichten": []}


def test_sammle_doppelt_gespeichert_nie(tmp_path, telegram):
    telegram.updates = [_nachricht(6, "eins")]
    b = _bot(tmp_path, telegram)
    assert b.sammle() == 1
    schreibe_json(tmp_path / "daten" / "bot.json", {"chat_id": 42, "letzte_update_id": 5})  # Absturz vor dem Stand
    assert b.sammle() == 0
    assert [n["text"] for n in b.neue_nachrichten()[0]] == ["eins"]


def test_eingang_kaputt(tmp_path, telegram):
    b = _bot(tmp_path, telegram)
    (tmp_path / "daten" / "bot-eingang.json").write_text("{kaputt", encoding="utf-8")
    with pytest.raises(BotFehler, match="kaputt"):
        b.neue_nachrichten()


# --- Kleinere Fehlerfälle ---

def test_anfrage_http_exception(monkeypatch):
    import http.client
    monkeypatch.setattr(bot, "_token", lambda: "123456:GEHEIM")

    def urlopen(req, timeout):
        raise http.client.IncompleteRead(b"123456:GEHEIM")
    monkeypatch.setattr(bot.urllib.request, "urlopen", urlopen)
    with pytest.raises(BotFehler, match="nicht erreichbar") as info:
        telegram_anfrage("getUpdates", {"offset": 1})
    assert "GEHEIM" not in str(info.value)


def _zu_viele(retry_after):
    def fehler(req):
        body = {"ok": False, "description": "Too Many Requests"}
        if retry_after is not None:
            body["parameters"] = {"retry_after": retry_after}
        return urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", None,
                                      io.BytesIO(json.dumps(body).encode()))
    return fehler


@pytest.mark.parametrize("retry_after, gewartet", [(3, 3), (120, 30)])
def test_anfrage_429_wartet_einmal(monkeypatch, retry_after, gewartet):
    monkeypatch.setattr(bot, "_token", lambda: "123456:GEHEIM")
    versuche, schlaf = [], []

    def urlopen(req, timeout):
        versuche.append(req)
        if len(versuche) == 1:
            raise _zu_viele(retry_after)(req)
        return io.BytesIO(json.dumps({"ok": True, "result": {"message_id": 7}}).encode())
    monkeypatch.setattr(bot.urllib.request, "urlopen", urlopen)
    assert telegram_anfrage("sendMessage", {"chat_id": 42, "text": "x"}, warte=schlaf.append) == {"message_id": 7}
    assert len(versuche) == 2 and schlaf == [gewartet]


def test_anfrage_429_zweimal_scheitert(monkeypatch):
    monkeypatch.setattr(bot, "_token", lambda: "123456:GEHEIM")
    schlaf = []

    def urlopen(req, timeout):
        raise _zu_viele(None)(req)
    monkeypatch.setattr(bot.urllib.request, "urlopen", urlopen)
    with pytest.raises(BotFehler, match="429") as info:
        telegram_anfrage("sendMessage", {"chat_id": 42, "text": "x"}, warte=schlaf.append)
    assert len(schlaf) == 1 and "GEHEIM" not in str(info.value)


def test_teile_ohne_leere_teile():
    text = "x" * 3999 + "\n" + " " * 10 + "\n" + "y" * 50
    teile = bot._teile(text)
    assert teile and all(t.strip() for t in teile)
    assert len(bot._teile("a\n" + "\n" * 5000)) == 1


@pytest.mark.parametrize("text", ["", "   \n  "])
def test_sende_leeren_text(tmp_path, telegram, text):
    with pytest.raises(BotFehler, match="leer"):
        _bot(tmp_path, telegram).sende_text(text)
    assert telegram.aufrufe == []


def test_verkleinere_zeitlimit_und_stderr(tmp_path):
    quelle = tmp_path / "reel.mp4"
    quelle.write_bytes(b"x")
    gesehen = {}

    def f(befehl, **kw):
        gesehen.update(kw)
        return subprocess.CompletedProcess(befehl, 1, "", "erste Zeile\nInvalid data found " + "z" * 300 + "\n")
    with pytest.raises(BotFehler) as info:
        verkleinere(quelle, tmp_path / "klein.mp4", ausfuehren=f)
    assert gesehen["timeout"] == 600
    meldung = str(info.value)
    assert "Invalid data found" in meldung and "erste Zeile" not in meldung and len(meldung) < 300


@pytest.mark.parametrize("fehler, text", [
    (FileNotFoundError("ffmpeg"), "nicht gefunden"),
    (subprocess.TimeoutExpired(["ffmpeg"], 600), "Zeitlimit"),
])
def test_verkleinere_ffmpeg_fehlt_oder_haengt(tmp_path, fehler, text):
    quelle = tmp_path / "reel.mp4"
    quelle.write_bytes(b"x")

    def f(befehl, **kw):
        raise fehler
    with pytest.raises(BotFehler, match=text):
        verkleinere(quelle, tmp_path / "klein.mp4", ausfuehren=f)


from lib.bot import ordne_zu

FRAGEN = [{"nr": 1, "index": 1, "nachricht": 501}, {"nr": 3, "index": 2, "nachricht": 502}]


def _m(mid, text, antwort_auf=None):
    m = {"message_id": mid, "chat": {"id": 42}, "text": text}
    if antwort_auf:
        m["reply_to_message"] = {"message_id": antwort_auf}
    return m


def test_zuordnung_per_antworten():
    assert ordne_zu([_m(510, "Glücksspiel!", 502), _m(511, "Und: zu riskant", 502)], FRAGEN) == (
        {3: ["Glücksspiel!", "Und: zu riskant"]}, 0)


def test_zuordnung_per_nummer():
    # «1 Nur so» hat kein Trennzeichen: keine Nummer, sondern Fortsetzung von Frage 2 (Themen-Nr 3), ungekürzt
    assert ordne_zu([_m(510, "1: Das sagt der Kollege"), _m(511, "2) Feierabend"), _m(512, "1 Nur so")], FRAGEN) == (
        {1: ["Das sagt der Kollege"], 3: ["Feierabend", "1 Nur so"]}, 0)


def test_zuordnung_fortsetzung_nach_nummer():
    assert ordne_zu([_m(510, "1: erste"), _m(511, "das ist die zweite Antwort")], FRAGEN) == (
        {1: ["erste", "das ist die zweite Antwort"]}, 0)


def test_zuordnung_eine_offene_frage_vor_jeder_zuordnung():
    assert ordne_zu([_m(510, "das sagt der Kollege"), _m(511, "2: Feierabend")], FRAGEN) == (
        {1: ["das sagt der Kollege"], 3: ["Feierabend"]}, 0)


def test_zuordnung_nur_eine_frage_gesendet():
    assert ordne_zu([_m(510, "a", 501), _m(511, "b")], FRAGEN[:1]) == ({1: ["a", "b"]}, 0)


def test_nicht_zuordenbar():
    assert ordne_zu([_m(510, "hallo")], FRAGEN) == ({}, 1)


def test_befehle_zaehlen_nicht():
    assert ordne_zu([_m(510, "/start")], FRAGEN) == ({}, 0)


def test_reihenfolge_nach_nachricht():
    assert ordne_zu([_m(512, "später", 501), _m(511, "früher", 501)], FRAGEN) == ({1: ["früher", "später"]}, 0)


def test_zahl_ohne_trennzeichen_als_fortsetzung_ungekuerzt():
    text = "2 Kinder hatte ich damals, das war hart"
    assert ordne_zu([_m(510, "1: a"), _m(511, text)], FRAGEN) == ({1: ["a", text]}, 0)


def test_zahl_ohne_trennzeichen_als_erste_nachricht_nicht_zugeordnet():
    assert ordne_zu([_m(510, "2 Kinder hatte ich damals, das war hart")], FRAGEN) == ({}, 1)


def test_nur_nummer_setzt_frage_fuer_folgende_nachrichten():
    assert ordne_zu([_m(510, "1:"), _m(511, "Kollege sagt Zocker")], FRAGEN) == ({1: ["Kollege sagt Zocker"]}, 0)
    assert ordne_zu([_m(510, "Frage 2:"), _m(511, "Feierabend")], FRAGEN) == ({3: ["Feierabend"]}, 0)


def test_fortsetzung_nach_antworten_auf_frage():
    assert ordne_zu([_m(510, "Kollege sagt Zocker", 501), _m(511, "und der Chef meint, das sei Glück")], FRAGEN) == (
        {1: ["Kollege sagt Zocker", "und der Chef meint, das sei Glück"]}, 0)


def test_antworten_auf_eigene_antwort_folgt_deren_frage():
    nachrichten = [_m(510, "1: Kollege"), _m(511, "2: Feierabend"), _m(512, "noch dazu: der Chef", 510)]
    assert ordne_zu(nachrichten, FRAGEN) == ({1: ["Kollege", "noch dazu: der Chef"], 3: ["Feierabend"]}, 0)


def test_antworten_auf_frage_schlaegt_nummer():
    assert ordne_zu([_m(510, "2: eigentlich zur ersten", 501)], FRAGEN) == ({1: ["2: eigentlich zur ersten"]}, 0)


def test_nummer_mit_punkt():
    assert ordne_zu([_m(510, "1. Kollege sagt Zocker"), _m(511, "2. Feierabend")], FRAGEN) == (
        {1: ["Kollege sagt Zocker"], 3: ["Feierabend"]}, 0)


def test_nummer_mit_wort_frage_und_zahlwort():
    assert ordne_zu([_m(510, "Frage 1: x"), _m(511, "Zwei) y")], FRAGEN) == ({1: ["x"], 3: ["y"]}, 0)
    assert ordne_zu([_m(510, "Eins: x")], FRAGEN) == ({1: ["x"]}, 0)
    assert ordne_zu([_m(510, "frage 2) y")], FRAGEN) == ({3: ["y"]}, 0)


def test_dezimalzahl_und_datum_sind_keine_nummer():
    for text in ("1.5 Mio sind viel", "2.10. war der Termin", "1:30 Uhr war es"):
        assert ordne_zu([_m(510, "2: a"), _m(511, text)], FRAGEN) == ({3: ["a", text]}, 0), text


def test_unbekannte_nummer_wird_nicht_abgeschnitten():
    assert ordne_zu([_m(510, "1: a"), _m(511, "5: Punkte hat er")], FRAGEN) == ({1: ["a", "5: Punkte hat er"]}, 0)


def test_nur_emoji_wird_ignoriert():
    assert ordne_zu([_m(510, "👍")], FRAGEN) == ({}, 0)
    assert ordne_zu([_m(510, "1: a"), _m(511, "👍 🙏"), _m(512, "b")], FRAGEN) == ({1: ["a", "b"]}, 0)


def test_aeltere_nachrichten_werden_ignoriert():
    assert ordne_zu([_m(500, "alte Nachricht"), _m(501, "gleiche ID wie Frage"), _m(510, "1: a")], FRAGEN) == (
        {1: ["a"]}, 0)
