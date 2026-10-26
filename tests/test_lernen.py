import json
from datetime import date, datetime
from pathlib import Path

import pytest

from lib import lernen
from lib.freigabe import manifest_pfad
from lib.manifest import schreibe_json
from lib.umgebung import Pfade

JETZT = datetime(2026, 10, 30, 20, 0)


@pytest.fixture
def pfade(tmp_path):
    return Pfade(basis=tmp_path / "fb", agentur=tmp_path / "agentur", skill=tmp_path / "skill",
                 agentur_python=tmp_path / "kein-python")


def _woche(pfade, woche, themen, beitraege):
    """Plan und Manifest einer Woche, so knapp wie nötig."""
    schreibe_json(pfade.plan(woche), {"woche": woche, "schritte": {}, "vermerke": [], "ausreisser": [],
                                      "themen": themen, "reserve": []})
    schreibe_json(manifest_pfad(pfade, woche), {"woche": woche, "beitraege": beitraege})


def _thema(nr, format, termin, slug, status="gesendet"):
    return {"nr": nr, "format": format, "termin": termin, "slug": slug, "thema": f"Thema {slug}",
            "quelle": {"art": "ideen", "detail": "x"}, "hook_idee": f"Hook {slug}", "status": status}


def test_faellig_und_stand(pfade):
    assert lernen.faellig(pfade, "2026-KW45")
    lernen.schreibe_stand(pfade, "2026-KW45", JETZT, "fehler", "weg")
    assert not lernen.faellig(pfade, "2026-KW45")
    assert lernen.faellig(pfade, "2026-KW46")
    assert json.loads((pfade.daten / "lernen.json").read_text()) == {
        "woche": "2026-KW45", "zeit": "2026-10-30T20:00:00", "ergebnis": "fehler", "grund": "weg"}


def test_faellig_bei_kaputtem_stand(pfade):
    pfade.daten.mkdir(parents=True)
    (pfade.daten / "lernen.json").write_text("kaputt")
    assert lernen.faellig(pfade, "2026-KW45")


def test_fliessband_beitraege_der_letzten_28_tage(pfade):
    _woche(pfade, "2026-KW44",
           [_thema(1, "reel", "2026-10-27T19:00", "a"), _thema(2, "karussell", "2026-10-28T19:00", "b"),
            _thema(4, "karussell", "2026-10-31T19:00", "zukunft")],
           [{"id": "2026-KW44-reel-a", "status": "gepostet", "instagram_id": "m3",
             "notizen": [{"zeit": "2026-10-25T09:00", "text": "Hook kürzer"}]},
            {"id": "2026-KW44-b", "status": "verworfen", "notizen": []}])
    _woche(pfade, "2026-KW39", [_thema(1, "reel", "2026-09-22T19:00", "alt")], [])
    (pfade.basis / "wochen" / "2026-KW40").mkdir(parents=True)   # leerer Ordner stört nicht
    liste = lernen.fliessband_beitraege(pfade, JETZT)
    assert [b["id"] for b in liste] == ["2026-KW44-reel-a", "2026-KW44-b"]
    assert liste[0] == {"id": "2026-KW44-reel-a", "woche": "2026-KW44", "titel": "Thema a", "format": "reel",
                        "termin": "2026-10-27T19:00", "hook_idee": "Hook a", "quelle": "ideen",
                        "status": "gepostet", "notizen": ["Hook kürzer"], "instagram_id": "m3",
                        "laenge": "lang (vor Etappe 7)", "dauer_s": None,
                        "einstieg": None, "einladung": "ohne Einladung (vor Etappe 9)"}
    assert liste[1]["status"] == "verworfen" and liste[1]["instagram_id"] is None
    assert liste[1]["laenge"] is None and liste[1]["dauer_s"] is None


def test_fliessband_beitraege_ohne_wochen(pfade):
    assert lernen.fliessband_beitraege(pfade, JETZT) == []


