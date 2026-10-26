"""Wochenplan wochen/<KW>/plan.json: Themen, Zustände, Vermerke. Jede Änderung wird sofort atomar gespeichert,
darum kann jeder Schritt nach einem Abbruch dort weitermachen, wo er aufgehört hat."""
import json
from datetime import datetime
from pathlib import Path

from lib.kalender import RESERVE_LAENGE
from lib.manifest import schreibe_json

ZUSTAENDE = ("geplant", "frage_gesendet", "bereit", "text_fertig", "getestet", "gebaut", "gesendet",
             "ersetzt", "fehlgeschlagen")
FERTIG = ("gebaut", "gesendet")
AUS = ("ersetzt", "fehlgeschlagen")


class PlanFehler(Exception):
    pass


def neu(woche: str) -> dict:
    return {"woche": woche,
            "schritte": {"vorbereitet": None, "gebaut": None, "gesendet": None},
            "vermerke": [], "ausreisser": [], "themen": [], "reserve": [],
            "ausfall_gemeldet": False}


def arbeitsfelder(thema: dict) -> dict:
    """Ein Thema des Planers mit den Feldern, die der Ablauf füllt."""
    return dict(thema, antwort=None, status="geplant", beitrag=None, test=[], vermerk="",
                frage_nachricht=None, ordner=None)


def haenge_an(alt: str, neu_text: str) -> str:
    """Vermerke aneinanderhängen, ohne leere Teile."""
    return "; ".join(v for v in (alt, neu_text) if v)


def _setze_laenge(thema: dict, format: str) -> None:
    """Reels brauchen eine Länge (eingesprungene oder umgeschriebene: immer kurz), Karussells keine."""
    if format == "reel":
        thema["laenge"] = RESERVE_LAENGE
    else:
        thema.pop("laenge", None)


class Wochenplan:
    def __init__(self, pfad: Path, daten: dict):
        self.pfad = pfad
        self.daten = daten

    @classmethod
    def lade(cls, pfad: Path, woche: str) -> "Wochenplan":
        if not pfad.exists():
            return cls(pfad, neu(woche))
        try:
            daten = json.loads(pfad.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise PlanFehler(f"plan.json ist kein gültiges JSON: {pfad} ({e})") from e
        if daten.get("woche") != woche:
            raise PlanFehler(f"{pfad} gehört zu {daten.get('woche')}, nicht zu {woche}")
        return cls(pfad, daten)

    def speichere(self) -> None:
        schreibe_json(self.pfad, self.daten)

    @property
    def themen(self) -> list[dict]:
        return self.daten["themen"]

    @property
    def vorbereitet(self) -> bool:
        return bool(self.daten["schritte"]["vorbereitet"])

    def aktive(self) -> list[dict]:
        """Themen, die einen Termin besetzen (ohne ersetzte), nach Nummer."""
        return sorted((t for t in self.themen if t["status"] != "ersetzt"), key=lambda t: t["nr"])

    def setze(self, thema: dict, status: str, vermerk: str | None = None) -> None:
        if status not in ZUSTAENDE:
            raise PlanFehler(f"unbekannter Zustand '{status}'")
        thema["status"] = status
        if vermerk is not None:
            thema["vermerk"] = vermerk
        self.speichere()

    def vermerke(self, text: str) -> None:
        if text not in self.daten["vermerke"]:
            self.daten["vermerke"].append(text)
        self.speichere()

    def schritt_fertig(self, schritt: str, zeit: datetime) -> None:
        self.daten["schritte"][schritt] = zeit.isoformat(timespec="minutes")
        self.speichere()

    def ersetze(self, thema: dict, grund: str, format: str | None = None,
                andere_erlaubt: bool = True) -> dict | None:
        """Setzt das Thema auf 'ersetzt' und holt ein Reserve-Thema auf seinen Termin (Zustand 'bereit').
        Zuerst eine Reserve im gewünschten Format, sonst (falls erlaubt) die andere, im gewünschten Format.
        Ohne passende Reserve: None, das Thema bleibt unverändert."""
        ziel = format or thema["format"]
        reserve = self.daten["reserve"]
        wahl = next((r for r in reserve if r["format"] == ziel), None)
        if wahl is None and andere_erlaubt and reserve:
            wahl = reserve[0]
        if wahl is None:
            return None
        reserve.remove(wahl)
        vermerk = f"Reserve für «{thema['thema']}» ({grund})"
        if wahl["format"] != ziel:
            vermerk += f", als {ziel} umgeschrieben"
        ersatz = dict(wahl, nr=thema["nr"], termin=thema["termin"], format=ziel, status="bereit", vermerk=vermerk)
        _setze_laenge(ersatz, ziel)
        thema["status"] = "ersetzt"
        thema["vermerk"] = grund
        self.themen.append(ersatz)
        self.speichere()
        return ersatz

    def schreibe_um(self, thema: dict, format: str, grund: str) -> None:
        """Gleiches Thema in anderem Format neu schreiben (Text und Tests von vorne)."""
        thema.update(format=format, status="bereit", beitrag=None, test=[],
                     vermerk=haenge_an(thema["vermerk"], f"als {format} neu geschrieben ({grund})"))
        _setze_laenge(thema, format)
        self.speichere()
