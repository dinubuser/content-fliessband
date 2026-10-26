"""Kleine ffprobe-Helfer für Ton- und Videodateien."""
import json
import subprocess
from pathlib import Path


class MedienFehler(Exception):
    pass


def _probe(pfad: Path) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(pfad)],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise MedienFehler(f"ffprobe kann {pfad} nicht lesen: {r.stderr.strip()[:200]}")
    return json.loads(r.stdout)


def _dauer_aus(pfad: Path, daten: dict) -> float:
    try:
        return float(daten["format"]["duration"])
    except (KeyError, TypeError, ValueError):
        raise MedienFehler(f"ffprobe liefert keine Dauer für {pfad}") from None


def dauer(pfad: Path) -> float:
    return _dauer_aus(pfad, _probe(pfad))


def video_info(pfad: Path) -> tuple[int, int, float]:
    """(Breite, Höhe, Dauer in Sekunden) des ersten Videostreams."""
    daten = _probe(pfad)
    video = next((s for s in daten["streams"] if s["codec_type"] == "video"), None)
    if video is None:
        raise MedienFehler(f"{pfad} hat keinen Videostream")
    return int(video["width"]), int(video["height"]), _dauer_aus(pfad, daten)


def hat_ton(pfad: Path) -> bool:
    """True, wenn die Datei mindestens einen Audiostream hat."""
    return any(s.get("codec_type") == "audio" for s in _probe(pfad)["streams"])
