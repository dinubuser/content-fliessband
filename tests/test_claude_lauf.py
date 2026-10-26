import json
import subprocess
from pathlib import Path

import pytest

from lib.claude_lauf import ClaudeFehler, ClaudeLauf, Frist, ZeitAbgelaufen, befehl, mit_frist

OK = json.dumps({"type": "result", "is_error": False, "result": "fertig"})


def _ausfuehren(ziel, schreibt=True, rc=0, stdout=OK, stderr=""):
    aufrufe = []

    def f(cmd, **kw):
        aufrufe.append((cmd, kw))
        if schreibt:
            ziel.write_text("[]", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, rc, stdout, stderr)
    f.aufrufe = aufrufe
    return f


def test_befehl_ohne_bash():
    b = befehl("content-agent", ("Read", "Write"), ())
    assert b[1:4] == ["-p", "--agent", "content-agent"]
    assert b[b.index("--permission-mode") + 1] == "acceptEdits"
    assert b[b.index("--permission-prompts") + 1] == "none"
    assert b[b.index("--tools") + 1] == "Read,Write"
    assert b[b.index("--allowedTools") + 1:b.index("--allowedTools") + 3] == ["Read", "Write"]
    assert b[b.index("--output-format") + 1] == "json"
    assert "--no-session-persistence" in b and "--strict-mcp-config" in b
    assert "Bash" not in " ".join(b)


def test_befehl_mit_ordnern(tmp_path):
    b = befehl("trend-agent", ("Read", "Write", "WebSearch", "WebFetch"), (tmp_path, tmp_path / "x"), nur_lesen=())
    assert b[b.index("--tools") + 1] == "Read,Write,WebSearch,WebFetch"
    assert b[-4:] == ["--add-dir", str(tmp_path), "--add-dir", str(tmp_path / "x")]


def test_auftrag_ueber_stdin_mit_zeitlimit_und_gateguard(tmp_path):
    ziel = tmp_path / "urteile_01.json"
    f = _ausfuehren(ziel)
    lauf = ClaudeLauf(cwd=tmp_path, log=tmp_path / "logs" / "lauf.log", ausfuehren=f)
    assert lauf("follower-agent", "Bewerte den Beitrag", ziel, ordner=(tmp_path / "skill",), zeitlimit=120) == ziel
    cmd, kw = f.aufrufe[0]
    assert kw["input"] == "Bewerte den Beitrag"
    assert kw["timeout"] == 120 and kw["cwd"] == tmp_path
    assert kw["env"]["GATEGUARD_EXEMPT_GLOBS"] == f"{tmp_path}/**,{tmp_path / 'skill'}/**"
    assert kw["env"]["GATEGUARD_BASH_ROUTINE_DISABLED"] == "1"
    assert "--agent follower-agent" in (tmp_path / "logs" / "lauf.log").read_text(encoding="utf-8")


def test_datei_nicht_geschrieben(tmp_path):
    ziel = tmp_path / "aus.json"
    lauf = ClaudeLauf(cwd=tmp_path, log=tmp_path / "l.log", ausfuehren=_ausfuehren(ziel, schreibt=False))
    with pytest.raises(ClaudeFehler, match="aus.json nicht geschrieben"):
        lauf("content-agent", "x", ziel)


def test_alte_datei_zaehlt_nicht(tmp_path):
    ziel = tmp_path / "aus.json"
    ziel.write_text("alt", encoding="utf-8")
    lauf = ClaudeLauf(cwd=tmp_path, log=tmp_path / "l.log", ausfuehren=_ausfuehren(ziel, schreibt=False))
    with pytest.raises(ClaudeFehler, match="nicht geschrieben"):
        lauf("content-agent", "x", ziel)


def test_exit_code(tmp_path):
    ziel = tmp_path / "aus.json"
    f = _ausfuehren(ziel, schreibt=False, rc=1, stdout="", stderr="Error: Not logged in")
    with pytest.raises(ClaudeFehler, match="Not logged in"):
        ClaudeLauf(cwd=tmp_path, log=tmp_path / "l.log", ausfuehren=f)("content-agent", "x", ziel)


