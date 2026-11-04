import json
from pathlib import Path

import pytest

from lib import fakten
from lib.claude_lauf import ClaudeFehler
from lib.fakten import (HOECHSTENS, MARKER, Fund, FaktenUebersprungen, _zahlen, gueltige_funde, hinweis,
                        pruef_text, wende_an)

TEXT = """# Reel: Test

## Voiceover-Text zum Einfügen in ElevenLabs

Die Franchise beträgt 300 Franken.

## Szenen fürs Fliessband

**Szene 1 (Hook)**
Sprechtext: Die Franchise beträgt 300 Franken im Jahr.
Einblendung: Franchise 300

**Szene 2**
Sprechtext: Trading birgt Verlustrisiken. Schreib START in die Kommentare.
Einblendung: Kommentiere START

## Caption

Wusstest du das? Die AHV zahlt ab 70.

Kommentiere START, dann erzähl ich dir mehr.
"""


def _f(stelle, urteil="falsch", korrektur="neu", quelle="https://www.bag.admin.ch/x", grund="g"):
    return {"stelle": stelle, "urteil": urteil, "korrektur": korrektur, "quelle": quelle, "grund": grund}


def _roh(*funde, geprueft=4):
    return {"geprueft": geprueft, "funde": list(funde)}


def test_pruef_text_ohne_voiceover():
    t = pruef_text(TEXT)
    assert "Voiceover" not in t
    assert t.count("Die Franchise beträgt 300 Franken") == 1
    assert "## Szenen fürs Fliessband" in t and "## Caption" in t


def test_falscher_fund_mit_quelle_wird_korrigiert():
    k, o, v = gueltige_funde(_roh(_f("beträgt 300 Franken im Jahr", korrektur="beträgt 2'500 Franken ohne Wahlfranchise")),
                             TEXT)
    assert [f.stelle for f in k] == ["beträgt 300 Franken im Jahr"] and o == [] and v == []


def test_nicht_belegbar_ohne_neue_zahl_wird_korrigiert():
    k, o, _ = gueltige_funde(_roh(_f("zahlt ab 70", urteil="nicht_belegbar", korrektur="zahlt im Rentenalter", quelle="")), TEXT)
    assert len(k) == 1 and o == []


@pytest.mark.parametrize("fund", [
    _f("zahlt ab 70", urteil="nicht_belegbar", korrektur="zahlt ab 65", quelle=""),   # neue Zahl
    _f("zahlt ab 70", korrektur="zahlt ab 65", quelle=""),                             # falsch ohne Quelle
    _f("zahlt ab 70", korrektur="zahlt ab 65", quelle="http://x.ch/a"),                # kein https
    _f("zahlt ab 70", korrektur=""),                                                   # leere Korrektur
    _f("zahlt ab 70", korrektur="zahlt ab 70"),                                        # keine Änderung
    _f("zahlt ab 70", korrektur="zahlt\nab 65"),                                       # Zeilenumbruch
])
def test_nicht_korrigierbar_wird_offen(fund):
    k, o, v = gueltige_funde(_roh(fund), TEXT)
    assert k == [] and len(o) == 1 and v == []


def test_stelle_die_nicht_vorkommt_wird_verworfen():
    k, o, v = gueltige_funde(_roh(_f("gibt es nicht im Text")), TEXT)
    assert k == [] and o == [] and "genau einmal" in v[0]


def test_voiceover_kopie_zaehlt_nicht_mit():
    # Steht im Voiceover und in Szene 1, im Prüftext aber nur einmal
    k, _, v = gueltige_funde(_roh(_f("Die Franchise beträgt 300 Franken")), TEXT)
    assert len(k) == 1 and v == []


@pytest.mark.parametrize("stelle", ["Verlustrisiken", "Schreib START in die Kommentare", "## Caption"])
def test_geschuetzter_text_wird_verworfen(stelle):
    k, o, v = gueltige_funde(_roh(_f(stelle)), TEXT)
    assert k == [] and o == [] and "geschützt" in v[0]


