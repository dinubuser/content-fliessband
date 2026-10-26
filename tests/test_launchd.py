import os
import plistlib
import subprocess
from pathlib import Path

import pytest

LAUNCHD = Path(__file__).resolve().parent.parent / "launchd"


@pytest.mark.parametrize("schritt, tag, stunde", [("lernen", 5, 20), ("vorbereiten", 5, 22), ("bauen", 6, 22)])
def test_plist(schritt, tag, stunde):
    roh = (LAUNCHD / f"com.example.fliessband-{schritt}.plist").read_text(encoding="utf-8").replace("__DIR__", "/x")
    p = plistlib.loads(roh.encode("utf-8"))
    assert p["Label"] == f"com.example.fliessband-{schritt}"
    assert p["ProgramArguments"] == ["/bin/zsh", "/x/launchd/woche.sh", schritt]
    assert p["StartCalendarInterval"] == {"Weekday": tag, "Hour": stunde, "Minute": 0}
    assert p["StandardOutPath"] == p["StandardErrorPath"] == "/x/logs/launchd.log"
    assert "RunAtLoad" not in p


@pytest.mark.parametrize("schritt", ["lernen", "vorbereiten", "bauen"])
def test_plist_lint(schritt):
    # plutil prüft nur die Datei im Repo, nichts in ~/Library/LaunchAgents
    r = subprocess.run(["plutil", "-lint", str(LAUNCHD / f"com.example.fliessband-{schritt}.plist")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize("skript", ["woche.sh", "installieren.sh"])
def test_skripte_ausfuehrbar_und_ohne_syntaxfehler(skript):
    assert os.access(LAUNCHD / skript, os.X_OK)
    r = subprocess.run(["/bin/zsh", "-n", str(LAUNCHD / skript)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_woche_sh_ohne_schritt():
    r = subprocess.run(["/bin/zsh", str(LAUNCHD / "woche.sh")], capture_output=True, text=True)
    assert r.returncode == 2
    assert "lernen|vorbereiten|bauen" in r.stderr


def test_woche_sh_path_caffeinate_und_job():
    text = (LAUNCHD / "woche.sh").read_text(encoding="utf-8")
    for teil in ["$HOME/.local/bin", "/opt/homebrew/bin", "/usr/local/bin", "caffeinate -i",
                 'fliessband" woche job "$SCHRITT"']:
        assert teil in text, teil


def test_installieren_nennt_pmset():
    text = (LAUNCHD / "installieren.sh").read_text(encoding="utf-8")
    assert "sudo pmset repeat wakeorpoweron FS 21:55:00" in text
    assert "launchctl bootstrap" in text and "plutil -lint" in text


def test_woche_sh_unter_launchd_umgebung(tmp_path):
    # Nachbau des Projektordners mit Attrappe statt echter CLI; Umgebung wie bei launchd (nur HOME und knapper PATH)
    (tmp_path / "launchd").mkdir()
    skript = tmp_path / "launchd" / "woche.sh"
    skript.write_text((LAUNCHD / "woche.sh").read_text(encoding="utf-8"), encoding="utf-8")
    attrappe = tmp_path / "fliessband"
    attrappe.write_text('#!/bin/sh\necho "ARGS=$*"\necho "PATH=$PATH"\n'
                        'echo "UNBUFFERED=$PYTHONUNBUFFERED"\nexit 7\n', encoding="utf-8")
    attrappe.chmod(0o755)
    env = {"HOME": "/home/user", "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
    r = subprocess.run(["/bin/zsh", str(skript), "bauen"], capture_output=True, text=True, env=env)
    assert r.returncode == 7, r.stdout + r.stderr
    assert "ARGS=woche job bauen" in r.stdout
    assert "PATH=/home/user/.local/bin:/opt/homebrew/bin:/usr/local/bin:" in r.stdout
    assert "UNBUFFERED=1" in r.stdout
    assert "Ende Job bauen (Exit 7)" in r.stdout
    assert (tmp_path / "logs").is_dir()


def test_plist_entscheide():
    roh = (LAUNCHD / "com.example.fliessband-entscheide.plist").read_text(encoding="utf-8").replace("__DIR__", "/x")
    p = plistlib.loads(roh.encode("utf-8"))
    assert p["Label"] == "com.example.fliessband-entscheide"
    assert p["ProgramArguments"] == ["/bin/zsh", "/x/launchd/entscheide.sh"]
    assert p["StartInterval"] == 900 and "StartCalendarInterval" not in p
    assert p["StandardOutPath"] == p["StandardErrorPath"] == "/x/logs/entscheide-launchd.log"
    assert "RunAtLoad" not in p
    r = subprocess.run(["plutil", "-lint", str(LAUNCHD / "com.example.fliessband-entscheide.plist")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_entscheide_sh_und_installieren():
    pfad = LAUNCHD / "entscheide.sh"
    assert os.access(pfad, os.X_OK)
    r = subprocess.run(["/bin/zsh", "-n", str(pfad)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert 'caffeinate -i "$DIR/fliessband" entscheide' in pfad.read_text(encoding="utf-8")
    assert "for JOB in lernen vorbereiten bauen entscheide" in (LAUNCHD / "installieren.sh").read_text(encoding="utf-8")


def test_woche_sh_lernen_ist_erlaubt(tmp_path):
    (tmp_path / "launchd").mkdir()
    skript = tmp_path / "launchd" / "woche.sh"
    skript.write_text((LAUNCHD / "woche.sh").read_text(encoding="utf-8"), encoding="utf-8")
    attrappe = tmp_path / "fliessband"
    attrappe.write_text('#!/bin/sh\necho "ARGS=$*"\n', encoding="utf-8")
    attrappe.chmod(0o755)
    r = subprocess.run(["/bin/zsh", str(skript), "lernen"], capture_output=True, text=True,
                       env={"HOME": "/home/user", "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0 and "ARGS=woche job lernen" in r.stdout
