import pytest

from lib.aussprache import HOECHSTENS, AusspracheUebersprungen, gueltige_funde, kerne
from lib.reel_modell import Szene


def _szenen(*texte):
    return [Szene(nummer=i, hook=(i == 1), sprechtext=t, einblendung="x") for i, t in enumerate(texte, 1)]


SZENEN = _szenen("Auf dem Trottoir liegt Glace.", "Das kostet 30'000 Franken, sagt die AHV!")


def _f(wort, ersatz):
    return {"wort": wort, "ersatz": ersatz, "grund": "Test"}


def test_kerne_ohne_satzzeichen():
    assert {"Trottoir", "Glace", "30'000", "AHV", "Franken"} <= kerne(SZENEN)
    assert "Glace." not in kerne(SZENEN)


def test_gueltige_funde_werden_uebernommen():
    neu, verworfen = gueltige_funde({"funde": [_f("Trottoir", "Gehweg"), _f("AHV", "A-H-V"),
                                               _f("30'000", "dreissigtausend")]}, SZENEN, {})
    assert neu == {"Trottoir": "Gehweg", "AHV": "A-H-V", "30'000": "dreissigtausend"}
    assert verworfen == []


@pytest.mark.parametrize("fund, grund", [
    (_f("Velo", "Fahrrad"), "kommt im Sprechtext nicht vor"),
    (_f("Trottoir", "Weg am Rand"), "nicht genau ein Wort"),
    (_f("Glace.", "Eis"), "nicht genau ein Wort"),
    (_f("Trottoir", ""), "nicht genau ein Wort"),
    (_f("Trottoir", "Trottoir"), "Ersatz gleich wie Wort"),
    (_f("Glace", "Eis"), "steht schon auf der Liste"),
    ({"wort": 3, "ersatz": "drei"}, "nicht genau ein Wort"),
    ("Trottoir", "kein Eintrag"),
    (_f("Glace", "Eis→x"), "nicht genau ein Wort"),
    (_f("a→b", "x"), "nicht genau ein Wort"),
])
def test_ungueltige_funde_werden_verworfen(fund, grund):
    neu, verworfen = gueltige_funde({"funde": [fund]}, SZENEN, {"Glace": "Eis"})
    assert neu == {}
    assert len(verworfen) == 1 and grund in verworfen[0]


def test_doppelter_fund_zaehlt_einmal():
    neu, verworfen = gueltige_funde({"funde": [_f("Trottoir", "Gehweg"), _f("Trottoir", "Bürgersteig")]}, SZENEN, {})
    assert neu == {"Trottoir": "Gehweg"}
    assert "steht schon auf der Liste" in verworfen[0]


def test_hoechstens_fuenf_funde():
    woerter = [f"Wort{i}" for i in range(HOECHSTENS + 2)]
    neu, verworfen = gueltige_funde({"funde": [_f(w, w + "x") for w in woerter]}, _szenen(" ".join(woerter)), {})
    assert list(neu) == woerter[:HOECHSTENS]
    assert len(verworfen) == 2 and all(f"mehr als {HOECHSTENS}" in v for v in verworfen)


@pytest.mark.parametrize("roh", [None, [], {"funde": "Trottoir"}, {"andere": []}])
def test_falsche_form_ueberspringt(roh):
    with pytest.raises(AusspracheUebersprungen):
        gueltige_funde(roh, SZENEN, {})


def test_keine_funde():
    assert gueltige_funde({"funde": []}, SZENEN, {}) == ({}, [])


from datetime import date

from lib.aussprache import haenge_an, hinweis, lade_listen, logzeile
from lib.pruefungen import AusspracheFehler, lade_aussprache


def test_haenge_an_neue_datei_bleibt_lesbar(tmp_path):
    pfad = tmp_path / "daten" / "aussprache-auto.txt"
    haenge_an(pfad, {"Trottoir": "Gehweg"}, date(2026, 10, 31), "reel-x")
    haenge_an(pfad, {"AHV": "A-H-V"}, date(2026, 11, 3), "reel-y")
    text = pfad.read_text(encoding="utf-8")
    assert text.startswith("# Automatisch")
    assert "# 2026-10-31, reel-x\nTrottoir → Gehweg\n" in text
    assert "# 2026-11-03, reel-y\nAHV → A-H-V\n" in text
    assert lade_aussprache(pfad) == {"Trottoir": "Gehweg", "AHV": "A-H-V"}


