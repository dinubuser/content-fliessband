"""Dateien eines gebauten Beitrags für Instagram (Etappe 5): Grenzen prüfen, Slides und Cover als JPEG (Instagram
nimmt über die Schnittstelle nur JPEG), Video unverändert. Teile: «01» … «10» (Slides), «video», «cover»."""
import re
from pathlib import Path

from PIL import Image

MIN_BILDER, MAX_BILDER = 2, 10
MAX_CAPTION = 2200
MAX_HASHTAGS = 30
QUALITAET = 92
HASHTAG = re.compile(r"(?<!\w)#\w+")


class InstagramPruefung(Exception):
    pass


def caption(ordner: Path) -> str:
    return (Path(ordner) / "caption.txt").read_text(encoding="utf-8").strip()


def _slides(ordner: Path) -> list[Path]:
    return sorted(Path(ordner).glob("slide-*.png"))


def pruefe(format: str, ordner: Path) -> None:
    """Wirft InstagramPruefung mit einem Satz für den Betreiber, wenn der Beitrag so nicht auf Instagram kann."""
    ordner = Path(ordner)
    if format == "karussell":
        n = len(_slides(ordner))
        if n > MAX_BILDER:
            raise InstagramPruefung(f"{n} Bilder, Instagram nimmt höchstens 10 Bilder")
        if n < MIN_BILDER:
            raise InstagramPruefung(f"{n} Bild, ein Karussell braucht mindestens 2 Bilder")
    elif not (ordner / "reel.mp4").exists():
        raise InstagramPruefung("reel.mp4 fehlt")
    text = caption(ordner)
    if len(text) > MAX_CAPTION:
        raise InstagramPruefung(f"Caption zu lang ({len(text)} von höchstens 2'200 Zeichen)")
    tags = len(HASHTAG.findall(text))
    if tags > MAX_HASHTAGS:
        raise InstagramPruefung(f"zu viele Hashtags ({tags} von höchstens 30)")


def _als_jpeg(png: Path, jpg: Path) -> Path:
    with Image.open(png) as im:
        im.convert("RGB").save(jpg, "JPEG", quality=QUALITAET, optimize=True)
    return jpg


def dateien(format: str, ordner: Path, ziel: Path) -> list[tuple[Path, str]]:
    """(Datei, Teil) in der Reihenfolge für Instagram. JPEGs entstehen in ziel (wird überschrieben)."""
    ordner, ziel = Path(ordner), Path(ziel)
    ziel.mkdir(parents=True, exist_ok=True)
    if format == "karussell":
        return [(_als_jpeg(png, ziel / f"{i:02d}.jpg"), f"{i:02d}") for i, png in enumerate(_slides(ordner), 1)]
    liste = [(ordner / "reel.mp4", "video")]
    if (ordner / "cover.png").exists():
        liste.append((_als_jpeg(ordner / "cover.png", ziel / "cover.jpg"), "cover"))
    return liste
