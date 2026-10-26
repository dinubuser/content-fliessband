"""Prüft und rendert die HyperFrames-Komposition, kontrolliert das fertige MP4."""
import subprocess
from pathlib import Path

from lib.medien import hat_ton, video_info

PROJEKT = Path(__file__).resolve().parent.parent
HYPERFRAMES = PROJEKT / "node_modules" / ".bin" / "hyperframes"
TOLERANZ = 0.5
CHECK_TIMEOUT = 180  # Sekunden
RENDER_TIMEOUT = 900  # Sekunden


class RenderFehler(Exception):
    pass


def _lauf(befehl: list[str], log: Path, was: str, timeout: int) -> None:
    if not HYPERFRAMES.exists():
        raise RenderFehler(f"{HYPERFRAMES} fehlt, im Projektordner 'npm install' ausführen")
    log.parent.mkdir(parents=True, exist_ok=True)
    # Anhängen mit Kopfzeile: check- und render-Ausgabe bleiben beide im Protokoll
    with log.open("a", encoding="utf-8") as f:
        f.write(f"=== hyperframes {was} ===\n")
        f.flush()
        try:
            r = subprocess.run(befehl, stdout=f, stderr=subprocess.STDOUT, cwd=PROJEKT, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise RenderFehler(
                f"HyperFrames {was} nach {timeout} s abgebrochen (Zeitlimit), Protokoll: {log}") from None
    if r.returncode != 0:
        raise RenderFehler(f"HyperFrames {was} gescheitert, Protokoll: {log}")


def pruefe_komposition(ordner: Path, log: Path) -> None:
    # Kontrast-Prüfung aus: Orange auf Creme ist der Look des Betreibers (wie beim Karussell) und bewusst gewählt
    _lauf([str(HYPERFRAMES), "check", str(ordner), "--no-contrast"], log, "check", CHECK_TIMEOUT)


def rendere(ordner: Path, ziel: Path, log: Path) -> Path:
    _lauf([str(HYPERFRAMES), "render", str(ordner), "-o", str(ziel), "--fps", "30", "--quality", "standard"],
          log, "render", RENDER_TIMEOUT)
    if not ziel.exists():
        raise RenderFehler(f"HyperFrames hat kein Video geschrieben, Protokoll: {log}")
    return ziel


def pruefe_video(mp4: Path, erwartet: float) -> None:
    b, h, d = video_info(mp4)
    if (b, h) != (1080, 1920):
        raise RenderFehler(f"Video hat {b} × {h} statt 1080 × 1920")
    if abs(d - erwartet) > TOLERANZ:
        raise RenderFehler(f"Länge {d:.1f} s statt {erwartet:.1f} s")
    if not hat_ton(mp4):
        raise RenderFehler("Video ohne Ton")
