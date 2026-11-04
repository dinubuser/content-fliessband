import json
import re
from datetime import datetime
from pathlib import Path

import pytest

from lib import entscheide, reel_bauer, texter, woche
from lib.freigabe import eintrag, manifest_pfad
from lib.pruefungen import SATZZEICHEN, lade_aussprache
from lib.reel_leser import lese_reel
from lib.reel_renderer import RenderFehler
from lib.wochenplan import Wochenplan

WOCHE = "2026-KW44"
SONNTAG = datetime(2026, 10, 25, 9, 0)
REEL1 = "2026-KW44-reel-beispiel-reel-eins"
KARUSSELL = "2026-KW44-notgroschen-beispiel"


@pytest.fixture
def gesendet(wochen_umgebung, agentur_attrappe, briefkasten, schnell, schnelles_karussell):
    """Wie in test_entscheide.py: Karussell-Texte ohne [Platzhalter], sonst wären sie braucht_eingabe und ohne Knöpfe
    (gilt auch für die neue Fassung aus texter.ueberarbeite)."""
    class OhnePlatzhalter(agentur_attrappe):
        def claude(self, agent, auftrag, ausgabe, *args, **kwargs):
            pfad = super().claude(agent, auftrag, ausgabe, *args, **kwargs)
            if pfad.suffix == ".md" and "_reel_" not in pfad.name:
                pfad.write_text(re.sub(r"\[[^\]]+\]", "", pfad.read_text(encoding="utf-8")), encoding="utf-8")
            return pfad

    u = wochen_umgebung
    a = OhnePlatzhalter(fragen=0)
    for schritt, jetzt in (("job-vorbereiten", datetime(2026, 10, 23, 22, 0)),
                           ("job-bauen", datetime(2026, 10, 24, 22, 0))):
        assert woche.fuehre_aus(schritt, WOCHE, u.pfade, u.dienste(a, jetzt=jetzt, briefkasten=briefkasten),
                                lambda t: None) == 0
    u.telegram.aufrufe.clear()
    briefkasten.gemeldet.clear()
    return u, a


def _lauf(u, a, briefkasten, rest=30000, log=None):
    return entscheide.entscheide(u.pfade, u.dienste(a, jetzt=SONNTAG, briefkasten=briefkasten, rest=rest),
                                 (log if log is not None else []).append)


def _letzter(a):
    """Letzter Auftrag ohne den Faktencheck (Etappe 10 hängt dem Neubau einen fakten-agent-Aufruf an)."""
    return [x for x in a.auftraege if x[0] != "fakten-agent"][-1]


def _thema(u, slug):
    return next(t for t in Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE).themen if t["slug"] == slug)


def _e(u, id):
    return eintrag(manifest_pfad(u.pfade, WOCHE), WOCHE, id)


def test_aendern_karussell(gesendet, briefkasten):
    u, a = gesendet
    vorher = Path(_thema(u, "notgroschen-beispiel")["beitrag"])
    briefkasten.ereignis("aendern", beitrag=KARUSSELL, notiz="Slide 3 ist zu voll")
    assert _lauf(u, a, briefkasten) == 1
    t = _thema(u, "notgroschen-beispiel")
    assert t["beitrag"] == str(vorher.with_name(vorher.stem + "_v2.md")) and Path(t["beitrag"]).exists()
    agent, auftrag = _letzter(a)
    assert agent == "content-agent" and "Slide 3 ist zu voll" in auftrag
    e = _e(u, KARUSSELL)
    assert (e["status"], e["version"], e["neubauten"], e["entschieden"]) == ("entwurf", 2, 1, None)
    assert e["notizen"] == [{"zeit": "2026-10-25T09:00:00+01:00", "text": "Slide 3 ist zu voll"}]
    assert u.telegram.methoden() == ["sendMediaGroup", "sendMessage"]
    assert (briefkasten.gemeldet[-1]["id"], briefkasten.gemeldet[-1]["version"],
            briefkasten.gemeldet[-1]["neubauten"]) == (KARUSSELL, 2, 1)
    assert t["angemeldet"] == 2 and "Version 2 nach Betreiber-Notiz" in t["vermerk"]