def test_verbinde():
    zahlen = [{"ig_id": "m3", "werte": {}}, {"ig_id": "m9", "werte": {}}]
    beitraege = [{"id": "x", "instagram_id": "m3"}, {"id": "y", "instagram_id": None}]
    verbunden = lernen.verbinde(zahlen, beitraege)
    assert verbunden[0]["fliessband"] == {"id": "x", "instagram_id": "m3"}
    assert verbunden[1]["fliessband"] is None


ALT = "# Learnings\n\n## Stand 14.10.2026 (Ersteinrichtung)\n" + "Beobachtung mit Beleg.\n" * 20
HEUTE = date(2026, 10, 30)


def test_pruefe_besteht():
    neu = ALT + "\n## Stand 30.10.2026 (Lern-Schleife)\nNeu.\n"
    assert lernen.pruefe(ALT, neu, HEUTE) is None


def test_pruefe_ueberschrift_fehlt():
    neu = ALT.replace("## Stand 14.10.2026 (Ersteinrichtung)", "Weg") + "\n## Stand 30.10.2026 (Lern-Schleife)\n"
    assert lernen.pruefe(ALT, neu, HEUTE) == "Überschrift fehlt: ## Stand 14.10.2026 (Ersteinrichtung)"


def test_pruefe_zu_kurz():
    neu = "# Learnings\n## Stand 14.10.2026 (Ersteinrichtung)\n## Stand 30.10.2026 (Lern-Schleife)\n"
    assert lernen.pruefe(ALT, neu, HEUTE) == "neue learnings.md ist zu kurz"


def test_pruefe_ohne_neuen_abschnitt():
    assert lernen.pruefe(ALT, ALT + "mehr\n", HEUTE) == "Abschnitt «Stand 30.10.2026» fehlt"


def test_auftrag_nennt_pfade_und_regeln(pfade, tmp_path):
    text = lernen.auftrag(pfade, tmp_path / "daten.json", tmp_path / "learnings.md", tmp_path / "bericht.json", HEUTE)
    for teil in (str(tmp_path / "daten.json"), str(tmp_path / "learnings.md"), str(tmp_path / "bericht.json"),
                 str(pfade.regelwerk), str(pfade.agentur / "profil.md"), "## Stand 30.10.2026 (Lern-Schleife)",
                 "## Aus Betreiber-Änderungen", "widerlegt", "Hinweis", "Kein Wochenplan", '"erkenntnisse"'):
        assert teil in text


def test_bericht_text():
    text = lernen.bericht_text({"erkenntnisse": ["A", "B", "C", "D"],
                                "bester": {"titel": "Reel X", "grund": "doppelte Reichweite"},
                                "schwaechster": {"titel": "Karussell Y", "grund": "kaum Aufrufe"},
                                "aenderungen": ["Neue Vorgabe: Hook kürzer"]})
    assert text == ("📈 Lern-Schleife\n\nWichtigste Erkenntnisse:\n• A\n• B\n• C\n\n"
                    "Bester Beitrag: «Reel X»\ndoppelte Reichweite\n\n"
                    "Schwächster Beitrag: «Karussell Y»\nkaum Aufrufe\n\n"
                    "Neu in learnings.md:\n• Neue Vorgabe: Hook kürzer")


@pytest.mark.parametrize("bericht", [None, [], {"erkenntnisse": "keine Liste"}])
def test_bericht_text_ersatz(bericht):
    assert lernen.bericht_text(bericht) == lernen.OHNE_BERICHT


