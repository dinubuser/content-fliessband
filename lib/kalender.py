"""Zielwoche, Termine und Zeitfenster der Wochen-Jobs (lokale Zeit des Macs).

Posttage und Postzeit sind einstellbar: FLIESSBAND_POSTTAGE (vier Wochentage, 1 = Montag bis 7 = Sonntag, Standard
2,3,4,6 = Di Mi Do Sa) und FLIESSBAND_POSTZEIT (HH:MM, Standard 19:00). Die Zeitzone des Servers steht in
FLIESSBAND_ZEITZONE (siehe .env.example)."""
import json
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path

from lib.konfig import wert
from lib.manifest import schreibe_json, woche_von

# Vierer-Plan: Reel, Karussell, Reel, Karussell an den vier Posttagen (Standard Di Mi Do Sa).
# Sechser-Plan (Schalter «plaetze» = 6, Standard bleibt 4): Mo Karussell und Fr Reel kommen dazu, deshalb müssen
# Montag und Freitag frei sein. Die Nummern laufen nach Datum, damit Übersicht und Planer in Terminreihenfolge arbeiten.
STANDARD_POSTTAGE = "2,3,4,6"
STANDARD_POSTZEIT = "19:00"
PLAETZE_DATEI = Path("daten") / "plaetze.json"   # relativ zur Basis, nicht in Git; fehlt sie, gilt 4
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


def posttage() -> list[int]:
    """Die vier Posttage als ISO-Wochentage (1 = Montag bis 7 = Sonntag), aufsteigend, aus FLIESSBAND_POSTTAGE."""
    roh = wert("FLIESSBAND_POSTTAGE", STANDARD_POSTTAGE)
    try:
        tage = [int(x) for x in roh.split(",")]
    except ValueError:
        tage = []
    if len(tage) != 4 or tage != sorted(set(tage)) or not all(1 <= t <= 7 for t in tage):
        raise KalenderFehler(f"FLIESSBAND_POSTTAGE '{roh}' ungültig: vier verschiedene Wochentage, aufsteigend, "
                             f"1 = Montag bis 7 = Sonntag, z.B. {STANDARD_POSTTAGE}")
    return tage


def postzeit() -> time:
    """Uhrzeit aller Posts aus FLIESSBAND_POSTZEIT (HH:MM)."""
    roh = wert("FLIESSBAND_POSTZEIT", STANDARD_POSTZEIT)
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", roh.strip())
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise KalenderFehler(f"FLIESSBAND_POSTZEIT '{roh}' ungültig, erwartet HH:MM, z.B. {STANDARD_POSTZEIT}")
    return time(int(m.group(1)), int(m.group(2)))


def postzeit_text() -> str:
    return f"{postzeit():%H:%M}"


def uhr(termin: str) -> str:
    """'2026-10-27T19:00' → '19:00'"""
    return f"{datetime.fromisoformat(termin):%H:%M}"


def _pruefe_sechs(tage: list[int]) -> None:
    if 1 in tage or 5 in tage:
        raise KalenderFehler("6 Plätze pro Woche brauchen einen freien Montag und Freitag, aber FLIESSBAND_POSTTAGE "
                             f"enthält {','.join(str(t) for t in tage)}. Entweder 4 Plätze lassen oder die Posttage ändern.")


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
    if anzahl == 6:
        _pruefe_sechs(posttage())
    schreibe_json(Path(basis) / PLAETZE_DATEI, {"plaetze": anzahl})


def termine(woche: str, plaetze: int = 4) -> list[dict]:
    """Die Termine der Woche (4 oder 6), nach Datum: [{nr, format, termin 'YYYY-MM-DDTHH:MM'}], Reels mit laenge."""
    pruefe_woche(woche)
    jahr, kw = int(woche[:4]), int(woche[-2:])
    tage, zeit = posttage(), postzeit()
    # (Format, ISO-Wochentag, Reel-Rolle): Rolle 1 und 3 sind die beiden Reels des Vierer-Plans, «kurz» das Zusatz-Reel
    plan = [("reel", tage[0], 1), ("karussell", tage[1], None), ("reel", tage[2], 3), ("karussell", tage[3], None)]
    if plaetze == 6:
        _pruefe_sechs(tage)
        plan += [("karussell", 1, None), ("reel", 5, "kurz")]
    plan.sort(key=lambda p: p[1])
    liste = []
    for nr, (format, tag, rolle) in enumerate(plan, 1):
        t = {"nr": nr, "format": format,
             "termin": datetime.combine(date.fromisocalendar(jahr, kw, tag), zeit).isoformat(timespec="minutes")}
        if format == "reel":
            # erstes Reel wie bisher, zweites die andere Länge, jedes Zusatz-Reel kurz: am wenigsten ElevenLabs-Zeichen
            t["laenge"] = "kurz" if rolle == "kurz" else reel_laenge(woche, rolle)
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