def test_unbekanntes_urteil_und_kaputte_eintraege_werden_verworfen():
    k, o, v = gueltige_funde(_roh(_f("zahlt ab 70", urteil="vielleicht"), "text", {"stelle": 3}), TEXT)
    assert k == [] and o == [] and len(v) == 3


def test_doppelte_stelle_zaehlt_einmal():
    k, o, v = gueltige_funde(_roh(_f("zahlt ab 70"), _f("zahlt ab 70", korrektur="anders")), TEXT)
    assert len(k) == 1 and len(v) == 1 and "doppelt" in v[0]


def test_mehr_als_fuenf_gueltige_funde_werden_offen():
    woerter = [f"wortzahl{i}" for i in range(HOECHSTENS + 2)]   # mindestens 8 Zeichen
    text = "## Szenen\n" + "\n".join(woerter) + "\n"
    k, o, _ = gueltige_funde(_roh(*[_f(w, korrektur=w + "x") for w in woerter]), text)
    assert [f.stelle for f in k] == woerter[:HOECHSTENS] and [f.stelle for f in o] == woerter[HOECHSTENS:]


@pytest.mark.parametrize("roh", [None, [], {"funde": []}, {"geprueft": 3}, {"geprueft": True, "funde": []},
                                 {"geprueft": 2, "funde": "x"}])
def test_antwort_ohne_geprueft_und_funde_ist_uebersprungen(roh):
    with pytest.raises(FaktenUebersprungen):
        gueltige_funde(roh, TEXT)


def test_wende_an_ersetzt_ueberall_auch_im_voiceover():
    k = [Fund("Die Franchise beträgt 300 Franken", "falsch", "Die Franchise beträgt ab 300 Franken", "https://a.ch/x", "")]
    neu, uebersprungen = wende_an(TEXT, k, [])
    assert neu.count("Die Franchise beträgt ab 300 Franken") == 2 and uebersprungen == []


def test_wende_an_markiert_offene_und_nur_einmal():
    o = [Fund("zahlt ab 70", "falsch", "", "", "")]
    neu, _ = wende_an(TEXT, [], o)
    assert f"zahlt ab 70{MARKER}" in neu
    zweimal, _ = wende_an(neu, [], o)
    assert zweimal == neu
    ohne, _ = wende_an(TEXT, [], o, markiere=False)
    assert ohne == TEXT


def test_wende_an_meldet_nicht_mehr_vorhandene_stellen():
    k = [Fund("Die Franchise beträgt 300 Franken im Jahr", "falsch", "x", "https://a.ch/x", ""),
         Fund("Franchise beträgt 300 Franken im Jahr", "falsch", "y", "https://a.ch/x", "")]
    _, uebersprungen = wende_an(TEXT, k, [])
    assert uebersprungen == ["Franchise beträgt 300 Franken im Jahr"]


def test_hinweis_faelle():
    assert hinweis(None) is None
    assert hinweis({"lief": False, "geprueft": 0, "korrigiert": [], "offen": []}) == \
        "⚠️ Faktencheck nicht gelaufen, bitte selbst prüfen"
    assert hinweis({"lief": True, "geprueft": 0, "korrigiert": [], "offen": []}) is None
    assert hinweis({"lief": True, "geprueft": 6, "korrigiert": [], "offen": []}) == \
        "🔎 Faktencheck: 6 Aussagen geprüft, alles belegt"
    assert hinweis({"lief": True, "geprueft": 1, "korrigiert": [], "offen": []}) == \
        "🔎 Faktencheck: 1 Aussage geprüft, alles belegt"
    k = [{"stelle": "Franchise 300", "korrektur": "Franchise 2'500", "quelle": "https://www.bag.admin.ch/x", "urteil": "falsch"}]
    assert hinweis({"lief": True, "geprueft": 6, "korrigiert": k, "offen": []}) == \
        "🔎 Faktencheck: 6 Aussagen geprüft, 1 korrigiert: Franchise 300 → Franchise 2'500 (bag.admin.ch)"
    k2 = [{"stelle": "viele", "korrektur": "einige", "quelle": "", "urteil": "nicht_belegbar"}]
    assert "(nicht belegbar)" in hinweis({"lief": True, "geprueft": 2, "korrigiert": k2, "offen": []})
    o = [{"stelle": "zahlt ab 70", "grund": "g"}]
    assert hinweis({"lief": True, "geprueft": 3, "korrigiert": [], "offen": o}) == \
        "🔎 Faktencheck: 3 Aussagen geprüft, 1 offen: zahlt ab 70 [prüfen], bitte selbst klären"


