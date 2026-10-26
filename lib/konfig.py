"""Konfiguration des Fliessbands: Umgebungsvariablen, sonst die Datei .env im Projektordner, sonst der Standard.

Alle Werte stehen in .env.example. Die Platzhalter-Standards (your-…, example.com) müssen vor dem Einsatz
ersetzt werden. Ein fehlender Wert bricht nicht sofort ab, der Fehler kommt erst beim Aufruf des Dienstes.
"""
import os
from pathlib import Path

ORDNER = Path(__file__).resolve().parent.parent
_geladen = False


def _lade_env_datei(pfad: Path) -> None:
    if not pfad.is_file():
        return
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#") or "=" not in zeile:
            continue
        schluessel, _, wert = zeile.partition("=")
        os.environ.setdefault(schluessel.strip(), wert.strip().strip('"').strip("'"))


def wert(name: str, standard: str = "") -> str:
    """Wert der Variable `name`: Umgebung, dann .env im Projektordner, dann `standard`."""
    global _geladen
    if not _geladen:
        _lade_env_datei(ORDNER / ".env")
        _geladen = True
    return os.environ.get(name) or standard
