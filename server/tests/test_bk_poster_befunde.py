"""Befunde aus der Prüfung des Posters (Etappe 5): Container-Stand gegen Doppelposts, vorgemerkte Meldungen,
Schlüssel stündlich, Frist für Jetzt posten, neue Version während Post, Startdatum, Stopp, kleine Punkte."""
from datetime import datetime, timedelta

import pytest
from hilfen_bk import MEDIEN, daten, knopf

from briefkasten import texte
from briefkasten.ablauf import ZONE
from briefkasten.instagram import InstagramFehler
from briefkasten.poster import Poster


def _um(uhr, tag, stunde, minute=0):
    uhr.zeit = datetime(2026, 10, tag, stunde, minute, tzinfo=ZONE)


def _b(ablauf, frei, i=0):
    return ablauf.s.beitrag(frei[i]["id"])


def _gesendet(tg):
    return [f for m, f in tg.aufrufe if m == "sendMessage"]


def _knoepfe(f):
    return [k["text"] for k in f["reply_markup"]["inline_keyboard"][0]]


# --- 1. Doppelpost-Schutz über den Container ---

def _veroeffentlichen_scheitert(poster, ig, uhr):
    """Container c1 angelegt, Veröffentlichen scheitert (Antwort verloren)."""
    ig.veroeffentlichen_fehler = [InstagramFehler("Instagram nicht erreichbar (TimeoutError)")]
    _um(uhr, 27, 19, 0)
    poster.takt()


def test_container_published_gilt_als_gepostet_ohne_link(poster, frei, ablauf, ig, tg, uhr):
    _veroeffentlichen_scheitert(poster, ig, uhr)
    assert ablauf.s.post(frei[0]["id"])["creation_id"] == "c1"
    ig.status["c1"] = "PUBLISHED"
    _um(uhr, 27, 19, 2)
    poster.takt()
    p = ablauf.s.post(frei[0]["id"])
    assert (p["post_status"], p["instagram_id"], p["permalink"]) == ("gepostet", None, None)
    assert ig.methoden().count("bereite_vor") == 1 and ig.methoden().count("veroeffentliche") == 1
    assert "✅ Gepostet: «Thema 1»" in tg.gesendet()


def test_container_published_link_ueber_abgleich(poster, frei, ablauf, ig, uhr):
    _veroeffentlichen_scheitert(poster, ig, uhr)
    ig.status["c1"] = "PUBLISHED"
    ig.letzte_liste = [{"id": "m9", "caption": "Caption 1", "timestamp": "2026-10-27T18:00:30+0000",
                        "permalink": "https://www.instagram.com/p/m9/"}]
    _um(uhr, 27, 19, 2)
    poster.takt()
    p = ablauf.s.post(frei[0]["id"])
    assert (p["instagram_id"], p["permalink"]) == ("m9", "https://www.instagram.com/p/m9/")


def test_container_finished_nochmals_veroeffentlichen(poster, frei, ablauf, ig, uhr):
    _veroeffentlichen_scheitert(poster, ig, uhr)
    _um(uhr, 27, 19, 2)
    poster.takt()
    assert ablauf.s.post(frei[0]["id"])["post_status"] == "gepostet"
    assert ig.methoden().count("bereite_vor") == 1
    assert [a for m, a in ig.aufrufe if m == "veroeffentliche"] == [("c1",), ("c1",)]


def test_container_abgelaufen_neu_anlegen(poster, frei, ablauf, ig, uhr):
    _veroeffentlichen_scheitert(poster, ig, uhr)
    ig.status["c1"] = "EXPIRED"
    _um(uhr, 27, 19, 2)
    poster.takt()
    assert ablauf.s.post(frei[0]["id"])["post_status"] == "gepostet"
    assert [a for m, a in ig.aufrufe if m == "veroeffentliche"] == [("c1",), ("c2",)]


