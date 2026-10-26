import pytest

from briefkasten.speicher import POST_STATUS, Speicher


def _b(**ueber):
    b = {"id": "2026-KW44-reel-x", "woche": "2026-KW44", "version": 1, "titel": "Titel X", "format": "reel",
         "termin": "2026-10-27T19:00", "status": "offen", "neubauten": 0, "nachricht_id": None}
    b.update(ueber)
    return b


def test_beitrag_speichern_lesen_und_ersetzen():
    s = Speicher(":memory:")
    erst = s.speichere_beitrag(_b())
    assert erst["nr"] == 1 and erst["titel"] == "Titel X" and erst["nachricht_id"] is None
    zweit = s.speichere_beitrag(_b(version=2, nachricht_id=7))
    assert zweit["nr"] == 1 and zweit["version"] == 2 and zweit["nachricht_id"] == 7
    assert s.beitrag_nr(1) == zweit
    assert s.beitrag("fehlt") is None and s.beitrag_nr(99) is None


def test_beitraege_nach_termin_und_woche():
    s = Speicher(":memory:")
    s.speichere_beitrag(_b(id="b", termin="2026-10-29T19:00"))
    s.speichere_beitrag(_b(id="a", termin="2026-10-27T19:00"))
    s.speichere_beitrag(_b(id="c", woche="2026-KW45", termin="2026-11-03T19:00"))
    assert [b["id"] for b in s.beitraege()] == ["a", "b", "c"]
    assert [b["id"] for b in s.beitraege("2026-KW44")] == ["a", "b"]


def test_setze_prueft_felder_und_status():
    s = Speicher(":memory:")
    s.speichere_beitrag(_b())
    assert s.setze("2026-KW44-reel-x", status="freigegeben")["status"] == "freigegeben"
    with pytest.raises(ValueError):
        s.setze("2026-KW44-reel-x", farbe="rot")
    with pytest.raises(ValueError):
        s.setze("2026-KW44-reel-x", status="weg")
    with pytest.raises(ValueError):
        s.speichere_beitrag(_b(status="weg"))


def test_ereignisse_nach_nummer_und_art():
    s = Speicher(":memory:")
    s.ereignis("2026-10-25T09:00:00+01:00", "freigegeben", beitrag="x", woche="2026-KW44", version=1)
    s.ereignis("2026-10-25T09:01:00+01:00", "nachricht", nachricht={"update_id": 5, "message": {"text": "Hä?"}})
    s.ereignis("2026-10-25T09:02:00+01:00", "aendern", beitrag="x", woche="2026-KW44", version=1, notiz="kürzer")
    entscheide = s.ereignisse(0, ["freigegeben", "aendern"])
    assert [(e["nr"], e["art"]) for e in entscheide] == [(1, "freigegeben"), (3, "aendern")]
    assert entscheide[1]["notiz"] == "kürzer" and entscheide[0]["nachricht"] is None
    assert s.ereignisse(1, ["freigegeben", "aendern"])[0]["nr"] == 3
    assert s.ereignisse(0, ["nachricht"])[0]["nachricht"] == {"update_id": 5, "message": {"text": "Hä?"}}


def test_stand_mit_vorgabe_und_datei_bleibt(tmp_path):
    pfad = tmp_path / "daten" / "briefkasten.db"
    s = Speicher(pfad)
    assert s.lies("update_id") is None and s.lies("liste", []) == []
    s.schreibe("update_id", 41)
    s.schreibe("liste", [{"a": 1}])
    s.speichere_beitrag(_b())
    neu = Speicher(pfad)
    assert neu.lies("update_id") == 41 and neu.lies("liste") == [{"a": 1}]
    assert neu.beitrag("2026-KW44-reel-x")["titel"] == "Titel X"


def test_platzhalter_vorgabe_false_und_als_bool():
    s = Speicher(":memory:")
    ohne = s.speichere_beitrag(_b())
    assert ohne["platzhalter"] is False
    mit = s.speichere_beitrag(_b(version=2, platzhalter=True))
    assert mit["platzhalter"] is True and s.beitrag_nr(1)["platzhalter"] is True
    assert s.beitraege()[0]["platzhalter"] is True
    assert s.setze("2026-KW44-reel-x", platzhalter=False)["platzhalter"] is False


