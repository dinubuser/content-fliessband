"""Etappe 4: Betreiber-Entscheide aus dem Briefkasten umsetzen («fliessband entscheide», launchd alle 15 Minuten,
solange der Mac wach ist). Jedes Ereignis läuft unter der Sperre seiner Woche und gilt erst danach als gelesen.
Ist eine Woche gesperrt (Samstags-Bau läuft), folgt der Rest beim nächsten Lauf. Danach werden für die laufende
und die nächste Woche liegengebliebene Sendungen und Anmeldungen nachgeholt."""
import json
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

from lib import freigabe, guthaben, hochladen, manifest, texter
from lib.aussprache import pruefer as aussprache_pruefer
from lib.bauer import baue_karussell
from lib.bot import BotFehler
from lib.briefkasten import BriefkastenFehler
from lib.claude_lauf import Frist, ZeitAbgelaufen, mit_frist
from lib.fehler import einzeilig
from lib.kalender import zielwoche
from lib.leser import lese_beitrag
from lib.manifest import ManifestFehler, schreibe_json, woche_von
from lib.pruefungen import pruefe, pruefe_reel
from lib.reel_bauer import _rette_stimme, baue_reel
from lib.reel_leser import lese_reel
from lib.woche import (START_SCHLUSS_VERMERK, START_VERMERK, STIMME_RESERVE, THEMA_FEHLER, ZEIT_BAUEN, Sperre, SperreBelegt, baue_offene,
                       melde_offene, neue_sprechzeichen, sende_beitrag, senden, termin_erreicht)
from lib.wochenplan import PlanFehler, Wochenplan, haenge_an


class EntscheidFehler(Exception):
    pass


ZEIT_NEUBAU = 60 * 60   # Sekunden für Content-Agent und Bau eines Beitrags
VORLAUF_PUFFER = timedelta(minutes=15)   # Verwerfen: Reserve nur, wenn Bau plus Puffer vor dem Termin Platz hat
STAND = "entscheide-stand.json"   # in daten/: Fehlläufe in Folge und ob die Störung gemeldet ist
TAKT_MINUTEN = 15       # launchd-Takt von «fliessband entscheide»
SCHWELLE = 8            # so viele gescheiterte Läufe in Folge (2 Stunden), dann einmal Meldung an den Betreiber
# Pflichtfelder eines Entscheid-Ereignisses (Server schreibt sie immer, siehe server/briefkasten/ablauf.py)
PFLICHT = {"nr": int, "art": str, "beitrag": str, "woche": str}
PFLICHT_ENTSCHEID = {"zeit": str, "version": int}
PFLICHT_ART = {"aendern": {"notiz": str}, "gepostet": {"nachricht": dict}}
MAX_NEUBAUTEN = 2       # Spec: höchstens 2 Neubauten pro Beitrag (Schutz auf dem Mac, der Server sperrt den Knopf)
# Freigabe-Felder, die der Bauer beim Ersetzen des Manifest-Eintrags nicht kennt
FREIGABE_FELDER = ("version", "neubauten", "notizen", "notizen_ab", "notiz_nr", "umgesetzt_nr", "entschieden",
                   "mediathek", "medien_gemeldet", "instagram_fehler", "mediathek_fehler")
# Neubau scheitert mit Meldung an den Betreiber, die alte Version gilt weiter. KeyError: thema["beitrag"] fehlt.
NEUBAU_FEHLER = THEMA_FEHLER + (EntscheidFehler, guthaben.GuthabenFehler, BotFehler, KeyError)


def wochen(heute: date) -> list[str]:
    """Laufende Woche und die Woche nach dem laufenden Wochenende."""
    return sorted({woche_von(None, heute), zielwoche(heute)})


def _thema(plan: Wochenplan, woche: str, id: str) -> dict | None:
    return next((t for t in plan.themen if freigabe.beitrag_id(woche, t) == id), None)


