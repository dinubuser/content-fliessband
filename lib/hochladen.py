"""Etappe 5 auf dem Mac: Dateien angemeldeter Beiträge in die Mediathek von example.com laden, die Adressen dem
Briefkasten nachreichen und nie gepostete Dateien wieder löschen. Läuft in senden, anmelden und bei jedem
entscheide-Lauf (nachholen), bis alles gemeldet ist.
Manifest pro Beitrag: mediathek [{version, teil, name, wp_id, url, geloescht}], medien_gemeldet (Version),
mediathek_fehler (Version, für den Betreiber einen dauerhaften Upload-Fehler gemeldet bekam).
Jeder Upload wird sofort im Manifest vermerkt, ein Abbruch lädt nichts doppelt hoch."""
from datetime import datetime, timedelta
from pathlib import Path

from lib import freigabe, instagram_medien, manifest
from lib.bot import BotFehler
from lib.briefkasten import BriefkastenFehler
from lib.fehler import einzeilig
from lib.manifest import ManifestFehler
from lib.mediathek import MediathekFehler

HOCHLADEN = ("entwurf", "braucht_eingabe", "freigegeben")
AUFRAEUMEN = ("verworfen", "ausgelassen", "verpasst")
NACHHOLEN = timedelta(hours=3)   # so lange versucht der Server nach dem Termin noch zu posten


def _zu_spaet(t: dict, dienste) -> bool:
    jetzt = dienste.jetzt()
    if jetzt.tzinfo is not None:
        jetzt = jetzt.astimezone().replace(tzinfo=None)
    return datetime.fromisoformat(t["termin"]) + NACHHOLEN <= jetzt


def _lade_hoch(t: dict, e: dict, woche: str, pfade, mt, pfad: Path) -> list[dict]:
    """Alle Teile der aktuellen Version in der Mediathek (fehlende hochladen). Liefert die Einträge in Reihenfolge."""
    version, liste = e["version"], list(e.get("mediathek") or [])
    ziel = pfade.basis / "zwischenspeicher" / "instagram" / f"{e['id']}-v{version}"
    eintraege = []
    for datei, teil in instagram_medien.dateien(t["format"], Path(t["ordner"]), ziel):
        da = next((x for x in liste if x["version"] == version and x["teil"] == teil and not x.get("geloescht")), None)
        if da is None:
            name = f"fliessband-{e['id']}-v{version}-{teil}{datei.suffix}"
            da = {"version": version, "teil": teil, "name": name, **mt.lade_hoch(datei, name), "geloescht": False}
            liste.append(da)
            freigabe.aendere(pfad, woche, e["id"], mediathek=liste)
        eintraege.append(da)
    return eintraege


def _melde_mediathek_fehler(t: dict, e: dict, woche: str, pfad: Path, dienste, log, grund: str) -> None:
    """Dauerhafter Upload-Fehler: Betreiber bekommt pro Beitrag und Version genau eine Nachricht. Scheitert das
    Senden, versucht es der nächste Lauf wieder."""
    if e.get("mediathek_fehler") == e["version"]:
        return
    try:
        dienste.bot.sende_text(f"Dateien von «{freigabe.titel_von(t)}» konnten nicht in die Mediathek: {grund}. "
                               "Ohne Dateien wird nicht gepostet.")
    except BotFehler as bx:
        log(f"Thema {t['nr']}: Hinweis zur Mediathek nicht gesendet ({einzeilig(bx)})")
        return
    freigabe.aendere(pfad, woche, e["id"], mediathek_fehler=e["version"])


def _briefkasten_gestoert(ex: BriefkastenFehler) -> bool:
    """Nur Ausfälle zählen als Störung (nicht erreichbar, 5xx), nicht abgelehnte Anfragen (4xx)."""
    return ex.code is None or ex.code >= 500