def test_alte_datenbank_ohne_spalte_wird_migriert(tmp_path):
    import sqlite3
    pfad = tmp_path / "alt.db"
    db = sqlite3.connect(str(pfad))
    db.executescript("""
CREATE TABLE beitraege (
  nr INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL, woche TEXT NOT NULL, version INTEGER NOT NULL,
  titel TEXT NOT NULL, format TEXT NOT NULL, termin TEXT NOT NULL, status TEXT NOT NULL,
  neubauten INTEGER NOT NULL, nachricht_id INTEGER);
INSERT INTO beitraege (id, woche, version, titel, format, termin, status, neubauten, nachricht_id)
  VALUES ('2026-KW44-reel-x', '2026-KW44', 1, 'Titel X', 'reel', '2026-10-27T19:00', 'offen', 0, 501);
""")
    db.commit()
    db.close()
    s = Speicher(pfad)
    alt = s.beitrag("2026-KW44-reel-x")
    assert alt["platzhalter"] is False and alt["nachricht_id"] == 501 and alt["nr"] == 1
    assert s.setze(alt["id"], platzhalter=True)["platzhalter"] is True
    s.db.close()
    assert Speicher(pfad).beitrag("2026-KW44-reel-x")["platzhalter"] is True   # zweiter Start: nichts doppelt



def _beitrag(s, id="2026-KW44-reel-x", version=1, status="freigegeben"):
    return s.speichere_beitrag({"id": id, "woche": "2026-KW44", "version": version, "titel": "X",
                                "format": "reel", "termin": "2026-10-27T19:00", "status": status,
                                "neubauten": 0, "nachricht_id": 501, "platzhalter": False})


def test_neue_status_gepostet_und_ausgelassen():
    s = Speicher(":memory:")
    _beitrag(s)
    assert s.setze("2026-KW44-reel-x", status="gepostet")["status"] == "gepostet"
    assert s.setze("2026-KW44-reel-x", status="ausgelassen")["status"] == "ausgelassen"


def test_post_neu_setzen_lesen():
    s = Speicher(":memory:")
    _beitrag(s)
    assert s.post("2026-KW44-reel-x") is None
    p = s.neuer_post("2026-KW44-reel-x", 1)
    assert p["post_status"] == "geplant" and p["medien"] is None and p["versuche"] == 0
    assert p["manuell"] is False
    p = s.setze_post("2026-KW44-reel-x", medien=["https://example.com/a.mp4"], cover="https://example.com/c.jpg",
                     caption="Text", manuell=True)
    assert p["medien"] == ["https://example.com/a.mp4"] and p["manuell"] is True
    assert [x["id"] for x in s.posts()] == ["2026-KW44-reel-x"]


def test_neuer_post_setzt_alles_zurueck():
    s = Speicher(":memory:")
    _beitrag(s)
    s.neuer_post("2026-KW44-reel-x", 1)
    s.setze_post("2026-KW44-reel-x", medien=["u"], versuche=3, vorwarnung_id=9)
    p = s.neuer_post("2026-KW44-reel-x", 2)
    assert (p["version"], p["medien"], p["versuche"], p["vorwarnung_id"]) == (2, None, 0, None)


def test_setze_post_prueft_felder_und_status():
    s = Speicher(":memory:")
    _beitrag(s)
    s.neuer_post("2026-KW44-reel-x", 1)
    with pytest.raises(ValueError):
        s.setze_post("2026-KW44-reel-x", unbekannt=1)
    with pytest.raises(ValueError):
        s.setze_post("2026-KW44-reel-x", post_status="komisch")
    assert "unklar" in POST_STATUS


def test_letzte_freigabe():
    s = Speicher(":memory:")
    _beitrag(s)
    s.ereignis("2026-10-25T09:00:00+01:00", "freigegeben", beitrag="2026-KW44-reel-x", woche="2026-KW44", version=1)
    s.ereignis("2026-10-25T10:00:00+01:00", "zurueckgenommen", beitrag="2026-KW44-reel-x", woche="2026-KW44", version=1)
    s.ereignis("2026-10-27T18:30:00+01:00", "freigegeben", beitrag="2026-KW44-reel-x", woche="2026-KW44", version=1)
    s.ereignis("2026-10-26T09:00:00+01:00", "freigegeben", beitrag="2026-KW44-reel-x", woche="2026-KW44", version=2)
    assert s.letzte_freigabe("2026-KW44-reel-x", 1) == "2026-10-27T18:30:00+01:00"
    assert s.letzte_freigabe("2026-KW44-reel-y", 1) is None


def test_alte_datenbank_bekommt_posts(tmp_path):
    import sqlite3
    pfad = tmp_path / "alt.db"
    db = sqlite3.connect(pfad)
    db.executescript("CREATE TABLE beitraege (nr INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL, "
                     "woche TEXT NOT NULL, version INTEGER NOT NULL, titel TEXT NOT NULL, format TEXT NOT NULL, "
                     "termin TEXT NOT NULL, status TEXT NOT NULL, neubauten INTEGER NOT NULL, nachricht_id INTEGER, "
                     "platzhalter INTEGER NOT NULL DEFAULT 0);")
    db.close()
    s = Speicher(pfad)
    _beitrag(s)
    assert s.neuer_post("2026-KW44-reel-x", 1)["post_status"] == "geplant"