def test_container_stand_nicht_abfragbar_normal_wiederholen(poster, frei, ablauf, ig, uhr):
    _veroeffentlichen_scheitert(poster, ig, uhr)
    ig.status_fehler = [InstagramFehler("Instagram nicht erreichbar (URLError)")]
    _um(uhr, 27, 19, 2)
    poster.takt()
    p = ablauf.s.post(frei[0]["id"])
    assert (p["post_status"], p["versuche"], p["creation_id"]) == ("fehler", 2, "c1")
    assert p["grund"] == "Instagram nicht erreichbar (URLError)"
    assert ig.methoden().count("bereite_vor") == 1 and ig.methoden().count("veroeffentliche") == 1


def _laeuft(ablauf, b, creation_id):
    ablauf.s.setze_post(b["id"], post_status="laeuft", creation_id=creation_id)


def test_start_container_published_ohne_treffer_gepostet(poster, frei, ablauf, ig, uhr):
    _um(uhr, 27, 19, 3)
    _laeuft(ablauf, frei[0], "c7")
    ig.status["c7"] = "PUBLISHED"
    poster.beim_start()
    p = ablauf.s.post(frei[0]["id"])
    assert (p["post_status"], p["instagram_id"]) == ("gepostet", None)
    assert "veroeffentliche" not in ig.methoden()


def test_start_container_finished_veroeffentlicht_denselben(poster, frei, ablauf, ig, uhr):
    _um(uhr, 27, 19, 3)
    _laeuft(ablauf, frei[0], "c7")
    ig.status["c7"] = "FINISHED"
    poster.beim_start()
    p = ablauf.s.post(frei[0]["id"])
    assert (p["post_status"], p["creation_id"]) == ("fehler", "c7")
    poster.takt()
    assert ablauf.s.post(frei[0]["id"])["post_status"] == "gepostet"
    assert "bereite_vor" not in ig.methoden()
    assert [a for m, a in ig.aufrufe if m == "veroeffentliche"] == [("c7",)]


def test_start_container_abgelaufen_neu(poster, frei, ablauf, ig, uhr):
    _um(uhr, 27, 19, 3)
    _laeuft(ablauf, frei[0], "c7")
    ig.status["c7"] = "ERROR"
    poster.beim_start()
    p = ablauf.s.post(frei[0]["id"])
    assert (p["post_status"], p["creation_id"]) == ("fehler", None)
    poster.takt()
    assert ig.methoden().count("bereite_vor") == 1


# --- 2. Vorgemerkte Meldungen ---

def test_unklar_meldung_wird_nachgesendet(poster, frei, ablauf, ig, tg, uhr):
    _um(uhr, 27, 19, 3)
    _laeuft(ablauf, frei[0], "c7")
    ig.status_fehler = [InstagramFehler("weg")]
    tg.scheitern_bei = "sendMessage"
    poster.beim_start()
    assert ablauf.s.post(frei[0]["id"])["post_status"] == "unklar"
    tg.scheitern_bei = None
    poster.takt()
    poster.takt()
    unklar = [f for f in _gesendet(tg) if f["text"].startswith("❓")]
    assert len(unklar) == 1 and _knoepfe(unklar[0]) == ["🔁 Jetzt posten", "❌ Auslassen"]
    assert ablauf.s.post(frei[0]["id"])["meldung_id"] is not None


def test_verpasst_meldung_wird_nachgesendet(poster, frei, ablauf, ig, tg, uhr):
    poster.schalter(False)
    tg.scheitern_bei = "sendMessage"
    _um(uhr, 27, 22, 0)
    poster.takt()
    assert ablauf.s.post(frei[0]["id"])["post_status"] == "verpasst_post"
    tg.scheitern_bei = None
    _um(uhr, 27, 22, 1)
    poster.takt()
    poster.takt()
    verpasst = [f for f in _gesendet(tg) if f["text"].startswith("⚠️ Verpasst")]
    assert [f["text"] for f in verpasst] == ["⚠️ Verpasst: «Thema 1» (geplant Di 27.10., 19:00). "
                                             "Grund: Poster war ausgeschaltet"]


def _verpasst(poster, uhr):
    poster.schalter(False)
    _um(uhr, 27, 22, 0)
    poster.takt()
    poster.schalter(True)