def _status(status: str):
    def aktion(e, plan, t, pfade, dienste, log):
        pfad = freigabe.manifest_pfad(pfade, e["woche"])
        if status in ("freigegeben", "entwurf") and \
                freigabe.eintrag(pfad, e["woche"], e["beitrag"])["status"] == freigabe.PLATZHALTER:
            # Der Server zeigt dafür keinen Knopf. Kommt das Ereignis trotzdem, gilt es als gelesen, ändert nichts.
            log(f"Ereignis {e['nr']} ({e['art']} {e['beitrag']}): hat noch Platzhalter, nicht umgesetzt")
            if status == "freigegeben":
                _sage(dienste, log, f"«{freigabe.titel_von(t)}» nicht freigegeben, hat noch Platzhalter.")
            return
        entschieden = None if status == "entwurf" else e["zeit"]
        freigabe.aendere(pfad, e["woche"], e["beitrag"], status=status, entschieden=entschieden)
        log(f"{e['beitrag']}: {status}")
    return aktion


def _pruefe_guthaben(alt: Path, neu: Path, dienste) -> None:
    noetig = neue_sprechzeichen(alt, neu)
    if noetig == 0:
        return
    rest = dienste.elevenlabs_rest()
    if rest < noetig + STIMME_RESERVE:
        raise EntscheidFehler(f"ElevenLabs-Guthaben zu klein ({rest} von {noetig + STIMME_RESERVE} Zeichen)")


def _baue(t: dict, beitrag: Path, pfade, dienste, frist=None):
    termin = datetime.fromisoformat(t["termin"])
    if t["format"] == "reel":
        lauf = mit_frist(dienste.claude, frist) if frist else dienste.claude
        pruefer = aussprache_pruefer(lauf, pfade.basis / "zwischenspeicher" / "aussprache")
        return baue_reel(beitrag, termin=termin, basis=pfade.basis, anfrage=dienste.stimme, laenge=t.get("laenge"),
                         aussprache_pruefer=pruefer)
    return baue_karussell(beitrag, termin=termin, basis=pfade.basis)


def _melde_fehler(dienste, id: str, grund: str, log) -> bool:
    """True: Betreiber bekommt die Meldung (Briefkasten erreicht)."""
    try:
        dienste.briefkasten.fehler(id, grund)
        return True
    except BriefkastenFehler as ex:
        log(f"Fehler von {id} nicht gemeldet: {einzeilig(ex)}")
        return False


def _pruefe_platzhalter(neu: Path, format: str, geltend=()) -> None:
    """Gleiche Prüfung wie der Bauer (braucht_eingabe): eine neue Fassung muss ohne Platzhalter sein, sonst bliebe
    sie ohne Freigeben-Knopf. Die Meldung nennt die offenen Stellen der neuen Fassung und (geltend) die der
    geltenden Version, damit Betreiber sie in der nächsten Notiz füllen kann. Frühere Notizen zählen mit."""
    pruefungen = pruefe_reel(lese_reel(neu)) if format == "reel" else pruefe(lese_beitrag(neu))
    if pruefungen["platzhalter"]:
        geltend_teil = f" Offen in der geltenden Version: {', '.join(geltend)}." if geltend else ""
        raise EntscheidFehler(f"Neue Fassung hat noch Platzhalter ({', '.join(pruefungen['platzhalter'])})."
                              f"{geltend_teil} Bitte per ✏️ Ändern angeben, was dort stehen soll, "
                              "frühere Notizen zählen mit.")


def _notizen_ab(e: dict) -> int:
    """Ab welcher Notiz (Index in notizen) gelten sie für die geltende Version: alle seit dem letzten
    Versionswechsel. Ältere Einträge ohne notizen_ab: Version 1 alle, sonst nur die neueste."""
    if "notizen_ab" in e:
        return e["notizen_ab"]
    return 0 if e["version"] == 1 else max(len(e["notizen"]) - 1, 0)


