from pathlib import Path

from lib import cli, fakten


def test_fakten_ein_aus_status(tmp_path, capsys):
    assert cli.main(["fakten", "status", "--basis", str(tmp_path)]) == 0
    assert capsys.readouterr().out == "Faktencheck: an\n"
    assert cli.main(["fakten", "aus", "--basis", str(tmp_path)]) == 0
    assert capsys.readouterr().out == "Faktencheck: aus\n"
    assert fakten.ist_an(tmp_path) is False
    assert cli.main(["fakten", "ein", "--basis", str(tmp_path)]) == 0
    assert capsys.readouterr().out == "Faktencheck: an\n"
    assert fakten.ist_an(tmp_path) is True


def test_hand_bau_ruft_check_und_zeigt_zeile(tmp_path, monkeypatch, capsys):
    quelle = tmp_path / "2026-10-27_reel_a.md"
    quelle.write_text("x", encoding="utf-8")
    aufrufe = []

    def attrappe_check(pfad, format, lauf, basis, markiere_offen=True):
        aufrufe.append((Path(pfad), format, markiere_offen))
        return {"lief": True, "geprueft": 3, "korrigiert": [], "offen": []}

    monkeypatch.setattr(cli.fakten, "pruefe_beitrag", attrappe_check)
    monkeypatch.setattr(cli, "baue_reel", lambda quelle, termin=None, basis=None, **mehr:
                        (tmp_path / "ziel", {"status": "entwurf", "pruefungen": {
                            "platzhalter": [], "risikohinweis_ergaenzt": [], "schreibweise_korrekturen": 0}}))
    assert cli.main(["reel", str(quelle), "--basis", str(tmp_path)]) == 0
    assert aufrufe == [(quelle.resolve(), "reel", True)]
    assert "🔎 Faktencheck: 3 Aussagen geprüft, alles belegt" in capsys.readouterr().out
