import json
from datetime import datetime
from pathlib import Path

import pytest

from lib import manifest, woche
from lib.notiz import zeilen_hash
from lib.reel_renderer import RenderFehler
from lib.woche import SchrittFehler, _bau_vermerk
from lib.wochenplan import Wochenplan

WOCHE = "2026-KW44"
FREITAG, SAMSTAG = datetime(2026, 10, 23, 22, 0), datetime(2026, 10, 24, 22, 0)
ANTWORT = {"update_id": 7, "message": {"message_id": 900, "chat": {"id": 42, "type": "private"},
                                       "text": "Glücksspiel, sagt der Kollege.",
                                       "reply_to_message": {"message_id": 101}}}


class _Bauten(list):
    """Liste der Bauten (format, slug, termin); laengen: mitgegebene Länge je Reel-Bau;
    pruefer: mitgegebener Aussprache-Prüfer je Reel-Bau; aussprache: Antwort für aussprache_neu."""
    laengen: list
    pruefer: list
    aussprache: list


@pytest.fixture
def gebaut(monkeypatch):
    """Ersetzt baue_reel und baue_karussell in lib.woche (schnell, ohne ffmpeg). Liste der Bauten."""
    liste = _Bauten()
    liste.laengen = []
    liste.pruefer = []
    liste.aussprache = []

    def bauer(format):
        def bauen(quelle, termin=None, basis=None, anfrage=None, laenge=None, aussprache_pruefer=None):
            slug = manifest.slug_von(Path(quelle))
            ziel = basis / "wochen" / WOCHE / (f"reel-{slug}" if format == "reel" else slug)
            ziel.mkdir(parents=True, exist_ok=True)
            pruefungen = {"platzhalter": []}
            if format == "reel":
                (ziel / "reel.mp4").write_bytes(b"mp4")
                liste.laengen.append(laenge)
                liste.pruefer.append(aussprache_pruefer)
                pruefungen["aussprache_neu"] = liste.aussprache
            else:
                for n in (1, 2):
                    (ziel / f"slide-{n:02d}.png").write_bytes(b"png")
            (ziel / "caption.txt").write_text(f"Caption {slug}\n", encoding="utf-8")
            liste.append((format, slug, termin))
            return ziel, {"pruefungen": pruefungen, "dauer_s": 27.5}
        return bauen

    monkeypatch.setattr(woche, "baue_reel", bauer("reel"))
    monkeypatch.setattr(woche, "baue_karussell", bauer("karussell"))
    return liste


def _vorbereitet(u, a, fragen=True):
    woche.vorbereiten(WOCHE, u.pfade, u.dienste(a, jetzt=FREITAG), lambda t: None, fragen=fragen)


def _plan(u):
    return Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE)


def _bauen(u, a, **mehr):
    return woche.bauen(WOCHE, u.pfade, u.dienste(a, jetzt=SAMSTAG, **mehr), lambda t: None)


def test_bauen_ganze_woche(wochen_umgebung, agentur_attrappe, gebaut):
    u = wochen_umgebung
    a = agentur_attrappe()
    _vorbereitet(u, a)
    u.telegram.updates = [ANTWORT]
    _bauen(u, a)
    plan = _plan(u)
    assert [t["status"] for t in plan.aktive()] == ["gesendet"] * 4
    assert plan.themen[0]["antwort"] == "Glücksspiel, sagt der Kollege."
    content = [t for agent, t in a.auftraege if agent == "content-agent"]
    assert "Glücksspiel, sagt der Kollege." in content[0]
    assert [(f, s) for f, s, _ in gebaut] == [("reel", "beispiel-reel-eins"), ("karussell", "notgroschen-beispiel"),
                                              ("reel", "drei-fehler"), ("karussell", "demokonto-woche")]
    assert gebaut[0][2] == datetime(2026, 10, 27, 19, 0)
    assert plan.daten["schritte"]["gebaut"] == "2026-10-24T22:00"
    assert plan.daten["schritte"]["gesendet"] == "2026-10-24T22:00"
    assert json.loads((u.pfade.daten / "bot.json").read_text(encoding="utf-8"))["letzte_update_id"] == 7
    assert json.loads((u.pfade.daten / "verwendet.json").read_text(encoding="utf-8"))["hashes"] == [
        zeilen_hash("Die Sätze aus dem Teamraum")]
    methoden = u.telegram.methoden()
    assert methoden.count("sendVideo") == 2 and methoden.count("sendMediaGroup") == 2