def _gescheitert(pfad: Path, woche: str, id: str, nr: int, grund: str, dienste, log) -> None:
    log(f"{id}: Neubau gescheitert ({grund})")
    freigabe.aendere(pfad, woche, id, umgesetzt_nr=nr, fehler_grund=grund, fehler_gemeldet=False)
    if _melde_fehler(dienste, id, grund, log):
        freigabe.aendere(pfad, woche, id, fehler_gemeldet=True)


def _aendere(e, plan, t, pfade, dienste, log) -> None:
    """Notiz sichern, Text überarbeiten, neu bauen, senden, als neue Version anmelden. Scheitert etwas, gilt
    die alte Version weiter (Ordner und Manifest-Eintrag werden zurückgeholt) und der Betreiber bekommt den Grund.
    Wiederholung desselben Ereignisses (Abholen gilt «mindestens einmal»): Die Ereignis-nr steht im Manifest
    (notiz_nr: Notiz gesichert, umgesetzt_nr: Neubau versucht), so gibt es keine doppelte Notiz und keinen
    zweiten Neubau. Eine gescheiterte Fehlermeldung (fehler_gemeldet False) wird dabei einmal nachgeholt."""
    woche, id = e["woche"], e["beitrag"]
    pfad = freigabe.manifest_pfad(pfade, woche)
    alt = freigabe.eintrag(pfad, woche, id)
    if alt.get("umgesetzt_nr", 0) >= e["nr"]:
        log(f"Ereignis {e['nr']} ({id}): schon umgesetzt")
        if alt.get("fehler_gemeldet") is False and alt.get("fehler_grund"):
            if _melde_fehler(dienste, id, alt["fehler_grund"], log):
                freigabe.aendere(pfad, woche, id, fehler_gemeldet=True)
        return
    notizen = alt["notizen"]
    if alt.get("notiz_nr") != e["nr"]:
        notizen = notizen + [{"zeit": e["zeit"], "text": e["notiz"]}]
        alt = freigabe.aendere(pfad, woche, id, notizen=notizen, notiz_nr=e["nr"])   # zuerst sichern (Etappe 6)
    if termin_erreicht(t, dienste):
        # Notiz ist gesichert, aber kein Neubau mehr (keine Kosten), der Server setzt ohnehin verpasst
        log(f"Ereignis {e['nr']} ({id}): Termin vorbei, kein Neubau")
        freigabe.aendere(pfad, woche, id, umgesetzt_nr=e["nr"])
        return
    if alt["neubauten"] >= MAX_NEUBAUTEN:
        _gescheitert(pfad, woche, id, e["nr"], f"Schon {alt['neubauten']} Neubauten, mehr sind nicht vorgesehen",
                     dienste, log)
        return
    sicherung = pfade.basis / "zwischenspeicher" / "neubau" / f"{id}-v{alt['version']}"
    log(f"{id}: Neubau nach Notiz «{e['notiz']}»")
    try:
        ordner = Path(t["ordner"])
        offen = (alt.get("pruefungen", {}).get("platzhalter") or []) if alt["status"] == freigabe.PLATZHALTER else []
        frist = Frist(ZEIT_NEUBAU, dienste.uhr)
        neu = texter.ueberarbeite(t, e["notiz"], pfade, mit_frist(dienste.claude, frist),
                                  platzhalter=offen, fruehere=[n["text"] for n in notizen[_notizen_ab(alt):-1]])
        _pruefe_platzhalter(neu, t["format"], offen)
        if t["format"] == "reel":
            _pruefe_guthaben(Path(t["beitrag"]), neu, dienste)
        if sicherung.exists():
            shutil.rmtree(sicherung)
        shutil.copytree(ordner, sicherung)
        gebaut = False
        start_ergaenzt = False
        start_schluss_fehlt = False
        alte_dauer = t.get("dauer_s")
        alte_aussprache = t.get("aussprache_neu")
        try:
            _, eintrag_neu = _baue(t, neu, pfade, dienste, frist)
            gebaut = True
            start_ergaenzt = bool(eintrag_neu["pruefungen"].get("start_ergaenzt"))
            start_schluss_fehlt = bool(eintrag_neu["pruefungen"].get("start_schluss_fehlt"))
            if t["format"] == "reel":
                t["dauer_s"] = eintrag_neu.get("dauer_s")   # für den Längen-Hinweis beim Senden
                t["aussprache_neu"] = eintrag_neu["pruefungen"].get("aussprache_neu", [])
            freigabe.aendere(pfad, woche, id, **{k: alt[k] for k in FREIGABE_FELDER if k in alt})
            sende_beitrag(t, woche, pfade, dienste)
        except BaseException:
            if t["format"] == "reel":
                t["dauer_s"] = alte_dauer
                if alte_aussprache is None:
                    t.pop("aussprache_neu", None)
                else:
                    t["aussprache_neu"] = alte_aussprache
            if gebaut and t["format"] == "reel":
                # Die neue Stimme ist bezahlt: für den nächsten Versuch retten (wie baue_reel)
                try:
                    _rette_stimme(ordner / "stimme", pfade.basis / "zwischenspeicher" / id)
                except OSError as ex:
                    log(f"{id}: Stimme nicht gerettet ({einzeilig(ex)})")
            # Zuerst Ordner, dann Manifest zurückholen
            shutil.rmtree(ordner, ignore_errors=True)
            shutil.copytree(sicherung, ordner)
            manifest.trage_ein(pfad, woche, alt)
            shutil.rmtree(sicherung, ignore_errors=True)   # erst nach geglücktem Zurückholen
            raise
        shutil.rmtree(sicherung, ignore_errors=True)
    except ZeitAbgelaufen:
        # Wie ein Neubau-Fehler, sonst hinge jeder Lauf am selben Ereignis
        _gescheitert(pfad, woche, id, e["nr"], "Überarbeitung hat zu lange gedauert", dienste, log)
        return
    except NEUBAU_FEHLER as ex:
        _gescheitert(pfad, woche, id, e["nr"], einzeilig(ex), dienste, log)
        return
    version = alt["version"] + 1
    freigabe.aendere(pfad, woche, id, status="entwurf", entschieden=None, version=version,
                     neubauten=alt["neubauten"] + 1, notizen=notizen, notizen_ab=len(notizen),
                     umgesetzt_nr=e["nr"])
    t["beitrag"] = str(neu)
    t["vermerk"] = haenge_an(t["vermerk"], f"Version {version} nach Betreiber-Notiz")
    for flag, vermerk in ((start_ergaenzt, START_VERMERK), (start_schluss_fehlt, START_SCHLUSS_VERMERK)):
        if flag and vermerk not in t["vermerk"]:
            t["vermerk"] = haenge_an(t["vermerk"], vermerk)
    plan.speichere()
    log(f"{id}: Version {version} gesendet")
    melde_offene(plan, woche, pfade, dienste, log)