class FalscherLauf:
    """Ersatz für den Claude-Lauf: schreibt learnings (Text, None = unverändert) ins Ziel aus dem Auftrag und den
    Bericht (dict, Text, None = nicht schreiben). fehler: Ausnahme nach dem Schreiben der learnings."""

    def __init__(self, learnings=None, bericht=None, fehler=None):
        self.learnings, self.bericht, self.fehler, self.aufrufe = learnings, bericht, fehler, []

    def __call__(self, agent, auftrag, ausgabe, werkzeuge=(), ordner=(), zeitlimit=None):
        self.aufrufe.append((agent, auftrag, ausgabe, tuple(werkzeuge), tuple(ordner), zeitlimit))
        ziel = Path(auftrag.split("Lies zuerst: ")[1].split(" (bisherige")[0])
        if self.learnings is not None:
            ziel.write_text(self.learnings, encoding="utf-8")
        if self.fehler is not None:
            raise self.fehler
        if self.bericht is not None:
            text = self.bericht if isinstance(self.bericht, str) else json.dumps(self.bericht)
            Path(ausgabe).write_text(text, encoding="utf-8")
        return ausgabe


NEU = ALT + "\n## Stand 30.10.2026 (Lern-Schleife)\nNeu.\n"
BERICHT = {"erkenntnisse": ["A"], "aenderungen": []}


@pytest.fixture
def lern(wochen_umgebung, agentur_attrappe, briefkasten):
    u = wochen_umgebung
    u.pfade.agentur.mkdir(parents=True, exist_ok=True)
    (u.pfade.agentur / "learnings.md").write_text(ALT, encoding="utf-8")
    briefkasten.zahlen_liste = [{"ig_id": "m1", "werte": {"reach": 10}}]

    def starte(lauf, probe=False, mit_briefkasten=True):
        d = u.dienste(agentur_attrappe(), jetzt=JETZT, briefkasten=briefkasten if mit_briefkasten else None)
        d.claude = lauf
        log = []
        return lernen.lauf(u.pfade, d, "2026-KW45", log.append, probe=probe), log

    return starte


def _gesendet(u):
    return [f["text"] for m, f, _ in u.telegram.aufrufe if m == "sendMessage"]


def _learnings(u):
    return (u.pfade.agentur / "learnings.md").read_text(encoding="utf-8")


def test_lauf_ok(lern, wochen_umgebung):
    u = wochen_umgebung
    lauf = FalscherLauf(NEU, BERICHT)
    ergebnis, _ = lern(lauf)
    assert ergebnis == "ok" and _learnings(u) == NEU
    assert (u.pfade.agentur / "learnings.2026-10-30.md").read_text(encoding="utf-8") == ALT
    agent, _, ausgabe, werkzeuge, ordner, zeitlimit = lauf.aufrufe[0]
    assert agent == "analyse-agent" and Path(ausgabe).name == "bericht-2026-10-30.json"
    assert werkzeuge == ("Read", "Write", "Edit") and zeitlimit == 900
    assert ordner == (u.pfade.skill, u.pfade.daten / "lernen")
    daten = json.loads((u.pfade.daten / "lernen" / "daten-2026-10-30.json").read_text())
    assert daten["instagram"] == [{"ig_id": "m1", "werte": {"reach": 10}, "fliessband": None}]
    assert _gesendet(u) == [lernen.bericht_text(BERICHT)]
    assert not lernen.faellig(u.pfade, "2026-KW45")


def test_sicherung_wird_nicht_ueberschrieben(lern, wochen_umgebung):
    u = wochen_umgebung
    (u.pfade.agentur / "learnings.2026-10-30.md").write_text("früher", encoding="utf-8")
    lern(FalscherLauf(NEU, BERICHT))
    assert (u.pfade.agentur / "learnings.2026-10-30.md").read_text(encoding="utf-8") == "früher"


def test_pruefung_scheitert_legt_zurueck(lern, wochen_umgebung):
    u = wochen_umgebung
    ergebnis, _ = lern(FalscherLauf("# kaputt\n", BERICHT))
    assert ergebnis == "zurueckgelegt" and _learnings(u) == ALT
    assert _gesendet(u)[0].startswith("⚠️ Lern-Schleife: learnings.md zurückgelegt")
    assert json.loads((u.pfade.daten / "lernen.json").read_text())["ergebnis"] == "zurueckgelegt"