def test_offene_frage_wird_durch_reserve_ersetzt(wochen_umgebung, agentur_attrappe, gebaut):
    u = wochen_umgebung
    a = agentur_attrappe()
    _vorbereitet(u, a)
    _bauen(u, a)
    plan = _plan(u)
    assert plan.themen[0]["status"] == "ersetzt"
    assert [t["slug"] for t in plan.aktive()] == ["reserve-reel", "notgroschen-beispiel", "drei-fehler",
                                                  "demokonto-woche"]
    assert gebaut[0][:2] == ("reel", "reserve-reel")
    uebersicht = next(t for t in u.telegram.texte() if t.startswith("Wochenpaket"))
    assert "Ersetzt: «Thema beispiel-reel-eins» (keine Antwort auf die Frage)" in uebersicht
    assert not (u.pfade.daten / "verwendet.json").exists()


def test_wiederaufnahme_nach_absturz_beim_texten(wochen_umgebung, agentur_attrappe, gebaut):
    u = wochen_umgebung
    a1 = agentur_attrappe(abbruch_bei="drei-fehler")
    _vorbereitet(u, a1)
    u.telegram.updates = [ANTWORT]
    with pytest.raises(KeyboardInterrupt):
        _bauen(u, a1)
    assert [t["status"] for t in _plan(u).aktive()] == ["getestet", "getestet", "bereit", "bereit"]
    a2 = agentur_attrappe()
    _bauen(u, a2)
    assert a2.anzahl("content-agent") == 2 and a2.anzahl("follower-agent") == 4
    assert not [n for _, n in a2.aufrufe if "beispiel-reel-eins" in n or "notgroschen-beispiel" in n]
    assert [t["status"] for t in _plan(u).aktive()] == ["gesendet"] * 4


def test_wiederaufnahme_nach_absturz_beim_bauen(wochen_umgebung, agentur_attrappe, gebaut, monkeypatch):
    u = wochen_umgebung
    _vorbereitet(u, agentur_attrappe(fragen=0), fragen=False)
    echt = woche.baue_reel

    def abbruch(quelle, **kw):
        if "drei-fehler" in str(quelle):
            raise KeyboardInterrupt
        return echt(quelle, **kw)
    monkeypatch.setattr(woche, "baue_reel", abbruch)
    with pytest.raises(KeyboardInterrupt):
        _bauen(u, agentur_attrappe(fragen=0))
    assert [t["status"] for t in _plan(u).aktive()] == ["gebaut", "gebaut", "getestet", "getestet"]
    monkeypatch.setattr(woche, "baue_reel", echt)
    a2 = agentur_attrappe(fragen=0)
    _bauen(u, a2)
    assert a2.aufrufe == []
    assert [s for _, s, _ in gebaut] == ["beispiel-reel-eins", "notgroschen-beispiel", "drei-fehler", "demokonto-woche"]


def test_elevenlabs_zu_wenig_guthaben(wochen_umgebung, agentur_attrappe, gebaut):
    u = wochen_umgebung
    a = agentur_attrappe(fragen=0)
    _vorbereitet(u, a, fragen=False)
    _bauen(u, a, rest=100)
    plan = _plan(u)
    assert [f for f, _, _ in gebaut] == ["karussell"] * 4
    aktive = plan.aktive()
    assert (aktive[0]["slug"], aktive[0]["format"]) == ("reserve-karussell", "karussell")
    assert aktive[2]["slug"] == "drei-fehler"
    assert aktive[2]["vermerk"].startswith("als karussell neu geschrieben (ElevenLabs-Guthaben zu klein (100 von")
    assert any(v.startswith("ElevenLabs-Guthaben zu klein (100 von") for v in plan.daten["vermerke"])
    assert a.anzahl("content-agent") == 6


def test_zeitlimit_laufendes_thema_fehlgeschlagen(wochen_umgebung, agentur_attrappe, gebaut):
    u = wochen_umgebung
    a = agentur_attrappe(fragen=0)
    _vorbereitet(u, a, fragen=False)
    zeiten = iter([0, 0, 0])
    with pytest.raises(SchrittFehler, match="Zeitlimit"):
        _bauen(u, a, uhr=lambda: next(zeiten, 8000))
    aktive = _plan(u).aktive()
    assert [t["status"] for t in aktive] == ["fehlgeschlagen", "bereit", "bereit", "bereit"]
    assert "Zeitlimit" in aktive[0]["vermerk"]
    assert gebaut == []
    assert any(t.startswith("Wochenpaket") for t in u.telegram.texte())


