import json
from datetime import datetime

from lib import woche
from lib.notiz import zeilen_hash
from lib.wochenplan import Wochenplan

WOCHE = "2026-KW44"


def test_ganze_woche_mit_echten_bauern(wochen_umgebung, agentur_attrappe, schnell, schnelles_karussell):
    u = wochen_umgebung
    a = agentur_attrappe(konkurrenz=True)
    log = []

    freitag = u.dienste(a, jetzt=datetime(2026, 10, 23, 22, 0))
    assert woche.fuehre_aus("job-vorbereiten", WOCHE, u.pfade, freitag, log.append) == 0
    assert u.telegram.texte()[0].startswith("Frage 1/1 (Reel Di 27.10.)")

    u.telegram.updates = [{"update_id": 3, "message": {
        "message_id": 700, "chat": {"id": 42, "type": "private"}, "text": "Glücksspiel, sagt der Kollege.",
        "reply_to_message": {"message_id": 101}}}]
    samstag = u.dienste(a, jetzt=datetime(2026, 10, 24, 22, 0))
    assert woche.fuehre_aus("job-bauen", WOCHE, u.pfade, samstag, log.append) == 0

    plan = Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE)
    assert [t["status"] for t in plan.aktive()] == ["gesendet"] * 4
    ordner = u.pfade.woche(WOCHE)
    for name in ["reel-beispiel-reel-eins/reel.mp4", "reel-drei-fehler/cover.png",
                 "notgroschen-beispiel/slide-10.png", "demokonto-woche/caption.txt"]:
        assert (ordner / name).exists(), name
    manifest = json.loads((ordner / "manifest.json").read_text(encoding="utf-8"))
    assert sorted(b["id"] for b in manifest["beitraege"]) == [
        "2026-KW44-demokonto-woche", "2026-KW44-notgroschen-beispiel",
        "2026-KW44-reel-drei-fehler", "2026-KW44-reel-beispiel-reel-eins"]
    assert {b["termin"] for b in manifest["beitraege"]} == {
        "2026-10-27T19:00", "2026-10-28T19:00", "2026-10-29T19:00", "2026-10-31T19:00"}
    karussell = next(t for t in plan.aktive() if t["slug"] == "notgroschen-beispiel")
    assert "offen: Slide" in karussell["vermerk"]

    methoden = u.telegram.methoden()
    assert methoden.count("sendVideo") == 2 and methoden.count("sendMediaGroup") == 2
    assert all(f["disable_notification"] is True for m, f, _ in u.telegram.aufrufe if m.startswith("send"))

    content = [t for agent, t in a.auftraege if agent == "content-agent"]
    assert "Glücksspiel, sagt der Kollege." in content[0]
    assert "«Drei Fehler beim Start»" in content[2]
    assert a.anzahl("apify.py") == 2 and a.anzahl("viral-agent") == 0
    assert json.loads((u.pfade.daten / "verwendet.json").read_text(encoding="utf-8"))["hashes"] == [
        zeilen_hash("Die Sätze aus dem Teamraum")]
    assert not (u.pfade.daten / f"sperre-{WOCHE}").exists()
    assert not [z for z in log if z.startswith("Fehler")]