def test_claude_fehler_legt_zurueck_und_meldet(lern, wochen_umgebung):
    from lib.claude_lauf import ClaudeFehler
    u = wochen_umgebung
    ergebnis, _ = lern(FalscherLauf("# halb geschrieben\n", fehler=ClaudeFehler("analyse-agent: keine Antwort")))
    assert ergebnis == "fehler" and _learnings(u) == ALT
    assert _gesendet(u) == ["⚠️ Lern-Schleife ausgefallen: analyse-agent: keine Antwort"]
    assert not lernen.faellig(u.pfade, "2026-KW45")


def test_server_weg(lern, wochen_umgebung, briefkasten):
    u = wochen_umgebung
    briefkasten.nicht_erreichbar = True
    lauf = FalscherLauf(NEU, BERICHT)
    ergebnis, _ = lern(lauf)
    assert ergebnis == "fehler" and lauf.aufrufe == [] and _learnings(u) == ALT
    assert "nicht erreichbar" in _gesendet(u)[0]


def test_learnings_fehlt(lern, wochen_umgebung):
    u = wochen_umgebung
    (u.pfade.agentur / "learnings.md").unlink()
    ergebnis, _ = lern(FalscherLauf(NEU, BERICHT))
    assert ergebnis == "fehler" and _gesendet(u) == ["⚠️ Lern-Schleife ausgefallen: learnings.md fehlt"]


def test_kaputter_bericht_behaelt_learnings(lern, wochen_umgebung):
    u = wochen_umgebung
    ergebnis, _ = lern(FalscherLauf(NEU, "kein json"))
    assert ergebnis == "ok" and _learnings(u) == NEU and _gesendet(u) == [lernen.OHNE_BERICHT]


def test_probe_aendert_nichts(lern, wochen_umgebung):
    u = wochen_umgebung
    text, log = lern(FalscherLauf(NEU, BERICHT), probe=True)
    assert text == lernen.bericht_text(BERICHT) and text in log
    assert _learnings(u) == ALT and _gesendet(u) == []
    assert not (u.pfade.agentur / "learnings.2026-10-30.md").exists()
    assert lernen.faellig(u.pfade, "2026-KW45")
    assert (u.pfade.daten / "lernen" / "probe-learnings.md").read_text(encoding="utf-8") == NEU


def test_ohne_briefkasten_uebersprungen(lern, wochen_umgebung):
    u = wochen_umgebung
    ergebnis, log = lern(FalscherLauf(NEU, BERICHT), mit_briefkasten=False)
    assert ergebnis == "uebersprungen" and _gesendet(u) == [] and lernen.faellig(u.pfade, "2026-KW45")
    assert log == ["Lern-Schleife übersprungen: Briefkasten nicht eingerichtet"]


def test_bericht_nicht_gesendet_nur_log(lern, wochen_umgebung):
    u = wochen_umgebung
    u.telegram.scheitern_bei = "sendMessage"
    ergebnis, log = lern(FalscherLauf(NEU, BERICHT))
    assert ergebnis == "ok" and any("nicht gesendet" in z for z in log)


def test_fliessband_beitraege_ueberspringt_kaputtes(pfade):
    kaputt = {"nr": 3, "format": "reel", "termin": "kein Datum", "slug": "k", "thema": "x"}
    ohne_thema = {"nr": 4, "format": "reel", "termin": "2026-10-28T19:00", "slug": "o"}
    _woche(pfade, "2026-KW44", [kaputt, "kein dict", ohne_thema, _thema(1, "reel", "2026-10-27T19:00", "a")],
           ["kein dict", {"id": "2026-KW44-reel-a", "status": "gepostet", "instagram_id": "m3", "notizen": []}])
    liste = lernen.fliessband_beitraege(pfade, JETZT)
    assert [b["id"] for b in liste] == ["2026-KW44-reel-a"] and liste[0]["instagram_id"] == "m3"