def test_is_error(tmp_path):
    ziel = tmp_path / "aus.json"
    f = _ausfuehren(ziel, stdout=json.dumps({"is_error": True, "result": "Credit balance is too low"}))
    with pytest.raises(ClaudeFehler, match="Credit balance"):
        ClaudeLauf(cwd=tmp_path, log=tmp_path / "l.log", ausfuehren=f)("content-agent", "x", ziel)


def test_zeitlimit(tmp_path):
    def f(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])
    with pytest.raises(ClaudeFehler, match="innerhalb von 2 Min"):
        ClaudeLauf(cwd=tmp_path, log=tmp_path / "l.log", ausfuehren=f)("viral-agent", "x", tmp_path / "a.md",
                                                                     zeitlimit=120)


def test_frist():
    t = [0.0]
    frist = Frist(1000, uhr=lambda: t[0])
    assert frist.zeitlimit() == 900
    t[0] = 400
    assert frist.zeitlimit() == 600
    t[0] = 1000
    with pytest.raises(ZeitAbgelaufen):
        frist.pruefe()
    assert issubclass(ZeitAbgelaufen, ClaudeFehler)
    assert Frist(None).zeitlimit() == 900


def test_mit_frist_gibt_zeitlimit_weiter():
    aufrufe = []

    def lauf(agent, auftrag, ausgabe, werkzeuge=("Read", "Write"), ordner=(), zeitlimit=900):
        aufrufe.append((agent, werkzeuge, zeitlimit))
        return ausgabe

    gebunden = mit_frist(lauf, Frist(300, uhr=lambda: 0.0))
    gebunden("content-agent", "x", Path("a.md"))
    assert aufrufe == [("content-agent", ("Read", "Write"), 300)]


def test_mit_frist_kleineres_limit_gewinnt():
    aufrufe = []

    def lauf(agent, auftrag, ausgabe, werkzeuge=("Read", "Write"), ordner=(), zeitlimit=900):
        aufrufe.append(zeitlimit)
        return ausgabe

    mit_frist(lauf, Frist(300, uhr=lambda: 0.0))("a", "x", Path("a.md"), zeitlimit=180)
    mit_frist(lauf, Frist(100, uhr=lambda: 0.0))("a", "x", Path("a.md"), zeitlimit=180)
    assert aufrufe == [180, 100]


def test_befehl_skill_ordner_nur_lesbar(tmp_path):
    schutz = tmp_path / "claude"
    skill = schutz / "skills" / "agentur"
    b = befehl("trend-agent", ("Read", "Write"), (tmp_path / "woche", skill), nur_lesen=(schutz,))
    i = b.index("--disallowedTools")
    regeln = b[i + 1:i + 3]
    ziel = "/" + str(schutz.resolve())
    assert regeln == [f"Write({ziel}/**)", f"Edit({ziel}/**)"]
    assert regeln[0].startswith("Write(//")
    assert b[-4:] == ["--add-dir", str(tmp_path / "woche"), "--add-dir", str(skill)]
    assert i < b.index("--add-dir")


def test_befehl_schuetzt_standardmaessig_claude_ordner():
    from lib.claude_lauf import SCHREIBSCHUTZ
    assert Path.home() / ".claude" in SCHREIBSCHUTZ
    b = befehl("planer", ("Read", "Write"), ())
    regeln = b[b.index("--disallowedTools") + 1:]
    assert f"Edit(/{(Path.home() / '.claude').resolve()}/**)" in regeln


def test_lauf_gibt_schreibschutz_weiter(tmp_path):
    ziel = tmp_path / "aus.json"
    f = _ausfuehren(ziel)
    lauf = ClaudeLauf(cwd=tmp_path, log=tmp_path / "l.log", ausfuehren=f, nur_lesen=(tmp_path / "skill",))
    lauf("trend-agent", "x", ziel, ordner=(tmp_path / "skill",))
    cmd = f.aufrufe[0][0]
    assert f"Write(/{(tmp_path / 'skill').resolve()}/**)" in cmd
