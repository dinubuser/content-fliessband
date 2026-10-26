from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Grafik:
    art: str  # zahl | vergleich | liste
    teile: list[str]


@dataclass
class Bild:
    haltung: str             # Name aus katalog.json (haltungen)
    gegenstaende: list[str]  # 0 bis 2 Namen aus katalog.json (gegenstaende)


@dataclass
class Szene:
    nummer: int
    hook: bool
    sprechtext: str
    einblendung: str
    grafik: Grafik | None = None
    hinweis: str | None = None  # feste Hinweiszeile (z. B. Risikohinweis), nicht gesprochen
    bild: Bild | None = None    # Figurenszene in der Bildmitte, beim Hook immer None
    bild_hinweise: list[str] = field(default_factory=list)  # Ersatz durch den toleranten Leser


@dataclass
class Reel:
    szenen: list[Szene]
    caption: str


@dataclass
class Wort:
    wort: str     # Originalschreibweise (für Untertitel)
    start: float  # Sekunden
    ende: float


@dataclass
class Aufnahme:
    nummer: int
    datei: Path
    dauer: float
    woerter: list[Wort] = field(default_factory=list)  # Zeiten ab Beginn der Szenen-Aufnahme