# ---- Nachbesserungen nach Review ----

TEXT2 = """# Titel

## Szenen fürs Fliessband

**Szene 1 (Hook)**
Sprechtext: Die Rente beträgt 2'000 Franken im Monat.
Einblendung: Rente 2000

## Caption

Mehr dazu unten.
#familie #rente
"""


def test_ueberlappende_stellen_nur_die_erste_bleibt():
    lang, kurz = "beträgt 300 Franken im Jahr", "300 Franken"
    k, o, v = gueltige_funde(_roh(_f(lang), _f(kurz)), TEXT)
    assert [f.stelle for f in k] == [lang] and o == [] and len(v) == 1 and "überlappt" in v[0]
    k, o, v = gueltige_funde(_roh(_f(kurz), _f(lang)), TEXT)
    assert [f.stelle for f in k] == [kurz] and o == [] and len(v) == 1 and "überlappt" in v[0]


def test_ueberlappung_zaehlt_auch_fuer_offene():
    k, o, v = gueltige_funde(_roh(_f("beträgt 300 Franken im Jahr", korrektur=""), _f("300 Franken")), TEXT)
    assert k == [] and len(o) == 1 and len(v) == 1


@pytest.mark.parametrize("stelle", ["Szenen fürs", "Sprechtext:", "Sprechtext", "**Szene 1 (Hook)**",
                                    "Sprechtext: Die Rente", "Rente beträgt 2'000 Franken im Monat.\nEinblendung"])
def test_struktur_wird_verworfen(stelle):
    k, o, v = gueltige_funde(_roh(_f(stelle)), TEXT2)
    assert k == [] and o == [] and len(v) == 1


def test_mehrzeilige_stelle_wird_verworfen():
    k, o, v = gueltige_funde(_roh(_f("Mehr dazu unten.\n#familie #rente")), TEXT2)
    assert k == [] and o == [] and "mehrzeilig" in v[0]


def test_text_hinter_label_und_hashtags_bleiben_gueltig():
    k, o, v = gueltige_funde(_roh(_f("Die Rente beträgt 2'000 Franken im Monat"), _f("#familie #rente")), TEXT2)
    assert len(k) == 2 and o == [] and v == []


def test_zu_kurze_stelle_wird_verworfen():
    k, o, v = gueltige_funde(_roh(_f("AHV 70")), TEXT)
    assert k == [] and o == [] and "zu kurz" in v[0]
    k, o, v = gueltige_funde(_roh(_f("Wusstest", korrektur="Wusstet")), TEXT)    # genau 8 Zeichen
    assert len(k) == 1 and v == []


def test_marker_nicht_im_voiceover_und_nie_doppelt():
    o = [Fund("Die Franchise beträgt 300 Franken", "falsch", "", "", "")]
    neu, _ = wende_an(TEXT, [], o)
    assert neu.count(MARKER) == 1
    assert neu.split("## Szenen")[0] == TEXT.split("## Szenen")[0]
    assert "Die Franchise beträgt 300 Franken [prüfen] im Jahr" in neu
    assert wende_an(neu, [], o)[0] == neu


def test_wende_an_meldet_verschwundene_offene_stellen():
    k = [Fund("Die Franchise beträgt 300 Franken im Jahr", "falsch", "Anders", "https://a.ch/x", "")]
    o = [Fund("beträgt 300 Franken im", "falsch", "", "", "")]
    neu, uebersprungen = wende_an(TEXT, k, o)
    assert uebersprungen == ["beträgt 300 Franken im"] and MARKER not in neu


def test_hinweis_wirft_nie_bei_unvollstaendigem_dict():
    assert hinweis({"lief": True}) is None
    assert hinweis({"geprueft": 1}).startswith("⚠️")
    z = hinweis({"lief": True, "geprueft": 2, "korrigiert": [{"stelle": "abc"}], "offen": [{}]})
    assert "1 korrigiert" in z and "1 offen" in z