def test_aendern_reel(gesendet, briefkasten):
    u, a = gesendet
    briefkasten.ereignis("aendern", beitrag=REEL1, notiz="Hook kürzer")
    assert _lauf(u, a, briefkasten) == 1
    assert _e(u, REEL1)["version"] == 2
    assert u.telegram.methoden() == ["sendVideo", "sendMessage"]


def test_guthaben_zu_klein(gesendet, briefkasten, monkeypatch):
    u, a = gesendet
    alt = Path(_thema(u, "beispiel-reel-eins")["beitrag"]).read_text(encoding="utf-8")
    original = texter.ueberarbeite

    def anders(thema, notiz, pfade, lauf, **kw):
        neu = original(thema, notiz, pfade, lauf, **kw)
        neu.write_text(alt.replace("Sprechtext: ", "Sprechtext: Neu: "), encoding="utf-8")
        return neu
    monkeypatch.setattr(texter, "ueberarbeite", anders)
    briefkasten.ereignis("aendern", beitrag=REEL1, notiz="Alles neu")
    assert _lauf(u, a, briefkasten, rest=100) == 1
    id, grund = briefkasten.fehler_gemeldet[0]
    assert id == REEL1 and grund.startswith("ElevenLabs-Guthaben zu klein (100 von")
    e = _e(u, REEL1)
    assert e["version"] == 1 and e["notizen"][0]["text"] == "Alles neu"
    assert u.telegram.aufrufe == []


def test_neubau_scheitert_alte_version_bleibt(gesendet, briefkasten, monkeypatch):
    u, a = gesendet
    ordner = Path(_thema(u, "notgroschen-beispiel")["ordner"])
    slides = sorted(p.name for p in ordner.glob("slide-*.png"))

    def kaputt(*args, **kwargs):
        (ordner / "slide-01.png").unlink()
        raise RenderFehler("Chromium abgestürzt")
    monkeypatch.setattr(entscheide, "baue_karussell", kaputt)
    briefkasten.ereignis("aendern", beitrag=KARUSSELL, notiz="Kürzer")
    log = []
    assert _lauf(u, a, briefkasten, log=log) == 1
    assert briefkasten.fehler_gemeldet == [(KARUSSELL, "Chromium abgestürzt")]
    assert sorted(p.name for p in ordner.glob("slide-*.png")) == slides
    e = _e(u, KARUSSELL)
    assert (e["version"], e["status"]) == (1, "entwurf") and e["notizen"][0]["text"] == "Kürzer"
    assert any("Neubau gescheitert" in z for z in log)


def test_senden_scheitert_alte_version_bleibt(gesendet, briefkasten):
    u, a = gesendet
    u.telegram.scheitern_bei = "sendMediaGroup"
    briefkasten.ereignis("aendern", beitrag=KARUSSELL, notiz="Kürzer")
    assert _lauf(u, a, briefkasten) == 1
    assert briefkasten.fehler_gemeldet[0][0] == KARUSSELL
    assert _e(u, KARUSSELL)["version"] == 1
    assert _thema(u, "notgroschen-beispiel")["beitrag"].endswith("notgroschen-beispiel.md")


def test_veraltetes_ereignis_baut_nicht_nochmals(gesendet, briefkasten):
    """Wiederholung nach erfolgreichem Neubau (Absturz vor merke): Version 1 ist veraltet, kein zweiter Neubau."""
    u, a = gesendet
    briefkasten.ereignis("aendern", beitrag=KARUSSELL, notiz="Kürzer")
    assert _lauf(u, a, briefkasten) == 1
    auftraege = len(a.auftraege)
    briefkasten.stand["entscheide"] = 0
    log = []
    assert _lauf(u, a, briefkasten, log=log) == 1
    assert len(a.auftraege) == auftraege and _e(u, KARUSSELL)["version"] == 2
    assert len(_e(u, KARUSSELL)["notizen"]) == 1 and any("veraltet" in z for z in log)


def test_wiederholung_nach_fehler_meldet_nicht_doppelt(gesendet, briefkasten, monkeypatch):
    u, a = gesendet

    def kaputt(*args, **kwargs):
        raise RenderFehler("Chromium abgestürzt")
    monkeypatch.setattr(entscheide, "baue_karussell", kaputt)
    briefkasten.ereignis("aendern", beitrag=KARUSSELL, notiz="Kürzer")
    assert _lauf(u, a, briefkasten) == 1
    briefkasten.stand["entscheide"] = 0
    log = []
    assert _lauf(u, a, briefkasten, log=log) == 1
    assert len(briefkasten.fehler_gemeldet) == 1 and len(_e(u, KARUSSELL)["notizen"]) == 1
    assert any("schon umgesetzt" in z for z in log)