def test_haenge_an_ohne_funde_schreibt_nichts(tmp_path):
    pfad = tmp_path / "aussprache-auto.txt"
    haenge_an(pfad, {}, date(2026, 10, 31), "reel-x")
    assert not pfad.exists()


def test_lade_listen_hand_gewinnt(tmp_path):
    hand, auto, log = tmp_path / "aussprache.txt", tmp_path / "auto.txt", tmp_path / "log.txt"
    hand.write_text("Glace → Eis\n", encoding="utf-8")
    auto.write_text("Glace → Speiseeis\nTrottoir → Gehweg\n", encoding="utf-8")
    assert lade_listen(hand, auto, log) == {"Glace": "Eis", "Trottoir": "Gehweg"}


def test_lade_listen_ohne_auto(tmp_path):
    hand = tmp_path / "aussprache.txt"
    hand.write_text("Glace → Eis\n", encoding="utf-8")
    assert lade_listen(hand, tmp_path / "fehlt.txt", tmp_path / "log.txt") == {"Glace": "Eis"}


def test_lade_listen_kaputte_auto_wird_ignoriert(tmp_path):
    hand, auto, log = tmp_path / "aussprache.txt", tmp_path / "auto.txt", tmp_path / "log.txt"
    hand.write_text("Glace → Eis\n", encoding="utf-8")
    auto.write_text("das ist kaputt\n", encoding="utf-8")
    assert lade_listen(hand, auto, log) == {"Glace": "Eis"}
    assert "auto.txt ignoriert" in log.read_text(encoding="utf-8")


def test_lade_listen_kaputte_hand_bricht_ab(tmp_path):
    hand = tmp_path / "aussprache.txt"
    hand.write_text("kaputt\n", encoding="utf-8")
    with pytest.raises(AusspracheFehler):
        lade_listen(hand, tmp_path / "auto.txt", tmp_path / "log.txt")


def test_hinweis():
    assert hinweis([]) is None and hinweis(None) is None
    assert hinweis([["Trottoir", "Gehweg"], ["30'000", "dreissigtausend"]]) == \
        "🗣 Neu für die Stimme: Trottoir → Gehweg, 30'000 → dreissigtausend"


def test_logzeile_haengt_an(tmp_path):
    log = tmp_path / "logs" / "x.log"
    logzeile(log, "eins")
    logzeile(log, "zwei")
    assert log.read_text(encoding="utf-8") == "=== aussprache === eins\n=== aussprache === zwei\n"


import json

from lib.aussprache import AGENT, ZEITLIMIT, auftrag, ergaenze, pruefer
from lib.claude_lauf import ClaudeFehler


def test_auftrag_enthaelt_texte_liste_und_ausgabe(tmp_path):
    a = auftrag(SZENEN, {"Glace": "Eis"}, tmp_path / "aussprache.json")
    assert "Szene 1: Auf dem Trottoir liegt Glace." in a
    assert "Szene 2: Das kostet 30'000 Franken, sagt die AHV!" in a
    assert "Glace" in a.split("Schon auf der Liste")[1].splitlines()[0]
    assert str(tmp_path / "aussprache.json") in a
    assert '"funde"' in a


class _Lauf:
    """Attrappe für ClaudeLauf: schreibt `inhalt` in die Ausgabe oder wirft `fehler`."""

    def __init__(self, inhalt=None, fehler=None):
        self.inhalt, self.fehler, self.aufrufe = inhalt, fehler, []

    def __call__(self, agent, auftrag, ausgabe, werkzeuge=("Read", "Write"), ordner=(), zeitlimit=900):
        self.aufrufe.append((agent, werkzeuge, tuple(ordner), zeitlimit))
        if self.fehler:
            raise self.fehler
        if self.inhalt is not None:
            ausgabe.write_text(self.inhalt, encoding="utf-8")
        return ausgabe


def test_pruefer_liefert_gueltige_funde(tmp_path):
    lauf = _Lauf(json.dumps({"funde": [_f("Trottoir", "Gehweg"), _f("Velo", "Fahrrad")]}))
    neu, verworfen = pruefer(lauf, tmp_path / "zw")(SZENEN, {})
    assert neu == {"Trottoir": "Gehweg"} and len(verworfen) == 1
    assert lauf.aufrufe == [(AGENT, ("Write",), (tmp_path / "zw",), ZEITLIMIT)]


