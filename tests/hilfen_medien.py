"""Hilfen für die Mac-Tests. Eigenes Modul statt conftest, weil server/tests ein zweites conftest hat."""
import subprocess
from pathlib import Path


def stille_mp3(pfad: Path, sekunden: float) -> Path:
    """Erzeugt eine stille MP3 (44,1 kHz, 128 kbit/s) mit ffmpeg."""
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
         "-t", f"{sekunden:.3f}", "-c:a", "libmp3lame", "-b:a", "128k", str(pfad)],
        check=True,
    )
    return pfad
