from datetime import datetime

from lib import hochladen
from lib.freigabe import aendere, eintrag, manifest_pfad
from lib.wochenplan import Wochenplan

WOCHE = "2026-KW44"
REEL1 = "2026-KW44-reel-beispiel-reel-eins"
KARUSSELL = "2026-KW44-notgroschen-beispiel"
REEL2 = "2026-KW44-reel-drei-fehler"
SONNTAG = datetime(2026, 10, 25, 9, 0)


def _reiche(u, a, briefkasten, mediathek, jetzt=SONNTAG, log=None):
    plan = Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE)
    dienste = u.dienste(a, jetzt=jetzt, briefkasten=briefkasten, mediathek=mediathek)
    return hochladen.reiche_nach(plan, WOCHE, u.pfade, dienste, (log if log is not None else []).append)


def test_alle_hochladen_und_melden(gesendet, briefkasten, mediathek):
    u, a = gesendet
    assert _reiche(u, a, briefkasten, mediathek) is True
    namen = [n for n, _ in mediathek.hochgeladen]
    assert f"fliessband-{REEL1}-v1-video.mp4" in namen
    assert f"fliessband-{KARUSSELL}-v1-01.jpg" in namen
    gemeldet = dict(briefkasten.medien_gemeldet)
    assert gemeldet[REEL1]["medien"] == [
        f"https://example.com/wp-content/uploads/2026/10/fliessband-{REEL1}-v1-video.mp4"]
    assert gemeldet[KARUSSELL]["cover"] is None and len(gemeldet[KARUSSELL]["medien"]) >= 2
    assert gemeldet[REEL1]["version"] == 1 and gemeldet[REEL1]["caption"]
    e = eintrag(manifest_pfad(u.pfade, WOCHE), WOCHE, REEL1)
    assert e["medien_gemeldet"] == 1 and e["mediathek"][0]["teil"] == "video"
    anzahl = len(mediathek.hochgeladen)
    assert _reiche(u, a, briefkasten, mediathek) is True
    assert len(mediathek.hochgeladen) == anzahl and len(briefkasten.medien_gemeldet) == 4


def test_mediathek_weg_spaeter_nachholen(gesendet, briefkasten, mediathek):
    u, a = gesendet
    mediathek.nicht_erreichbar = True
    log = []
    assert _reiche(u, a, briefkasten, mediathek, log=log) is False
    assert briefkasten.medien_gemeldet == [] and any("Mediathek nicht erreichbar" in z for z in log)
    mediathek.nicht_erreichbar = False
    assert _reiche(u, a, briefkasten, mediathek) is True
    assert len(briefkasten.medien_gemeldet) == 4


def test_briefkasten_weg_kein_zweiter_upload(gesendet, briefkasten, mediathek):
    u, a = gesendet
    briefkasten.nicht_erreichbar = True
    assert _reiche(u, a, briefkasten, mediathek) is False
    anzahl = len(mediathek.hochgeladen)
    briefkasten.nicht_erreichbar = False
    assert _reiche(u, a, briefkasten, mediathek) is True
    assert len(mediathek.hochgeladen) == anzahl


def test_entschiedene_und_zu_spaete_nicht(gesendet, briefkasten, mediathek):
    u, a = gesendet
    aendere(manifest_pfad(u.pfade, WOCHE), WOCHE, KARUSSELL, status="verworfen")
    _reiche(u, a, briefkasten, mediathek, jetzt=datetime(2026, 10, 27, 22, 1))   # Reel 1: Termin + 3 h vorbei
    ids = [i for i, _ in briefkasten.medien_gemeldet]
    assert KARUSSELL not in ids and REEL1 not in ids and len(ids) == 2


def test_ohne_mediathek_nichts(gesendet, briefkasten):
    u, a = gesendet
    assert _reiche(u, a, briefkasten, None) is True
    assert briefkasten.medien_gemeldet == []