def _sage(dienste, log, text: str) -> bool:
    """True: in Telegram angekommen."""
    log(text)
    try:
        dienste.bot.sende_text(text)
        return True
    except BotFehler as ex:
        log(f"Nicht gesendet: {einzeilig(ex)}")
        return False


def _offene_reserve(plan, t) -> dict | None:
    """Aktives Thema mit gleicher nr, das noch nicht gebaut ist (Reserve nach Absturz mitten im Verwerfen)."""
    return next((r for r in plan.aktive() if r["nr"] == t["nr"] and r["status"] in ("bereit", "text_fertig",
                                                                                     "getestet")), None)


def _vorlauf_zu_kurz(t: dict, dienste) -> bool:
    """Reicht die Zeit bis zum Termin nicht für einen ganzen Bau (ZEIT_BAUEN) plus 15 Minuten?"""
    jetzt = dienste.jetzt()
    if jetzt.tzinfo is not None:
        jetzt = jetzt.astimezone().replace(tzinfo=None)   # Termine sind lokale Zeit ohne Zone
    return datetime.fromisoformat(t["termin"]) - jetzt < timedelta(seconds=ZEIT_BAUEN) + VORLAUF_PUFFER


def _verwirf(e, plan, t, pfade, dienste, log) -> None:
    """Beitrag verwerfen, Reserve im gleichen Format auf denselben Termin holen, bauen, senden, anmelden.
    Ist der Termin näher als ein ganzer Bau plus 15 Minuten, fällt der Beitrag ohne Reserve weg.
    Wiederholung desselben Ereignisses (Abholen gilt «mindestens einmal»): Ist das Thema schon ersetzt oder die
    Ereignis-nr als umgesetzt gemerkt, gibt es keine zweite Reserve und keine doppelte Meldung. Liegt die
    Reserve nach einem Absturz noch ungebaut im Plan, wird sie fertig gebaut und gesendet. Eine Reserve mit
    Platzhaltern (braucht_eingabe) bekommt wie am Samstag nur Ändern und Verwerfen, Betreiber erfährt die offenen Stellen."""
    woche, id = e["woche"], e["beitrag"]
    pfad = freigabe.manifest_pfad(pfade, woche)
    titel = freigabe.titel_von(t)
    if t["status"] == "ersetzt" or freigabe.eintrag(pfad, woche, id).get("umgesetzt_nr", 0) >= e["nr"]:
        if t["status"] != "ersetzt" or _offene_reserve(plan, t) is None:
            log(f"Ereignis {e['nr']} ({id}): schon verworfen")
            return
        log(f"{id}: Reserve nach Abbruch fertig bauen")
    else:
        freigabe.aendere(pfad, woche, id, status="verworfen", entschieden=e["zeit"])
        if _vorlauf_zu_kurz(t, dienste):
            freigabe.aendere(pfad, woche, id, umgesetzt_nr=e["nr"])
            _sage(dienste, log, f"Termin zu nah, «{titel}» fällt weg, keine Reserve.")
            return
        ersatz = plan.ersetze(t, "Der Betreiber hat verworfen", andere_erlaubt=False)
        if ersatz is None:
            freigabe.aendere(pfad, woche, id, umgesetzt_nr=e["nr"])
            _sage(dienste, log, f"Keine Reserve mehr: «{titel}» fällt diese Woche weg.")
            return
        log(f"{id}: verworfen, Reserve {ersatz['slug']}")
    baue_offene(plan, pfade, dienste, log)
    # Neu auflösen: die Guthaben-Prüfung kann die Reserve nochmals ersetzt haben
    ersatz = next((r for r in plan.aktive() if r["nr"] == t["nr"]), None)
    if ersatz is None or ersatz["status"] != "gebaut":
        if ersatz is not None and ersatz["status"] == "fehlgeschlagen":
            grund = ersatz["vermerk"]
        else:
            grund = "nicht fertig geworden"
        _sage(dienste, log, f"Reserve für «{titel}» gescheitert: {grund}")
        return
    try:
        senden(woche, pfade, dienste, log, plan=plan, mit_uebersicht=False)
    except BotFehler as ex:
        log(f"Reserve nicht gesendet ({einzeilig(ex)}), nächster Versuch beim nächsten Lauf")
        return
    try:
        neu = freigabe.eintrag(pfad, woche, freigabe.beitrag_id(woche, ersatz))
    except ManifestFehler as ex:
        log(f"Reserve {ersatz['slug']}: Manifest nicht lesbar ({einzeilig(ex)})")
        return
    if neu["status"] == "braucht_eingabe":
        offen = neu.get("pruefungen", {}).get("platzhalter") or []
        liste = f" ({', '.join(offen)})" if offen else ""
        _sage(dienste, log, f"Reserve für «{titel}» hat noch Platzhalter{liste}, bitte per ✏️ Ändern ergänzen.")