def test_jetzt_posten_gescheitert_meldung_wird_nachgesendet(poster, frei, ablauf, ig, tg, uhr):
    _verpasst(poster, uhr)
    ablauf.verarbeite(knopf(_b(ablauf, frei), "j", update_id=70))
    ig.fehler = [InstagramFehler("weg")]
    tg.scheitern_bei = "sendMessage"
    poster.takt()
    p = ablauf.s.post(frei[0]["id"])
    assert (p["post_status"], p["manuell"]) == ("verpasst_post", False)
    tg.scheitern_bei = None
    tg.aufrufe.clear()
    poster.takt()
    poster.takt()
    gesendet = _gesendet(tg)
    assert [f["text"] for f in gesendet] == ["⚠️ Nicht gepostet: «Thema 1», Grund: weg"]
    assert _knoepfe(gesendet[0]) == ["🔁 Jetzt posten", "❌ Auslassen"]
    assert ig.methoden().count("bereite_vor") == 1


# --- 3. Schlüssel erneuern höchstens stündlich ---

class Schluessel:
    def __init__(self, tage):
        self.tage = tage

    def alter_tage(self, heute):
        return self.tage


def test_erneuern_nach_fehlversuch_erst_nach_einer_stunde(poster, ig, tg, uhr):
    ig.schluessel = Schluessel(55)
    versuche = []

    def kaputt(heute):
        versuche.append(heute)
        raise InstagramFehler("Instagram HTTP 400: abgelaufen")
    ig.erneuere = kaputt
    for minute in (0, 1, 59):
        uhr.zeit = datetime(2026, 10, 24, 22, 30, tzinfo=ZONE) + timedelta(minutes=minute)
        poster.takt()
    assert len(versuche) == 1
    uhr.zeit = datetime(2026, 10, 24, 23, 31, tzinfo=ZONE)
    poster.takt()
    assert len(versuche) == 2
    assert len([t for t in tg.gesendet() if t.startswith("⚠️ Instagram-Schlüssel")]) == 1



def test_netzausfall_beim_schluessel_meldet_nichts(poster, ig, tg, uhr):
    ig.schluessel = Schluessel(55)

    def weg(heute):
        raise InstagramFehler("Instagram nicht erreichbar (URLError)")
    ig.erneuere = weg
    poster.takt()
    assert not [t for t in tg.gesendet() if t.startswith("⚠️ Instagram-Schlüssel")]

# --- 4. Jetzt posten mit Frist ---

def test_jetzt_posten_frist_vorbei_wieder_verpasst(poster, frei, ablauf, ig, tg, uhr):
    _verpasst(poster, uhr)
    _um(uhr, 28, 8, 0)
    ablauf.verarbeite(knopf(_b(ablauf, frei), "j", update_id=71))
    assert ablauf.s.post(frei[0]["id"])["manuell_bis"] == "2026-10-28T08:30:00+01:00"
    poster.schalter(False)
    _um(uhr, 28, 8, 20)
    poster.takt()
    poster.schalter(True)
    tg.aufrufe.clear()
    _um(uhr, 28, 8, 31)
    poster.takt()
    assert "bereite_vor" not in ig.methoden()
    p = ablauf.s.post(frei[0]["id"])
    assert (p["post_status"], p["manuell"]) == ("verpasst_post", False)
    gesendet = _gesendet(tg)
    assert [f["text"] for f in gesendet] == ["⚠️ Verpasst: «Thema 1» (geplant Di 27.10., 19:00). "
                                             "Grund: Jetzt posten hat nicht innert 30 Minuten geklappt"]
    assert _knoepfe(gesendet[0]) == ["🔁 Jetzt posten", "❌ Auslassen"]
    poster.takt()
    assert "bereite_vor" not in ig.methoden()


# --- 5. Neue Version während Post ---