def test_zeit_abgelaufen_gilt_als_fehler(gesendet, briefkasten, monkeypatch):
    """Sonst hinge jeder Lauf endlos am selben Ereignis."""
    from lib.claude_lauf import ZeitAbgelaufen
    u, a = gesendet

    def zu_spaet(*args, **kwargs):
        raise ZeitAbgelaufen("Zeit abgelaufen")
    monkeypatch.setattr(texter, "ueberarbeite", zu_spaet)
    briefkasten.ereignis("aendern", beitrag=KARUSSELL, notiz="Kürzer")
    assert _lauf(u, a, briefkasten) == 1
    assert briefkasten.stand["entscheide"] == 1
    assert briefkasten.fehler_gemeldet == [(KARUSSELL, "Überarbeitung hat zu lange gedauert")]
    e = _e(u, KARUSSELL)
    assert (e["version"], e["neubauten"]) == (1, 0) and len(e["notizen"]) == 1


def test_neue_fassung_mit_platzhalter(gesendet, briefkasten, monkeypatch):
    u, a = gesendet
    original = texter.ueberarbeite

    def mit_platzhalter(thema, notiz, pfade, lauf, **kw):
        neu = original(thema, notiz, pfade, lauf, **kw)
        text = neu.read_text(encoding="utf-8")
        assert "## Caption\n" in text
        neu.write_text(text.replace("## Caption\n", "## Caption\n[Zahl einsetzen] ", 1), encoding="utf-8")
        return neu
    monkeypatch.setattr(texter, "ueberarbeite", mit_platzhalter)
    ordner = Path(_thema(u, "notgroschen-beispiel")["ordner"])
    vorher = {p.name: p.stat().st_mtime_ns for p in ordner.iterdir()}
    briefkasten.ereignis("aendern", beitrag=KARUSSELL, notiz="Mit Zahl")
    assert _lauf(u, a, briefkasten) == 1
    id, grund = briefkasten.fehler_gemeldet[0]
    assert id == KARUSSELL and grund.startswith("Neue Fassung hat noch Platzhalter (Caption: [Zahl einsetzen]")
    assert grund.endswith("Bitte per ✏️ Ändern angeben, was dort stehen soll, frühere Notizen zählen mit.")
    e = _e(u, KARUSSELL)
    assert (e["version"], e["neubauten"], e["status"]) == (1, 0, "entwurf")
    assert {p.name: p.stat().st_mtime_ns for p in ordner.iterdir()} == vorher
    assert u.telegram.aufrufe == []


def test_senden_scheitert_rettet_neue_stimme(gesendet, briefkasten):
    u, a = gesendet
    u.telegram.scheitern_bei = "sendVideo"
    ordner = Path(_thema(u, "beispiel-reel-eins")["ordner"])
    alt = sorted(p.name for p in ordner.rglob("*"))
    briefkasten.ereignis("aendern", beitrag=REEL1, notiz="Hook kürzer")
    assert _lauf(u, a, briefkasten) == 1
    assert briefkasten.fehler_gemeldet[0][0] == REEL1
    assert sorted(p.name for p in ordner.rglob("*")) == alt
    gerettet = u.pfade.basis / "zwischenspeicher" / REEL1
    assert any(gerettet.glob("szene-*.mp3"))
    e = _e(u, REEL1)
    assert (e["version"], e["neubauten"], e["notizen"][0]["text"]) == (1, 0, "Hook kürzer")


def test_freigabe_felder_vor_dem_senden(gesendet, briefkasten, monkeypatch):
    """Der Bauer ersetzt den Manifest-Eintrag. Beim Senden stehen die Freigabe-Felder schon wieder drin."""
    u, a = gesendet
    gesehen = []
    original = entscheide.sende_beitrag

    def schau(t, woche, pfade, dienste):
        gesehen.append(_e(u, KARUSSELL))
        original(t, woche, pfade, dienste)
    monkeypatch.setattr(entscheide, "sende_beitrag", schau)
    briefkasten.ereignis("aendern", beitrag=KARUSSELL, notiz="Kürzer")
    assert _lauf(u, a, briefkasten) == 1
    e = gesehen[0]
    assert e["notizen"][0]["text"] == "Kürzer" and e["notiz_nr"] == 1 and e["version"] == 1


