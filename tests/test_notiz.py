import json
import subprocess

import pytest

from lib import notiz
from lib.notiz import NotizFehler, merke_verwendet, offene_ideen, zeilen_hash

TEXT = ("Content-Ideen\nDie Sätze aus dem Teamraum\n\n  - Notgroschen   für Berufstätige \n"
        "• Erste Woche Demokonto\nDie Sätze aus dem Teamraum\n")


def test_liest_jede_zeile_als_idee(tmp_path):
    skripte = []

    def lesen(skript):
        skripte.append(skript)
        return TEXT

    assert offene_ideen(tmp_path / "verwendet.json", lesen) == [
        "Die Sätze aus dem Teamraum", "Notgroschen für Berufstätige", "Erste Woche Demokonto"]
    assert 'name is "Content-Ideen"' in skripte[0]
    assert "plaintext" in skripte[0]


def test_verwendete_zeilen_fallen_weg(tmp_path):
    verwendet = tmp_path / "daten" / "verwendet.json"
    merke_verwendet(verwendet, "Notgroschen  für Berufstätige")
    assert offene_ideen(verwendet, lambda s: TEXT) == ["Die Sätze aus dem Teamraum", "Erste Woche Demokonto"]
    assert json.loads(verwendet.read_text(encoding="utf-8")) == {"hashes": [zeilen_hash("Notgroschen für Berufstätige")]}


def test_fehlende_notiz_gibt_leere_liste(tmp_path):
    assert offene_ideen(tmp_path / "verwendet.json", lambda s: "") == []


def test_kaputte_verwendet_datei(tmp_path):
    verwendet = tmp_path / "verwendet.json"
    verwendet.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(NotizFehler, match="kaputt"):
        offene_ideen(verwendet, lambda s: TEXT)


def test_osascript_ohne_freigabe(monkeypatch):
    def run(befehl, **kw):
        return subprocess.CompletedProcess(befehl, 1, "", "execution error: Not authorized to send Apple events to Notes. (-1743)")
    monkeypatch.setattr(notiz.subprocess, "run", run)
    with pytest.raises(NotizFehler, match="nicht lesbar"):
        notiz.osascript(notiz.SKRIPT)


def test_osascript_zeitlimit(monkeypatch):
    def run(befehl, **kw):
        raise subprocess.TimeoutExpired(befehl, kw["timeout"])
    monkeypatch.setattr(notiz.subprocess, "run", run)
    with pytest.raises(NotizFehler, match="antwortet nicht"):
        notiz.osascript(notiz.SKRIPT)


def test_osascript_befehl(monkeypatch):
    aufrufe = []

    def run(befehl, **kw):
        aufrufe.append(befehl)
        return subprocess.CompletedProcess(befehl, 0, "Content-Ideen\nIdee\n", "")
    monkeypatch.setattr(notiz.subprocess, "run", run)
    assert notiz.osascript(notiz.SKRIPT) == "Content-Ideen\nIdee\n"
    assert aufrufe[0][:2] == ["osascript", "-e"]
