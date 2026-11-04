"""Zielwoche, Termine und Zeitfenster der Wochen-Jobs (lokale Zeit, Europe/Zurich)."""
import json
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path

from lib.manifest import schreibe_json, woche_von

# Thema-Nr, Format, ISO-Wochentag: Di Reel, Mi Karussell, Do Reel, Sa Karussell, je 19:00
WOCHENPLAN = [(1, "reel", 2), (2, "karussell", 3), (3, "reel", 4), (4, "karussell", 6)]
# Sechser-Plan (Schalter «plaetze» = 6, Standard bleibt 4): Mo Karussell und Fr Reel kommen dazu.
# Die Nummern laufen hier nach Datum, damit Übersicht und Planer in Terminreihenfolge arbeiten.
WOCHENPLAN_6 = [(1, "karussell", 1), (2, "reel", 2), (3, "karussell", 3), (4, "reel", 4), (5, "reel", 5),
                (6, "karussell", 6)]
PLAETZE_DATEI = Path("daten") / "plaetze.json"   # relativ zur Basis, nicht in Git; fehlt sie, gilt 4
UHRZEIT = time(19, 0)
WOCHE_MUSTER = re.compile(r"^(\d{4})-KW(\d{2})$")
TAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
FORMAT_NAME = {"reel": "Reel", "karussell": "Karussell"}
# Start der Jobs: Tage nach dem Freitag und Uhrzeit. Nachholen bis Sonntag 12:00.
START = {"lernen": (0, time(20, 0)), "vorbereiten": (0, time(22, 0)), "bauen": (1, time(22, 0))}
ENDE = (2, time(12, 0))
ENDE_LERNEN = (0, time(21, 30))   # lernen nur Fr 20:00 bis 21:30, danach holt vorbereiten es nach
# Etappe 7: Reel-Längen. Gerade KW: Di kurz, Do mittel; ungerade KW umgekehrt. Reserve-Reels immer kurz.
LAENGEN = {
    "kurz": {"text": "20 bis 30 s", "woerter": 70, "szenen": (3, 5), "hook": 12, "hinweis_ab": 35.0},
    "mittel": {"text": "30 bis 45 s", "woerter": 105, "szenen": (4, 6), "hook": 12, "hinweis_ab": 50.0},
}
RESERVE_LAENGE = "kurz"


class KalenderFehler(ValueError):
    pass


def zielwoche(heute: date) -> str:
    """ISO-Woche nach dem laufenden Wochenende: Montag der laufenden Woche + 7 Tage."""
    montag = heute - timedelta(days=heute.weekday()) + timedelta(days=7)
    return woche_von(None, montag)


def pruefe_woche(text: str) -> str:
    m = WOCHE_MUSTER.match(text)
    if not m:
        raise KalenderFehler(f"Woche '{text}' ungültig, erwartet z.B. 2026-KW44")
    try:
        date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1)
    except ValueError:
        raise KalenderFehler(f"Woche '{text}' gibt es nicht") from None
    return text


def reel_laenge(woche: str, nr: int) -> str:
    """Länge des Reels mit Thema-Nr 1 (Di) oder 3 (Do), im Wechsel nach Kalenderwoche."""
    kw = int(pruefe_woche(woche)[-2:])
    dienstag = "kurz" if kw % 2 == 0 else "mittel"
    if nr == 1:
        return dienstag
    return "mittel" if dienstag == "kurz" else "kurz"


def plaetze(basis: Path) -> int:
    """Plätze pro Woche aus dem Schalter: 4 (Standard) oder 6. Fehlende oder ungültige Datei gilt als 4."""
    try:
        wert = json.loads((Path(basis) / PLAETZE_DATEI).read_text(encoding="utf-8")).get("plaetze", 4)
    except (OSError, ValueError, AttributeError):
        return 4
    return wert if type(wert) is int and wert in (4, 6) else 4


def setze_plaetze(basis: Path, anzahl: int) -> None:
    if anzahl not in (4, 6):
        raise KalenderFehler(f"Plätze pro Woche: nur 4 oder 6, nicht {anzahl}")
    schreibe_json(Path(basis) / PLAETZE_DATEI, {"plaetze": anzahl})


def termine(woche: str, plaetze: int = 4) -> list[dict]:
    """Die Termine der Woche (4 oder 6), nach Datum: [{nr, format, termin 'YYYY-MM-DDT19:00'}], Reels mit laenge."""
    pruefe_woche(woche)
    jahr, kw = int(woche[:4]), int(woche[-2:])
    liste = []
    for nr, format, tag in (WOCHENPLAN_6 if plaetze == 6 else WOCHENPLAN):
        t = {"nr": nr, "format": format,
             "termin": datetime.combine(date.fromisocalendar(jahr, kw, tag), UHRZEIT).isoformat(timespec="minutes")}
        if format == "reel":
            # Di wie bisher, Do die andere Länge, jedes Zusatz-Reel (Fr) kurz: am wenigsten ElevenLabs-Zeichen
            t["laenge"] = reel_laenge(woche, 1) if tag == 2 else reel_laenge(woche, 3) if tag == 4 else "kurz"
        liste.append(t)
    return liste


def laengen_hinweis(laenge: str | None, dauer) -> str | None:
    """Hinweis, wenn ein Reel über der Hinweis-Grenze seiner Länge liegt, sonst None."""
    grenze = LAENGEN.get(laenge) if isinstance(laenge, str) else None
    if grenze is None or not isinstance(dauer, (int, float)) or dauer <= grenze["hinweis_ab"]:
        return None
    return f"⚠️ Reel ist {dauer:.0f} s lang (Ziel {laenge}: {grenze['text']})."


def kurz(termin: str) -> str:
    """'2026-10-27T19:00' → 'Di 27.10.'"""
    t = datetime.fromisoformat(termin)
    return f"{TAGE[t.weekday()]} {t:%d.%m.}"


def freitag(heute: date) -> date:
    """Freitag der laufenden ISO-Woche (das Wochenende, zu dem ein Lauf gehört)."""
    return heute - timedelta(days=heute.weekday()) + timedelta(days=4)


def fenster(schritt: str, jetzt: datetime) -> str:
    """'laufen' (vorbereiten Fr 22:00, bauen Sa 22:00, je bis So 12:00; lernen nur Fr 20:00 bis 21:30),
    'ausgefallen' (So 12:00 bis 23:59, nie bei lernen) oder 'ruhe'."""
    fr = freitag(jetzt.date())
    tage, uhr = START[schritt]
    start = datetime.combine(fr + timedelta(days=tage), uhr)
    if schritt == "lernen":
        ende = datetime.combine(fr + timedelta(days=ENDE_LERNEN[0]), ENDE_LERNEN[1])
        return "laufen" if start <= jetzt < ende else "ruhe"
    ende = datetime.combine(fr + timedelta(days=ENDE[0]), ENDE[1])
    schluss = datetime.combine(ende.date(), time(23, 59, 59))
    if start <= jetzt < ende:
        return "laufen"
    if ende <= jetzt <= schluss:
        return "ausgefallen"
    return "ruhe"
