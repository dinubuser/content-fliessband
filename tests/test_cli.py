import pytest

from lib import cli
from lib.umgebung import Pfade


def test_cli_meldet_formatfehler(tmp_path, capsys):
    f = tmp_path / "x.md"
    f.write_text("# leer\n", encoding="utf-8")
    assert cli.main(["karussell", str(f), "--basis", str(tmp_path)]) == 1
    assert "## Slides" in capsys.readouterr().err


def test_cli_meldet_fehlende_datei(tmp_path, capsys):
    assert cli.main(["karussell", str(tmp_path / "gibtsnicht.md"), "--basis", str(tmp_path)]) == 1
    assert "Fehler" in capsys.readouterr().err


def test_cli_baut_und_meldet_offene_stellen(tmp_path, karussell_quelle, capsys):
    assert cli.main(["karussell", str(karussell_quelle), "--termin", "2026-10-23T19:00",
                     "--basis", str(tmp_path)]) == 0
    aus = capsys.readouterr().out
    assert "Status: braucht_eingabe" in aus
    assert aus.count("offen:") == 3


def test_cli_termin_strikt(tmp_path, karussell_quelle):
    with pytest.raises(SystemExit) as e:
        cli.main(["karussell", str(karussell_quelle), "--termin", "2026-10-23", "--basis", str(tmp_path)])
    assert e.value.code == 2


def test_cli_faengt_unerwartete_fehler(tmp_path, capsys):
    assert cli.main(["karussell", str(tmp_path), "--basis", str(tmp_path)]) == 1
    assert "Fehler" in capsys.readouterr().err


def test_cli_meldet_manifestfehler(tmp_path, karussell_quelle, capsys):
    woche = tmp_path / "wochen" / "2026-KW43"
    woche.mkdir(parents=True)
    (woche / "manifest.json").write_text("{kaputt", encoding="utf-8")
    assert cli.main(["karussell", str(karussell_quelle), "--termin", "2026-10-23T19:00",
                     "--basis", str(tmp_path)]) == 1
    assert "manifest.json" in capsys.readouterr().err


def test_cli_meldet_schreibweise_korrekturen(tmp_path, capsys):
    q = tmp_path / "2026-10-20_karussell_mass.md"
    q.write_text(
        "## Slides\n\n**Slide 1**\nÜberschrift: Maß halten\nText: Kurz.\n\n"
        "**Slide 2**\nÜberschrift: Ende\nText: Fertig.\n\n## Caption\nSchöner Tag.\n",
        encoding="utf-8",
    )
    assert cli.main(["karussell", str(q), "--basis", str(tmp_path)]) == 0
    assert "Schreibweise korrigiert: 1" in capsys.readouterr().out


def test_cli_reel_meldet_formatfehler(tmp_path, capsys):
    f = tmp_path / "x.md"
    f.write_text("# leer\n", encoding="utf-8")
    assert cli.main(["reel", str(f), "--basis", str(tmp_path)]) == 1
    assert "Szenen fürs Fliessband" in capsys.readouterr().err


def test_cli_reel_meldet_status_und_laenge(tmp_path, reel_quelle, monkeypatch, capsys):
    def falsch_bauen(quelle, termin=None, basis=None, aussprache_pruefer=None):
        return basis / "wochen" / "2026-KW43" / "reel-beispiel", {
            "status": "braucht_eingabe", "dauer_s": 71.2,
            "pruefungen": {"platzhalter": ["Szene 2: [prüfen]"], "risikohinweis_ergaenzt": ["szene"],
                           "schreibweise_korrekturen": 0, "laenge": "lang"}}
    monkeypatch.setattr(cli, "baue_reel", falsch_bauen)
    assert cli.main(["reel", str(reel_quelle), "--termin", "2026-10-25T19:00", "--basis", str(tmp_path)]) == 0
    aus = capsys.readouterr().out
    assert "Status: braucht_eingabe" in aus
    assert "offen: Szene 2: [prüfen]" in aus
    assert "Risikohinweis ergänzt: szene" in aus
    assert "Länge: 71.2 s (lang, über 60 s)" in aus


def test_cli_reel_gibt_pruefer_mit_und_meldet_funde(tmp_path, reel_quelle, monkeypatch, capsys):
    mitgegeben = []

    def falsch_bauen(quelle, termin=None, basis=None, aussprache_pruefer=None):
        mitgegeben.append(aussprache_pruefer)
        return basis / "wochen" / "2026-KW43" / "reel-beispiel", {
            "status": "entwurf", "dauer_s": 25.0,
            "pruefungen": {"platzhalter": [], "risikohinweis_ergaenzt": [], "schreibweise_korrekturen": 0,
                           "laenge": "ok", "aussprache_neu": [["Trottoir", "Gehweg"]]}}
    monkeypatch.setattr(cli, "baue_reel", falsch_bauen)
    assert cli.main(["reel", str(reel_quelle), "--basis", str(tmp_path)]) == 0
    assert callable(mitgegeben[0])
    assert "🗣 Neu für die Stimme: Trottoir → Gehweg" in capsys.readouterr().out