def test_aufraeumen_nur_nie_gepostete(gesendet, briefkasten, mediathek):
    u, a = gesendet
    _reiche(u, a, briefkasten, mediathek)
    pfad = manifest_pfad(u.pfade, WOCHE)
    alte = eintrag(pfad, WOCHE, REEL1)["mediathek"]
    neue = [dict(x, version=2, wp_id=x["wp_id"] + 500) for x in alte]
    aendere(pfad, WOCHE, REEL1, version=2, status="gepostet", mediathek=alte + neue)
    aendere(pfad, WOCHE, KARUSSELL, status="verworfen")
    offen = eintrag(pfad, WOCHE, REEL2)["mediathek"]
    dienste = u.dienste(a, jetzt=SONNTAG, briefkasten=briefkasten, mediathek=mediathek)
    hochladen.aufraeumen(WOCHE, u.pfade, dienste, lambda t: None)
    geloescht = set(mediathek.geloescht)
    assert {x["wp_id"] for x in alte} <= geloescht                                       # alte Version
    assert not {x["wp_id"] for x in neue} & geloescht                                    # gepostete Version bleibt
    assert {x["wp_id"] for x in eintrag(pfad, WOCHE, KARUSSELL)["mediathek"]} <= geloescht   # verworfen
    assert not {x["wp_id"] for x in offen} & geloescht                                   # offen, bleibt
    assert all(x["geloescht"] for x in eintrag(pfad, WOCHE, KARUSSELL)["mediathek"])
    anzahl = len(mediathek.geloescht)
    hochladen.aufraeumen(WOCHE, u.pfade, dienste, lambda t: None)
    assert len(mediathek.geloescht) == anzahl


def test_aufraeumen_fehler_naechster_lauf(gesendet, briefkasten, mediathek):
    u, a = gesendet
    _reiche(u, a, briefkasten, mediathek)
    aendere(manifest_pfad(u.pfade, WOCHE), WOCHE, KARUSSELL, status="verworfen")
    dienste = u.dienste(a, jetzt=SONNTAG, briefkasten=briefkasten, mediathek=mediathek)
    mediathek.nicht_erreichbar = True
    hochladen.aufraeumen(WOCHE, u.pfade, dienste, lambda t: None)
    mediathek.nicht_erreichbar = False
    hochladen.aufraeumen(WOCHE, u.pfade, dienste, lambda t: None)
    assert all(x["geloescht"] for x in eintrag(manifest_pfad(u.pfade, WOCHE), WOCHE, KARUSSELL)["mediathek"])


def test_entscheide_reicht_nach_und_raeumt_auf(gesendet, briefkasten, mediathek):
    from lib import entscheide
    u, a = gesendet
    dienste = u.dienste(a, jetzt=SONNTAG, briefkasten=briefkasten, mediathek=mediathek)
    entscheide.entscheide(u.pfade, dienste, lambda t: None)
    assert len(briefkasten.medien_gemeldet) == 4
    aendere(manifest_pfad(u.pfade, WOCHE), WOCHE, KARUSSELL, status="verworfen")
    entscheide.entscheide(u.pfade, dienste, lambda t: None)
    assert mediathek.geloescht


def test_senden_reicht_nach(wochen_umgebung, agentur_attrappe, briefkasten, mediathek, schnell, schnelles_karussell):
    from lib import woche
    u = wochen_umgebung
    a = agentur_attrappe(fragen=0)
    for schritt, jetzt in (("job-vorbereiten", datetime(2026, 10, 23, 22, 0)),
                           ("job-bauen", datetime(2026, 10, 24, 22, 0))):
        woche.fuehre_aus(schritt, WOCHE, u.pfade,
                         u.dienste(a, jetzt=jetzt, briefkasten=briefkasten, mediathek=mediathek), lambda t: None)
    assert {i for i, _ in briefkasten.medien_gemeldet} == {b["id"] for b in briefkasten.gemeldet}


MELDUNG = "konnten nicht in die Mediathek"


def _meldungen(u):
    return [t for t in u.telegram.texte() if MELDUNG in t]