@pytest.mark.parametrize("korrektur", ["zahlt ab 70 [prüfen]", "zahlt ab 70 [Quelle]", "zahlt ab 70, schreib START",
                                       "Verlustrisiken zahlt ab 70"])
def test_korrektur_mit_platzhalter_oder_schutztext_wird_offen(korrektur):
    k, o, v = gueltige_funde(_roh(_f("zahlt ab 70", korrektur=korrektur)), TEXT)
    assert k == [] and len(o) == 1 and v == []


@pytest.mark.parametrize("korrektur", ["Die Rente beträgt 2000 Franken im Monat", "Die Rente beträgt 2 000 Franken im Monat",
                                       "Die Rente beträgt 2.000 Franken im Monat"])
def test_tausendertrenner_zaehlen_nicht_als_neue_zahl(korrektur):
    f = _f("Die Rente beträgt 2'000 Franken im Monat", urteil="nicht_belegbar", korrektur=korrektur, quelle="")
    k, o, _ = gueltige_funde(_roh(f), TEXT2)
    assert len(k) == 1 and o == []


def test_neue_zahl_bei_nicht_belegbar_bleibt_offen():
    f = _f("Die Rente beträgt 2'000 Franken im Monat", urteil="nicht_belegbar",
           korrektur="Die Rente beträgt 2'500 Franken im Monat", quelle="")
    k, o, _ = gueltige_funde(_roh(f), TEXT2)
    assert k == [] and len(o) == 1


@pytest.mark.parametrize("quelle", ["https://.", "https://a.", "https://a..ch/x", "https://nopunkt/x", "https://a b.ch/x",
                                    "https://.ch/x"])
def test_kaputte_quellen_werden_offen(quelle):
    k, o, _ = gueltige_funde(_roh(_f("zahlt ab 70", korrektur="zahlt ab 65", quelle=quelle)), TEXT)
    assert k == [] and len(o) == 1


# ---- Nachbesserungen, zweite Runde ----

KARUSSELL = """## Slides

**Slide 1 (Hook)**
Überschrift: Zuerst der Notgroschen
Text: Spare drei Monatslöhne und starte dann.

**Slide 2**
Überschrift: 1. Notgroschen aufbauen
Text: Das hilft sehr. Im Text: etwas steht mitten im Satz.

## Caption

Spare zuerst, dann lern Trading. Trading birgt Verlustrisiken.
"""


@pytest.mark.parametrize("stelle", ["**Slide 2**", "Überschrift: Zuerst der", "Text: Spare drei Monatslöhne",
                                    "**Slide 1 (Hook)**", "Text: Das hilft sehr"])
def test_karussell_geruest_wird_verworfen(stelle):
    k, o, v = gueltige_funde(_roh(_f(stelle)), KARUSSELL)
    assert k == [] and o == [] and len(v) == 1 and "geschützt" in v[0]


def test_karussell_text_hinter_label_und_label_mitten_im_satz_bleiben_gueltig():
    k, o, v = gueltige_funde(_roh(_f("Spare drei Monatslöhne und starte dann"), _f("Im Text: etwas steht"),
                                  _f("Zuerst der Notgroschen")), KARUSSELL)
    assert len(k) == 3 and o == [] and v == []


@pytest.mark.parametrize("a, b", [("0.5 Prozent", "5 Prozent"), ("3.5 Prozent", "5 Prozent"), ("3,5 Prozent", "5 Prozent"),
                                  ("0.5 Prozent", "0.50 Prozent")])
def test_dezimalzahlen_sind_eine_zahl(a, b):
    assert _zahlen(a) != _zahlen(b)


def test_zahlen_tausendertrenner_und_leerzeichen():
    assert _zahlen("2'500") == _zahlen("2500") == _zahlen("2’500") == _zahlen("2.500") == _zahlen("2 500")
    assert _zahlen("1'000'000") == {"1000000"}
    assert _zahlen("65 100 Franken") == {"65", "100"}
    assert _zahlen("3,5 Prozent") == _zahlen("3.5 Prozent")


