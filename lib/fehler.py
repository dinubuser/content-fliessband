"""Fehlerarten, die eine saubere Meldung in einer Zeile bekommen statt eines Tracebacks."""
from lib.figuren import FigurenFehler
from lib.leser import LeserFehler
from lib.manifest import ManifestFehler
from lib.medien import MedienFehler
from lib.musik import MusikFehler
from lib.pruefungen import AusspracheFehler
from lib.reel_renderer import RenderFehler
from lib.renderer import ZuLangFehler
from lib.stimme import StimmFehler
from lib.zeitplan import LaengeFehler

# Fehler beim Bauen eines Beitrags (Etappe 1 und 2).
# OSError umfasst FileNotFoundError, fehlende Rechte und "ist ein Ordner".
BAU_FEHLER = (LeserFehler, ManifestFehler, StimmFehler, LaengeFehler, MusikFehler, ZuLangFehler,
              RenderFehler, MedienFehler, AusspracheFehler, FigurenFehler, OSError)


def einzeilig(fehler: BaseException) -> str:
    """Meldung eines Fehlers als eine Zeile."""
    return " ".join(str(fehler).split())
