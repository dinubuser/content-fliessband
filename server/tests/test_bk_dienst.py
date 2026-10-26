import os
import subprocess
from pathlib import Path

import pytest

from briefkasten import dienst
from briefkasten.telegram import TelegramFehler

SERVER = Path(__file__).resolve().parent.parent


def test_lade_env(tmp_path):
    pfad = tmp_path / "geheim.env"
    pfad.write_text("# Kommentar\nTELEGRAM_TOKEN=1:abc\nCHAT_ID=42\nAPI_SCHLUESSEL=\"s\"\n", encoding="utf-8")
    assert dienst.lade_env(pfad) == {"TELEGRAM_TOKEN": "1:abc", "CHAT_ID": "42", "API_SCHLUESSEL": "s"}
    pfad.write_text("TELEGRAM_TOKEN=1:abc\nCHAT_ID=\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="CHAT_ID, API_SCHLUESSEL"):
        dienst.lade_env(pfad)


class FalscherAblauf:
    def __init__(self, ergebnisse):
        self.ergebnisse = list(ergebnisse)

    def _naechstes(self):
        e = self.ergebnisse.pop(0)
        if isinstance(e, Exception):
            raise e
        return e

    def abholen(self):
        return self._naechstes()

    def zeitgeber(self):
        self._naechstes()


def test_abhol_schleife_wartet_und_verdoppelt_pause():
    pausen = []
    a = FalscherAblauf([None, TelegramFehler("weg"), TelegramFehler("weg"), TelegramFehler("429", warten=7), 3,
                        RuntimeError("Programmfehler")])
    dienst.abhol_schleife(a, schlafe=pausen.append, runden=6)
    assert pausen == [30, 1, 2, 7, 1]


def test_zeitgeber_schleife_laeuft_nach_fehler_weiter():
    pausen = []
    dienst.zeitgeber_schleife(FalscherAblauf([TelegramFehler("weg"), RuntimeError("x"), None]),
                              schlafe=pausen.append, runden=3)
    assert pausen == [60, 60, 60]


def test_service_datei():
    text = (SERVER / "system" / "fliessband-briefkasten.service").read_text(encoding="utf-8")
    for zeile in ["User=fliessband", "ExecStart=/opt/fliessband/venv/bin/python -m briefkasten.dienst",
                  "WorkingDirectory=/opt/fliessband/app", "Restart=always", "ReadWritePaths=/var/lib/fliessband"]:
        assert zeile in text


@pytest.mark.parametrize("skript, shell", [("einrichten.sh", "bash"), ("deploy.sh", "bash"),
                                           ("zugang.sh", "/bin/zsh")])
def test_skripte(skript, shell):
    pfad = SERVER / skript
    if not pfad.exists():
        pytest.skip(f"{skript} liegt nur auf dem Mac")
    assert os.access(pfad, os.X_OK)
    if shell.startswith("/") and not Path(shell).exists():
        pytest.skip(f"{shell} fehlt")
    r = subprocess.run([shell, "-n", str(pfad)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_poster_schleife_haelt_fehler_aus():
    from briefkasten.dienst import poster_schleife

    class Kaputt:
        n = 0

        def takt(self):
            self.n += 1
            raise RuntimeError("kaputt")

    p, schlaf = Kaputt(), []
    poster_schleife(p, schlafe=schlaf.append, runden=3)
    assert p.n == 3 and schlaf == [30, 30, 30]


def test_kommentar_schleife_haelt_fehler_aus():
    from briefkasten.dienst import KOMMENTAR_TAKT, kommentar_schleife

    class Kaputt:
        n = 0

        def runde(self):
            self.n += 1
            raise RuntimeError("kaputt")

    k, schlaf = Kaputt(), []
    kommentar_schleife(k, schlafe=schlaf.append, runden=3)
    assert k.n == 3 and schlaf == [300, 300, 300] and KOMMENTAR_TAKT == 300


def test_dienst_startet_kommentare():
    text = (SERVER / "briefkasten" / "dienst.py").read_text(encoding="utf-8")
    assert "Kommentare(ablauf, instagram)" in text
    assert "target=kommentar_schleife, args=(kommentare,)" in text
