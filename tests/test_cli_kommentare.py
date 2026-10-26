from lib import cli


def test_kommentare_ein_status_aus(tmp_path, monkeypatch, capsys, briefkasten):
    monkeypatch.setattr(cli.Briefkasten, "lade", classmethod(lambda cls, daten, anfrage=None: briefkasten))
    assert cli.main(["kommentare", "ein", "--basis", str(tmp_path)]) == 0
    aus = capsys.readouterr().out
    assert briefkasten.kommentare_an is True
    assert "Kommentare: an" in aus and "Gelesen: 12 Kommentare, davon 2 mit START" in aus
    assert "Letzte Runde: 2026-10-26 10:05" in aus
    assert "Abgelehnt" not in aus
    assert cli.main(["kommentare", "aus", "--basis", str(tmp_path)]) == 0
    assert "Kommentare: aus" in capsys.readouterr().out and briefkasten.kommentare_an is False
    assert cli.main(["kommentare", "status", "--basis", str(tmp_path)]) == 0
    assert "Gelesen:" in capsys.readouterr().out


def test_kommentare_text_mit_problem_ohne_runde():
    text = cli.kommentare_text({"an": True, "kommentare": 0, "start": 0, "letzte_runde": None,
                                "problem": "Instagram HTTP 403: keine Berechtigung"})
    assert text == ("Kommentare: an\nGelesen: 0 Kommentare, davon 0 mit START\nLetzte Runde: noch keine\n"
                    "Problem: Instagram HTTP 403: keine Berechtigung")


def test_kommentare_text_zeigt_abgelehnt():
    text = cli.kommentare_text({"an": True, "kommentare": 5, "start": 3, "abgelehnt": 2,
                                "letzte_runde": None, "problem": None})
    assert "Abgelehnt: 2 Meldungen, die Telegram dauerhaft abgelehnt hat" in text


def test_kommentare_ohne_briefkasten(tmp_path, capsys):
    assert cli.main(["kommentare", "status", "--basis", str(tmp_path)]) == 1
    assert "Briefkasten nicht eingerichtet" in capsys.readouterr().err


def test_kommentare_server_weg(tmp_path, monkeypatch, capsys, briefkasten):
    briefkasten.nicht_erreichbar = True
    monkeypatch.setattr(cli.Briefkasten, "lade", classmethod(lambda cls, daten, anfrage=None: briefkasten))
    assert cli.main(["kommentare", "ein", "--basis", str(tmp_path)]) == 1
    assert "nicht erreichbar" in capsys.readouterr().err


def test_kommentare_404_hinweis(tmp_path, monkeypatch, capsys, briefkasten):
    from lib.briefkasten import BriefkastenFehler

    def weg(an=None):
        raise BriefkastenFehler("Briefkasten GET /kommentare: HTTP 404 Not Found", 404)
    briefkasten.kommentare_stand = weg
    monkeypatch.setattr(cli.Briefkasten, "lade", classmethod(lambda cls, daten, anfrage=None: briefkasten))
    assert cli.main(["kommentare", "status", "--basis", str(tmp_path)]) == 1
    assert "Server kennt Kommentare noch nicht, zuerst server/deploy.sh" in capsys.readouterr().err