def test_thema_scheitert_haelt_andere_nicht_auf(wochen_umgebung, agentur_attrappe, gebaut, monkeypatch):
    u = wochen_umgebung
    a = agentur_attrappe(fragen=0)
    _vorbereitet(u, a, fragen=False)
    echt = woche.baue_reel

    def kaputt(quelle, **kw):
        if "drei-fehler" in str(quelle):
            raise RenderFehler("HyperFrames render gescheitert, Protokoll: x.log")
        return echt(quelle, **kw)
    monkeypatch.setattr(woche, "baue_reel", kaputt)
    _bauen(u, a)
    plan = _plan(u)
    assert [t["status"] for t in plan.aktive()] == ["gesendet", "gesendet", "fehlgeschlagen", "gesendet"]
    assert plan.aktive()[2]["vermerk"] == "HyperFrames render gescheitert, Protokoll: x.log"
    assert "FEHLGESCHLAGEN" in next(t for t in u.telegram.texte() if t.startswith("Wochenpaket"))
    assert plan.daten["schritte"]["gebaut"] and plan.daten["schritte"]["gesendet"]


def test_bauen_ohne_vorbereitung(wochen_umgebung, agentur_attrappe):
    u = wochen_umgebung
    with pytest.raises(SchrittFehler, match="nicht vorbereitet"):
        _bauen(u, agentur_attrappe())


def test_elevenlabs_zu_wenig_guthaben_antwort_bleibt(wochen_umgebung, agentur_attrappe, gebaut):
    """Reel mit Betreiber-Antwort wird als Karussell neu geschrieben (Antwort bleibt), die Reserve geht an das
    Reel ohne Antwort."""
    u = wochen_umgebung
    a = agentur_attrappe()
    _vorbereitet(u, a)
    u.telegram.updates = [ANTWORT]
    _bauen(u, a, rest=100)
    aktive = _plan(u).aktive()
    assert (aktive[0]["slug"], aktive[0]["format"]) == ("beispiel-reel-eins", "karussell")
    assert aktive[0]["antwort"] == "Glücksspiel, sagt der Kollege."
    assert (aktive[2]["slug"], aktive[2]["format"]) == ("reserve-karussell", "karussell")
    content = [t for agent, t in a.auftraege if agent == "content-agent"]
    assert sum("Glücksspiel, sagt der Kollege." in t for t in content) == 2
    assert [f for f, _, _ in gebaut] == ["karussell"] * 4


def test_fehlende_reel_datei_bei_guthaben_pruefung_nur_dieses_thema(wochen_umgebung, agentur_attrappe, gebaut,
                                                                   monkeypatch):
    """Fehlt eine Reel-Datei beim Zählen der Sprechzeichen, scheitert nur dieses Thema."""
    u = wochen_umgebung
    a = agentur_attrappe(fragen=0)
    _vorbereitet(u, a, fragen=False)
    echt = woche.sprechzeichen

    def zaehle(beitrag):
        if "drei-fehler" in str(beitrag):
            raise FileNotFoundError(f"[Errno 2] No such file or directory: '{beitrag}'")
        return echt(beitrag)
    monkeypatch.setattr(woche, "sprechzeichen", zaehle)
    _bauen(u, a)
    aktive = _plan(u).aktive()
    assert [t["status"] for t in aktive] == ["gesendet", "gesendet", "fehlgeschlagen", "gesendet"]
    assert "No such file" in aktive[2]["vermerk"]


def test_nie_gesendete_frage_ehrlicher_vermerk(wochen_umgebung, agentur_attrappe, gebaut):
    """Telegram am Freitag weg: Die Frage ging nie raus. Das Ersatzthema sagt das, nicht «keine Antwort»."""
    u = wochen_umgebung
    a = agentur_attrappe()
    u.telegram.scheitern_bei = "sendMessage"
    with pytest.raises(SchrittFehler):
        _vorbereitet(u, a)
    u.telegram.scheitern_bei = None
    _bauen(u, a)
    plan = _plan(u)
    alt = next(t for t in plan.themen if t["slug"] == "beispiel-reel-eins")
    assert (alt["status"], alt["vermerk"]) == ("ersetzt", "Frage wurde nie gesendet")
    assert "getUpdates" not in u.telegram.methoden()