def test_fliessband_beitraege_manifest_ohne_liste(pfade):
    _woche(pfade, "2026-KW44", [_thema(1, "reel", "2026-10-27T19:00", "a")], "kein Liste")
    liste = lernen.fliessband_beitraege(pfade, JETZT)   # Thema bleibt, ohne Manifest-Angaben
    assert [b["id"] for b in liste] == ["2026-KW44-reel-a"] and liste[0]["instagram_id"] is None


def test_verbinde_ueberspringt_kein_dict():
    assert lernen.verbinde([{"ig_id": "m1"}, "x", None], [{"id": "x", "instagram_id": "m1"}, 5]) == [
        {"ig_id": "m1", "fliessband": {"id": "x", "instagram_id": "m1"}}]


def test_auftrag_ueberschrift_und_schreibgrenze(pfade, tmp_path):
    text = lernen.auftrag(pfade, tmp_path / "d.json", tmp_path / "learnings.md", tmp_path / "b.json", HEUTE)
    assert "\n## Stand 30.10.2026 (Lern-Schleife)\n" in text and "genau so" in text
    assert f"Schreibe ausschliesslich {tmp_path / 'learnings.md'} und {tmp_path / 'b.json'}. " \
           "Ändere keine andere Datei." in text


class Schreiber(FalscherLauf):
    """Wie FalscherLauf, schreibt zusätzlich Dateien (name → Text, None = löschen) relativ zu agentur."""

    def __init__(self, agentur, dateien, **kw):
        super().__init__(**kw)
        self.agentur, self.dateien = agentur, dateien

    def __call__(self, *a, **kw):
        for name, text in self.dateien.items():
            if text is None:
                (self.agentur / name).unlink()
            else:
                (self.agentur / name).write_text(text, encoding="utf-8")
        return super().__call__(*a, **kw)


def test_unerwartete_ausnahme_legt_zurueck_und_meldet(lern, wochen_umgebung):
    u = wochen_umgebung
    ergebnis, _ = lern(FalscherLauf("# halb\n", fehler=RuntimeError("boom")))
    assert ergebnis == "fehler" and _learnings(u) == ALT
    assert _gesendet(u) == ["⚠️ Lern-Schleife ausgefallen: RuntimeError: boom"]
    assert not lernen.faellig(u.pfade, "2026-KW45")


def test_agent_loescht_learnings(lern, wochen_umgebung):
    u = wochen_umgebung
    ergebnis, _ = lern(Schreiber(u.pfade.agentur, {"learnings.md": None}, bericht=BERICHT))
    assert ergebnis in ("fehler", "zurueckgelegt") and _learnings(u) == ALT


def test_agent_aendert_profil(lern, wochen_umgebung):
    u = wochen_umgebung
    (u.pfade.agentur / "profil.md").write_text("Profil", encoding="utf-8")
    ergebnis, _ = lern(Schreiber(u.pfade.agentur, {"profil.md": "kaputt"}, learnings=NEU, bericht=BERICHT))
    assert ergebnis == "fehler" and _learnings(u) == ALT
    assert (u.pfade.agentur / "profil.md").read_text(encoding="utf-8") == "Profil"
    assert _gesendet(u) == ["⚠️ Lern-Schleife ausgefallen: Agent hat profil.md geändert, zurückgelegt"]


def test_agent_loescht_profil(lern, wochen_umgebung):
    u = wochen_umgebung
    (u.pfade.agentur / "profil.md").write_text("Profil", encoding="utf-8")
    ergebnis, _ = lern(Schreiber(u.pfade.agentur, {"profil.md": None}, learnings=NEU, bericht=BERICHT))
    assert ergebnis == "fehler" and (u.pfade.agentur / "profil.md").read_text(encoding="utf-8") == "Profil"


def test_neue_datei_bleibt_wird_gelogged(lern, wochen_umgebung):
    u = wochen_umgebung
    ergebnis, log = lern(Schreiber(u.pfade.agentur, {"neu.md": "x"}, learnings=NEU, bericht=BERICHT))
    assert ergebnis == "ok" and (u.pfade.agentur / "neu.md").exists() and any("neu.md" in z for z in log)