def test_hoechstens_zwei_neubauten(gesendet, briefkasten):
    u, a = gesendet
    from lib.freigabe import aendere
    aendere(manifest_pfad(u.pfade, WOCHE), WOCHE, KARUSSELL, neubauten=2)
    auftraege = len(a.auftraege)
    briefkasten.ereignis("aendern", beitrag=KARUSSELL, notiz="Nochmals")
    assert _lauf(u, a, briefkasten) == 1
    assert briefkasten.fehler_gemeldet[0][0] == KARUSSELL and "Neubauten" in briefkasten.fehler_gemeldet[0][1]
    assert len(a.auftraege) == auftraege and _e(u, KARUSSELL)["version"] == 1


def test_fehlermeldung_wird_nachgeholt(gesendet, briefkasten, monkeypatch):
    u, a = gesendet

    def kaputt(*args, **kwargs):
        raise RenderFehler("Chromium abgestürzt")
    monkeypatch.setattr(entscheide, "baue_karussell", kaputt)
    briefkasten.ereignis("aendern", beitrag=KARUSSELL, notiz="Kürzer")
    original = briefkasten.fehler

    def weg(id, grund):
        from lib.briefkasten import BriefkastenFehler
        raise BriefkastenFehler("nicht erreichbar")
    briefkasten.fehler = weg
    assert _lauf(u, a, briefkasten) == 1
    assert briefkasten.fehler_gemeldet == []
    briefkasten.fehler = original
    briefkasten.stand["entscheide"] = 0
    assert _lauf(u, a, briefkasten) == 1
    assert briefkasten.fehler_gemeldet == [(KARUSSELL, "Chromium abgestürzt")]
    briefkasten.stand["entscheide"] = 0
    assert _lauf(u, a, briefkasten) == 1
    assert len(briefkasten.fehler_gemeldet) == 1


def test_art_ohne_aktion(gesendet, briefkasten, monkeypatch):
    u, a = gesendet
    monkeypatch.delitem(entscheide.AKTIONEN, "aendern")
    briefkasten.ereignis("aendern", beitrag=KARUSSELL, notiz="Kürzer")
    log = []
    assert _lauf(u, a, briefkasten, log=log) == 1
    assert any("nicht unterstützt" in z for z in log)


def test_termin_vorbei_kein_neubau(gesendet, briefkasten):
    """Termin erreicht: kein Neubau (keine Kosten), nur Log und Ereignis als umgesetzt merken. Der Server setzt
    den Beitrag ohnehin auf verpasst."""
    u, a = gesendet
    auftraege = len(a.auftraege)
    nr = briefkasten.ereignis("aendern", beitrag=REEL1, notiz="Hook kürzer")
    log = []
    dienste = u.dienste(a, jetzt=datetime(2026, 10, 27, 19, 0), briefkasten=briefkasten)
    assert entscheide.entscheide(u.pfade, dienste, log.append) == 1
    assert len(a.auftraege) == auftraege
    e = _e(u, REEL1)
    assert (e["version"], e["neubauten"], e["umgesetzt_nr"]) == (1, 0, nr)
    assert briefkasten.fehler_gemeldet == [] and u.telegram.aufrufe == []
    assert any("Termin vorbei" in z for z in log)
    assert e["notizen"] == [{"zeit": "2026-10-25T09:00:00+01:00", "text": "Hook kürzer"}]   # für Etappe 6
    briefkasten.stand["entscheide"] = 0   # Wiederholung: Notiz nicht doppelt
    assert entscheide.entscheide(u.pfade, dienste, log.append) == 1
    assert len(_e(u, REEL1)["notizen"]) == 1


