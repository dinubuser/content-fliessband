from lib import cli


def test_poster_ein_status_aus(tmp_path, monkeypatch, capsys, briefkasten):
    monkeypatch.setattr(cli.Briefkasten, "lade", classmethod(lambda cls, daten, anfrage=None: briefkasten))
    assert cli.main(["poster", "ein", "--basis", str(tmp_path)]) == 0
    aus = capsys.readouterr().out
    assert briefkasten.poster_an is True
    assert "Poster: an" in aus and "Instagram-Schlüssel: 3 Tage alt" in aus
    assert "Di 27.10., 19:00 · Reel «Thema beispiel-reel-eins» · geplant · Dateien da" in aus
    assert cli.main(["poster", "aus", "--basis", str(tmp_path)]) == 0
    assert "Poster: aus" in capsys.readouterr().out
    assert briefkasten.poster_an is False
    assert cli.main(["poster", "status", "--basis", str(tmp_path)]) == 0
    assert "Nächste Posts:" in capsys.readouterr().out


def test_poster_text_ohne_schluessel_und_posts():
    text = cli.poster_text({"an": False, "schluessel_tage": None, "naechste": []})
    assert text == "Poster: aus\nInstagram-Schlüssel: fehlt oder ungültig\nKeine geplanten Posts."
    text = cli.poster_text({"an": True, "schluessel_tage": 0, "naechste": [
        {"termin": "2026-10-28T19:00", "format": "karussell", "titel": "T", "post_status": "geplant",
         "dateien": False}]})
    assert text.endswith("  Mi 28.10., 19:00 · Karussell «T» · geplant · Dateien fehlen")


def test_poster_ohne_briefkasten(tmp_path, capsys):
    assert cli.main(["poster", "status", "--basis", str(tmp_path)]) == 1
    assert "Briefkasten nicht eingerichtet" in capsys.readouterr().err


def test_poster_server_weg(tmp_path, monkeypatch, capsys, briefkasten):
    briefkasten.nicht_erreichbar = True
    monkeypatch.setattr(cli.Briefkasten, "lade", classmethod(lambda cls, daten, anfrage=None: briefkasten))
    assert cli.main(["poster", "ein", "--basis", str(tmp_path)]) == 1
    assert "nicht erreichbar" in capsys.readouterr().err