def test_bau_vermerk_platzhalter_und_bild():
    t = {"vermerk": ""}
    _bau_vermerk(t, {"pruefungen": {"platzhalter": ["Szene 2: [prüfen]"],
                                    "bild_hinweise": ["Szene 3: Gegenstand 'einhorn' unbekannt, weggelassen"]}})
    assert "offen: Szene 2: [prüfen]" in t["vermerk"]
    assert "Bild ersetzt: Szene 3: Gegenstand 'einhorn' unbekannt, weggelassen" in t["vermerk"]


def test_bau_vermerk_karussell_ohne_bild_hinweise():
    t = {"vermerk": ""}
    _bau_vermerk(t, {"pruefungen": {"platzhalter": []}})
    assert t["vermerk"] == ""


@pytest.mark.parametrize("text", ["Bitte ein Ersatzthema nehmen", "Ersatz", "lieber ein anderes Thema",
                                  "Überspringen bitte", "nimm die Reserve"])
def test_antwort_will_ersatz(text):
    assert woche.will_ersatz(text)


@pytest.mark.parametrize("text", ["Glücksspiel, sagt der Kollege.",
                                  "Mein Kollege sagt, Trading sei kein Ersatz für ein Sparkonto, und der zweite "
                                  "meint, das sei nur Zocken, und der dritte fragt nach meinen Verlusten."])
def test_echte_antwort_will_keinen_ersatz(text):
    assert not woche.will_ersatz(text)


def test_antwort_mit_ersatzwunsch_wird_durch_reserve_ersetzt(wochen_umgebung, agentur_attrappe, gebaut):
    """KW44: Betreiber schrieb «Bitte ein Ersatzthema nehmen», das Fliessband baute das Thema trotzdem."""
    u = wochen_umgebung
    a = agentur_attrappe()
    _vorbereitet(u, a)
    nein = json.loads(json.dumps(ANTWORT))
    nein["message"]["text"] = "Bitte ein Ersatzthema nehmen"
    u.telegram.updates = [nein]
    _bauen(u, a)
    plan = _plan(u)
    assert plan.themen[0]["status"] == "ersetzt"
    assert plan.themen[0]["vermerk"] == "Der Betreiber wünscht ein Ersatzthema"
    assert gebaut[0][:2] == ("reel", "reserve-reel")
    assert not [t for agent, t in a.auftraege if agent == "content-agent" and "Ersatzthema nehmen" in t]


def test_bau_gibt_laenge_mit_und_merkt_dauer(wochen_umgebung, agentur_attrappe, gebaut):
    u = wochen_umgebung
    a = agentur_attrappe()
    _vorbereitet(u, a)
    u.telegram.updates = [ANTWORT]
    _bauen(u, a)
    assert gebaut.laengen == ["kurz", "mittel"]
    reels = [t for t in _plan(u).aktive() if t["format"] == "reel"]
    assert [(t["laenge"], t["dauer_s"]) for t in reels] == [("kurz", 27.5), ("mittel", 27.5)]
    assert not any("⚠️ Reel ist" in t for t in u.telegram.texte())


def test_bauen_gibt_pruefer_mit_und_meldet_funde(wochen_umgebung, agentur_attrappe, gebaut):
    u = wochen_umgebung
    a = agentur_attrappe()
    gebaut.aussprache = [["Trottoir", "Gehweg"]]
    _vorbereitet(u, a)
    u.telegram.updates = [ANTWORT]
    _bauen(u, a)
    assert len(gebaut.pruefer) == 2 and all(callable(p) for p in gebaut.pruefer)
    plan = _plan(u)
    assert plan.themen[0]["aussprache_neu"] == [["Trottoir", "Gehweg"]]
    assert "aussprache_neu" not in plan.themen[1]                     # Karussell
    assert sum(t == "🗣 Neu für die Stimme: Trottoir → Gehweg" for t in u.telegram.texte()) == 2