@pytest.mark.parametrize("post_status", ["laeuft", "unklar", "gepostet"])
def test_neue_version_abgelehnt_waehrend_post(poster, frei, ablauf, post_status):
    ablauf.s.setze_post(frei[0]["id"], post_status=post_status)
    with pytest.raises(ValueError):
        ablauf.melde_beitrag(daten(1, version=2))
    assert ablauf.s.beitrag(frei[0]["id"])["version"] == 1


@pytest.mark.parametrize("status", ["gepostet", "ausgelassen"])
def test_neue_version_abgelehnt_wenn_entschieden(poster, frei, ablauf, status):
    ablauf.s.setze(frei[0]["id"], status=status)
    with pytest.raises(ValueError):
        ablauf.melde_beitrag(daten(1, version=2))


def test_neue_version_geplant_erlaubt(poster, frei, ablauf):
    assert ablauf.melde_beitrag(daten(1, version=2))["version"] == 2


@pytest.mark.parametrize("post_status", ["laeuft", "unklar", "gepostet"])
def test_medien_ersetzt_laufenden_post_nie(poster, frei, ablauf, post_status):
    ablauf.s.setze_post(frei[0]["id"], post_status=post_status, creation_id="c7")
    ablauf.s.setze(frei[0]["id"], version=2)
    p = poster.medien(frei[0]["id"], dict(MEDIEN, version=2, caption="Neu"))
    assert (p["version"], p["post_status"], p["creation_id"], p["caption"]) == (1, post_status, "c7", "Caption 1")


# --- 6. Startdatum ---

def _frei_ohne_poster(ablauf, poster, vier):
    for i, b in enumerate(vier[:2]):
        ablauf.verarbeite(knopf(b, "f", update_id=80 + i))
    poster.medien(vier[0]["id"], MEDIEN)
    poster.medien(vier[1]["id"], {"version": 1, "medien": ["https://example.com/1.jpg", "https://example.com/2.jpg"],
                                  "cover": None, "caption": "Caption 2"})


def test_nie_eingeschaltet_keine_verpasst_meldung(ablauf, vier, ig, tg, uhr):
    poster = Poster(ablauf, ig)
    _frei_ohne_poster(ablauf, poster, vier)
    tg.aufrufe.clear()
    _um(uhr, 27, 18, 0)
    poster.takt()
    _um(uhr, 27, 22, 0)
    poster.takt()
    assert tg.gesendet() == []
    assert ablauf.s.post(vier[0]["id"])["post_status"] == "geplant"


def test_erst_spaeter_eingeschaltet_alte_termine_bleiben(ablauf, vier, ig, tg, uhr):
    poster = Poster(ablauf, ig)
    _frei_ohne_poster(ablauf, poster, vier)
    _um(uhr, 28, 8, 0)
    poster.schalter(True)
    assert ablauf.s.lies("poster_seit") == "2026-10-28T08:00:00+01:00"
    tg.aufrufe.clear()
    poster.takt()
    assert tg.gesendet() == []
    assert ablauf.s.post(vier[0]["id"])["post_status"] == "geplant"
    _um(uhr, 28, 19, 0)
    poster.takt()
    assert ablauf.s.post(vier[1]["id"])["post_status"] == "gepostet"
    assert ablauf.s.post(vier[0]["id"])["post_status"] == "geplant"


def test_poster_seit_nur_beim_ersten_einschalten(poster, ablauf, uhr):
    seit = ablauf.s.lies("poster_seit")
    assert seit == "2026-10-24T22:30:00+02:00"
    poster.schalter(False)
    _um(uhr, 28, 8, 0)
    poster.schalter(True)
    assert ablauf.s.lies("poster_seit") == seit


# --- 7. Stopp vor dem Termin ---

def test_stopp_setzt_post_zurueck_neue_vorwarnung_moeglich(poster, frei, ablauf, tg, uhr):
    _um(uhr, 27, 18, 0)
    poster.takt()
    ablauf.verarbeite(knopf(_b(ablauf, frei), "s", update_id=72))
    p = ablauf.s.post(frei[0]["id"])
    assert (p["post_status"], p["vorwarnung_id"]) == ("geplant", None)
    _um(uhr, 27, 17, 30)   # früh genug wieder freigegeben (Uhr nur für den Test zurück)
    ablauf.verarbeite(knopf(_b(ablauf, frei), "f", update_id=73))
    _um(uhr, 27, 18, 1)
    poster.takt()
    assert tg.gesendet().count("⏰ Um 19:00 geht «Thema 1» online.") == 2


