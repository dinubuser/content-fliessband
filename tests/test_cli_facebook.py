from lib import cli


def test_facebook_ein_status_aus(tmp_path, monkeypatch, capsys, briefkasten):
    monkeypatch.setattr(cli.Briefkasten, "lade", classmethod(lambda cls, daten, anfrage=None: briefkasten))
    assert cli.main(["facebook", "ein", "--basis", str(tmp_path)]) == 0
    aus = capsys.readouterr().out
    assert briefkasten.facebook_an is True
    assert aus.startswith("Facebook: an\nSeiten-Schlüssel: da\nLetzte Facebook-Posts:")
    assert "  Di 27.10., 19:00 · «Thema 1» · gepostet · https://www.facebook.com/reel/v1" in aus
    assert cli.main(["facebook", "aus", "--basis", str(tmp_path)]) == 0
    assert capsys.readouterr().out.startswith("Facebook: aus")
    assert cli.main(["facebook", "status", "--basis", str(tmp_path)]) == 0


def test_facebook_text_fehler_und_leer():
    text = cli.facebook_text({"an": False, "schluessel": False, "posts": []})
    assert text == "Facebook: aus\nSeiten-Schlüssel: fehlt oder ungültig\nNoch keine Facebook-Posts."
    text = cli.facebook_text({"an": True, "schluessel": True, "posts": [
        {"titel": "T", "termin": "2026-10-28T19:00", "fb_status": "fehler", "fb_link": None, "fb_grund": "weg"}]})
    assert text.endswith("  Mi 28.10., 19:00 · «T» · fehler · weg")


def test_facebook_text_leerer_termin():
    text = cli.facebook_text({"an": True, "schluessel": True, "posts": [
        {"titel": "T", "termin": "", "fb_status": "offen", "fb_link": None, "fb_grund": None}]})
    assert text.endswith("  ? · «T» · offen")


def test_facebook_ohne_briefkasten(tmp_path, capsys):
    assert cli.main(["facebook", "status", "--basis", str(tmp_path)]) == 1
    assert "Briefkasten nicht eingerichtet" in capsys.readouterr().err


def test_facebook_server_weg(tmp_path, monkeypatch, capsys, briefkasten):
    briefkasten.nicht_erreichbar = True
    monkeypatch.setattr(cli.Briefkasten, "lade", classmethod(lambda cls, daten, anfrage=None: briefkasten))
    assert cli.main(["facebook", "ein", "--basis", str(tmp_path)]) == 1
    assert "nicht erreichbar" in capsys.readouterr().err