def test_fehlermeldung_wird_ohne_wiederholung_nachgeholt(gesendet, briefkasten, monkeypatch):
    """Scheitert die Meldung «Neubau gescheitert», holt der nächste Lauf sie nach, auch ohne dass das
    Ereignis nochmals kommt. Danach nicht doppelt."""
    u, a = gesendet

    def kaputt(*args, **kwargs):
        raise RenderFehler("Chromium abgestürzt")
    monkeypatch.setattr(entscheide, "baue_karussell", kaputt)
    briefkasten.ereignis("aendern", beitrag=KARUSSELL, notiz="Kürzer")
    original = briefkasten.fehler

    def weg(id, grund):
        from lib.briefkasten import BriefkastenFehler
        raise BriefkastenFehler("nicht erreichbar")
    briefkasten.fehler = weg
    assert _lauf(u, a, briefkasten) == 1
    assert briefkasten.fehler_gemeldet == [] and _e(u, KARUSSELL)["fehler_gemeldet"] is False
    briefkasten.fehler = original
    log = []
    assert _lauf(u, a, briefkasten, log=log) == 0
    assert briefkasten.fehler_gemeldet == [(KARUSSELL, "Chromium abgestürzt")]
    assert _e(u, KARUSSELL)["fehler_gemeldet"] is True
    assert _lauf(u, a, briefkasten) == 0
    assert len(briefkasten.fehler_gemeldet) == 1


def _braucht_eingabe(u, id=KARUSSELL, offen=("Slide 3: [Betrag in Fr.]",)):
    """Manifest-Eintrag wie nach einem Bau mit Platzhaltern (Status braucht_eingabe)."""
    from lib import freigabe
    freigabe.aendere(manifest_pfad(u.pfade, WOCHE), WOCHE, id, status="braucht_eingabe",
                     pruefungen={"platzhalter": list(offen)})


def test_aendern_braucht_eingabe_ohne_platzhalter_wird_entwurf(gesendet, briefkasten):
    u, a = gesendet
    _braucht_eingabe(u)
    briefkasten.ereignis("aendern", beitrag=KARUSSELL, notiz="Betrag: 3000 Fr.")
    assert _lauf(u, a, briefkasten) == 1
    _, auftrag = _letzter(a)
    assert "Slide 3: [Betrag in Fr.]" in auftrag and "Platzhalter" in auftrag
    e = _e(u, KARUSSELL)
    assert (e["status"], e["version"], e["neubauten"]) == ("entwurf", 2, 1)
    assert (briefkasten.gemeldet[-1]["id"], briefkasten.gemeldet[-1]["version"],
            briefkasten.gemeldet[-1]["platzhalter"]) == (KARUSSELL, 2, False)
    assert briefkasten.fehler_gemeldet == []


def test_aendern_braucht_eingabe_immer_noch_platzhalter(gesendet, briefkasten, monkeypatch):
    u, a = gesendet
    _braucht_eingabe(u)
    original = texter.ueberarbeite

    def mit_platzhalter(thema, notiz, pfade, lauf, **kw):
        neu = original(thema, notiz, pfade, lauf, **kw)
        text = neu.read_text(encoding="utf-8")
        neu.write_text(text.replace("## Caption\n", "## Caption\n[Betrag in Fr.] ", 1), encoding="utf-8")
        return neu
    monkeypatch.setattr(texter, "ueberarbeite", mit_platzhalter)
    briefkasten.ereignis("aendern", beitrag=KARUSSELL, notiz="Mach es schöner")
    assert _lauf(u, a, briefkasten) == 1
    (id, grund), = briefkasten.fehler_gemeldet
    assert id == KARUSSELL and "Caption: [Betrag in Fr.]" in grund and "was dort stehen soll" in grund
    e = _e(u, KARUSSELL)
    assert (e["status"], e["version"], e["neubauten"]) == ("braucht_eingabe", 1, 0)
    assert briefkasten.gemeldet == []