# --- 8. Kleine Punkte ---

def _vier_fehler(poster, ig, uhr):
    ig.fehler = [InstagramFehler("weg") for _ in range(5)]
    for minute in (0, 2, 7, 17):
        _um(uhr, 27, 19, minute)
        poster.takt()


def test_nochmals_bei_poster_aus(poster, frei, ablauf, ig, tg, uhr):
    _vier_fehler(poster, ig, uhr)
    poster.schalter(False)
    ablauf.verarbeite(knopf(_b(ablauf, frei), "n", update_id=74))
    assert tg.antworten()[-1] == "Poster ist aus, zuerst «fliessband poster ein»"


def test_nochmals_gescheitert_bearbeitet_meldung(poster, frei, ablauf, ig, tg, uhr):
    _vier_fehler(poster, ig, uhr)
    meldung = ablauf.s.post(frei[0]["id"])["meldung_id"]
    _um(uhr, 27, 19, 20)
    ablauf.verarbeite(knopf(_b(ablauf, frei), "n", update_id=75))
    tg.aufrufe.clear()
    poster.takt()
    assert _gesendet(tg) == []
    f = tg.bearbeitet()[-1]
    assert f["message_id"] == meldung
    assert f["text"] == "⚠️ Nicht gepostet: «Thema 1»\nNochmals gescheitert (19:20): weg"
    assert f["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == f"n:{frei[0]['nr']}:1"


def test_kaputter_beitrag_haelt_andere_nicht_auf(poster, frei, ablauf, tg, uhr):
    ablauf.s.speichere_beitrag(dict(daten(3), id="2026-KW45-kaputt", woche="2026-KW45", termin="2026-00-kaputt",
                                    status="freigegeben", nachricht_id=None))
    _um(uhr, 27, 18, 0)
    poster.takt()
    assert "⏰ Um 19:00 geht «Thema 1» online." in tg.gesendet()
    _um(uhr, 27, 19, 0)
    poster.takt()
    assert ablauf.s.post(frei[0]["id"])["post_status"] == "gepostet"
    _um(uhr, 27, 22, 30)
    poster.takt()


def test_stand_schluessel_fehler_und_wartende(poster, frei, ablauf, ig, uhr):
    class Kaputt:
        def alter_tage(self, heute):
            raise ValueError("Datum kaputt")
    _verpasst(poster, uhr)
    ig.schluessel = Kaputt()
    _um(uhr, 29, 8, 0)
    stand = poster.stand()
    assert stand["schluessel_tage"] is None
    assert [(n["titel"], n["post_status"]) for n in stand["naechste"]] == [("Thema 1", "verpasst_post")]


def test_jetzt_posten_bei_unklar_zeigt_unklar_text(poster, frei, ablauf, ig, tg, uhr):
    _um(uhr, 27, 19, 3)
    _laeuft(ablauf, frei[0], "c7")
    ig.status_fehler = [InstagramFehler("weg")]
    poster.beim_start()
    ablauf.verarbeite(knopf(_b(ablauf, frei), "j", update_id=76))
    assert tg.bearbeitet()[-1]["text"] == ("❓ Unklar, ob «Thema 1» online ist. Bitte auf Instagram nachschauen."
                                           "\n🔁 Wird gepostet")


@pytest.mark.parametrize("nr,medien", [(2, ["https://example.com/1.jpg"]), (1, ["https://example.com/v.mp4", "https://example.com/w.mp4"])])
def test_medien_anzahl_passt_zum_format(poster, vier, nr, medien):
    with pytest.raises(ValueError):
        poster.medien(vier[nr - 1]["id"], dict(MEDIEN, medien=medien))


# --- Schlussprüfung: Vorwarnung ohne Dateien, täglicher Schlüssel-Check ---

DATEIEN_FEHLEN = "⚠️ Die Dateien fehlen noch. Kommen sie nicht bis zum Termin, wird nicht gepostet."


def test_vorwarnung_warnt_wenn_dateien_fehlen(ablauf, poster, vier, tg, uhr):
    from hilfen_bk import MEDIEN, knopf
    ablauf.verarbeite(knopf(vier[0], "f", update_id=10))
    tg.aufrufe.clear()
    uhr.zeit = datetime(2026, 10, 27, 18, 0, tzinfo=ZONE)
    poster.takt()
    sendungen = [f for m, f in tg.aufrufe if m == "sendMessage"]
    assert [s["text"] for s in sendungen] == ["⏰ Um 19:00 geht «Thema 1» online.\n" + DATEIEN_FEHLEN]
    assert sendungen[0]["reply_markup"]["inline_keyboard"][0][0]["text"] == "⏸ Stopp"
    poster.medien(vier[0]["id"], MEDIEN)   # Dateien kommen doch noch: Warnung verschwindet, Stopp bleibt
    letzte = tg.bearbeitet()[-1]
    assert letzte["text"] == "⏰ Um 19:00 geht «Thema 1» online."
    assert letzte["reply_markup"]["inline_keyboard"][0][0]["text"] == "⏸ Stopp"
    anzahl = len(tg.bearbeitet())
    poster.medien(vier[0]["id"], MEDIEN)   # nochmals dieselben: keine weitere Bearbeitung
    assert len(tg.bearbeitet()) == anzahl


def test_vorwarnung_mit_dateien_ohne_warnung(poster, frei, tg, uhr):
    uhr.zeit = datetime(2026, 10, 27, 18, 0, tzinfo=ZONE)
    poster.takt()
    assert tg.gesendet() == ["⏰ Um 19:00 geht «Thema 1» online."]


def test_schluessel_taeglich_geprueft(poster, ig, uhr):
    ig.schluessel = Schluessel(10)
    poster.takt()
    poster.takt()
    assert ig.methoden().count("pruefe") == 1
    uhr.zeit = datetime(2026, 10, 25, 9, 0, tzinfo=ZONE)
    poster.takt()
    assert ig.methoden().count("pruefe") == 2


def test_schluessel_ungueltig_faellt_am_selben_tag_auf(poster, ig, tg, uhr):
    ig.schluessel = Schluessel(10)
    ig.pruefe_fehler = [InstagramFehler("Instagram HTTP 400: Invalid OAuth access token", ungueltig=True)]
    poster.takt()
    meldungen = [t for t in tg.gesendet() if t.startswith("⚠️ Instagram-Schlüssel")]
    assert meldungen == [texte.schluessel_meldung("Instagram HTTP 400: Invalid OAuth access token")]
    uhr.zeit = datetime(2026, 10, 24, 23, 0, tzinfo=ZONE)
    poster.takt()
    assert ig.methoden().count("pruefe") == 1   # frühestens nach einer Stunde wieder
    ig.pruefe_fehler = [InstagramFehler("Instagram HTTP 400: Invalid OAuth access token", ungueltig=True)]
    uhr.zeit = datetime(2026, 10, 24, 23, 31, tzinfo=ZONE)
    poster.takt()
    assert ig.methoden().count("pruefe") == 2
    assert len([t for t in tg.gesendet() if t.startswith("⚠️ Instagram-Schlüssel")]) == 1   # einmal pro Tag
    uhr.zeit = datetime(2026, 10, 25, 1, 0, tzinfo=ZONE)
    poster.takt()
    poster.takt()
    assert ig.methoden().count("pruefe") == 3   # geklappt, heute nicht mehr


def test_schluessel_pruefen_ohne_sperre(poster, ablauf, ig):
    ig.schluessel = Schluessel(10)
    gehalten = []

    def pruefe():
        gehalten.append(ablauf.sperre._is_owned())
    ig.pruefe = pruefe
    poster.takt()
    assert gehalten == [False]
