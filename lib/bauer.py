"""Setzt Leser, Prüfungen, Renderer und Manifest zu einem Karussell zusammen."""
import shutil
from datetime import date, datetime
from pathlib import Path

from lib import manifest
from lib.leser import lese_beitrag
from lib.pruefungen import pruefe
from lib.renderer import rendere_slides

STANDARD_BASIS = Path.home() / "content-fliessband"


def baue_karussell(quelle: Path, termin: datetime | None = None,
                   basis: Path = STANDARD_BASIS, heute: date | None = None) -> tuple[Path, dict]:
    quelle = Path(quelle).expanduser().resolve()
    beitrag = lese_beitrag(quelle)
    pruefungen = pruefe(beitrag)

    woche = manifest.woche_von(termin, heute or date.today())
    slug = manifest.slug_von(quelle)
    wochen_ordner = basis / "wochen" / woche
    ziel = wochen_ordner / slug
    tmp = wochen_ordner / f".tmp-{slug}"
    manifest_pfad = wochen_ordner / "manifest.json"

    # Kaputtes Manifest vor dem Rendern erkennen, damit kein fertiger Ordner ohne Eintrag bleibt
    manifest.lade(manifest_pfad, woche)

    # Erst in einen temporären Ordner bauen, damit ein Abbruch nichts Halbfertiges hinterlässt
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        pngs = rendere_slides(beitrag.slides, tmp)
        (tmp / "caption.txt").write_text(beitrag.caption + "\n", encoding="utf-8")
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    shutil.rmtree(ziel, ignore_errors=True)
    tmp.rename(ziel)

    eintrag = {
        "id": f"{woche}-{slug}",
        "format": "karussell",
        "quelle": str(quelle),
        "termin": termin.isoformat(timespec="minutes") if termin else None,
        "status": "braucht_eingabe" if pruefungen["platzhalter"] else "entwurf",
        "caption": "caption.txt",
        "medien": [p.name for p in pngs],
        "pruefungen": pruefungen,
        "notiz": "",
        "erstellt": datetime.now().isoformat(timespec="seconds"),
    }
    manifest.trage_ein(manifest_pfad, woche, eintrag)
    return ziel, eintrag