def _gepostet(e, plan, t, pfade, dienste, log) -> None:
    n = e["nachricht"]
    freigabe.aendere(freigabe.manifest_pfad(pfade, e["woche"]), e["woche"], e["beitrag"], status="gepostet",
                     gepostet=e["zeit"], instagram_id=str(n.get("instagram_id") or ""), permalink=n.get("permalink"))
    log(f"{e['beitrag']}: gepostet {n.get('permalink') or ''}".rstrip())


AKTIONEN = {
    "freigegeben": _status("freigegeben"),
    "zurueckgenommen": _status("entwurf"),
    "verpasst": _status("verpasst"),
    "aendern": _aendere,
    "verworfen": _verwirf,
    "gepostet": _gepostet,
    "ausgelassen": _status("ausgelassen"),
}


def _verarbeite(e: dict, pfade, dienste, log) -> None:
    plan = Wochenplan.lade(pfade.plan(e["woche"]), e["woche"])
    t = _thema(plan, e["woche"], e["beitrag"])
    aktion = AKTIONEN.get(e["art"])
    if aktion is None:
        log(f"Ereignis {e['nr']} übersprungen ({e['art']} {e['beitrag']}): nicht unterstützt")
        return
    if t is None:
        log(f"Ereignis {e['nr']} übersprungen ({e['art']} {e['beitrag']}): unbekannt")
        return
    aktuell = freigabe.eintrag(freigabe.manifest_pfad(pfade, e["woche"]), e["woche"], e["beitrag"])["version"]
    if e.get("version") is not None and e["version"] != aktuell:
        log(f"Ereignis {e['nr']} übersprungen ({e['art']} {e['beitrag']}): veraltet "
            f"(Version {e['version']}, aktuell {aktuell})")
        return
    aktion(e, plan, t, pfade, dienste, log)


