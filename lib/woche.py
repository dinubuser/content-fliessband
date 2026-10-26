"""Wochenablauf des Fliessbands: vorbereiten (Fr), bauen und senden (Sa), status und job (launchd).
Jeder Schritt ist wiederholbar und macht dort weiter, wo der letzte Lauf aufgehört hat (plan.json)."""
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from lib import freigabe, geschichten, guthaben, hochladen, instagram_medien, kalender, konkurrenz, lernen, notiz, planer, texter
from lib.aussprache import hinweis as aussprache_hinweis, pruefer as aussprache_pruefer
from lib.bauer import baue_karussell
from lib.bot import VERSAND_GRENZE, Bot, BotFehler, ordne_zu, verkleinere
from lib.briefkasten import Briefkasten, BriefkastenFehler
from lib.claude_lauf import ClaudeFehler, ClaudeLauf, Frist, ZeitAbgelaufen, mit_frist
from lib.fehler import BAU_FEHLER, einzeilig
from lib.kalender import FORMAT_NAME, KalenderFehler, kurz
from lib.manifest import ManifestFehler
from lib.mediathek import Mediathek
from lib.reel_bauer import baue_reel
from lib.reel_leser import lese_reel
from lib.stimme import elevenlabs_anfrage
from lib.umgebung import Pfade, agentur_werkzeug
from lib.wochenplan import AUS, FERTIG, PlanFehler, Wochenplan, haenge_an

ZEIT_BAUEN = 2 * 60 * 60   # Sekunden für den ganzen Schritt bauen
STIMME_RESERVE = 500       # Zeichen Puffer beim ElevenLabs-Guthaben
ANMELDEN = ("entwurf", "braucht_eingabe")   # Manifest-Status, die beim Briefkasten Knöpfe bekommen
QUELLE_NAME = {"notiz": "Apple-Notiz", "ideen": "Ideen-Liste", "konkurrenz": "Konkurrenz",
               "learnings": "Learnings", "trend": "Trend"}
# Kurze Antwort, mit der Betreiber statt eines Erlebnisses ein anderes Thema will (z.B. «Bitte ein Ersatzthema nehmen»)
ERSATZ_MUSTER = re.compile(r"ersatz|anderes thema|überspring|ueberspring|reserve|weglassen", re.IGNORECASE)
ERSATZ_MAX_WOERTER = 8
START_SCHLUSS_VERMERK = "START fehlt am Schluss"   # Etappe 9: letzte Szene/Slide ohne Einladung, nur die Caption hat sie
START_VERMERK = "START-Satz in der Caption ergänzt"   # Etappe 9: Text kam ohne Einladung, der Bau ergänzte sie


def will_ersatz(antwort: str) -> bool:
    return len(antwort.split()) <= ERSATZ_MAX_WOERTER and bool(ERSATZ_MUSTER.search(antwort))


class SchrittFehler(Exception):
    """Der ganze Schritt scheitert: Exit 1, eine Zeile im Log und per Telegram."""


class SperreBelegt(Exception):
    pass


# Ein Thema scheitert, die anderen laufen weiter
THEMA_FEHLER = BAU_FEHLER + (ClaudeFehler, texter.TexterFehler)
# Ein ganzer Schritt scheitert mit sauberer Meldung (alles andere sind Programmierfehler mit Traceback)
SCHRITT_FEHLER = BAU_FEHLER + (SchrittFehler, PlanFehler, KalenderFehler, planer.PlanerFehler, ClaudeFehler,
                               BotFehler, konkurrenz.KonkurrenzFehler, guthaben.GuthabenFehler,
                               texter.TexterFehler, notiz.NotizFehler, BriefkastenFehler)


@dataclass
class Dienste:
    """Alles, was nach aussen geht. Tests geben Attrappen mit."""
    claude: Callable          # (agent, auftrag, ausgabe, werkzeuge=…, ordner=…, zeitlimit=…) -> Path
    werkzeug: Callable        # Agentur-Werkzeug: (name, argumente, zeitlimit) -> CompletedProcess
    notiz: Callable           # AppleScript ausführen: (skript) -> Text
    bot: Bot
    elevenlabs_rest: Callable  # () -> verbleibende Zeichen
    stimme: Callable          # ElevenLabs-Anfrage für baue_reel: (text) -> dict
    jetzt: Callable = datetime.now
    uhr: Callable = time.monotonic
    briefkasten: object = None   # lib.briefkasten.Briefkasten nach der Umstellung, sonst None
    mediathek: object = None     # lib.mediathek.Mediathek, nur mit Briefkasten (Etappe 5)
    lernen: Callable | None = None   # lib.lernen.lauf (Etappe 6); ohne: keine Lern-Schleife in den Jobs

    @classmethod
    def echt(cls, pfade: Pfade, log: Path) -> "Dienste":
        briefkasten = Briefkasten.lade(pfade.daten)
        return cls(claude=ClaudeLauf(cwd=pfade.agentur, log=log), werkzeug=agentur_werkzeug(pfade),
                   notiz=notiz.osascript, bot=Bot(pfade.daten / "bot.json", briefkasten=briefkasten),
                   elevenlabs_rest=guthaben.elevenlabs_rest, stimme=elevenlabs_anfrage, briefkasten=briefkasten,
                   mediathek=Mediathek() if briefkasten else None, lernen=lernen.lauf)