def test_dezimalzahl_als_neue_zahl_bei_nicht_belegbar_bleibt_offen():
    f = _f("Die Zinsen liegen bei 5 Prozent im Jahr", urteil="nicht_belegbar",
           korrektur="Die Zinsen liegen bei 0.5 Prozent im Jahr", quelle="")
    k, o, _ = gueltige_funde(_roh(f), "## Szenen\nDie Zinsen liegen bei 5 Prozent im Jahr\n")
    assert k == [] and len(o) == 1


def test_teilueberlappung_wird_verworfen():
    a, b = "beträgt 300 Franken", "300 Franken im Jahr"
    k, o, v = gueltige_funde(_roh(_f(a), _f(b)), TEXT)
    assert [f.stelle for f in k] == [a] and o == [] and len(v) == 1 and "überlappt" in v[0]
    k, o, v = gueltige_funde(_roh(_f(b), _f(a)), TEXT)
    assert [f.stelle for f in k] == [b] and len(v) == 1 and "überlappt" in v[0]


def test_benachbarte_stellen_ueberlappen_nicht():
    k, o, v = gueltige_funde(_roh(_f("Die Franchise beträgt"), _f(" 300 Franken im Jahr.")), TEXT)
    assert len(k) == 2 and v == []


@pytest.mark.parametrize("korrektur", ["## Neue Überschrift", "**Szene 9** ersetzt", "**Slide 3** neu",
                                       "Sprechtext: zahlt ab 65", "Überschrift: zahlt ab 65", "Text: zahlt ab 65",
                                       "Einblendung: zahlt ab 65", "Bild: zahlt ab 65", "Grafik: zahlt ab 65"])
def test_korrektur_die_mit_geruest_beginnt_wird_offen(korrektur):
    k, o, v = gueltige_funde(_roh(_f("zahlt ab 70", korrektur=korrektur)), TEXT)
    assert k == [] and len(o) == 1 and v == []


def test_hashtag_korrektur_ist_keine_ueberschrift():
    k, _, _ = gueltige_funde(_roh(_f("zahlt ab 70", korrektur="#familie zahlt ab 65")), TEXT)
    assert len(k) == 1


def test_offene_stelle_nur_noch_im_voiceover_gilt_als_uebersprungen():
    k = [Fund("Die Franchise beträgt 300 Franken im Jahr", "falsch", "Anders", "https://a.ch/x", "")]
    o = [Fund("Die Franchise beträgt 300 Franken.", "falsch", "", "", "")]   # steht nur noch im Voiceover
    neu, uebersprungen = wende_an(TEXT, k, o)
    assert uebersprungen == ["Die Franchise beträgt 300 Franken."] and MARKER not in neu


# --- Task 3: Schalter, Agent-Aufruf, pruefe_beitrag ---

REEL = Path(__file__).parent / "fixtures" / "reel_beispiel.md"
KARUSSELL_DATEI = Path(__file__).parent / "fixtures" / "karussell_beispiel-thema_v2.md"
STELLE_PREIS = "höchstens zehn Franken pro Trade"       # Sprechtext Szene 3, genau einmal
STELLE_OFFEN = "Du startest mit einem Demokonto"          # Sprechtext Szene 2, genau einmal


def _lauf(antwort, aufrufe=None):
    """Attrappe: schreibt `antwort` (dict, Text oder Ausnahme) in die verlangte Ausgabedatei."""
    def lauf(agent, auftrag, ausgabe, werkzeuge=(), ordner=(), zeitlimit=0):
        if aufrufe is not None:
            aufrufe.append((agent, auftrag, tuple(werkzeuge), zeitlimit))
        if isinstance(antwort, Exception):
            raise antwort
        Path(ausgabe).write_text(antwort if isinstance(antwort, str) else json.dumps(antwort), encoding="utf-8")
        return Path(ausgabe)
    return lauf


@pytest.fixture
def reel(tmp_path):
    ziel = tmp_path / "2026-10-27_reel_a.md"
    ziel.write_text(REEL.read_text(encoding="utf-8"), encoding="utf-8")
    return ziel


