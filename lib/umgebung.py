"""Orte des Fliessbands und der Agentur, Aufruf der Agentur-Werkzeuge. Tests geben eigene Pfade mit."""
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from lib.bauer import STANDARD_BASIS
from lib.konfig import wert

HOME = Path.home()


def _pfad(name: str, standard: Path) -> Path:
    """Pfad aus der Konfiguration. «~/…» aus der .env löst Python selbst auf (die Shell tut es hier nicht)."""
    return Path(wert(name, str(standard))).expanduser()

Werkzeug = Callable[[str, list[str], int], subprocess.CompletedProcess]


@dataclass(frozen=True)
class Pfade:
    basis: Path = STANDARD_BASIS
    agentur: Path = _pfad("FLIESSBAND_AGENTUR_DIR", HOME / "meine-agentur")
    skill: Path = _pfad("FLIESSBAND_AGENTUR_SKILL", HOME / ".claude" / "skills" / "agentur")
    agentur_python: Path = _pfad("FLIESSBAND_AGENTUR_PYTHON", HOME / ".social-agentur" / "venv" / "bin" / "python")

    @property
    def daten(self) -> Path:
        return self.basis / "daten"

    def woche(self, woche: str) -> Path:
        return self.basis / "wochen" / woche

    def plan(self, woche: str) -> Path:
        return self.woche(woche) / "plan.json"

    def log(self, woche: str, schritt: str) -> Path:
        return self.basis / "logs" / f"woche-{woche}-{schritt}.log"

    @property
    def regelwerk(self) -> Path:
        return self.skill / "regeln" / "regelwerk.md"

    @property
    def geschichten(self) -> Path:
        """Etappe 9: Betreiber-Antworten auf Planer-Fragen."""
        return self.agentur / "geschichten.md"


def agentur_werkzeug(pfade: Pfade) -> Werkzeug:
    """Ruft ein Werkzeug der Agentur (tools/<name>) mit deren Python auf. Zeitlimit in Sekunden.
    Die Werkzeuge lesen ihre Schlüssel selbst und geben sie nie aus."""
    def ausfuehren(name: str, argumente: list[str], zeitlimit: int) -> subprocess.CompletedProcess:
        befehl = [str(pfade.agentur_python), str(pfade.skill / "tools" / name), *argumente]
        try:
            return subprocess.run(befehl, capture_output=True, text=True, timeout=zeitlimit)
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(befehl, 124, "", f"Fehler: {name} nach {zeitlimit} s abgebrochen")
        except FileNotFoundError:
            return subprocess.CompletedProcess(befehl, 127, "", f"Fehler: {pfade.agentur_python} fehlt")
    return ausfuehren


MAX_CAPTION = 300
MAX_NAME = 60


def fremd(text, laenge: int) -> str:
    """Fremde Daten (Captions, Accountnamen) für einen Agenten-Auftrag: eine Zeile, ohne führendes #,
    höchstens `laenge` Zeichen. So kann ein fremder Text keine eigene Überschrift oder Anweisung bilden."""
    return " ".join(str(text or "").split()).lstrip("#").strip()[:laenge]


def letzte_zeile(text: str) -> str:
    """Letzte nicht leere Zeile (die Agentur-Werkzeuge schreiben dort 'Fehler: …'), höchstens 200 Zeichen."""
    zeilen = [z.strip() for z in (text or "").splitlines() if z.strip()]
    return zeilen[-1][:200] if zeilen else "keine Meldung"
