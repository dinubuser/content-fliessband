"""Zeiten fürs Reel: wann jede Szene läuft, wie Untertitel und Hook-Wörter gruppiert werden."""
from dataclasses import dataclass, field

from lib.reel_modell import Aufnahme, Wort

PAUSE = 0.35      # Sekunden zwischen zwei Szenen
NACHLAUF = 0.8    # Sekunden nach der letzten Szene
NORMAL_BIS = 60.0
MAX_LAENGE = 90.0


class LaengeFehler(Exception):
    pass


@dataclass
class SzenenZeit:
    nummer: int
    start: float   # Sekunden ab Reel-Beginn
    dauer: float   # sichtbar bis zum Start der nächsten Szene


@dataclass
class Plan:
    szenen: list[SzenenZeit]
    gesamt: float


@dataclass
class Gruppe:
    start: float
    ende: float
    woerter: list[Wort] = field(default_factory=list)  # Zeiten ab Reel-Beginn


def plane(aufnahmen: list[Aufnahme]) -> Plan:
    # Grenzen aus der gerundeten Summe, Dauer als Differenz zweier Grenzen:
    # so endet jede Szene genau dort, wo die nächste beginnt (keine ±1 ms Lücke).
    grenzen, t = [0.0], 0.0
    for i, a in enumerate(aufnahmen):
        letzte = i == len(aufnahmen) - 1
        t += a.dauer + (NACHLAUF if letzte else PAUSE)
        grenzen.append(round(t, 3))
    szenen = [SzenenZeit(a.nummer, grenzen[i], round(grenzen[i + 1] - grenzen[i], 3))
              for i, a in enumerate(aufnahmen)]
    return Plan(szenen=szenen, gesamt=grenzen[-1])


SCHLIESSER = "»«\"'“”‘’)]}›‹"


def gruppiere(woerter: list[Wort], max_woerter: int, max_zeichen: int, brueche: str,
              versatz: float, ende: float) -> list[Gruppe]:
    """Teilt Wörter in Anzeige-Gruppen und verschiebt ihre Zeiten um 'versatz'.
    Die erste Gruppe beginnt bei 'versatz', jede Gruppe bleibt bis zum Start der nächsten, die letzte bis 'ende'."""
    gruppen: list[list[Wort]] = []
    aktuell: list[Wort] = []
    for w in woerter:
        abs_w = Wort(w.wort, round(w.start + versatz, 3), round(w.ende + versatz, 3))
        laenge = len(" ".join(x.wort for x in aktuell + [abs_w]))
        if aktuell and (len(aktuell) >= max_woerter or laenge > max_zeichen):
            gruppen.append(aktuell)
            aktuell = []
        aktuell.append(abs_w)
        if w.wort.rstrip(SCHLIESSER)[-1:] in brueche and w.wort.rstrip(SCHLIESSER):
            gruppen.append(aktuell)
            aktuell = []
    if aktuell:
        gruppen.append(aktuell)

    ergebnis = []
    for i, g in enumerate(gruppen):
        g_start = versatz if i == 0 else g[0].start
        g_ende = gruppen[i + 1][0].start if i + 1 < len(gruppen) else ende
        ergebnis.append(Gruppe(start=round(g_start, 3), ende=round(g_ende, 3), woerter=g))
    return ergebnis


def laenge_status(gesamt: float) -> str:
    if gesamt > MAX_LAENGE:
        raise LaengeFehler(f"Reel ist {gesamt:.0f} s lang (höchstens {MAX_LAENGE:.0f} s). Sprechtext kürzen.")
    return "ok" if gesamt <= NORMAL_BIS else "lang"