def test_schalter_standard_an_und_umschalten(tmp_path):
    assert fakten.ist_an(tmp_path) is True
    fakten.setze(tmp_path, False)
    assert fakten.ist_an(tmp_path) is False
    assert fakten.schalter_text(tmp_path) == "Faktencheck: aus"
    fakten.setze(tmp_path, True)
    assert fakten.schalter_text(tmp_path) == "Faktencheck: an"


def test_schalter_kaputte_datei_gilt_als_an(tmp_path):
    (tmp_path / "daten").mkdir()
    (tmp_path / "daten" / "fakten.json").write_text("{kaputt", encoding="utf-8")
    assert fakten.ist_an(tmp_path) is True


def test_pruefe_beitrag_schalter_aus_ruft_nichts(tmp_path, reel):
    fakten.setze(tmp_path, False)
    aufrufe = []
    assert fakten.pruefe_beitrag(reel, "reel", _lauf({}, aufrufe), tmp_path) is None
    assert aufrufe == []


def test_pruefe_beitrag_korrigiert_datei_und_meldet(tmp_path, reel):
    aufrufe = []
    antwort = {"geprueft": 3, "funde": [_f(STELLE_PREIS, korrektur="höchstens ein Prozent pro Trade")]}
    e = fakten.pruefe_beitrag(reel, "reel", _lauf(antwort, aufrufe), tmp_path)
    assert e["lief"] and e["geprueft"] == 3 and e["offen"] == []
    assert e["korrigiert"][0]["quelle"] == "https://www.bag.admin.ch/x"
    assert "höchstens ein Prozent pro Trade" in reel.read_text(encoding="utf-8")
    agent, auftrag, werkzeuge, zeitlimit = aufrufe[0]
    assert agent == "fakten-agent" and "WebSearch" in werkzeuge and zeitlimit == fakten.ZEITLIMIT
    assert STELLE_PREIS in auftrag and "Dieser Abschnitt wird vom Bauer ignoriert" not in auftrag


def test_pruefe_beitrag_setzt_marker_bei_offenen(tmp_path, reel):
    antwort = {"geprueft": 2, "funde": [_f(STELLE_OFFEN, korrektur="", quelle="")]}
    e = fakten.pruefe_beitrag(reel, "reel", _lauf(antwort), tmp_path)
    assert e["offen"] == [{"stelle": STELLE_OFFEN, "grund": "g"}]
    assert f"{STELLE_OFFEN}{MARKER}" in reel.read_text(encoding="utf-8")


def test_pruefe_beitrag_ohne_marker_bei_neubau(tmp_path, reel):
    antwort = {"geprueft": 2, "funde": [_f(STELLE_OFFEN, korrektur="", quelle="")]}
    vorher = reel.read_text(encoding="utf-8")
    e = fakten.pruefe_beitrag(reel, "reel", _lauf(antwort), tmp_path, markiere_offen=False)
    assert len(e["offen"]) == 1 and reel.read_text(encoding="utf-8") == vorher


AUSFALL = {"lief": False, "geprueft": 0, "korrigiert": [], "offen": []}


@pytest.mark.parametrize("antwort", [
    ClaudeFehler("fakten-agent: keine Antwort innerhalb von 6 Min"), "kein json", {"funde": []}, ["x"],
    RuntimeError("unerwartet im Agenten-Lauf"), KeyError("x")])
def test_pruefe_beitrag_ausfall_laesst_beitrag_durch(tmp_path, reel, antwort):
    vorher = reel.read_text(encoding="utf-8")
    e = fakten.pruefe_beitrag(reel, "reel", _lauf(antwort), tmp_path)
    assert e == AUSFALL
    assert reel.read_text(encoding="utf-8") == vorher
    assert (tmp_path / "logs" / "fakten.log").exists()


def test_pruefe_beitrag_unerwarteter_fehler_wird_geloggt(tmp_path, reel):
    fakten.pruefe_beitrag(reel, "reel", _lauf(RuntimeError("boom")), tmp_path)
    assert "boom" in (tmp_path / "logs" / "fakten.log").read_text(encoding="utf-8")


