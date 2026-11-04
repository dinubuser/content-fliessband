"""Kontozahlen für die Social-Kacheln in AgenticOS (Teil 2): Follower und Aufrufe pro Konto."""
from datetime import date, datetime, time
from urllib.parse import parse_qs

from briefkasten.ablauf import ZONE

MAX_TAGE = 30
MAX_FEHLER = 300


def stempel(tag: date) -> int:
    """Mitternacht Schweizer Zeit als Unix-Zeit (für since/until)."""
    return int(datetime.combine(tag, time(), ZONE).timestamp())


def summe(antwort: dict, name: str):
    """Wert einer Kennzahl: total_value, sonst Summe der Tageswerte, sonst None."""
    for m in antwort.get("data", []) if isinstance(antwort, dict) else []:
        if m.get("name") != name:
            continue
        tv = m.get("total_value")
        if isinstance(tv, dict) and "value" in tv:
            return tv["value"]
        werte = [v.get("value") for v in m.get("values", []) if isinstance(v.get("value"), (int, float))]
        return sum(werte) if werte else None
    return None


def tage_aus(abfrage: str) -> int:
    tage = int(parse_qs(abfrage).get("tage", ["3"])[0])
    if not 1 <= tage <= MAX_TAGE:
        raise ValueError(f"tage muss zwischen 1 und {MAX_TAGE} liegen")
    return tage


def sammle(konten: dict, tage: int, heute: date | None = None) -> dict:
    heute = heute or datetime.now(ZONE).date()
    aus = {}
    for name, client in konten.items():
        try:
            aus[name] = client.konto(tage, heute)
        except Exception as e:  # ein Konto darf die anderen nie verhindern; Clients schwärzen den Schlüssel selbst
            aus[name] = {"fehler": (str(e) or type(e).__name__)[:MAX_FEHLER]}
    return {"stand": datetime.now(ZONE).isoformat(timespec="seconds"), "konten": aus}