def test_zweite_aendern_runde_bekommt_alle_notizen(gesendet, briefkasten, monkeypatch):
    """Notiz 1 füllt A, B fehlt noch: abgelehnt. Notiz 2 füllt B: der Agent bekommt beide Notizen (älteste
    zuerst), die neue Fassung wird entwurf. Nach dem Versionswechsel zählen die alten Notizen nicht mehr."""
    u, a = gesendet
    _braucht_eingabe(u, offen=("Slide 3: [A]", "Caption: [B]"))
    original = texter.ueberarbeite
    runde = []

    def erst_b_offen(thema, notiz, pfade, lauf, **kw):
        neu = original(thema, notiz, pfade, lauf, **kw)
        runde.append(1)
        if len(runde) == 1:
            text = neu.read_text(encoding="utf-8")
            neu.write_text(text.replace("## Caption\n", "## Caption\n[B] ", 1), encoding="utf-8")
        return neu
    monkeypatch.setattr(texter, "ueberarbeite", erst_b_offen)
    briefkasten.ereignis("aendern", beitrag=KARUSSELL, notiz="A ist 3000 Fr.")
    assert _lauf(u, a, briefkasten) == 1
    (_, grund), = briefkasten.fehler_gemeldet
    assert "Caption: [B]" in grund and "Slide 3: [A]" in grund and "frühere Notizen zählen mit" in grund
    briefkasten.ereignis("aendern", beitrag=KARUSSELL, notiz="B ist 12 Monate", zeit="2026-10-25T10:00:00+01:00")
    assert _lauf(u, a, briefkasten) == 1
    _, auftrag = _letzter(a)
    assert auftrag.index("A ist 3000 Fr.") < auftrag.index("B ist 12 Monate")
    e = _e(u, KARUSSELL)
    assert (e["status"], e["version"], len(e["notizen"]), e["notizen_ab"]) == ("entwurf", 2, 2, 2)
    briefkasten.ereignis("aendern", beitrag=KARUSSELL, version=2, notiz="Slide 1 kürzer",
                         zeit="2026-10-25T11:00:00+01:00")
    assert _lauf(u, a, briefkasten) == 1
    _, auftrag = _letzter(a)
    assert "Slide 1 kürzer" in auftrag and "A ist 3000 Fr." not in auftrag and "B ist 12 Monate" not in auftrag


def test_aendern_reel_behaelt_laenge_und_merkt_neue_dauer(gesendet, briefkasten):
    u, a = gesendet
    plan = Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE)
    t = next(t for t in plan.themen if t["slug"] == "beispiel-reel-eins")
    t["dauer_s"] = 999.0   # alte Dauer: der Hinweis darf nicht darauf beruhen
    plan.speichere()
    briefkasten.ereignis("aendern", beitrag=REEL1, notiz="Hook kürzer")
    assert _lauf(u, a, briefkasten) == 1
    e, t = _e(u, REEL1), _thema(u, "beispiel-reel-eins")
    assert e["version"] == 2 and e["laenge"] == t["laenge"]
    assert t["dauer_s"] == e["dauer_s"] != 999.0
    assert not any("⚠️ Reel ist" in x for x in u.telegram.texte())


def _weg(x):
    """Entfernt die Längenfelder rekursiv (alte Manifeste kannten sie nicht)."""
    if isinstance(x, dict):
        x.pop("laenge", None)
        x.pop("dauer_s", None)
        for v in x.values():
            _weg(v)
    elif isinstance(x, list):
        for v in x:
            _weg(v)


def _ohne_laenge(u):
    """Macht Plan und Manifest zu einem Stand aus der Zeit vor Etappe 7."""
    plan = Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE)
    for t in plan.themen + plan.daten["reserve"]:
        t.pop("laenge", None)
        t.pop("dauer_s", None)
    plan.speichere()
    p = manifest_pfad(u.pfade, WOCHE)
    d = json.loads(p.read_text(encoding="utf-8"))
    _weg(d)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def test_aendern_reel_alte_daten_ohne_laenge(gesendet, briefkasten):
    u, a = gesendet
    _ohne_laenge(u)
    briefkasten.ereignis("aendern", beitrag=REEL1, notiz="Hook kürzer")
    assert _lauf(u, a, briefkasten) == 1
    e = _e(u, REEL1)
    assert e["version"] == 2 and "laenge" not in e
    auftrag = [t for ag, t in a.auftraege if ag == "content-agent"][-1]
    assert "170 Wörter" in auftrag
    assert not any("⚠️ Reel ist" in x for x in u.telegram.texte())


def _wort_aus(beitrag):
    """Ein Wort des ersten Sprechtexts, das nicht auf aussprache.txt steht."""
    bekannt = set(lade_aussprache(reel_bauer.PROJEKT / "aussprache.txt"))
    for token in lese_reel(Path(beitrag)).szenen[0].sprechtext.split():
        kern = SATZZEICHEN.match(token).group(2)
        if kern.isalpha() and kern not in bekannt:
            return kern
    raise AssertionError("kein passendes Wort")