@pytest.mark.parametrize("name", ["LeserFehler", "ManifestFehler", "StimmFehler", "LaengeFehler",
                                  "MusikFehler", "ZuLangFehler", "RenderFehler", "MedienFehler",
                                  "AusspracheFehler", "FileNotFoundError"])
def test_cli_reel_faengt_alle_fehlerarten_einzeilig(name, tmp_path, reel_quelle, monkeypatch, capsys):
    import builtins
    klassen = {"LeserFehler": "lib.leser", "ManifestFehler": "lib.manifest", "StimmFehler": "lib.stimme",
               "LaengeFehler": "lib.zeitplan", "MusikFehler": "lib.musik", "ZuLangFehler": "lib.renderer",
               "RenderFehler": "lib.reel_renderer", "MedienFehler": "lib.medien",
               "AusspracheFehler": "lib.pruefungen"}
    if name in klassen:
        import importlib
        klasse = getattr(importlib.import_module(klassen[name]), name)
    else:
        klasse = getattr(builtins, name)

    def wirf(*a, **k):
        raise klasse("Zeile eins\n  Zeile zwei\n\nZeile drei")
    monkeypatch.setattr(cli, "baue_reel", wirf)
    assert cli.main(["reel", str(reel_quelle), "--basis", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert err == "Fehler: Zeile eins Zeile zwei Zeile drei\n"


def test_cli_reel_abbruch_ohne_traceback(tmp_path, reel_quelle, monkeypatch, capsys):
    def wirf(*a, **k):
        raise KeyboardInterrupt
    monkeypatch.setattr(cli, "baue_reel", wirf)
    assert cli.main(["reel", str(reel_quelle), "--basis", str(tmp_path)]) == 130
    assert capsys.readouterr().err == "Abgebrochen.\n"


def test_cli_karussell_fehler_einzeilig(tmp_path, karussell_quelle, monkeypatch, capsys):
    def wirf(*a, **k):
        raise cli.LeserFehler("a\nb")
    monkeypatch.setattr(cli, "baue_karussell", wirf)
    assert cli.main(["karussell", str(karussell_quelle), "--basis", str(tmp_path)]) == 1
    assert capsys.readouterr().err == "Fehler: a b\n"


@pytest.mark.parametrize("befehl, name", [("karussell", "baue_karussell"), ("reel", "baue_reel")])
def test_cli_verschluckt_programmierfehler_nicht(befehl, name, tmp_path, reel_quelle, monkeypatch):
    def wirf(*a, **k):
        raise RuntimeError("Bug")
    monkeypatch.setattr(cli, name, wirf)
    with pytest.raises(RuntimeError, match="Bug"):
        cli.main([befehl, str(reel_quelle), "--basis", str(tmp_path)])


def test_cli_woche_status_ohne_plan(tmp_path, capsys):
    assert cli.main(["woche", "status", "--woche", "2026-KW44", "--basis", str(tmp_path)]) == 0
    assert capsys.readouterr().out.startswith("Woche 2026-KW44\nvorbereitet: offen")


def test_cli_woche_status_lesefehler_einzeilig(tmp_path, capsys):
    plan = Pfade(basis=tmp_path).plan("2026-KW44")
    plan.mkdir(parents=True)  # Verzeichnis statt Datei: read_text wirft OSError
    assert cli.main(["woche", "status", "--woche", "2026-KW44", "--basis", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("Fehler: ") and err.count("\n") == 1


def test_cli_woche_ungueltige_woche(tmp_path, capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["woche", "bauen", "--woche", "2026-44", "--basis", str(tmp_path)])
    assert e.value.code == 2
    assert "2026-KW44" in capsys.readouterr().err


@pytest.mark.parametrize("schritt", ["vorbereiten", "bauen", "senden"])
def test_cli_woche_ruft_schritt_auf(schritt, tmp_path, monkeypatch):
    aufrufe = []

    def falsch(befehl, woche, pfade, dienste, log):
        aufrufe.append((befehl, woche, pfade.basis, log.pfad.name, type(dienste).__name__))
        return 0
    monkeypatch.setattr(cli, "fuehre_aus", falsch)
    assert cli.main(["woche", schritt, "--woche", "2026-KW44", "--basis", str(tmp_path)]) == 0
    assert aufrufe == [(schritt, "2026-KW44", tmp_path, f"woche-2026-KW44-{schritt}.log", "Dienste")]


def test_cli_woche_gibt_exit_code_weiter(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "fuehre_aus", lambda *a: 1)
    assert cli.main(["woche", "bauen", "--basis", str(tmp_path)]) == 1


def test_cli_job_nimmt_zielwoche(tmp_path, monkeypatch):
    aufrufe = []
    monkeypatch.setattr(cli, "zielwoche", lambda heute: "2026-KW44")
    monkeypatch.setattr(cli, "fuehre_aus",
                        lambda befehl, woche, pfade, dienste, log: aufrufe.append((befehl, woche, log.pfad.name)) or 0)
    assert cli.main(["woche", "job", "bauen", "--basis", str(tmp_path)]) == 0
    assert aufrufe == [("job-bauen", "2026-KW44", "woche-2026-KW44-bauen.log")]


@pytest.mark.parametrize("schritt", ["vorbereiten", "bauen"])
def test_cli_job_woche_und_zeitfenster_aus_derselben_uhr(schritt, tmp_path, monkeypatch):
    # So 23:59:59 der KW44: Zielwoche KW45. Der Job muss für sein Zeitfenster genau diesen Zeitpunkt sehen,
    # auch wenn die Uhr inzwischen auf Montag (neue Zielwoche) gesprungen ist.
    from datetime import datetime
    zeiten = iter([datetime(2026, 11, 1, 23, 59, 59), datetime(2026, 11, 2, 0, 0, 1)])
    monkeypatch.setattr(cli, "uhr", lambda: next(zeiten))
    aufrufe = []

    def falsch(befehl, woche, pfade, dienste, log):
        aufrufe.append((befehl, woche, dienste.jetzt(), log.pfad.name))
        return 0
    monkeypatch.setattr(cli, "fuehre_aus", falsch)
    assert cli.main(["woche", "job", schritt, "--basis", str(tmp_path)]) == 0
    assert aufrufe == [(f"job-{schritt}", "2026-KW45", datetime(2026, 11, 1, 23, 59, 59),
                        f"woche-2026-KW45-{schritt}.log")]


def test_cli_job_uhr_laeuft_nach_dem_ersten_blick_weiter(tmp_path, monkeypatch):
    from datetime import datetime
    zeiten = iter([datetime(2026, 10, 31, 22, 0), datetime(2026, 10, 31, 23, 30)])
    monkeypatch.setattr(cli, "uhr", lambda: next(zeiten))
    gesehen = []
    monkeypatch.setattr(cli, "fuehre_aus",
                        lambda befehl, woche, pfade, dienste, log: gesehen.extend([dienste.jetzt(), dienste.jetzt()]) or 0)
    assert cli.main(["woche", "job", "bauen", "--basis", str(tmp_path)]) == 0
    assert gesehen == [datetime(2026, 10, 31, 22, 0), datetime(2026, 10, 31, 23, 30)]


def test_cli_bot_einrichten(tmp_path, monkeypatch, capsys):
    class FalscherBot:
        def __init__(self, stand):
            assert stand == tmp_path / "daten" / "bot.json"

        def einrichten(self):
            return 42
    monkeypatch.setattr(cli, "Bot", FalscherBot)
    assert cli.main(["bot", "einrichten", "--basis", str(tmp_path)]) == 0
    assert "Chat 42" in capsys.readouterr().out


def test_cli_bot_einrichten_fehler(tmp_path, monkeypatch, capsys):
    class FalscherBot:
        def __init__(self, stand):
            pass

        def einrichten(self):
            raise cli.BotFehler("Keine /start-Nachricht gefunden.\nNochmals.")
    monkeypatch.setattr(cli, "Bot", FalscherBot)
    assert cli.main(["bot", "einrichten", "--basis", str(tmp_path)]) == 1
    assert capsys.readouterr().err == "Fehler: Keine /start-Nachricht gefunden. Nochmals.\n"


@pytest.mark.parametrize("schritt", ["vorbereiten", "bauen", "senden"])
def test_cli_woche_ohne_job_friert_die_uhr_nicht_ein(schritt, tmp_path, monkeypatch):
    # bauen/senden fragen die Uhr erst am Ende (schritt_fertig): das muss die echte Endzeit sein, nicht der Start
    from datetime import datetime
    zeiten = iter([datetime(2026, 10, 31, 22, 0), datetime(2026, 10, 31, 23, 30)])
    monkeypatch.setattr(cli, "uhr", lambda: next(zeiten))
    gesehen = []
    monkeypatch.setattr(cli, "fuehre_aus",
                        lambda befehl, woche, pfade, dienste, log: gesehen.append(dienste.jetzt()) or 0)
    assert cli.main(["woche", schritt, "--woche", "2026-KW45", "--basis", str(tmp_path)]) == 0
    assert gesehen == [datetime(2026, 10, 31, 23, 30)]


def test_lernen_befehle(tmp_path, monkeypatch):
    from datetime import datetime
    aufrufe = []
    monkeypatch.setattr(cli, "fuehre_aus", lambda befehl, woche, pfade, dienste, log:
                        aufrufe.append((befehl, woche, log.pfad.name)) or 0)
    monkeypatch.setattr(cli, "uhr", lambda: datetime(2026, 10, 30, 20, 0))
    assert cli.main(["lernen", "--basis", str(tmp_path)]) == 0
    assert cli.main(["lernen", "--probe", "--basis", str(tmp_path)]) == 0
    assert cli.main(["woche", "job", "lernen", "--basis", str(tmp_path)]) == 0
    assert aufrufe == [("lernen", "2026-KW45", "woche-2026-KW45-lernen.log"),
                       ("lernen-probe", "2026-KW45", "woche-2026-KW45-lernen.log"),
                       ("job-lernen", "2026-KW45", "woche-2026-KW45-lernen.log")]