def _fehler_nachholen(woche: str, pfade, dienste, log) -> None:
    """Gescheiterte Meldungen «Neubau gescheitert» (fehler_gemeldet False) erneut an den Briefkasten schicken,
    auch wenn das Ereignis nicht nochmals kommt. Scheitert es wieder, folgt der nächste Versuch beim nächsten Lauf."""
    pfad = freigabe.manifest_pfad(pfade, woche)
    if not pfad.exists():
        return
    try:
        beitraege = manifest.lade(pfad, woche)["beitraege"]
    except ManifestFehler as ex:
        log(f"Fehlermeldungen {woche} nicht nachgeholt: {einzeilig(ex)}")
        return
    for b in beitraege:
        if b.get("fehler_gemeldet") is False and b.get("fehler_grund"):
            if _melde_fehler(dienste, b["id"], b["fehler_grund"], log):
                freigabe.aendere(pfad, woche, b["id"], fehler_gemeldet=True)
                log(f"{b['id']}: Fehlermeldung nachgeholt")


def nachholen(woche: str, pfade, dienste, log, fehler: list[str] | None = None) -> None:
    """Gebaute, aber nicht gesendete Beiträge senden (z.B. Reserve nach Telegram-Fehler), gescheiterte
    Fehlermeldungen und Anmeldungen nachholen. fehler: sammelt Gründe gescheiterter Briefkasten-Aufrufe
    (siehe melde_offene)."""
    plan = Wochenplan.lade(pfade.plan(woche), woche)
    _fehler_nachholen(woche, pfade, dienste, log)
    if plan.daten["schritte"]["gesendet"] and any(t["status"] == "gebaut" for t in plan.aktive()):
        try:
            senden(woche, pfade, dienste, log, plan=plan, mit_uebersicht=False)
        except BotFehler as ex:
            log(f"Senden {woche} gescheitert: {einzeilig(ex)}")
            return
    melde_offene(plan, woche, pfade, dienste, log, fehler=fehler)
    hochladen.reiche_nach(plan, woche, pfade, dienste, log, fehler=fehler)
    hochladen.aufraeumen(woche, pfade, dienste, log)