def test_pruefe_beitrag_unlesbare_korrektur_wird_zurueckgesetzt(tmp_path, reel, monkeypatch):
    def kaputt(format, pfad):
        raise ValueError("Datei nicht mehr lesbar")
    monkeypatch.setattr(fakten, "_lese", kaputt)
    vorher = reel.read_text(encoding="utf-8")
    antwort = {"geprueft": 1, "funde": [_f(STELLE_PREIS, korrektur="höchstens ein Prozent pro Trade")]}
    e = fakten.pruefe_beitrag(reel, "reel", _lauf(antwort), tmp_path)
    assert e["lief"] is False and reel.read_text(encoding="utf-8") == vorher
    assert "zurückgesetzt" in (tmp_path / "logs" / "fakten.log").read_text(encoding="utf-8")


def test_pruefe_beitrag_lesbare_korrektur_bleibt_und_leser_wird_gerufen(tmp_path, reel, monkeypatch):
    gerufen = []
    monkeypatch.setattr(fakten, "_lese", lambda format, pfad: gerufen.append((format, pfad)))
    antwort = {"geprueft": 1, "funde": [_f(STELLE_PREIS, korrektur="höchstens ein Prozent pro Trade")]}
    e = fakten.pruefe_beitrag(reel, "reel", _lauf(antwort), tmp_path)
    assert e["lief"] is True and gerufen == [("reel", reel)]
    assert "höchstens ein Prozent pro Trade" in reel.read_text(encoding="utf-8")


def test_pruefe_beitrag_echter_leser_akzeptiert_korrigierte_fixture(tmp_path, reel):
    antwort = {"geprueft": 1, "funde": [_f(STELLE_PREIS, korrektur="höchstens ein Prozent pro Trade")]}
    assert fakten.pruefe_beitrag(reel, "reel", _lauf(antwort), tmp_path)["lief"] is True


def test_pruefe_beitrag_karussell(tmp_path):
    k = tmp_path / "2026-10-28_karussell_a.md"
    k.write_text(KARUSSELL_DATEI.read_text(encoding="utf-8"), encoding="utf-8")
    e = fakten.pruefe_beitrag(k, "karussell", _lauf({"geprueft": 4, "funde": []}), tmp_path)
    assert e == {"lief": True, "geprueft": 4, "korrigiert": [], "offen": [], "markiert": True}


def test_wende_an_doppelter_marker_bei_stelle_mit_marker():
    text = "# T\n\n**Szene 1**\nSprechtext: Die Franchise ist hoch [prüfen] und teuer.\n"
    o = [Fund("Die Franchise ist hoch [prüfen]", "falsch", "", "", "")]
    neu, _ = wende_an(text, [], o)
    assert neu.count(MARKER) == 1 and "[prüfen] [prüfen]" not in neu


def test_hinweis_ohne_marker_bei_neubau():
    e = {"lief": True, "geprueft": 4, "korrigiert": [], "offen": [{"stelle": "X", "grund": "g"}], "markiert": False}
    assert hinweis(e) == "🔎 Faktencheck: 4 Aussagen geprüft, 1 offen: X, bitte selbst klären"


def test_hinweis_ohne_feld_markiert_gilt_als_markiert():
    e = {"lief": True, "geprueft": 4, "korrigiert": [], "offen": [{"stelle": "X", "grund": "g"}]}
    assert hinweis(e).endswith("X [prüfen], bitte selbst klären")


def test_ergebnis_markiert_je_nach_schalter(tmp_path, reel):
    antwort = {"geprueft": 2, "funde": [_f(STELLE_OFFEN, korrektur="", quelle="")]}
    assert fakten.pruefe_beitrag(reel, "reel", _lauf(antwort), tmp_path)["markiert"] is True
    assert fakten.pruefe_beitrag(reel, "reel", _lauf(antwort), tmp_path, markiere_offen=False)["markiert"] is False


