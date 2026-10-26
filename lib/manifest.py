"""Wochen-Manifest: eine JSON-Datei pro Woche, die alle Etappen teilen."""
import json
import os
import re
from datetime import date, datetime
from pathlib import Path


def woche_von(termin: datetime | None, heute: date) -> str:
    jahr, kw, _ = (termin.date() if termin else heute).isocalendar()
    return f"{jahr}-KW{kw:02d}"


def slug_von(pfad: Path) -> str:
    stamm = Path(pfad).stem
    stamm = re.sub(r"^\d{4}-\d{2}-\d{2}_", "", stamm)
    stamm = re.sub(r"^(karussell|reel)_", "", stamm)
    return re.sub(r"_v\d+$", "", stamm)


class ManifestFehler(Exception):
    pass


def schreibe_json(pfad: Path, daten) -> None:
    """Schreibt JSON atomar: erst eine Hilfsdatei daneben, dann in einem Schritt ersetzen."""
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    tmp = pfad.with_name(pfad.name + ".tmp")
    tmp.write_text(json.dumps(daten, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, pfad)


def lade(manifest_pfad: Path, woche: str) -> dict:
    """Liest das Manifest oder liefert ein leeres, falls die Datei fehlt."""
    if not manifest_pfad.exists():
        return {"woche": woche, "beitraege": []}
    try:
        return json.loads(manifest_pfad.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ManifestFehler(f"Manifest ist kein gültiges JSON: {manifest_pfad} ({e})") from e


def trage_ein(manifest_pfad: Path, woche: str, eintrag: dict) -> None:
    """Fügt den Eintrag hinzu oder ersetzt den mit gleicher id. Schreibt atomar."""
    daten = lade(manifest_pfad, woche)
    for i, b in enumerate(daten["beitraege"]):
        if b["id"] == eintrag["id"]:
            daten["beitraege"][i] = eintrag
            break
    else:
        daten["beitraege"].append(eintrag)
    schreibe_json(manifest_pfad, daten)