def test_probe_schuetzt_echte_learnings(lern, wochen_umgebung):
    u = wochen_umgebung
    text, _ = lern(Schreiber(u.pfade.agentur, {"learnings.md": "vom Agenten"}, learnings=NEU, bericht=BERICHT),
                   probe=True)
    assert _learnings(u) == ALT and "learnings.md geändert" in text


def test_zuruecklegen_scheitert_wird_gemeldet(lern, wochen_umgebung, monkeypatch):
    u = wochen_umgebung
    echt = Path.write_text

    def schreibe(self, text, *a, **kw):
        if self.name == "learnings.md":
            raise OSError("voll")
        return echt(self, text, *a, **kw)
    lauf = FalscherLauf("# kaputt\n", BERICHT)
    ursprung = lauf.__call__

    def mit_patch(*a, **kw):
        r = ursprung(*a, **kw)
        monkeypatch.setattr(Path, "write_text", schreibe)
        return r
    ergebnis, _ = lern(mit_patch)
    assert ergebnis == "fehler"
    assert _gesendet(u) == ["⚠️ Lern-Schleife: learnings.md konnte nicht zurückgelegt werden, "
                            "Sicherung: learnings.2026-10-30.md"]
    assert json.loads((u.pfade.daten / "lernen.json").read_text())["ergebnis"] == "fehler"


def test_bot_wirft_oserror_lauf_wirft_nicht(lern, wochen_umgebung, monkeypatch):
    from lib.bot import Bot

    def kaputt(self, text):
        raise OSError("platt")
    monkeypatch.setattr(Bot, "sende_text", kaputt)
    ergebnis, log = lern(FalscherLauf(NEU, BERICHT))
    assert ergebnis == "ok" and any("nicht gesendet" in z for z in log)


def test_fliessband_beitraege_mit_laenge_und_dauer(pfade):
    _woche(pfade, "2026-KW44",
           [dict(_thema(1, "reel", "2026-10-27T19:00", "a"), laenge="kurz")],
           [{"id": "2026-KW44-reel-a", "status": "gepostet", "instagram_id": "m3", "dauer_s": 26.4, "notizen": []}])
    b = lernen.fliessband_beitraege(pfade, JETZT)[0]
    assert (b["laenge"], b["dauer_s"]) == ("kurz", 26.4)


def test_auftrag_vergleicht_laengen(pfade, tmp_path):
    text = lernen.auftrag(pfade, tmp_path / "d.json", tmp_path / "l.md", tmp_path / "b.json", JETZT.date())
    assert "laenge (nur Reels)" in text
    assert "Vergleiche Reels nach laenge getrennt" in text


def test_fliessband_beitraege_mit_einstieg(pfade):
    t = dict(_thema(1, "reel", "2026-10-27T19:00", "a"), einstieg="Tom fragt beim Abendessen nach Geld.")
    _woche(pfade, "2026-KW44", [t], [])
    b = lernen.fliessband_beitraege(pfade, JETZT)[0]
    assert (b["einstieg"], b["einladung"]) == ("Tom fragt beim Abendessen nach Geld.", "START")


def test_verbinde_behaelt_start_kommentare():
    v = lernen.verbinde([{"ig_id": "m3", "start_kommentare": 2}], [{"id": "x", "instagram_id": "m3"}])
    assert v[0]["start_kommentare"] == 2


def test_auftrag_vergleicht_start_kommentare(pfade, tmp_path):
    text = lernen.auftrag(pfade, tmp_path / "d.json", tmp_path / "l.md", tmp_path / "b.json", JETZT.date())
    for teil in ("start_kommentare", "START-Kommentare", "ohne Einladung (vor Etappe 9)",
                 "welche Themen und Einstiege START-Kommentare bringen"):
        assert teil in text, teil
