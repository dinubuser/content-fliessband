"""Setzt Leser, Prüfungen, Stimme, Musik, Komposition und Renderer zu einem Reel zusammen."""
import os
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from lib import manifest
from lib.bauer import STANDARD_BASIS
from lib.komposition import baue_komposition, hook_gruppen
from lib.musik import erzeuge_bett
from lib.aussprache import AUTO_DATEI, ergaenze, lade_listen
from lib.pruefungen import pruefe_reel
from lib.reel_bilder import rendere_cover, waehle_skalen
from lib.reel_leser import lese_reel
from lib.reel_renderer import pruefe_komposition, pruefe_video, rendere
from lib.stimme import elevenlabs_anfrage, vertone
from lib.zeitplan import laenge_status, plane

PROJEKT = Path(__file__).resolve().parent.parent


def manifest_eintrag(woche: str, slug: str, quelle: Path, termin: datetime | None,
                     pruefungen: dict, dauer: float, laenge: str | None = None) -> dict:
    eintrag = {
        "id": f"{woche}-reel-{slug}",
        "format": "reel",
        "quelle": str(quelle),
        "termin": termin.isoformat(timespec="minutes") if termin else None,
        "status": "braucht_eingabe" if pruefungen["platzhalter"] else "entwurf",
        "caption": "caption.txt",
        "medien": ["reel.mp4"],
        "cover": "cover.png",
        "dauer_s": round(dauer, 1),
        "ki_stimme": True,
        "pruefungen": pruefungen,
        "notiz": "",
        "erstellt": datetime.now().isoformat(timespec="seconds"),
    }
    if laenge:
        eintrag["laenge"] = laenge
    return eintrag


def _hat_aufnahmen(ordner: Path) -> bool:
    return ordner.is_dir() and any(ordner.glob("szene-*.mp3"))


def _rette_stimme(stimme: Path, gerettet: Path) -> None:
    """Verschiebt die Aufnahmen nach 'gerettet'. Der alte Stand wird per Umbenennen ersetzt,
    damit nie 'gerettet/stimme/' verschachtelt entsteht."""
    if not _hat_aufnahmen(stimme):
        return
    gerettet.parent.mkdir(parents=True, exist_ok=True)
    neu = gerettet.parent / f".tmp-neu-{gerettet.name}"
    alt = gerettet.parent / f".tmp-alt-{gerettet.name}"
    shutil.rmtree(neu, ignore_errors=True)
    shutil.rmtree(alt, ignore_errors=True)
    shutil.move(str(stimme), str(neu))
    if gerettet.exists():
        os.replace(gerettet, alt)
    os.replace(neu, gerettet)
    shutil.rmtree(alt, ignore_errors=True)


def baue_reel(quelle: Path, termin: datetime | None = None, basis: Path = STANDARD_BASIS,
              heute: date | None = None,
              anfrage: Callable[[str], dict] = elevenlabs_anfrage,
              laenge: str | None = None,
              aussprache_pruefer: Callable | None = None) -> tuple[Path, dict]:
    """Baut reel.mp4, cover.png, caption.txt und stimme/ in wochen/<woche>/reel-<slug>/ und trägt ins Manifest ein.
    'anfrage' ist die ElevenLabs-Anfrage (Tests geben eine Attrappe mit).
    'laenge' (kurz oder mittel aus dem Wochenplan) landet im Manifest.
    'aussprache_pruefer' (Etappe 8): (szenen, liste) -> (neu, verworfen); ohne ihn keine Aussprache-Prüfung."""
    quelle = Path(quelle).expanduser().resolve()
    reel = lese_reel(quelle)
    pruefungen = pruefe_reel(reel)

    woche = manifest.woche_von(termin, heute or date.today())
    slug = manifest.slug_von(quelle)
    wochen_ordner = basis / "wochen" / woche
    ziel = wochen_ordner / f"reel-{slug}"
    tmp = wochen_ordner / f".tmp-reel-{slug}"
    manifest_pfad = wochen_ordner / "manifest.json"
    log = basis / "logs" / f"{woche}-reel-{slug}.log"
    # Aufnahmen eines gescheiterten Laufs (ausserhalb von wochen/, damit dort nichts Halbfertiges liegt)
    gerettet = basis / "zwischenspeicher" / f"{woche}-reel-{slug}"

    # Kaputtes Manifest vor dem teuren Teil erkennen
    manifest.lade(manifest_pfad, woche)

    aussprache = lade_listen(PROJEKT / "aussprache.txt", basis / AUTO_DATEI, log)
    if aussprache_pruefer is not None:
        pruefungen["aussprache_neu"] = ergaenze(aussprache, reel.szenen, aussprache_pruefer, basis / AUTO_DATEI,
                                                slug, heute or date.today(), log)

    # Erst in einen temporären Ordner bauen, damit ein Abbruch nichts Halbfertiges hinterlässt
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        tmp.mkdir(parents=True)
        # Zwischenspeicher der Stimme übernehmen (spart ElevenLabs-Guthaben). Der gerettete Stand
        # ist jünger als der im fertigen Ordner, weil ein erfolgreicher Lauf ihn wegräumt.
        alt = gerettet if _hat_aufnahmen(gerettet) else ziel / "stimme"
        if alt.is_dir():
            shutil.copytree(alt, tmp / "stimme")
        aufnahmen = vertone(reel.szenen, tmp / "stimme", aussprache, anfrage=anfrage)
        plan = plane(aufnahmen)
        pruefungen["laenge"] = laenge_status(plan.gesamt)

        sprache = [(z.start, z.start + a.dauer) for z, a in zip(plan.szenen, aufnahmen)]
        bett = erzeuge_bett(plan.gesamt, sprache, tmp / "_ton" / "bett.wav",
                            musik_ordner=PROJEKT / "musik", woche_nr=int(woche[-2:]))

        hook_text = [" ".join(w.wort for w in g.woerter) for g in hook_gruppen(aufnahmen, plan)]
        skalen = waehle_skalen(reel.szenen, {1: hook_text})
        komp = baue_komposition(reel, aufnahmen, plan, skalen, bett, tmp / "_komposition")
        pruefe_komposition(komp, log)
        rendere(komp, tmp / "reel.mp4", log)
        pruefe_video(tmp / "reel.mp4", plan.gesamt)

        rendere_cover(reel.szenen[0].einblendung, tmp / "cover.png")
        (tmp / "caption.txt").write_text(reel.caption + "\n", encoding="utf-8")
        shutil.rmtree(tmp / "_komposition")
        shutil.rmtree(tmp / "_ton")
    except BaseException:
        # Die Rettung der Stimme darf den ursprünglichen Fehler nie verdecken und tmp immer wegräumen
        try:
            _rette_stimme(tmp / "stimme", gerettet)
        except BaseException:
            pass
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        raise
    shutil.rmtree(ziel, ignore_errors=True)
    tmp.rename(ziel)
    shutil.rmtree(gerettet, ignore_errors=True)

    eintrag = manifest_eintrag(woche, slug, quelle, termin, pruefungen, plan.gesamt, laenge)
    manifest.trage_ein(manifest_pfad, woche, eintrag)
    return ziel, eintrag