def test_aendern_reel_meldet_neue_aussprache(gesendet, briefkasten):
    u, a = gesendet
    wort = _wort_aus(_thema(u, "beispiel-reel-eins")["beitrag"])
    a.aussprache_funde = [{"wort": wort, "ersatz": "Ersatzwort", "grund": "Test"}]
    (u.pfade.daten / "aussprache-auto.txt").unlink(missing_ok=True)
    briefkasten.ereignis("aendern", beitrag=REEL1, notiz="Hook kürzer")
    assert _lauf(u, a, briefkasten) == 1
    t = _thema(u, "beispiel-reel-eins")
    assert t["aussprache_neu"] == [[wort, "Ersatzwort"]]
    assert f"🗣 Neu für die Stimme: {wort} → Ersatzwort" in u.telegram.texte()


def test_aendern_fehler_stellt_aussprache_zurueck(gesendet, briefkasten, monkeypatch):
    u, a = gesendet
    wort = _wort_aus(_thema(u, "beispiel-reel-eins")["beitrag"])
    a.aussprache_funde = [{"wort": wort, "ersatz": "Ersatzwort", "grund": "Test"}]
    (u.pfade.daten / "aussprache-auto.txt").unlink(missing_ok=True)
    plan = Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE)
    t = next(t for t in plan.themen if t["slug"] == "beispiel-reel-eins")
    t["aussprache_neu"] = [["Alt", "Wort"]]
    plan.speichere()
    gesehen = []

    def kaputt(thema, *args, **kwargs):
        gesehen.append((thema, [list(p) for p in thema["aussprache_neu"]]))
        raise RenderFehler("Telegram weg")
    monkeypatch.setattr(entscheide, "sende_beitrag", kaputt)
    briefkasten.ereignis("aendern", beitrag=REEL1, notiz="Hook kürzer")
    _lauf(u, a, briefkasten)
    thema, beim_senden = gesehen[0]
    assert beim_senden == [[wort, "Ersatzwort"]]   # der neue Wert war gesetzt
    assert thema["aussprache_neu"] == [["Alt", "Wort"]]   # und ist zurückgestellt


def test_aendern_ohne_neue_funde_sendet_keine_aussprachezeile(gesendet, briefkasten):
    u, a = gesendet
    plan = Wochenplan.lade(u.pfade.plan(WOCHE), WOCHE)
    t = next(t for t in plan.themen if t["slug"] == "beispiel-reel-eins")
    t["aussprache_neu"] = [["Alt", "Wort"]]
    plan.speichere()
    a.aussprache_funde = []
    briefkasten.ereignis("aendern", beitrag=REEL1, notiz="Hook kürzer")
    assert _lauf(u, a, briefkasten) == 1
    assert _thema(u, "beispiel-reel-eins")["aussprache_neu"] == []
    assert "🗣" not in "\n".join(u.telegram.texte())


def test_aendern_ohne_start_korrektur_und_standardsatz(gesendet, briefkasten):
    from lib.pruefungen import START_STANDARD
    u, a = gesendet
    echt = a.claude

    def ohne_start(agent, auftrag, ausgabe, *args, **kwargs):
        pfad = echt(agent, auftrag, ausgabe, *args, **kwargs)
        if agent == "content-agent":
            pfad.write_text(pfad.read_text(encoding="utf-8").replace("START", "Start"), encoding="utf-8")
        return pfad

    a.claude = ohne_start
    vorher = a.anzahl("content-agent")
    briefkasten.ereignis("aendern", beitrag=KARUSSELL, notiz="Slide 3 ist zu voll")
    assert _lauf(u, a, briefkasten) == 1
    assert a.anzahl("content-agent") == vorher + 2                  # Korrekturlauf wegen START
    assert "Kommentiere START" in _letzter(a)[1]
    t = _thema(u, "notgroschen-beispiel")
    assert START_STANDARD in (Path(t["ordner"]) / "caption.txt").read_text(encoding="utf-8")
    assert "START-Satz in der Caption ergänzt" in t["vermerk"]
    assert t["vermerk"].count("START-Satz in der Caption ergänzt") == 1       # nicht doppelt
    assert t["vermerk"].count("START fehlt am Schluss") == 1                  # Schluss ohne START: Vermerk