def test_pruefer_alte_antwort_zaehlt_nicht(tmp_path):
    zw = tmp_path / "zw"
    zw.mkdir()
    (zw / "aussprache.json").write_text(json.dumps({"funde": [_f("Trottoir", "Gehweg")]}), encoding="utf-8")
    with pytest.raises(AusspracheUebersprungen):
        pruefer(_Lauf(inhalt=None), zw)(SZENEN, {})   # Agent schreibt nichts → alte Datei darf nicht gelten


@pytest.mark.parametrize("lauf", [_Lauf("kein json"), _Lauf(fehler=ClaudeFehler("aussprache-agent: weg"))])
def test_pruefer_fehler_ueberspringt(tmp_path, lauf):
    with pytest.raises(AusspracheUebersprungen):
        pruefer(lauf, tmp_path / "zw")(SZENEN, {})


def test_ergaenze_uebernimmt_merkt_und_loggt(tmp_path):
    liste, auto, log = {"Glace": "Eis"}, tmp_path / "daten" / "aussprache-auto.txt", tmp_path / "log.txt"

    def p(szenen, l):
        assert l == {"Glace": "Eis"}
        return {"Trottoir": "Gehweg"}, ["'Velo' → 'Fahrrad': kommt im Sprechtext nicht vor"]

    assert ergaenze(liste, SZENEN, p, auto, "reel-x", date(2026, 10, 31), log) == [["Trottoir", "Gehweg"]]
    assert liste == {"Glace": "Eis", "Trottoir": "Gehweg"}
    assert lade_aussprache(auto) == {"Trottoir": "Gehweg"}
    text = log.read_text(encoding="utf-8")
    assert "verworfen: 'Velo'" in text and "neu: Trottoir → Gehweg" in text


@pytest.mark.parametrize("fehler", [AusspracheUebersprungen("weg"), RuntimeError("kaputt"), ValueError()])
def test_ergaenze_scheitert_nie(tmp_path, fehler):
    def p(szenen, l):
        raise fehler
    liste = {"Glace": "Eis"}
    assert ergaenze(liste, SZENEN, p, tmp_path / "auto.txt", "reel-x", date(2026, 10, 31), tmp_path / "log.txt") == []
    assert liste == {"Glace": "Eis"}
    assert "übersprungen" in (tmp_path / "log.txt").read_text(encoding="utf-8")


def test_ergaenze_auto_nicht_schreibbar(tmp_path):
    gesperrt = tmp_path / "datei"
    gesperrt.write_text("x", encoding="utf-8")   # Ordner der Auto-Liste ist eine Datei → OSError
    liste = {}
    funde = ergaenze(liste, SZENEN, lambda s, l: ({"Trottoir": "Gehweg"}, []), gesperrt / "auto.txt",
                     "reel-x", date(2026, 10, 31), tmp_path / "log.txt")
    assert funde == [["Trottoir", "Gehweg"]] and liste == {"Trottoir": "Gehweg"}
    assert "nicht geschrieben" in (tmp_path / "log.txt").read_text(encoding="utf-8")


def test_pruefer_mit_frist_gebunden(tmp_path):
    from lib.claude_lauf import Frist, mit_frist
    lauf = _Lauf(json.dumps({"funde": [_f("Trottoir", "Gehweg")]}))
    neu, _ = pruefer(mit_frist(lauf, Frist(None)), tmp_path / "zw")(SZENEN, {})
    assert neu == {"Trottoir": "Gehweg"}


def test_ergaenze_log_nicht_schreibbar(tmp_path):
    gesperrt = tmp_path / "datei"
    gesperrt.write_text("x", encoding="utf-8")
    liste = {}
    funde = ergaenze(liste, SZENEN, lambda s, l: ({"Trottoir": "Gehweg"}, ["x"]), tmp_path / "auto.txt",
                     "reel-x", date(2026, 10, 31), gesperrt / "log.txt")
    assert funde == [["Trottoir", "Gehweg"]]


def test_haenge_an_ohne_schlusszeilenumbruch(tmp_path):
    pfad = tmp_path / "auto.txt"
    pfad.write_text("Velo → Rad", encoding="utf-8")
    haenge_an(pfad, {"AHV": "A-H-V"}, date(2026, 10, 31), "reel\nx")
    assert lade_aussprache(pfad) == {"Velo": "Rad", "AHV": "A-H-V"}
    assert "# 2026-10-31, reel x\n" in pfad.read_text(encoding="utf-8")