def test_agent_ueberschreibt_skript_wird_zurueckgelegt(tmp_path, reel):
    vorher = reel.read_text(encoding="utf-8")

    def boesartig(agent, auftrag, ausgabe, werkzeuge=(), ordner=(), zeitlimit=0):
        reel.write_text("manipuliert", encoding="utf-8")
        Path(ausgabe).write_text(json.dumps({"geprueft": 1, "funde": []}), encoding="utf-8")
        return Path(ausgabe)
    e = fakten.pruefe_beitrag(reel, "reel", boesartig, tmp_path)
    assert e == AUSFALL and reel.read_text(encoding="utf-8") == vorher
    assert "verändert" in (tmp_path / "logs" / "fakten.log").read_text(encoding="utf-8")


def test_zeit_abgelaufen_wird_nicht_verschluckt(tmp_path, reel):
    from lib.claude_lauf import ZeitAbgelaufen
    with pytest.raises(ZeitAbgelaufen):
        fakten.pruefe_beitrag(reel, "reel", _lauf(ZeitAbgelaufen("Zeitlimit des Schritts erreicht")), tmp_path)


def test_schreibgeschuetzt_betrifft_nur_eine_kopie(tmp_path):
    from lib.claude_lauf import SCHREIBSCHUTZ, ClaudeLauf
    orig = ClaudeLauf(cwd=tmp_path, log=tmp_path / "l.log")
    geschuetzt = fakten.schreibgeschuetzt(orig, tmp_path)
    assert tmp_path in geschuetzt.nur_lesen and orig.nur_lesen == SCHREIBSCHUTZ
    attrappe = _lauf({})
    assert fakten.schreibgeschuetzt(attrappe, tmp_path) is attrappe


def _korr(stelle, korrektur, quelle="https://www.bag.admin.ch/x"):
    return {"stelle": stelle, "korrektur": korrektur, "quelle": quelle, "urteil": "falsch"}


def _zeile(*k):
    return hinweis({"lief": True, "geprueft": 5, "korrigiert": list(k), "offen": []})


def test_hinweis_zeigt_nur_die_geaenderte_stelle_lange_zahl():
    z = _zeile(_korr("Die ordentliche Franchise in der Grundversicherung beträgt 3000 Franken.",
                     "Die ordentliche Franchise in der Grundversicherung beträgt 300 Franken für Erwachsene."))
    assert z == ("🔎 Faktencheck: 5 Aussagen geprüft, 1 korrigiert: … beträgt 3000 Franken. → "
                 "… beträgt 300 Franken für Erwachsene. (bag.admin.ch)")


def test_hinweis_diff_mit_umfeld_davor_und_danach():
    z = _zeile(_korr("Die AHV zahlt ab 70 Jahren eine Rente aus.", "Die AHV zahlt ab 65 Jahren eine Rente aus."))
    assert z.endswith("korrigiert: … ab 70 … → … ab 65 … (bag.admin.ch)")


def test_hinweis_reine_einfuegung_zeigt_zwei_woerter_davor_und_eines_danach():
    z = _zeile(_korr("Die Rente wird jeden Monat ausgezahlt.", "Die Rente wird jeden Monat bar ausgezahlt."))
    assert z.endswith("korrigiert: … jeden Monat ausgezahlt. → … jeden Monat bar ausgezahlt. (bag.admin.ch)")


def test_hinweis_reine_streichung():
    z = _zeile(_korr("Das Konto ist gratis und sehr sicher geführt", "Das Konto ist gratis geführt"))
    assert z.endswith("korrigiert: … ist gratis und sehr sicher geführt → … ist gratis geführt (bag.admin.ch)")


def test_hinweis_nur_satzzeichen_anders():
    z = _zeile(_korr("Das ist sicher.", "Das ist sicher!"))
    assert "korrigiert: … ist sicher. → … ist sicher! (bag.admin.ch)" in z


def test_hinweis_kuerzt_erst_nach_dem_diff_auf_80_zeichen():
    lang = "x" * 120
    z = _zeile(_korr(f"Kosten {lang} Franken", f"Kosten {lang}y Franken"))
    teile = z.split("korrigiert: ")[1].split(" (bag")[0].split(" → ")
    assert all(len(t) <= 80 for t in teile) and "…" in teile[0]