class Protokoll:
    """Schreibt jede Zeile mit Zeitstempel ins Log des Schritts und auf die Konsole."""

    def __init__(self, pfad: Path | None, ausgabe: Callable[[str], None] = print):
        self.pfad, self.ausgabe = pfad, ausgabe

    def __call__(self, text: str) -> None:
        self.ausgabe(text)
        if self.pfad:
            self.pfad.parent.mkdir(parents=True, exist_ok=True)
            with self.pfad.open("a", encoding="utf-8") as f:
                f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {text}\n")


def _pid(pfad: Path) -> int | None:
    try:
        return int(pfad.read_text().strip())
    except (OSError, ValueError):
        return None


def _lebt(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class Sperre:
    """Keine zwei Läufe gleichzeitig: Sperrdatei pro Woche mit der Prozess-ID. Verwaiste Sperren werden übernommen."""

    def __init__(self, pfad: Path):
        self.pfad = pfad

    def __enter__(self) -> "Sperre":
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.pfad, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                pid = _pid(self.pfad)
                if _lebt(pid):
                    raise SperreBelegt(f"Läuft bereits (PID {pid}), nichts gemacht") from None
                self.pfad.unlink(missing_ok=True)
                continue
            with os.fdopen(fd, "w") as f:
                f.write(str(os.getpid()))
            return self
        raise SperreBelegt("Sperre nicht zu bekommen, nichts gemacht")

    def __exit__(self, *fehler) -> bool:
        self.pfad.unlink(missing_ok=True)
        return False


def _konkurrenz(plan: Wochenplan, woche: str, pfade: Pfade, dienste: Dienste, log) -> list[dict]:
    """Konkurrenz-Liste (falls fällig erneuern), Apify-Lauf, Ausreisser. Probleme werden Vermerke."""
    heute = dienste.jetzt().date()
    liste_pfad = pfade.daten / "konkurrenz.json"
    apify_pfad = pfade.woche(woche) / "apify.json"
    try:
        liste = konkurrenz.lade_liste(liste_pfad)
        if not apify_pfad.exists() and konkurrenz.braucht_erneuerung(liste, heute):
            log("Konkurrenz-Liste erneuern (Trend-Agent)")
            try:
                liste = konkurrenz.erneuere(liste, pfade, dienste.claude, heute)
                konkurrenz.speichere_liste(liste_pfad, liste)
            except (ClaudeFehler, konkurrenz.KonkurrenzFehler) as e:
                plan.vermerke(f"Konkurrenz-Liste nicht erneuert: {einzeilig(e)}")
        if not liste or not liste["accounts"]:
            plan.vermerke("Kein Apify-Lauf: keine Konkurrenz-Liste")
            return []
        if not apify_pfad.exists():
            rest = guthaben.apify_rest(dienste.werkzeug)
            if rest < konkurrenz.MIN_GUTHABEN:
                plan.vermerke(f"Kein Apify-Lauf: Monatsguthaben {rest:.2f} $ unter 2 $")
                return []
            log(f"Apify-Lauf (Monatsguthaben {rest:.2f} $, höchstens {konkurrenz.MAX_KOSTEN} $)")
        ergebnis = konkurrenz.apify_lauf(liste, apify_pfad, dienste.werkzeug)
        konkurrenz.speichere_liste(liste_pfad, konkurrenz.zaehle_leere_wochen(liste, ergebnis, woche))
        return konkurrenz.ausreisser(ergebnis)
    except (konkurrenz.KonkurrenzFehler, guthaben.GuthabenFehler) as e:
        plan.vermerke(f"Kein Apify-Lauf: {einzeilig(e)}")
        return []


def antwort_frist(jetzt: datetime) -> datetime:
    """Bis Samstag 22:00 (dann startet der Bau) gelten Textnachrichten als Antworten auf die Fragen.
    Samstag nach 22:00 liefert denselben Samstag 22:00 (Frist schon vorbei, gewollt: keine neue Woche)."""
    samstag = jetzt.date() + timedelta(days=(5 - jetzt.weekday()) % 7)
    return datetime(samstag.year, samstag.month, samstag.day, 22, 0)


def _sende_fragen(plan: Wochenplan, dienste: Dienste, log) -> None:
    """Eine Nachricht pro Frage, die noch nicht gesendet ist. Telegram nicht erreichbar → Schritt scheitert."""
    alle = [t for t in plan.themen if t.get("frage")]
    for index, t in enumerate(alle, 1):
        if t["status"] != "geplant":
            continue
        text = (f"Frage {index}/{len(alle)} ({FORMAT_NAME[t['format']]} {kurz(t['termin'])}): {t['frage']}\n\n"
                "Tipp bei dieser Nachricht auf «Antworten» und schreib deine Antwort bis Samstag 22:00. "
                "Ohne Antwort oder mit «Ersatz» nehme ich ein anderes Thema.")
        try:
            t["frage_nachricht"] = dienste.bot.sende_text(text)
        except BotFehler as e:
            raise SchrittFehler(f"Frage {index} nicht gesendet: {einzeilig(e)}") from None
        plan.setze(t, "frage_gesendet")
        log(f"Frage {index} gesendet")
    if dienste.briefkasten is not None and any(t["status"] == "frage_gesendet" for t in alle):
        try:
            dienste.briefkasten.fragen_offen(antwort_frist(dienste.jetzt()))
        except BriefkastenFehler as e:
            plan.vermerke(f"Briefkasten: Fragen nicht gemeldet ({einzeilig(e)})")


def vorbereiten(woche: str, pfade: Pfade, dienste: Dienste, log, fragen: bool = True) -> Wochenplan:
    """Freitag: Konkurrenz, Apple-Notiz, Planer (4 Themen + 2 Reserve), Fragen an den Betreiber. Wiederholbar.
    fragen=False: Nachhol-Lauf am Samstag, nur Themen ohne Erlebnis."""
    plan = Wochenplan.lade(pfade.plan(woche), woche)
    if not plan.vorbereitet:
        plan.daten["ausreisser"] = _konkurrenz(plan, woche, pfade, dienste, log)
        plan.speichere()
        try:
            ideen = notiz.offene_ideen(pfade.daten / "verwendet.json", dienste.notiz)
        except notiz.NotizFehler as e:
            ideen = []
            plan.vermerke(f"Apple-Notiz nicht gelesen: {einzeilig(e)}")
        log(f"{len(ideen)} offene Notiz-Ideen, {len(plan.daten['ausreisser'])} Ausreisser")
        themen, reserve = planer.plane(pfade, woche, ideen, plan.daten["ausreisser"], dienste.claude,
                                       fragen_erlaubt=fragen)
        plan.daten["themen"], plan.daten["reserve"] = themen, reserve
        plan.schritt_fertig("vorbereitet", dienste.jetzt())
        log("Themen geplant: " + ", ".join(f"{t['nr']} {t['slug']}" for t in themen))
    if fragen:
        _sende_fragen(plan, dienste, log)
    return plan


def _test_text(t: dict) -> str:
    runde = next((r for r in reversed(t["test"]) if r["datei"] == t["beitrag"]), None)
    if runde is None:
        return "ohne Test"
    return (f"Test {runde['urteil']} (Wegwisch {round(runde['wegwisch'] * 100)} %, "
            f"Teilen {round(runde['teilen'] * 100)} %)")


def uebersicht(plan: Wochenplan) -> str:
    """Erste Nachricht des Wochenpakets: Termine mit Thema, Quelle, Test und Vermerken."""
    d = plan.daten
    tl = kalender.termine(d["woche"])
    z = [f"Wochenpaket {d['woche']} ({kurz(tl[0]['termin'])} bis {kurz(tl[-1]['termin'])}), nichts ist gepostet.",
         ""]
    for t in plan.aktive():
        quelle = QUELLE_NAME.get(t["quelle"]["art"], t["quelle"]["art"])
        if t.get("vorlage"):
            quelle += f" @{t['vorlage']['account']}"
        fehlgeschlagen = " · FEHLGESCHLAGEN" if t["status"] == "fehlgeschlagen" else ""
        z.append(f"{kurz(t['termin'])} 19:00 · {FORMAT_NAME[t['format']]} · {t['thema']}")
        z.append(f"   Quelle: {quelle} · {_test_text(t)}{fehlgeschlagen}")
        if t["vermerk"]:
            z.append(f"   Vermerk: {t['vermerk']}")
    for t in plan.themen:
        if t["status"] == "ersetzt":
            z.append(f"Ersetzt: «{t['thema']}» ({t['vermerk']})")
    if d["vermerke"]:
        z += ["", "Vermerke:"] + [f"- {v}" for v in d["vermerke"]]
    return "\n".join(z)


def _freigabe_text(t: dict, b: dict | None, gesendet: bool, umgestellt: bool) -> str:
    """Freigabe-Stand und auffällige Zustände eines Themas für status_text."""
    teile = []
    if b and t["status"] != "ersetzt":
        version, neubauten = b.get("version", 1), b.get("neubauten", 0)
        angaben = ([f"Version {version}"] if version > 1 else []) + \
            ([f"{neubauten} Neubau" + ("ten" if neubauten > 1 else "")] if neubauten else [])
        teile.append(b["status"] + (f" ({', '.join(angaben)})" if angaben else ""))
        if b["status"] == "gepostet" and b.get("permalink"):
            teile.append(b["permalink"])
        if b["status"] == "braucht_eingabe" and t["status"] == "gesendet":
            teile.append("Platzhalter, nur Ändern/Verwerfen")
        if (umgestellt and t["status"] == "gesendet" and b["status"] in ANMELDEN
                and t.get("angemeldet") != version):
            teile.append("nicht angemeldet")
        if (umgestellt and t["status"] == "gesendet" and b["status"] in hochladen.HOCHLADEN
                and t.get("angemeldet") == version and b.get("medien_gemeldet") != version):
            teile.append("Dateien nicht hochgeladen")
    if gesendet and t["status"] in ("bereit", "text_fertig", "getestet"):
        teile.append("hängt (Woche schon gesendet)")
    elif gesendet and t["status"] == "gebaut":
        teile.append("nicht gesendet")
    return "".join(f" · {x}" for x in teile)


def status_text(plan: Wochenplan, beitraege: dict | None = None, umgestellt: bool = False) -> str:
    """Stand der Woche für «fliessband woche status» (ohne Netz). beitraege: Manifest-Einträge nach id
    (zeigt Freigabe-Stand, Version und Neubauten). umgestellt: Briefkasten eingerichtet, dann fällt ein
    gesendeter Entwurf ohne Anmeldung (keine Knöpfe in Telegram) auf."""
    d, s = plan.daten, plan.daten["schritte"]
    beitraege = beitraege or {}
    z = [f"Woche {d['woche']}",
         f"vorbereitet: {s['vorbereitet'] or 'offen'} · gebaut: {s['gebaut'] or 'offen'} · "
         f"gesendet: {s['gesendet'] or 'offen'}"]
    for t in sorted(d["themen"], key=lambda t: (t["nr"], t["status"] != "ersetzt")):
        vermerk = f" ({t['vermerk']})" if t["vermerk"] else ""
        b = beitraege.get(freigabe.beitrag_id(d["woche"], t))
        frei = _freigabe_text(t, b, bool(s["gesendet"]), umgestellt)
        z.append(f"{t['nr']} {kurz(t['termin'])} {t['format']:<9} {t['slug']:<28} {t['status']}{frei}{vermerk}")
    if d["reserve"]:
        z.append("Reserve: " + ", ".join(f"{r['slug']} ({r['format']})" for r in d["reserve"]))
    z += [f"Vermerk: {v}" for v in d["vermerke"]]
    return "\n".join(z)


def sende_beitrag(t: dict, woche: str, pfade: Pfade, dienste: Dienste) -> None:
    """Reel als Video (über 50 MB verkleinert, Original bleibt), Karussell als Album, Caption darunter.
    Liegt ein Reel über der Hinweis-Grenze seiner Länge, folgt ein Hinweis.
    Neue Aussprache-Einträge folgen als eigene Zeile."""
    ordner = Path(t["ordner"])
    if t["format"] == "reel":
        mp4 = ordner / "reel.mp4"
        if mp4.stat().st_size > VERSAND_GRENZE:
            mp4 = verkleinere(mp4, pfade.basis / "zwischenspeicher" / "versand" / f"{woche}-{t['slug']}.mp4")
        dienste.bot.sende_video(mp4)
    else:
        dienste.bot.sende_album(sorted(ordner.glob("slide-*.png")))
    dienste.bot.sende_text((ordner / "caption.txt").read_text(encoding="utf-8").strip())
    hinweis = kalender.laengen_hinweis(t.get("laenge"), t.get("dauer_s")) if t["format"] == "reel" else None
    if hinweis:
        dienste.bot.sende_text(hinweis)
    zeile = aussprache_hinweis(t.get("aussprache_neu")) if t["format"] == "reel" else None
    if zeile:
        dienste.bot.sende_text(zeile)


def termin_erreicht(t: dict, dienste: Dienste) -> bool:
    """Ist der Termin des Themas erreicht? Termine sind lokale Zeit ohne Zone, jetzt evtl. mit Zone."""
    jetzt = dienste.jetzt()
    if jetzt.tzinfo is not None:
        jetzt = jetzt.astimezone().replace(tzinfo=None)
    termin = datetime.fromisoformat(t["termin"])
    if termin.tzinfo is not None:
        termin = termin.astimezone().replace(tzinfo=None)
    return termin <= jetzt


def melde_offene(plan: Wochenplan, woche: str, pfade: Pfade, dienste: Dienste, log,
                 fehler: list[str] | None = None) -> bool:
    """Meldet gesendete, noch nicht angemeldete Beiträge (aktuelle Version) beim Briefkasten an und danach die
    Woche als fertig. Nur Manifest-Status 'entwurf' und 'braucht_eingabe' (mit Merkmal platzhalter: nur Ändern und
    Verwerfen) vor dem Termin bekommen Knöpfe (Entschiedenes nicht nochmals, Termin vorbei nicht), der Rest hält
    'fertig' aber nicht auf. Ohne einen angemeldeten
    Beitrag entfällt 'fertig'. Scheitert der Briefkasten, bleibt der Rest für den nächsten Lauf.
    fehler: sammelt die Gründe gescheiterter Briefkasten-Aufrufe (für die Dauerfehler-Meldung in entscheide).
    True: alles gemeldet."""
    bk = dienste.briefkasten
    if bk is None:
        return True
    pfad = freigabe.manifest_pfad(pfade, woche)
    ohne_knoepfe = set()
    for t in plan.aktive():
        if t["status"] != "gesendet":
            continue
        try:
            e = freigabe.eintrag(pfad, woche, freigabe.beitrag_id(woche, t))
        except ManifestFehler as ex:
            log(f"Thema {t['nr']}: nicht angemeldet ({einzeilig(ex)})")
            continue
        if t.get("angemeldet") == e["version"]:
            continue
        if e["status"] not in ANMELDEN:
            ohne_knoepfe.add(t["nr"])
            continue
        if termin_erreicht(t, dienste):
            # Knöpfe kämen zu spät (der Server setzte ohnehin verpasst), zählt als erledigt
            log(f"Thema {t['nr']}: Termin vorbei, nicht angemeldet")
            ohne_knoepfe.add(t["nr"])
            continue
        try:
            instagram_medien.pruefe(t["format"], Path(t["ordner"]))
        except instagram_medien.InstagramPruefung as ex:
            ohne_knoepfe.add(t["nr"])
            log(f"Thema {t['nr']}: nicht angemeldet ({ex})")
            if e.get("instagram_fehler") != e["version"]:
                try:
                    dienste.bot.sende_text(f"«{freigabe.titel_von(t)}» kann so nicht auf Instagram: {ex}. "
                                           "Er bekommt keine Knöpfe und wird nicht gepostet.")
                    freigabe.aendere(pfad, woche, e["id"], instagram_fehler=e["version"])
                except BotFehler as bx:
                    log(f"Thema {t['nr']}: Hinweis nicht gesendet ({einzeilig(bx)})")
            continue
        try:
            bk.melde(freigabe.anmeldung(woche, t, e))
        except BriefkastenFehler as ex:
            log(f"Thema {t['nr']}: Anmelden gescheitert ({einzeilig(ex)}), nächster Versuch beim nächsten Lauf")
            if fehler is not None:
                fehler.append(einzeilig(ex))
            return False
        t["angemeldet"] = e["version"]
        plan.speichere()
        log(f"Thema {t['nr']} angemeldet (Version {e['version']})")
    alle = all(t["status"] in AUS or t.get("angemeldet") or t["nr"] in ohne_knoepfe for t in plan.aktive())
    if not (plan.daten["schritte"]["gesendet"] and alle):
        return False
    if not plan.daten.get("fertig_gemeldet") and not any(t.get("angemeldet") for t in plan.themen):
        # Kein Beitrag mit Knöpfen: Der Server kennt die Woche nicht (400), es gibt nichts zu melden
        log("Woche ohne angemeldete Beiträge, «fertig» entfällt")
        plan.daten["fertig_gemeldet"] = True
        plan.speichere()
    if not plan.daten.get("fertig_gemeldet"):
        try:
            bk.fertig(woche)
        except BriefkastenFehler as ex:
            log(f"Woche nicht als fertig gemeldet ({einzeilig(ex)})")
            if fehler is not None:
                fehler.append(einzeilig(ex))
            return False
        plan.daten["fertig_gemeldet"] = True
        plan.speichere()
    return True


def senden(woche: str, pfade: Pfade, dienste: Dienste, log, plan: Wochenplan | None = None,
           mit_uebersicht: bool = True) -> int:
    """Übersicht und alle gebauten, noch nicht gesendeten Beiträge nach Telegram (ohne Ton), danach Anmeldung
    beim Briefkasten (Knöpfe). Wiederholbar: schickt nur, was noch nicht 'gesendet' ist. Liefert die Zahl
    gesendeter Beiträge. Karussell ohne Slides: fehlgeschlagen, ohne Caption (steht so in der Übersicht).
    mit_uebersicht=False: Reserve nach «Verwerfen», die Wochenübersicht ging schon raus."""
    plan = plan or Wochenplan.lade(pfade.plan(woche), woche)
    if not plan.vorbereitet:
        raise SchrittFehler(f"{woche} ist nicht vorbereitet, es gibt nichts zu senden")
    for t in plan.aktive():
        if t["status"] == "gebaut" and t["format"] == "karussell" and not any(Path(t["ordner"]).glob("slide-*.png")):
            plan.setze(t, "fehlgeschlagen", haenge_an(t["vermerk"], f"keine Slides (slide-*.png) in {t['ordner']}"))
            log(f"Thema {t['nr']} fehlgeschlagen: keine Slides")
    offen = [t for t in plan.aktive() if t["status"] == "gebaut"]
    schon_gesendet = any(t["status"] == "gesendet" for t in plan.aktive())
    if not offen and (plan.daten["schritte"]["gesendet"] or schon_gesendet):
        # Die Übersicht ging schon mit dem ersten Beitrag raus. Fehlt nur der Schritt (Abbruch vor dem
        # Festhalten), wird er unten nachgeholt, ohne ein zweites Wochenpaket zu schicken.
        log("Nichts mehr zu senden")
    elif mit_uebersicht:
        dienste.bot.sende_text(uebersicht(plan))
    for t in offen:
        sende_beitrag(t, woche, pfade, dienste)
        plan.setze(t, "gesendet")
        log(f"Thema {t['nr']} gesendet")
    if not plan.daten["schritte"]["gesendet"] and all(t["status"] in ("gesendet",) + AUS for t in plan.aktive()):
        plan.schritt_fertig("gesendet", dienste.jetzt())
    melde_offene(plan, woche, pfade, dienste, log)
    hochladen.reiche_nach(plan, woche, pfade, dienste, log)
    return len(offen)


def anmelden(woche: str, pfade: Pfade, dienste: Dienste, log) -> None:
    """Gesendete Beiträge einer Woche beim Briefkasten anmelden (z.B. KW44 nach der Umstellung).
    Läuft über fuehre_aus, also unter der Sperre der Woche."""
    if dienste.briefkasten is None:
        raise SchrittFehler("Briefkasten nicht eingerichtet, zuerst «fliessband briefkasten umstellen»")
    plan = Wochenplan.lade(pfade.plan(woche), woche)
    if not plan.daten["schritte"]["gesendet"]:
        raise SchrittFehler(f"Woche noch nicht gesendet, zuerst «fliessband woche senden --woche {woche}»")
    if not melde_offene(plan, woche, pfade, dienste, log):
        raise SchrittFehler("Nicht alles angemeldet, Details im Log")
    if not hochladen.reiche_nach(plan, woche, pfade, dienste, log):
        raise SchrittFehler("Nicht alle Dateien hochgeladen oder gemeldet, Details im Log")


def sprechzeichen(beitrag: Path) -> int:
    """Zeichen des Sprechtexts eines Reels (so rechnet ElevenLabs ab)."""
    return sum(len(s.sprechtext) for s in lese_reel(beitrag).szenen)


def neue_sprechzeichen(alt: Path, neu: Path) -> int:
    """Zeichen, die ein Neubau bei ElevenLabs kostet: Die Stimme liegt pro Szenen-Nummer im Speicher (stimme/),
    nur Szenen mit anderem Sprechtext unter derselben Nummer werden neu vertont."""
    bisher = {s.nummer: s.sprechtext for s in lese_reel(alt).szenen}
    return sum(len(s.sprechtext) for s in lese_reel(neu).szenen if bisher.get(s.nummer) != s.sprechtext)


def _je_thema(plan: Wochenplan, thema: dict, arbeit: Callable[[], None], log) -> None:
    """Ein Thema, das scheitert, hält die anderen nicht auf. Das Zeitlimit beendet den ganzen Schritt."""
    try:
        arbeit()
    except ZeitAbgelaufen:
        plan.setze(thema, "fehlgeschlagen", "Zeitlimit des Schritts bauen (2 h) erreicht")
        raise
    except THEMA_FEHLER as e:
        plan.setze(thema, "fehlgeschlagen", einzeilig(e))
        log(f"Thema {thema['nr']} fehlgeschlagen: {einzeilig(e)}")


def _lies_antworten(plan: Wochenplan, dienste: Dienste, log) -> None:
    """Antworten aus Telegram den Fragen zuordnen. Ohne Antwort: Reserve-Thema. Danach alles 'bereit'."""
    alle = [t for t in plan.themen if t.get("frage")]
    gefragt = [t for t in alle if t["status"] == "frage_gesendet"]
    if gefragt:
        try:
            try:
                nachrichten, hoechste = dienste.bot.neue_nachrichten()
            except BriefkastenFehler as e:
                # Server weg: mit dem weitermachen, was schon im lokalen Eingang liegt (Bau geht trotzdem raus)
                vermerk = f"Briefkasten nicht erreichbar, Antworten evtl. unvollständig ({einzeilig(e)})"
                plan.vermerke(vermerk)
                log(vermerk)
                nachrichten, hoechste = dienste.bot.neue_nachrichten(sammeln=False)
        except BotFehler as e:
            raise SchrittFehler(f"Antworten nicht lesbar: {einzeilig(e)}") from None
        fragen = [{"nr": t["nr"], "index": alle.index(t) + 1, "nachricht": t["frage_nachricht"]} for t in gefragt]
        antworten, nicht = ordne_zu(nachrichten, fragen)
        for t in gefragt:
            if t["nr"] in antworten:
                t["antwort"] = "\n\n".join(antworten[t["nr"]])
        if nicht:
            plan.vermerke(f"{nicht} Telegram-Nachricht(en) keiner Frage zugeordnet")
        plan.speichere()
        dienste.bot.bestaetige(hoechste)
        log(f"Antworten: {len(antworten)} von {len(gefragt)} Fragen")
    for t in plan.aktive():
        if t["status"] not in ("geplant", "frage_gesendet"):
            continue
        if not t.get("frage") or (t.get("antwort") and not will_ersatz(t["antwort"])):
            plan.setze(t, "bereit")
            continue
        # 'geplant' mit Frage: Die Frage ging nie raus (z.B. Telegram am Freitag nicht erreichbar)
        if t.get("antwort"):
            grund = "Der Betreiber wünscht ein Ersatzthema"
        elif t["status"] == "frage_gesendet":
            grund = "keine Antwort auf die Frage"
        else:
            grund = "Frage wurde nie gesendet"
        if plan.ersetze(t, grund) is None:
            plan.setze(t, "fehlgeschlagen", f"{grund}, keine Reserve mehr")
        else:
            log(f"Thema {t['nr']} durch Reserve ersetzt ({grund})")


def _merke_geschichten(plan: Wochenplan, pfade: Pfade, dienste: Dienste, log) -> None:
    """Etappe 9: Betreiber-Antworten (keine Ersatz-Wünsche) je einmal in den Geschichten-Speicher.
    Ein Schreibfehler kostet nur den Eintrag (Vermerk), der Bau geht weiter."""
    for t in plan.themen:
        if not t.get("frage") or not t.get("antwort") or t.get("geschichte_gemerkt") or will_ersatz(t["antwort"]):
            continue
        try:
            geschichten.merke(pfade.geschichten, dienste.jetzt().date(), t["frage"], t["antwort"])
        except (OSError, ValueError) as e:
            plan.vermerke(f"Geschichte nicht gespeichert: {einzeilig(e)}")
            continue
        t["geschichte_gemerkt"] = True
        plan.speichere()   # sofort: nach einem Abbruch wird nichts doppelt angehängt
        log(f"Thema {t['nr']}: Antwort in geschichten.md gemerkt")


def _texte(plan: Wochenplan, pfade: Pfade, lauf, dienste: Dienste, frist: Frist, log) -> None:
    """Content-Agent und Follower-Test für alle Themen, die noch keinen geprüften Text haben."""
    for t in plan.aktive():
        if t["status"] not in ("bereit", "text_fertig"):
            continue
        frist.pruefe()

        def arbeit(t=t):
            if t["status"] == "bereit":
                log(f"Thema {t['nr']}: Content-Agent schreibt {t['slug']}")
                t["beitrag"] = str(texter.schreibe(t, pfade, lauf))
                t["test"] = []
                plan.setze(t, "text_fertig")
            log(f"Thema {t['nr']}: Follower-Test")
            texter.follower_schleife(t, pfade, lauf, dienste.werkzeug, plan.speichere)
            plan.setze(t, "getestet")
        _je_thema(plan, t, arbeit, log)


def _pruefe_stimme(plan: Wochenplan, dienste: Dienste, log) -> bool:
    """Vor dem ersten Reel: Reicht das ElevenLabs-Guthaben für alle Reels + 500 Zeichen? Sonst wird jedes Reel
    durch die Karussell-Reserve ersetzt bzw. als Karussell neu geschrieben. Reels mit Betreiber-Antwort werden immer
    neu geschrieben (die Antwort bleibt), die Reserve geht an Reels ohne Antwort. True, wenn etwas umgestellt wurde.
    Ein Reel, dessen Text nicht lesbar ist, scheitert allein."""
    reels = [t for t in plan.aktive() if t["format"] == "reel" and t["status"] == "getestet"]
    if not reels:
        return False
    try:
        rest = dienste.elevenlabs_rest()
    except guthaben.GuthabenFehler as e:
        plan.vermerke(f"ElevenLabs-Guthaben nicht abfragbar ({einzeilig(e)}), Reels trotzdem gebaut")
        return False
    zeichen = {}
    for t in reels:
        def arbeit(t=t):
            zeichen[t["nr"]] = sprechzeichen(Path(t["beitrag"]))
        _je_thema(plan, t, arbeit, log)
    reels = [t for t in reels if t["nr"] in zeichen]
    noetig = sum(zeichen.values()) + STIMME_RESERVE
    if not reels or rest >= noetig:
        return False
    grund = f"ElevenLabs-Guthaben zu klein ({rest} von {noetig} Zeichen)"
    plan.vermerke(grund)
    for t in sorted(reels, key=lambda t: not t.get("antwort")):
        if t.get("antwort") or plan.ersetze(t, grund, format="karussell", andere_erlaubt=False) is None:
            plan.schreibe_um(t, "karussell", grund)
        log(f"Thema {t['nr']}: Karussell statt Reel ({grund})")
    return True


def _bau_vermerk(t: dict, eintrag: dict) -> None:
    """Offene Platzhalter und vom Leser ersetzte Bilder kommen in den Vermerk (Wochenübersicht)."""
    p = eintrag["pruefungen"]
    if p["platzhalter"]:
        t["vermerk"] = haenge_an(t["vermerk"], "offen: " + ", ".join(p["platzhalter"]))
    if p.get("bild_hinweise"):
        t["vermerk"] = haenge_an(t["vermerk"], "Bild ersetzt: " + "; ".join(p["bild_hinweise"]))
    if p.get("start_ergaenzt"):
        t["vermerk"] = haenge_an(t["vermerk"], START_VERMERK)
    if p.get("start_schluss_fehlt"):
        t["vermerk"] = haenge_an(t["vermerk"], START_SCHLUSS_VERMERK)


def _baue(plan: Wochenplan, pfade: Pfade, dienste: Dienste, frist: Frist, log) -> None:
    """Baut jedes getestete Thema mit dem Bauer aus Etappe 1 bzw. 2 und seinem Termin."""
    for t in plan.aktive():
        if t["status"] != "getestet":
            continue
        frist.pruefe()

        def arbeit(t=t):
            log(f"Thema {t['nr']}: {FORMAT_NAME[t['format']]} bauen")
            termin = datetime.fromisoformat(t["termin"])
            if t["format"] == "reel":
                pruefer = aussprache_pruefer(mit_frist(dienste.claude, frist),
                                             pfade.basis / "zwischenspeicher" / "aussprache")
                ziel, eintrag = baue_reel(Path(t["beitrag"]), termin=termin, basis=pfade.basis, anfrage=dienste.stimme,
                                          laenge=t.get("laenge"), aussprache_pruefer=pruefer)
                t["dauer_s"] = eintrag.get("dauer_s")
                t["aussprache_neu"] = eintrag["pruefungen"].get("aussprache_neu", [])
            else:
                ziel, eintrag = baue_karussell(Path(t["beitrag"]), termin=termin, basis=pfade.basis)
            t["ordner"] = str(ziel)
            _bau_vermerk(t, eintrag)
            plan.setze(t, "gebaut")
            if t["quelle"]["art"] == "notiz":
                try:
                    notiz.merke_verwendet(pfade.daten / "verwendet.json", t["quelle"]["detail"])
                except notiz.NotizFehler as e:
                    plan.vermerke(f"Notiz-Idee nicht als verwendet gemerkt: {einzeilig(e)}")
        _je_thema(plan, t, arbeit, log)


def baue_offene(plan: Wochenplan, pfade: Pfade, dienste: Dienste, log) -> bool:
    """Texte und Follower-Tests, Guthaben-Prüfung und Bau für alle Themen, die noch nicht gebaut sind
    (Samstag und Reserve nach «Verwerfen»). True: Zeitlimit von 2 h erreicht, der Rest folgt später."""
    frist = Frist(ZEIT_BAUEN, dienste.uhr)
    lauf = mit_frist(dienste.claude, frist)
    try:
        _texte(plan, pfade, lauf, dienste, frist, log)
        if _pruefe_stimme(plan, dienste, log):
            _texte(plan, pfade, lauf, dienste, frist, log)
        _baue(plan, pfade, dienste, frist, log)
    except ZeitAbgelaufen:
        plan.vermerke("Zeitlimit bauen (2 h) erreicht, der Rest folgt beim nächsten Lauf")
        log("Zeitlimit erreicht")
        return True
    return False


def bauen(woche: str, pfade: Pfade, dienste: Dienste, log) -> Wochenplan:
    """Samstag: Antworten, Texte und Tests, Guthaben-Prüfung, Bauen, Senden. Wiederholbar.
    Gesamtzeit 2 h: danach ist das laufende Thema fehlgeschlagen, der Rest folgt beim nächsten Lauf."""
    plan = Wochenplan.lade(pfade.plan(woche), woche)
    if not plan.vorbereitet:
        raise SchrittFehler(f"{woche} ist nicht vorbereitet, zuerst «fliessband woche vorbereiten»")
    _lies_antworten(plan, dienste, log)
    _merke_geschichten(plan, pfade, dienste, log)
    zeit_um = baue_offene(plan, pfade, dienste, log)
    if not plan.daten["schritte"]["gebaut"] and all(t["status"] in FERTIG + AUS for t in plan.aktive()):
        plan.schritt_fertig("gebaut", dienste.jetzt())
    try:
        senden(woche, pfade, dienste, log, plan=plan)
    except BotFehler as e:
        raise SchrittFehler(f"Senden gescheitert ({einzeilig(e)}), mit «fliessband woche senden» wiederholen") from None
    if zeit_um:
        raise SchrittFehler("Zeitlimit von 2 h erreicht, den Rest mit «fliessband woche bauen» nachholen")
    return plan


def _ausfall_grund(plan: Wochenplan) -> str:
    gescheitert = [v for v in plan.daten["vermerke"] if "gescheitert" in v]
    if gescheitert:
        return gescheitert[-1]
    if not plan.vorbereitet:
        return "kein Lauf bis So 12:00 (Mac aus oder im Ruhezustand?)"
    return "bis So 12:00 nicht fertig gebaut"


def _lerne_nach(woche: str, pfade: Pfade, dienste: Dienste, log) -> None:
    """Vor der Themenplanung: Lern-Schleife nachholen, wenn sie diese Woche noch fehlt (Mac schlief um 20:00)."""
    if dienste.lernen is not None and lernen.faellig(pfade, woche):
        log("Lern-Schleife fehlt diese Woche: zuerst nachholen")
        dienste.lernen(pfade, dienste, woche, log)


def job(schritt: str, woche: str, pfade: Pfade, dienste: Dienste, log) -> None:
    """Für launchd: lernen Fr 20:00 bis 21:30, einmal pro Woche; vorbereiten holt es nach, wenn es fehlt.
    Vorbereiten Fr 22:00 bis So 12:00, bauen Sa 22:00 bis So 12:00 (holt vorbereiten ohne
    Fragen nach). So 12:00 bis 23:59: einmal «Paket KW xx ausgefallen», wenn nichts gebaut ist.
    Läuft vorbereiten erst im Fenster von bauen (beide Jobs nachgeholt, nur einer bekommt die Sperre),
    macht es gleich alles, was bauen macht."""
    jetzt = dienste.jetzt()
    lage = kalender.fenster(schritt, jetzt)
    if schritt == "lernen":
        if lage == "laufen" and dienste.lernen is not None and lernen.faellig(pfade, woche):
            dienste.lernen(pfade, dienste, woche, log)
        else:
            log("lernen: nichts zu tun (vorbereiten holt es nach)")
        return
    if lage == "ruhe":
        log(f"{schritt}: ausserhalb des Zeitfensters, nichts zu tun")
        return
    plan = Wochenplan.lade(pfade.plan(woche), woche)
    if lage == "ausgefallen":
        if any(t["status"] in FERTIG for t in plan.themen) or plan.daten.get("ausfall_gemeldet"):
            log(f"{schritt}: Zeitfenster vorbei, nichts zu melden")
            return
        try:
            dienste.bot.sende_text(f"Paket {woche[-4:]} ausgefallen: {_ausfall_grund(plan)}")
        except BotFehler as e:
            log(f"Ausfall nicht gemeldet: {einzeilig(e)}")
            return
        plan.daten["ausfall_gemeldet"] = True
        plan.speichere()
        return
    if schritt == "vorbereiten" and kalender.fenster("bauen", jetzt) != "laufen":
        if not plan.vorbereitet:
            _lerne_nach(woche, pfade, dienste, log)
        vorbereiten(woche, pfade, dienste, log)
        return
    if not plan.vorbereitet:
        log("Noch nicht vorbereitet: vorbereiten ohne Fragen")
        _lerne_nach(woche, pfade, dienste, log)
        vorbereiten(woche, pfade, dienste, log, fragen=False)
    bauen(woche, pfade, dienste, log)


def _melde_fehler(schritt: str, woche: str, grund: str, pfade: Pfade, dienste: Dienste) -> None:
    try:
        Wochenplan.lade(pfade.plan(woche), woche).vermerke(f"{schritt} gescheitert: {grund}")
    except (PlanFehler, OSError):
        pass
    try:
        dienste.bot.sende_text(f"Fliessband {woche}: {schritt} gescheitert. {grund}")
    except BotFehler:
        pass


def fuehre_aus(befehl: str, woche: str, pfade: Pfade, dienste: Dienste, log) -> int:
    """Führt vorbereiten, bauen, senden, anmelden, lernen, lernen-probe, job-lernen, job-vorbereiten oder
    job-bauen mit Sperre aus. Liefert den Exit-Code.
    Bekannte Fehler: Exit 1, eine Zeile im Log, Vermerk im Plan und per Telegram (falls erreichbar)."""
    try:
        with Sperre(pfade.daten / f"sperre-{woche}"):
            if befehl == "vorbereiten":
                vorbereiten(woche, pfade, dienste, log)
            elif befehl == "bauen":
                bauen(woche, pfade, dienste, log)
            elif befehl == "senden":
                senden(woche, pfade, dienste, log)
            elif befehl == "anmelden":
                anmelden(woche, pfade, dienste, log)
            elif befehl in ("lernen", "lernen-probe"):
                ergebnis = lernen.lauf(pfade, dienste, woche, log, probe=befehl == "lernen-probe")
                if befehl == "lernen" and ergebnis != "ok":
                    return 1
            elif befehl in ("job-lernen", "job-vorbereiten", "job-bauen"):
                job(befehl.removeprefix("job-"), woche, pfade, dienste, log)
            else:
                raise ValueError(f"unbekannter Schritt {befehl}")
    except SperreBelegt as e:
        log(str(e))
        return 0
    except SCHRITT_FEHLER as e:
        grund = einzeilig(e)
        log(f"Fehler: {grund}")
        _melde_fehler(befehl.removeprefix("job-"), woche, grund, pfade, dienste)
        return 1
    return 0
