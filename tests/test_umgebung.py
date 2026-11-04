import sys
from pathlib import Path

from lib.fehler import BAU_FEHLER, einzeilig
from lib.leser import LeserFehler
from lib import umgebung
from lib.umgebung import Pfade, agentur_werkzeug, letzte_zeile


def test_pfade(tmp_path):
    p = Pfade(basis=tmp_path / "fb", agentur=tmp_path / "ag", skill=tmp_path / "skill")
    assert p.daten == tmp_path / "fb" / "daten"
    assert p.woche("2026-KW44") == tmp_path / "fb" / "wochen" / "2026-KW44"
    assert p.plan("2026-KW44") == tmp_path / "fb" / "wochen" / "2026-KW44" / "plan.json"
    assert p.log("2026-KW44", "bauen") == tmp_path / "fb" / "logs" / "woche-2026-KW44-bauen.log"
    assert p.regelwerk == tmp_path / "skill" / "regeln" / "regelwerk.md"


def test_standardpfade():
    p = Pfade()
    assert p.basis == Path.home() / "content-fliessband"
    assert p.agentur == Path.home() / "meine-agentur"
    assert p.skill == Path.home() / ".claude" / "skills" / "agentur"
    assert p.agentur_python == Path.home() / ".social-agentur" / "venv" / "bin" / "python"


def test_pfad_aus_der_konfiguration_loest_die_tilde_auf(monkeypatch):
    """In .env.example steht ~/…: Python muss das selbst auflösen, die Shell tut es hier nicht."""
    monkeypatch.setenv("FLIESSBAND_AGENTUR_DIR", "~/mein-ordner")
    assert umgebung._pfad("FLIESSBAND_AGENTUR_DIR", Path("/anders")) == Path.home() / "mein-ordner"
    monkeypatch.delenv("FLIESSBAND_AGENTUR_DIR")
    assert umgebung._pfad("FLIESSBAND_AGENTUR_DIR", Path("/anders")) == Path("/anders")


def _werkzeug(tmp_path, code):
    tools = tmp_path / "skill" / "tools"
    tools.mkdir(parents=True)
    (tools / "probe.py").write_text(code, encoding="utf-8")
    return agentur_werkzeug(Pfade(skill=tmp_path / "skill", agentur_python=Path(sys.executable)))


def test_werkzeug_gibt_ausgabe_zurueck(tmp_path):
    w = _werkzeug(tmp_path, "import sys\nprint(' '.join(sys.argv[1:]))\n")
    r = w("probe.py", ["check", "--json"], 30)
    assert r.returncode == 0
    assert r.stdout.strip() == "check --json"


def test_werkzeug_zeitlimit(tmp_path):
    w = _werkzeug(tmp_path, "import time\ntime.sleep(5)\n")
    r = w("probe.py", [], 1)
    assert r.returncode == 124
    assert "abgebrochen" in r.stderr


def test_werkzeug_ohne_python(tmp_path):
    w = agentur_werkzeug(Pfade(skill=tmp_path, agentur_python=tmp_path / "fehlt"))
    r = w("probe.py", [], 5)
    assert r.returncode == 127


def test_letzte_zeile():
    assert letzte_zeile("a\n\nFehler: kaputt\n\n") == "Fehler: kaputt"
    assert letzte_zeile("") == "keine Meldung"


def test_bau_fehler_und_einzeilig():
    assert LeserFehler in BAU_FEHLER and OSError in BAU_FEHLER
    assert einzeilig(ValueError("Zeile eins\n  Zeile zwei")) == "Zeile eins Zeile zwei"
