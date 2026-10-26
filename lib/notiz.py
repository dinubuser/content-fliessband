"""Liest die Apple-Notiz «Content-Ideen» per osascript (nur lesen, nie ändern) und merkt sich verwendete Zeilen
in daten/verwendet.json (Hash pro Zeile)."""
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Callable

from lib.manifest import schreibe_json

NOTIZ = "Content-Ideen"
SKRIPT = f'''tell application "Notes"
  set treffer to (every note whose name is "{NOTIZ}")
  if (count of treffer) is 0 then return ""
  return plaintext of item 1 of treffer
end tell'''
AUFZAEHLUNG = "-*•◦– "  # Zeichen von Aufzählungen am Zeilenanfang


class NotizFehler(Exception):
    pass


def osascript(skript: str) -> str:
    """Führt AppleScript aus. Fehlt die Freigabe für die Automation, kommt NotizFehler."""
    try:
        r = subprocess.run(["osascript", "-e", skript], capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        raise NotizFehler("Notizen antwortet nicht (60 s), fehlt die Freigabe unter Datenschutz > Automation?") from None
    if r.returncode != 0:
        raise NotizFehler(f"Apple-Notiz nicht lesbar: {r.stderr.strip()[:150]}")
    return r.stdout


def zeilen_hash(zeile: str) -> str:
    return hashlib.sha256(" ".join(zeile.split()).encode("utf-8")).hexdigest()[:16]


def _verwendet(pfad: Path) -> set[str]:
    if not pfad.exists():
        return set()
    try:
        return set(json.loads(pfad.read_text(encoding="utf-8")).get("hashes", []))
    except (json.JSONDecodeError, AttributeError):
        raise NotizFehler(f"{pfad} ist kaputt (erwartet {{\"hashes\": [...]}})") from None


def offene_ideen(verwendet_pfad: Path, lesen: Callable[[str], str] = osascript) -> list[str]:
    """Jede nicht leere Zeile der Notiz ist eine Idee. Titelzeile, doppelte und verwendete Zeilen fallen weg."""
    benutzt = _verwendet(verwendet_pfad)
    ideen = []
    for roh in lesen(SKRIPT).splitlines():
        zeile = " ".join(roh.split()).lstrip(AUFZAEHLUNG).strip()
        if not zeile or zeile == NOTIZ or zeile in ideen or zeilen_hash(zeile) in benutzt:
            continue
        ideen.append(zeile)
    return ideen


def merke_verwendet(verwendet_pfad: Path, zeile: str) -> None:
    benutzt = _verwendet(verwendet_pfad)
    benutzt.add(zeilen_hash(zeile))
    schreibe_json(verwendet_pfad, {"hashes": sorted(benutzt)})
