"""Freigabe-Felder pro Beitrag im Wochen-Manifest (Etappe 4) und die Angaben für den Briefkasten.
Felder: status (entwurf, braucht_eingabe, freigegeben, verworfen, verpasst, gepostet, ausgelassen), version (ab 1), neubauten (ab 0),
notizen [{zeit, text}] (für Etappe 6), entschieden (ISO-Zeit oder None). Fehlende Felder gelten als Standard.
braucht_eingabe (der Bauer setzt es, Text hat noch Platzhalter) bekommt nur Ändern und Verwerfen und kann nie
direkt auf freigegeben wechseln, erst eine neue Fassung ohne Platzhalter (wieder entwurf).
gepostet (Felder gepostet ISO-Zeit, instagram_id, permalink) und ausgelassen kommen vom Server (Etappe 5)."""
from pathlib import Path

from lib import manifest
from lib.manifest import ManifestFehler, schreibe_json
from lib.umgebung import Pfade

STATUS = ("entwurf", "braucht_eingabe", "freigegeben", "verworfen", "verpasst", "gepostet", "ausgelassen")
PLATZHALTER = "braucht_eingabe"
STANDARD = {"version": 1, "neubauten": 0, "entschieden": None}
MAX_TITEL = 60


def beitrag_id(woche: str, thema: dict) -> str:
    """Gleiche id wie baue_reel (…-reel-<slug>) und baue_karussell (…-<slug>)."""
    if thema["format"] == "reel":
        return f"{woche}-reel-{thema['slug']}"
    return f"{woche}-{thema['slug']}"


def manifest_pfad(pfade: Pfade, woche: str) -> Path:
    return pfade.woche(woche) / "manifest.json"


def _mit_standard(b: dict) -> dict:
    return {**STANDARD, "notizen": [], **b}


def eintrag(pfad: Path, woche: str, id: str) -> dict:
    for b in manifest.lade(pfad, woche)["beitraege"]:
        if b["id"] == id:
            return _mit_standard(b)
    raise ManifestFehler(f"{id} fehlt im Manifest {pfad}")


def aendere(pfad: Path, woche: str, id: str, **felder) -> dict:
    if "status" in felder and felder["status"] not in STATUS:
        raise ManifestFehler(f"unbekannter Freigabe-Status {felder['status']}")
    daten = manifest.lade(pfad, woche)
    for i, b in enumerate(daten["beitraege"]):
        if b["id"] == id:
            if b.get("status") == PLATZHALTER and felder.get("status") == "freigegeben":
                raise ManifestFehler(f"{id} hat noch Platzhalter, freigeben geht nicht")
            daten["beitraege"][i] = {**_mit_standard(b), **felder}
            schreibe_json(pfad, daten)
            return daten["beitraege"][i]
    raise ManifestFehler(f"{id} fehlt im Manifest {pfad}")


def titel_von(thema: dict) -> str:
    """Thema als kurzer Titel für die Knopf-Nachricht (höchstens 60 Zeichen, an einer Wortgrenze gekürzt)."""
    text = " ".join(thema["thema"].split())
    if len(text) <= MAX_TITEL:
        return text
    return text[:MAX_TITEL - 1].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


def anmeldung(woche: str, thema: dict, e: dict) -> dict:
    return {"id": e["id"], "woche": woche, "version": e["version"], "titel": titel_von(thema),
            "format": thema["format"], "termin": thema["termin"], "neubauten": e["neubauten"],
            "platzhalter": e.get("status") == PLATZHALTER}
