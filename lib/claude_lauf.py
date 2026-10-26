"""Ruft einen Agenten headless auf: claude -p --agent <name>, fester Auftrag über stdin, Zeitlimit,
danach Prüfung der erwarteten Ausgabedatei. Keine Rückfragen: was eine Freigabe bräuchte, wird abgelehnt."""
import json
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

ZEITLIMIT = 15 * 60  # Sekunden pro Aufruf
# Nur lesbar für die Agenten: Skills (deren tools/*.py das Fliessband ausführt), Agenten und Einstellungen.
SCHREIBSCHUTZ = (Path.home() / ".claude",)


class ClaudeFehler(Exception):
    pass


class ZeitAbgelaufen(ClaudeFehler):
    pass


class Frist:
    """Gesamtzeit eines Schritts (z.B. 2 h für bauen). None = ohne Gesamtgrenze."""

    def __init__(self, sekunden: float | None, uhr: Callable[[], float] = time.monotonic):
        self.uhr = uhr
        self.ende = None if sekunden is None else uhr() + sekunden

    def zeitlimit(self) -> int:
        """Zeitlimit für den nächsten Aufruf: höchstens 15 Min, nie über die Gesamtzeit hinaus."""
        if self.ende is None:
            return ZEITLIMIT
        rest = self.ende - self.uhr()
        if rest <= 0:
            raise ZeitAbgelaufen("Zeitlimit des Schritts erreicht")
        return int(min(ZEITLIMIT, rest))

    def pruefe(self) -> None:
        self.zeitlimit()


def mit_frist(lauf, frist: Frist):
    """Bindet einen Lauf an die Gesamtzeit eines Schritts. Ein eigenes zeitlimit gilt, wenn es kürzer ist als die Frist."""
    def gebunden(agent, auftrag, ausgabe, werkzeuge=("Read", "Write"), ordner=(), zeitlimit=None):
        rest = frist.zeitlimit()
        return lauf(agent, auftrag, ausgabe, werkzeuge=werkzeuge, ordner=ordner,
                    zeitlimit=rest if zeitlimit is None else min(zeitlimit, rest))
    return gebunden


def programm() -> str:
    return shutil.which("claude") or str(Path.home() / ".local" / "bin" / "claude")


def schreibverbot(nur_lesen) -> list[str]:
    """Deny-Regeln für Write und Edit in diesen Ordnern. Deny gilt vor --allowedTools und acceptEdits.
    Absolute Pfade brauchen in Claude-Code-Regeln das Präfix //."""
    regeln = []
    for o in nur_lesen:
        for pfad in dict.fromkeys((Path(o), Path(o).resolve())):
            ziel = "/" + pfad.as_posix()
            regeln += [f"Write({ziel}/**)", f"Edit({ziel}/**)"]
    return regeln


def befehl(agent: str, werkzeuge, ordner, nur_lesen=SCHREIBSCHUTZ) -> list[str]:
    """Ordner in `ordner` sind per --add-dir erreichbar. Liegt einer in `nur_lesen`, darf der Agent dort nur lesen."""
    b = [programm(), "-p", "--agent", agent,
         "--permission-mode", "acceptEdits", "--permission-prompts", "none",
         "--tools", ",".join(werkzeuge), "--allowedTools", *werkzeuge,
         "--strict-mcp-config", "--no-session-persistence", "--output-format", "json"]
    verbot = schreibverbot(nur_lesen)
    if verbot:
        b += ["--disallowedTools", *verbot]
    for o in ordner:
        b += ["--add-dir", str(o)]
    return b


def umgebung(cwd: Path, ordner) -> dict:
    """GateGuard (Hook des ecc-Plugins) nur für die Ordner dieses Laufs lockern, wie bei den Vault-Jobs."""
    env = dict(os.environ)
    env["GATEGUARD_EXEMPT_GLOBS"] = ",".join(f"{p}/**" for p in (cwd, *ordner))
    env["GATEGUARD_BASH_ROUTINE_DISABLED"] = "1"
    return env


def _meldung(r: subprocess.CompletedProcess) -> str:
    try:
        ergebnis = json.loads(r.stdout).get("result")
    except (json.JSONDecodeError, AttributeError, TypeError):
        ergebnis = None
    text = ergebnis if isinstance(ergebnis, str) and ergebnis.strip() else (r.stderr or r.stdout or "")
    zeilen = [z.strip() for z in text.splitlines() if z.strip()]
    return zeilen[-1][:200] if zeilen else "keine Meldung"


def _ist_fehler(r: subprocess.CompletedProcess) -> bool:
    if r.returncode != 0:
        return True
    try:
        return bool(json.loads(r.stdout).get("is_error"))
    except (json.JSONDecodeError, AttributeError, TypeError):
        return False


class ClaudeLauf:
    """Echter Aufruf. Tests ersetzen 'ausfuehren' (sonst subprocess.run)."""

    def __init__(self, cwd: Path, log: Path, ausfuehren=subprocess.run, nur_lesen=SCHREIBSCHUTZ):
        self.cwd, self.log, self.ausfuehren, self.nur_lesen = cwd, log, ausfuehren, tuple(nur_lesen)

    def _protokoll(self, agent: str, ausgabe: Path, text: str) -> None:
        self.log.parent.mkdir(parents=True, exist_ok=True)
        with self.log.open("a", encoding="utf-8") as f:
            f.write(f"=== {datetime.now():%Y-%m-%d %H:%M:%S} claude --agent {agent} → {ausgabe} ===\n{text}\n")

    def __call__(self, agent: str, auftrag: str, ausgabe: Path, werkzeuge=("Read", "Write"), ordner=(),
                 zeitlimit: int = ZEITLIMIT) -> Path:
        ausgabe = Path(ausgabe)
        vorher = ausgabe.stat().st_mtime_ns if ausgabe.exists() else None
        try:
            r = self.ausfuehren(befehl(agent, werkzeuge, ordner, self.nur_lesen), input=auftrag, capture_output=True, text=True,
                                timeout=zeitlimit, cwd=self.cwd, env=umgebung(self.cwd, ordner))
        except subprocess.TimeoutExpired:
            self._protokoll(agent, ausgabe, f"Zeitlimit {zeitlimit} s überschritten")
            raise ClaudeFehler(f"{agent}: keine Antwort innerhalb von {zeitlimit // 60} Min") from None
        except FileNotFoundError:
            raise ClaudeFehler(f"claude nicht gefunden ({programm()})") from None
        self._protokoll(agent, ausgabe, f"Exit {r.returncode}\n{(r.stdout or '')[-3000:]}\n{(r.stderr or '')[-2000:]}")
        if _ist_fehler(r):
            raise ClaudeFehler(f"{agent}: {_meldung(r)}")
        if not ausgabe.exists() or ausgabe.stat().st_mtime_ns == vorher:
            raise ClaudeFehler(f"{agent}: hat {ausgabe.name} nicht geschrieben")
        return ausgabe