def fehlende_felder(e) -> list[str]:
    """Fehlende oder falsch getypte Pflichtfelder eines Ereignisses (leer: vollständig)."""
    if not isinstance(e, dict):
        return ["alles"]
    pflicht = dict(PFLICHT)
    if e.get("art") in AKTIONEN:
        pflicht.update(PFLICHT_ENTSCHEID, **PFLICHT_ART.get(e["art"], {}))
    return [f for f, typ in pflicht.items()
            if not isinstance(e.get(f), typ) or isinstance(e.get(f), bool) or e.get(f) in ("",)]


def _stoerung(pfade, dienste, log, grund: str | None) -> None:
    """Zählt gescheiterte Läufe in Folge (grund) in daten/entscheide-stand.json und meldet die Störung einmal per
    Telegram, sobald SCHWELLE erreicht ist. grund None: Lauf geglückt, Zähler zurück."""
    pfad = pfade.daten / STAND
    try:
        stand = json.loads(pfad.read_text(encoding="utf-8"))
        if not isinstance(stand, dict):
            stand = {}
    except (OSError, ValueError):
        stand = {}
    if grund is None:
        if stand.get("fehler_in_folge") or stand.get("gemeldet"):
            schreibe_json(pfad, {"fehler_in_folge": 0, "gemeldet": False})
        return
    n, gemeldet = int(stand.get("fehler_in_folge", 0)) + 1, bool(stand.get("gemeldet"))
    if n >= SCHWELLE and not gemeldet:
        stunden = SCHWELLE * TAKT_MINUTEN // 60
        gemeldet = _sage(dienste, log, f"Briefkasten seit {stunden} Stunden gestört ({grund}). "
                                       "Knöpfe funktionieren, umgesetzt wird erst danach.")
    schreibe_json(pfad, {"fehler_in_folge": n, "gemeldet": gemeldet, "grund": grund})


def entscheide(pfade, dienste, log) -> int:
    """Liefert die Zahl verarbeiteter Ereignisse (auch übersprungene). Unvollständige Ereignisse werden geloggt,
    als gelesen gemerkt und übersprungen. Scheitert der Briefkasten (Abholen oder Anmelden) SCHWELLE Läufe in
    Folge, bekommt Betreiber einmal eine Meldung."""
    bk = dienste.briefkasten
    if bk is None:
        raise EntscheidFehler("Briefkasten nicht eingerichtet, zuerst «fliessband briefkasten umstellen»")
    try:
        ereignisse = bk.ereignisse("entscheide")
    except BriefkastenFehler as ex:
        _stoerung(pfade, dienste, log, einzeilig(ex))
        raise
    erledigt = 0
    for e in ereignisse:
        fehlt = fehlende_felder(e)
        if fehlt:
            log(f"Ereignis {e.get('nr', '?') if isinstance(e, dict) else '?'} übersprungen: unvollständig "
                f"(fehlt {', '.join(fehlt)})")
            if "nr" not in fehlt:
                bk.merke("entscheide", e["nr"])
                erledigt += 1
            continue
        try:
            with Sperre(pfade.daten / f"sperre-{e['woche']}"):
                try:
                    _verarbeite(e, pfade, dienste, log)
                except (ManifestFehler, PlanFehler) as ex:
                    log(f"Ereignis {e['nr']} ({e['art']} {e['beitrag']}) nicht umgesetzt: {einzeilig(ex)}")
        except SperreBelegt:
            log(f"{e['woche']} ist gesperrt (Bau läuft), der Rest folgt beim nächsten Lauf")
            break
        bk.merke("entscheide", e["nr"])
        erledigt += 1
    fehler: list[str] = []
    for woche in wochen(dienste.jetzt().date()):
        if not pfade.plan(woche).exists():
            continue
        try:
            with Sperre(pfade.daten / f"sperre-{woche}"):
                nachholen(woche, pfade, dienste, log, fehler=fehler)
        except SperreBelegt:
            log(f"{woche} ist gesperrt, Nachholen beim nächsten Lauf")
    _stoerung(pfade, dienste, log, fehler[0] if fehler else None)
    return erledigt