def test_bauen_ohne_funde_keine_zeile(wochen_umgebung, agentur_attrappe, gebaut):
    u = wochen_umgebung
    a = agentur_attrappe()
    _vorbereitet(u, a)
    u.telegram.updates = [ANTWORT]
    _bauen(u, a)
    assert _plan(u).themen[0]["aussprache_neu"] == []
    assert not any("🗣" in t for t in u.telegram.texte())


def test_antwort_landet_einmal_in_den_geschichten(wochen_umgebung, agentur_attrappe, gebaut):
    u = wochen_umgebung
    a = agentur_attrappe()
    _vorbereitet(u, a)
    u.telegram.updates = [ANTWORT]
    _bauen(u, a)
    _bauen(u, a)
    text = u.pfade.geschichten.read_text(encoding="utf-8")
    assert text.startswith("# Geschichten des Betreibers")
    assert text.count("## 2026-10-24: Welche Sätze hörst du im Alltag, wenn du Trading erwähnst?\n\n"
                      "Glücksspiel, sagt der Kollege.\n") == 1
    assert _plan(u).themen[0]["geschichte_gemerkt"] is True


def test_ersatz_wunsch_ist_keine_geschichte(wochen_umgebung, agentur_attrappe, gebaut):
    u = wochen_umgebung
    a = agentur_attrappe()
    _vorbereitet(u, a)
    ersatz = json.loads(json.dumps(ANTWORT))
    ersatz["message"]["text"] = "Bitte ein Ersatzthema nehmen"
    u.telegram.updates = [ersatz]
    _bauen(u, a)
    assert not u.pfade.geschichten.exists()


def test_geschichte_nicht_schreibbar_nur_vermerk(wochen_umgebung, agentur_attrappe, gebaut):
    u = wochen_umgebung
    a = agentur_attrappe()
    _vorbereitet(u, a)
    u.pfade.geschichten.mkdir(parents=True)   # ein Ordner statt der Datei: OSError
    u.telegram.updates = [ANTWORT]
    _bauen(u, a)
    plan = _plan(u)
    assert [t["status"] for t in plan.aktive()] == ["gesendet"] * 4
    assert any(v.startswith("Geschichte nicht gespeichert") for v in plan.daten["vermerke"])


def test_geschichte_schreibfehler_bei_thema_2_holt_nach(wochen_umgebung, agentur_attrappe, gebaut, monkeypatch):
    from lib import geschichten
    u = wochen_umgebung
    a = agentur_attrappe()
    _vorbereitet(u, a)
    u.telegram.updates = [ANTWORT]
    plan = _plan(u)
    plan.themen[1]["frage"], plan.themen[1]["antwort"] = "Zweite Frage?", "Zweite Antwort."
    plan.themen[1]["status"] = "bereit"
    plan.speichere()
    echt = geschichten.merke

    def kaputt(pfad, datum, frage, antwort):
        if frage == "Zweite Frage?":
            raise UnicodeEncodeError("utf-8", "\ud800", 0, 1, "surrogate")
        return echt(pfad, datum, frage, antwort)
    monkeypatch.setattr(geschichten, "merke", kaputt)
    plan = _bauen(u, a)
    assert plan.themen[0]["geschichte_gemerkt"] is True and not plan.themen[1].get("geschichte_gemerkt")
    assert any(v.startswith("Geschichte nicht gespeichert") for v in plan.daten["vermerke"])
    monkeypatch.setattr(geschichten, "merke", echt)
    _bauen(u, a)
    text = u.pfade.geschichten.read_text(encoding="utf-8")
    assert text.count("Zweite Frage?") == 1 and text.count("Glücksspiel, sagt der Kollege.") == 1


def test_bau_vermerk_start_ergaenzt():
    t = {"vermerk": ""}
    _bau_vermerk(t, {"pruefungen": {"platzhalter": [], "start_ergaenzt": True}})
    assert t["vermerk"] == "START-Satz in der Caption ergänzt"
    t = {"vermerk": ""}
    _bau_vermerk(t, {"pruefungen": {"platzhalter": [], "start_ergaenzt": False}})
    assert t["vermerk"] == ""


def test_bau_vermerk_start_schluss_fehlt():
    t = {"vermerk": ""}
    _bau_vermerk(t, {"pruefungen": {"platzhalter": [], "start_schluss_fehlt": True}})
    assert t["vermerk"] == "START fehlt am Schluss"