def test_dauerhafter_fehler_einmal_pro_version(gesendet, briefkasten, mediathek):
    from lib.mediathek import MediathekFehler
    u, a = gesendet
    mediathek.fehler = MediathekFehler("Mediathek POST: HTTP 413 Datei zu gross", code=413)
    assert _reiche(u, a, briefkasten, mediathek) is False
    assert _reiche(u, a, briefkasten, mediathek) is False
    texte = _meldungen(u)
    assert len(texte) == 4   # je Beitrag genau eine
    assert all("HTTP 413 Datei zu gross" in t and t.endswith("Ohne Dateien wird nicht gepostet.") for t in texte)
    assert any(t.startswith("Dateien von «") for t in texte)
    assert eintrag(manifest_pfad(u.pfade, WOCHE), WOCHE, REEL1)["mediathek_fehler"] == 1


def test_passwort_fehlt_und_dateifehler_gemeldet(gesendet, briefkasten, mediathek):
    from lib.mediathek import MediathekFehler
    u, a = gesendet
    mediathek.fehler = MediathekFehler("Passwort für example.com fehlt im Schlüsselbund", dauerhaft=True)
    _reiche(u, a, briefkasten, mediathek)
    assert len(_meldungen(u)) == 4
    aendere(manifest_pfad(u.pfade, WOCHE), WOCHE, REEL1, mediathek_fehler=None)
    mediathek.fehler = OSError("Datei kaputt")
    _reiche(u, a, briefkasten, mediathek)
    assert len(_meldungen(u)) == 5 and "Datei kaputt" in _meldungen(u)[-1]


def test_voruebergehende_fehler_still(gesendet, briefkasten, mediathek):
    from lib.mediathek import MediathekFehler
    u, a = gesendet
    for fehler in (MediathekFehler("Mediathek nicht erreichbar (URLError)"),
                   MediathekFehler("Mediathek POST: HTTP 503", code=503),
                   MediathekFehler("Mediathek POST: HTTP 429", code=429),
                   MediathekFehler("Mediathek POST: HTTP 408", code=408),
                   MediathekFehler("Mediathek POST: HTTP 404", code=404)):
        mediathek.fehler = fehler
        assert _reiche(u, a, briefkasten, mediathek) is False
    assert _meldungen(u) == []
    assert "mediathek_fehler" not in eintrag(manifest_pfad(u.pfade, WOCHE), WOCHE, REEL1)


def test_meldung_nicht_gesendet_naechster_lauf(gesendet, briefkasten, mediathek):
    from lib.mediathek import MediathekFehler
    u, a = gesendet
    mediathek.fehler = MediathekFehler("Mediathek POST: HTTP 403 verboten", code=403)
    u.telegram.scheitern_bei = "sendMessage"
    log = []
    _reiche(u, a, briefkasten, mediathek, log=log)
    assert _meldungen(u) == [] and any("nicht gesendet" in z for z in log)
    assert eintrag(manifest_pfad(u.pfade, WOCHE), WOCHE, REEL1).get("mediathek_fehler") is None
    u.telegram.scheitern_bei = None
    _reiche(u, a, briefkasten, mediathek)
    assert len(_meldungen(u)) == 4


def _reiche_fehler(u, a, briefkasten, mediathek):
    plan = Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE)
    dienste = u.dienste(a, jetzt=SONNTAG, briefkasten=briefkasten, mediathek=mediathek)
    fehler = []
    hochladen.reiche_nach(plan, WOCHE, u.pfade, dienste, lambda t: None, fehler=fehler)
    return fehler


def test_stoerung_nur_bei_ausfall_des_briefkastens(gesendet, briefkasten, mediathek):
    from lib.briefkasten import BriefkastenFehler
    u, a = gesendet
    briefkasten.medien_fehler = BriefkastenFehler("Briefkasten POST /beitraege/x/medien: HTTP 400 ungueltig", code=400)
    assert _reiche_fehler(u, a, briefkasten, mediathek) == []
    briefkasten.medien_fehler = BriefkastenFehler("Briefkasten POST /beitraege/x/medien: HTTP 503", code=503)
    assert len(_reiche_fehler(u, a, briefkasten, mediathek)) == 4
    briefkasten.medien_fehler = None
    briefkasten.nicht_erreichbar = True
    assert len(_reiche_fehler(u, a, briefkasten, mediathek)) == 4