ALTE_POSTS = """
CREATE TABLE posts (
  id TEXT PRIMARY KEY, version INTEGER NOT NULL, medien TEXT, cover TEXT, caption TEXT,
  post_status TEXT NOT NULL, manuell INTEGER NOT NULL DEFAULT 0, versuche INTEGER NOT NULL DEFAULT 0,
  naechster_versuch TEXT, grund TEXT, creation_id TEXT, instagram_id TEXT, permalink TEXT, gepostet TEXT,
  vorwarnung_id INTEGER, meldung_id INTEGER, meldung_offen TEXT, manuell_bis TEXT,
  nochmals INTEGER NOT NULL DEFAULT 0);
INSERT INTO posts (id, version, post_status) VALUES ('alt', 1, 'gepostet');
"""


def test_facebook_spalten_migration(tmp_path):
    import sqlite3

    from briefkasten.speicher import Speicher
    pfad = tmp_path / "alt.db"
    db = sqlite3.connect(pfad)
    db.executescript(ALTE_POSTS)
    db.close()
    s = Speicher(pfad)
    p = s.post("alt")
    assert (p["fb_status"], p["fb_id"], p["fb_link"], p["fb_versuche"], p["fb_naechster"], p["fb_grund"],
            p["fb_meldung_id"], p["fb_beendet"], p["gepostet_id"]) == (None, None, None, 0, None, None, None, False, None)
    Speicher(pfad)   # zweites Öffnen migriert nicht nochmals


def test_facebook_felder_setzen():
    from briefkasten.speicher import Speicher
    s = Speicher(":memory:")
    s.neuer_post("x", 1)
    p = s.setze_post("x", fb_status="offen", fb_beendet=True, gepostet_id=7, fb_versuche=2)
    assert (p["fb_status"], p["fb_beendet"], p["gepostet_id"], p["fb_versuche"]) == ("offen", True, 7, 2)
    with pytest.raises(ValueError):
        s.setze_post("x", fb_status="unbekannt")


def _kommentar(id, media_id="m1", text="START", start=True, gemeldet=None, zeit="2026-10-27T18:10:00+0000"):
    return {"id": id, "media_id": media_id, "username": "anna_beispiel", "text": text, "zeit": zeit, "start": start,
            "gemeldet": gemeldet}


def test_kommentare_einmal_speichern_und_melden():
    s = Speicher(":memory:")
    assert s.neuer_kommentar(_kommentar("k1")) is True
    assert s.neuer_kommentar(_kommentar("k1", text="geändert")) is False   # bleibt, wie er war
    assert s.kommentar("k1")["text"] == "START" and s.kommentar("k1")["start"] is True
    s.neuer_kommentar({"id": "k2", "media_id": "m1", "username": "b", "text": "x" * 2000, "zeit": None,
                       "start": False})
    s.neuer_kommentar(_kommentar("k3", media_id="m2", text="start", gemeldet="still"))
    assert len(s.kommentar("k2")["text"]) == 1000 and s.kommentar("k2")["gemeldet"] is None
    assert [k["id"] for k in s.zu_melden()] == ["k1"]
    s.setze_gemeldet("k1", "2026-10-27T20:15:00+01:00")
    assert s.zu_melden() == [] and s.kommentar("k1")["gemeldet"] == "2026-10-27T20:15:00+01:00"
    assert s.start_anzahl() == {"m1": 1, "m2": 1}
    assert s.kommentar_zahlen() == {"kommentare": 3, "start": 2}
    assert s.kommentar("fehlt") is None


def test_zu_melden_nach_zeit():
    s = Speicher(":memory:")
    s.neuer_kommentar(_kommentar("b", zeit="2026-10-27T19:00:00+0000"))
    s.neuer_kommentar(_kommentar("a", zeit="2026-10-27T18:00:00+0000"))
    assert [k["id"] for k in s.zu_melden()] == ["a", "b"]


def test_kommentare_in_alter_datenbank(tmp_path):
    import sqlite3
    pfad = tmp_path / "briefkasten.db"
    alt = sqlite3.connect(pfad)
    alt.execute("CREATE TABLE stand (schluessel TEXT PRIMARY KEY, wert TEXT NOT NULL)")
    alt.execute("INSERT INTO stand VALUES ('poster_an', 'true')")
    alt.commit()
    alt.close()
    s = Speicher(pfad)
    assert s.lies("poster_an") is True
    assert s.kommentar_zahlen() == {"kommentare": 0, "start": 0}


def test_post_mit_instagram():
    s = Speicher(":memory:")
    s.neuer_post("2026-KW44-reel-x", 1)
    s.setze_post("2026-KW44-reel-x", instagram_id="m1")
    assert s.post_mit_instagram("m1")["id"] == "2026-KW44-reel-x"
    assert s.post_mit_instagram("m9") is None
