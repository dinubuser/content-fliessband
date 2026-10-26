"""Etappe 9: Geschichten-Speicher ~/agentur-daten/geschichten.md. Beantwortet Betreiber eine Planer-Frage, hängt das
Fliessband Frage und Antwort mit Datum an («## YYYY-MM-DD: <Frage>», darunter die Antwort). Nur anhängen, nie
überschreiben. Der Planer bekommt die letzten 30 Einträge in seine Eingabe."""
import re
from datetime import date
from pathlib import Path

KOPF = ("# Geschichten des Betreibers\n\nAntworten auf Fragen des Planers, vom Content-Fliessband angehängt. "
        "Nur anhängen, nie überschreiben.\n")
EINTRAG = re.compile(r"^## (\d{4}-\d{2}-\d{2}): (.*)$")
MAX_EINTRAEGE = 30


def merke(pfad: Path, datum: date, frage: str, antwort: str) -> None:
    """Hängt Frage und Antwort an. Fehlt die Datei, wird sie mit Kopfzeile angelegt."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    kopf = "" if pfad.exists() and pfad.stat().st_size > 0 else KOPF
    frage = " ".join(frage.split())
    antwort = "\n".join(z.rstrip() for z in antwort.strip().splitlines())
    with pfad.open("a", encoding="utf-8") as f:
        f.write(f"{kopf}\n## {datum.isoformat()}: {frage}\n\n{antwort}\n")


def lies(pfad: Path, anzahl: int = MAX_EINTRAEGE) -> list[dict]:
    """Die letzten `anzahl` Einträge als {datum, frage, antwort}, älteste zuerst. Fehlt die Datei: leer."""
    try:
        zeilen = pfad.read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        return []
    eintraege = []
    for z in zeilen:
        m = EINTRAG.match(z)
        if m:
            eintraege.append({"datum": m.group(1), "frage": m.group(2).strip(), "antwort": []})
        elif eintraege:
            eintraege[-1]["antwort"].append(z)
    for e in eintraege:
        e["antwort"] = "\n".join(e["antwort"]).strip()
    return eintraege[-anzahl:] if anzahl > 0 else []