def reiche_nach(plan, woche: str, pfade, dienste, log, fehler: list[str] | None = None) -> bool:
    """Für angemeldete Beiträge (aktuelle Version, Status entwurf, braucht_eingabe oder freigegeben, Termin + 3 h
    nicht vorbei) Dateien hochladen und Adressen melden. Scheitert ein Beitrag, laufen die anderen weiter.
    fehler: sammelt Gründe gescheiterter Briefkasten-Aufrufe (Dauerfehler-Meldung in entscheide).
    True: alles gemeldet."""
    bk, mt = dienste.briefkasten, dienste.mediathek
    if bk is None or mt is None:
        return True
    pfad = freigabe.manifest_pfad(pfade, woche)
    alles = True
    for t in plan.aktive():
        if t["status"] != "gesendet" or not t.get("angemeldet"):
            continue
        try:
            e = freigabe.eintrag(pfad, woche, freigabe.beitrag_id(woche, t))
        except ManifestFehler as ex:
            log(f"Thema {t['nr']}: Dateien nicht hochgeladen ({einzeilig(ex)})")
            continue
        if (e["status"] not in HOCHLADEN or t["angemeldet"] != e["version"]
                or e.get("medien_gemeldet") == e["version"] or _zu_spaet(t, dienste)):
            continue
        try:
            teile = _lade_hoch(t, e, woche, pfade, mt, pfad)
            caption = instagram_medien.caption(Path(t["ordner"]))
        except (MediathekFehler, OSError) as ex:
            log(f"Thema {t['nr']}: Dateien nicht hochgeladen ({einzeilig(ex)}), nächster Versuch beim nächsten Lauf")
            if not isinstance(ex, MediathekFehler) or ex.dauerhaft:
                _melde_mediathek_fehler(t, e, woche, pfad, dienste, log, einzeilig(ex))
            alles = False
            continue
        try:
            bk.medien(e["id"], {"version": e["version"],
                                "medien": [x["url"] for x in teile if x["teil"] != "cover"],
                                "cover": next((x["url"] for x in teile if x["teil"] == "cover"), None),
                                "caption": caption})
        except BriefkastenFehler as ex:
            log(f"Thema {t['nr']}: Dateien nicht gemeldet ({einzeilig(ex)}), nächster Versuch beim nächsten Lauf")
            if fehler is not None and _briefkasten_gestoert(ex):
                fehler.append(einzeilig(ex))
            alles = False
            continue
        freigabe.aendere(pfad, woche, e["id"], medien_gemeldet=e["version"])
        log(f"Thema {t['nr']}: Dateien in der Mediathek, Adressen gemeldet (Version {e['version']})")
    return alles


def aufraeumen(woche: str, pfade, dienste, log) -> None:
    """Nie gepostete Dateien löschen: alles von verworfenen, ausgelassenen und verpassten Beiträgen, dazu ältere
    Versionen. Gepostete Versionen bleiben (Entscheid Betreiber). Nur Einträge aus dem Manifest, nie Fremdes."""
    mt = dienste.mediathek
    pfad = freigabe.manifest_pfad(pfade, woche)
    if mt is None or not pfad.exists():
        return
    try:
        beitraege = manifest.lade(pfad, woche)["beitraege"]
    except ManifestFehler as ex:
        log(f"Mediathek {woche} nicht aufgeräumt: {einzeilig(ex)}")
        return
    for b in beitraege:
        liste = list(b.get("mediathek") or [])
        version = b.get("version", 1)
        weg = [x for x in liste if not x.get("geloescht")
               and (b.get("status") in AUFRAEUMEN or x["version"] < version)]
        geloescht = 0
        for x in weg:
            try:
                mt.loesche(x["wp_id"])
            except MediathekFehler as ex:
                log(f"{b['id']}: Mediathek-Eintrag {x['wp_id']} nicht gelöscht ({einzeilig(ex)})")
                break
            x["geloescht"] = True   # x ist ein Element von liste
            freigabe.aendere(pfad, woche, b["id"], mediathek=liste)
            geloescht += 1
        if geloescht:
            log(f"{b['id']}: {geloescht} nie gepostete Datei(en) aus der Mediathek gelöscht")
