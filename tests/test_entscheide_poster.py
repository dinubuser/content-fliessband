from datetime import datetime

from lib import entscheide, freigabe
from lib.freigabe import eintrag, manifest_pfad

WOCHE = "2026-KW44"
REEL1 = "2026-KW44-reel-beispiel-reel-eins"
DIENSTAG = datetime(2026, 10, 27, 19, 5)


def _lauf(u, a, briefkasten, log=None):
    return entscheide.entscheide(u.pfade, u.dienste(a, jetzt=DIENSTAG, briefkasten=briefkasten),
                                 (log if log is not None else []).append)


def test_gepostet_ins_manifest(gesendet, briefkasten):
    u, a = gesendet
    briefkasten.ereignis("freigegeben", REEL1)
    briefkasten.ereignis("gepostet", REEL1, zeit="2026-10-27T19:00:31+01:00",
                         nachricht={"instagram_id": "1790", "permalink": "https://www.instagram.com/reel/A/"})
    assert _lauf(u, a, briefkasten) == 2
    e = eintrag(manifest_pfad(u.pfade, WOCHE), WOCHE, REEL1)
    assert (e["status"], e["gepostet"], e["instagram_id"], e["permalink"]) == (
        "gepostet", "2026-10-27T19:00:31+01:00", "1790", "https://www.instagram.com/reel/A/")


def test_ausgelassen_ins_manifest(gesendet, briefkasten):
    u, a = gesendet
    briefkasten.ereignis("freigegeben", REEL1)
    briefkasten.ereignis("ausgelassen", REEL1)
    _lauf(u, a, briefkasten)
    assert eintrag(manifest_pfad(u.pfade, WOCHE), WOCHE, REEL1)["status"] == "ausgelassen"


def test_gepostet_ohne_nachricht_wird_uebersprungen(gesendet, briefkasten):
    u, a = gesendet
    briefkasten.ereignis("gepostet", REEL1)
    log = []
    assert _lauf(u, a, briefkasten, log) == 1
    assert any("unvollständig" in z for z in log)
    assert eintrag(manifest_pfad(u.pfade, WOCHE), WOCHE, REEL1)["status"] == "entwurf"


def test_status_liste():
    assert {"gepostet", "ausgelassen"} <= set(freigabe.STATUS)
