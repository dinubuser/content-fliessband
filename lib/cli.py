"""Kommandozeile:
  fliessband karussell <beitrag.md> [--termin YYYY-MM-DDTHH:MM]
  fliessband reel <reel.md> [--termin YYYY-MM-DDTHH:MM]
  fliessband woche vorbereiten|bauen|senden|status [--woche 2026-KW44]
  fliessband woche job lernen|vorbereiten|bauen  (für launchd, mit Zeitfenster)
  fliessband woche anmelden [--woche 2026-KW44]
  fliessband lernen [--probe]                 (Lern-Schleife: Instagram-Zahlen → learnings.md)
  fliessband entscheide                     (für launchd alle 15 Minuten)
  fliessband briefkasten umstellen [--adresse http://your-server-ip:8096]
  fliessband einrichten [--online]          (Einrichtung prüfen: neun Schritte, liest nur, Anleitung docs/anleitung/)
  fliessband bot einrichten                 (nur vor der Umstellung)
  fliessband poster ein|aus|status          (automatisches Posten auf Instagram, Server)
  fliessband facebook ein|aus|status        (nach Instagram auch auf die Facebook-Seite, Server)
  fliessband kommentare ein|aus|status      (START-Kommentare auf Instagram in Telegram melden, Server)
  fliessband fakten ein|aus|status          (Faktencheck vor dem Bauen, läuft lokal)
  fliessband trends ein|aus|status          (Trend-Scout: Web-Themen für den Planer am Freitag, Standard aus)
  fliessband trends jetzt [--woche 2026-KW46]  (Scout von Hand starten, Themen ansehen; Freitag nutzt dieselbe Datei)
  fliessband plaetze 4|6|status             (Beiträge pro Woche: 4 Standard, 6 mit Mo Karussell und Fr Reel)"""
import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

from lib import manifest
from lib.aussprache import hinweis as aussprache_hinweis, pruefer as aussprache_pruefer
from lib.bauer import STANDARD_BASIS, baue_karussell
from lib.bot import Bot, BotFehler
from lib.konfig import wert
from lib.briefkasten import DATEI as BRIEFKASTEN_DATEI
from lib.briefkasten import Briefkasten, BriefkastenFehler, umstellen
from lib.claude_lauf import ClaudeLauf, ZeitAbgelaufen
from lib.entscheide import EntscheidFehler, entscheide, wochen
from lib import einrichten, fakten, planer, trendscout
from lib.fehler import BAU_FEHLER, einzeilig
from lib.freigabe import manifest_pfad
from lib import kalender
from lib.kalender import FORMAT_NAME, KalenderFehler, kurz, pruefe_woche, zielwoche
from lib.leser import LeserFehler  # noqa: F401 (Tests greifen auf cli.LeserFehler zu)
from lib.reel_bauer import baue_reel
from lib.umgebung import Pfade
from lib.woche import SCHRITT_FEHLER, Dienste, Protokoll, SperreBelegt, fuehre_aus, status_text
from lib.wochenplan import PlanFehler, Wochenplan

# Bekannte Fehler: eine saubere Zeile. Alles andere (echte Programmierfehler) behält seinen Traceback.
BEKANNTE_FEHLER = BAU_FEHLER
# «fliessband entscheide»: dazu Fehler aus entscheide/nachholen (unvollständige Ereignisse überspringt entscheide)
ENTSCHEID_FEHLER = SCHRITT_FEHLER + (EntscheidFehler, BriefkastenFehler, SperreBelegt, ZeitAbgelaufen)

STANDARD_ADRESSE = wert("FLIESSBAND_BRIEFKASTEN_URL", "http://your-server-ip:8096")   # Briefkasten auf dem Server (Tailscale)

# Uhr der Dienste (Dienste.jetzt). Tests ersetzen sie.
uhr: Callable[[], datetime] = datetime.now


def _termin(wert: str) -> datetime:
    try:
        return datetime.strptime(wert, "%Y-%m-%dT%H:%M")
    except ValueError:
        raise argparse.ArgumentTypeError("Format YYYY-MM-DDTHH:MM, z.B. 2026-10-23T19:00") from None


def _woche_arg(wert: str) -> str:
    try:
        return pruefe_woche(wert)
    except KalenderFehler as e:
        raise argparse.ArgumentTypeError(str(e)) from None


def _melde(ziel: Path, eintrag: dict) -> None:
    print(f"Fertig: {ziel}")
    print(f"Status: {eintrag['status']}")
    p = eintrag["pruefungen"]
    for stelle in p["platzhalter"]:
        print(f"  offen: {stelle}")
    for wo in p["risikohinweis_ergaenzt"]:
        print(f"  Risikohinweis ergänzt: {wo}")
    if p["schreibweise_korrekturen"] > 0:
        print(f"  Schreibweise korrigiert: {p['schreibweise_korrekturen']}")
    if "laenge" in p:
        zusatz = " (lang, über 60 s)" if p["laenge"] == "lang" else ""
        print(f"  Länge: {eintrag['dauer_s']} s{zusatz}")
    zeile = aussprache_hinweis(p.get("aussprache_neu"))
    if zeile:
        print(f"  {zeile}")


def _baue(a) -> int:
    # Name im Modul nachschlagen, damit Tests baue_reel/baue_karussell ersetzen können
    bauen = baue_karussell if a.befehl == "karussell" else baue_reel
    pfade = Pfade(basis=a.basis)
    mehr = {}
    if a.befehl == "reel":
        lauf = ClaudeLauf(cwd=pfade.agentur, log=pfade.basis / "logs" / "aussprache.log")
        mehr["aussprache_pruefer"] = aussprache_pruefer(lauf, pfade.basis / "zwischenspeicher" / "aussprache")
    try:
        # Faktencheck arbeitet direkt an der Quelldatei, die der Bauer danach liest
        fakten_lauf = fakten.schreibgeschuetzt(
            ClaudeLauf(cwd=pfade.agentur, log=pfade.basis / "logs" / "fakten.log"), pfade.agentur)
        ergebnis = fakten.pruefe_beitrag(Path(a.quelle).expanduser().resolve(), a.befehl, fakten_lauf, pfade.basis)
        ziel, eintrag = bauen(a.quelle, termin=a.termin, basis=a.basis, **mehr)
    except BEKANNTE_FEHLER as e:
        print(f"Fehler: {einzeilig(e)}", file=sys.stderr)
        return 1
    _melde(ziel, eintrag)
    zeile = fakten.hinweis(ergebnis)
    if zeile:
        print(f"  {zeile}")
    return 0


def _zuerst(wert: datetime, danach: Callable[[], datetime]) -> Callable[[], datetime]:
    """Uhr, die beim ersten Blick `wert` liefert und danach normal weiterläuft."""
    erster = [True]

    def jetzt() -> datetime:
        if erster[0]:
            erster[0] = False
            return wert
        return danach()
    return jetzt


def _woche(a) -> int:
    pfade = Pfade(basis=a.basis)
    jetzt = uhr()
    if a.aktion == "job":
        woche, schritt, befehl = zielwoche(jetzt.date()), a.schritt, f"job-{a.schritt}"
    else:
        woche = a.woche or zielwoche(jetzt.date())
        schritt = befehl = a.aktion
    if befehl == "status":
        try:
            plan = Wochenplan.lade(pfade.plan(woche), woche)
            beitraege = {b["id"]: b for b in manifest.lade(manifest_pfad(pfade, woche), woche)["beitraege"]}
            umgestellt = (pfade.daten / BRIEFKASTEN_DATEI).exists()
            print(status_text(plan, beitraege, umgestellt=umgestellt))
        except (PlanFehler, manifest.ManifestFehler, OSError, KeyError) as e:
            print(f"Fehler: {einzeilig(e)}", file=sys.stderr)
            return 1
        return 0
    log = Protokoll(pfade.log(woche, schritt))
    dienste = Dienste.echt(pfade, log.pfad)
    # job prüft sein Zeitfenster mit dem ersten dienste.jetzt(): genau der Zeitpunkt, aus dem die Woche stammt.
    # Die anderen Schritte fragen die Uhr erst später (z.B. schritt_fertig am Ende) und brauchen die echte Zeit.
    dienste.jetzt = _zuerst(jetzt, uhr) if a.aktion == "job" else uhr
    return fuehre_aus(befehl, woche, pfade, dienste, log)


def _lernen(a) -> int:
    pfade = Pfade(basis=a.basis)
    woche = zielwoche(uhr().date())
    log = Protokoll(pfade.log(woche, "lernen"))
    dienste = Dienste.echt(pfade, log.pfad)
    dienste.jetzt = uhr
    return fuehre_aus("lernen-probe" if a.probe else "lernen", woche, pfade, dienste, log)


def _einrichten(a) -> int:
    schritte = einrichten.pruefe(einrichten.Umfeld.echt(a.basis), online=a.online)
    print(einrichten.text(schritte))
    return einrichten.exitcode(schritte)


def _bot(a) -> int:
    daten = Pfade(basis=a.basis).daten
    if (daten / BRIEFKASTEN_DATEI).exists():
        # Nach der Umstellung fragt nur der Server Telegram ab, ein getUpdates vom Mac gäbe 409 Conflict
        print(f"Fehler: Briefkasten schon umgestellt ({daten / BRIEFKASTEN_DATEI} besteht), er fragt Telegram "
              "ab. Einrichten ist nicht mehr nötig.", file=sys.stderr)
        return 1
    try:
        chat = Bot(daten / "bot.json").einrichten()
    except BotFehler as e:
        print(f"Fehler: {einzeilig(e)}", file=sys.stderr)
        return 1
    print(f"Bot eingerichtet (Chat {chat}). Die Bestätigung ist in Telegram.")
    return 0


def _entscheide(a) -> int:
    pfade = Pfade(basis=a.basis)
    log = Protokoll(pfade.basis / "logs" / "entscheide.log")
    dienste = Dienste.echt(pfade, log.pfad)
    dienste.jetzt = uhr
    if dienste.briefkasten is None:
        # Vor der Umstellung läuft der launchd-Job schon, soll aber kein Fehler-Rauschen erzeugen
        log("Briefkasten nicht eingerichtet, nichts zu tun")
        return 0
    try:
        n = entscheide(pfade, dienste, log)
    except ENTSCHEID_FEHLER as e:
        log(f"Fehler: {einzeilig(e)}")
        return 1
    if n:
        log(f"{n} Entscheid(e) umgesetzt")
    return 0


def _briefkasten(a) -> int:
    pfade = Pfade(basis=a.basis)
    try:
        update_id = umstellen(pfade.daten, a.adresse, Bot(pfade.daten / "bot.json"))
    except (BriefkastenFehler, BotFehler) as e:
        print(f"Fehler: {einzeilig(e)}", file=sys.stderr)
        return 1
    print(f"Umgestellt: Der Briefkasten fragt Telegram ab Update {update_id + 1} ab, der Mac nicht mehr.")
    for woche in _gesendete_wochen(pfade):
        print(f"Als Nächstes: fliessband woche anmelden --woche {woche}")
    return 0


def _gesendete_wochen(pfade: Pfade) -> list[str]:
    """Laufende und nächste Woche, soweit schon gesendet (deren Beiträge brauchen noch Knöpfe). Ohne solche:
    die Zielwoche, damit der nächste Schritt trotzdem dasteht."""
    heute = uhr().date()
    gesendet = []
    for woche in wochen(heute):
        try:
            if pfade.plan(woche).exists() and Wochenplan.lade(pfade.plan(woche), woche).daten["schritte"]["gesendet"]:
                gesendet.append(woche)
        except (PlanFehler, OSError):
            continue
    return gesendet or [zielwoche(heute)]


def kurz_termin(termin: str) -> str:
    """'2026-10-27T19:00' → 'Di 27.10., 19:00'"""
    return f"{kurz(termin)}, {datetime.fromisoformat(termin):%H:%M}"


def poster_text(stand: dict) -> str:
    tage = stand.get("schluessel_tage")
    z = [f"Poster: {'an' if stand.get('an') else 'aus'}",
         f"Instagram-Schlüssel: {tage} Tage alt" if tage is not None else "Instagram-Schlüssel: fehlt oder ungültig"]
    naechste = stand.get("naechste") or []
    z.append("Nächste Posts:" if naechste else "Keine geplanten Posts.")
    for n in naechste:
        z.append(f"  {kurz_termin(n['termin'])} · {FORMAT_NAME.get(n['format'], n['format'])} «{n['titel']}» · "
                 f"{n['post_status']} · {'Dateien da' if n['dateien'] else 'Dateien fehlen'}")
    return "\n".join(z)


def _poster(a) -> int:
    bk = Briefkasten.lade(Pfade(basis=a.basis).daten)
    if bk is None:
        print("Fehler: Briefkasten nicht eingerichtet (fliessband briefkasten umstellen)", file=sys.stderr)
        return 1
    try:
        stand = bk.poster_stand() if a.aktion == "status" else bk.poster(a.aktion == "ein")
    except BriefkastenFehler as e:
        print(f"Fehler: {einzeilig(e)}", file=sys.stderr)
        return 1
    print(poster_text(stand))
    return 0


def facebook_text(stand: dict) -> str:
    z = [f"Facebook: {'an' if stand.get('an') else 'aus'}",
         "Seiten-Schlüssel: da" if stand.get("schluessel") else "Seiten-Schlüssel: fehlt oder ungültig"]
    posts = stand.get("posts") or []
    z.append("Letzte Facebook-Posts:" if posts else "Noch keine Facebook-Posts.")
    for p in posts:
        zusatz = p.get("fb_link") or (p.get("fb_grund") if p["fb_status"] in ("fehler", "offen") else None)
        z.append(f"  {kurz_termin(p['termin']) if p['termin'] else '?'} · «{p['titel']}» · {p['fb_status']}"
                 + (f" · {zusatz}" if zusatz else ""))
    return "\n".join(z)


def _facebook(a) -> int:
    bk = Briefkasten.lade(Pfade(basis=a.basis).daten)
    if bk is None:
        print("Fehler: Briefkasten nicht eingerichtet (fliessband briefkasten umstellen)", file=sys.stderr)
        return 1
    try:
        stand = bk.facebook_stand() if a.aktion == "status" else bk.facebook(a.aktion == "ein")
    except BriefkastenFehler as e:
        print(f"Fehler: {einzeilig(e)}", file=sys.stderr)
        return 1
    print(facebook_text(stand))
    return 0


def _fakten(a) -> int:
    pfade = Pfade(basis=a.basis)
    if a.aktion in ("ein", "aus"):
        fakten.setze(pfade.basis, a.aktion == "ein")
    print(fakten.schalter_text(pfade.basis))
    return 0


def _trends(a) -> int:
    pfade = Pfade(basis=a.basis)
    if a.aktion in ("ein", "aus"):
        trendscout.setze(pfade.basis, a.aktion == "ein")
    if a.aktion == "jetzt":
        woche = a.woche or zielwoche(uhr().date())
        log = Protokoll(pfade.log(woche, "trends"))
        dienste = Dienste.echt(pfade, log.pfad)
        print(trendscout.handlauf(pfade, woche, fakten.schreibgeschuetzt(dienste.claude, pfade.agentur),
                                  planer.letzte_themen(pfade.basis / "wochen", woche)))
        return 0
    print(trendscout.schalter_text(pfade.basis))
    return 0


def _plaetze(a) -> int:
    pfade = Pfade(basis=a.basis)
    if a.aktion in ("4", "6"):
        kalender.setze_plaetze(pfade.basis, int(a.aktion))
    print(f"Plätze pro Woche: {kalender.plaetze(pfade.basis)}")
    return 0


def kommentare_text(stand: dict) -> str:
    runde = stand.get("letzte_runde")
    z = [f"Kommentare: {'an' if stand.get('an') else 'aus'}",
         f"Gelesen: {stand.get('kommentare', 0)} Kommentare, davon {stand.get('start', 0)} mit START",
         f"Letzte Runde: {runde[:16].replace('T', ' ')}" if runde else "Letzte Runde: noch keine"]
    if stand.get("abgelehnt"):
        z.append(f"Abgelehnt: {stand['abgelehnt']} Meldungen, die Telegram dauerhaft abgelehnt hat")
    if stand.get("problem"):
        z.append(f"Problem: {stand['problem']}")
    return "\n".join(z)


def _kommentare(a) -> int:
    bk = Briefkasten.lade(Pfade(basis=a.basis).daten)
    if bk is None:
        print("Fehler: Briefkasten nicht eingerichtet (fliessband briefkasten umstellen)", file=sys.stderr)
        return 1
    try:
        stand = bk.kommentare_stand() if a.aktion == "status" else bk.kommentare(a.aktion == "ein")
    except BriefkastenFehler as e:
        if e.code == 404 or "HTTP 404" in str(e):
            print("Fehler: Server kennt Kommentare noch nicht, zuerst server/deploy.sh", file=sys.stderr)
            return 1
        print(f"Fehler: {einzeilig(e)}", file=sys.stderr)
        return 1
    print(kommentare_text(stand))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fliessband")
    unter = parser.add_subparsers(dest="befehl", required=True)
    for name, hilfe in [("karussell", "Karussell aus einem Agentur-Beitrag bauen"),
                        ("reel", "Erklär-Reel aus einem Agentur-Reel-Skript bauen")]:
        u = unter.add_parser(name, help=hilfe, description=hilfe)
        u.add_argument("quelle", type=Path)
        u.add_argument("--termin", type=_termin, help="YYYY-MM-DDTHH:MM")
        u.add_argument("--basis", type=Path, default=STANDARD_BASIS, help=argparse.SUPPRESS)

    w = unter.add_parser("woche", help="Wochenpaket planen, bauen und nach Telegram senden",
                         description="Wochenpaket planen, bauen und nach Telegram senden")
    wu = w.add_subparsers(dest="aktion", required=True)
    for name, hilfe in [("vorbereiten", "Freitag: Konkurrenz, Apple-Notiz, Planer, Fragen an den Betreiber"),
                        ("bauen", "Samstag: Texte, Follower-Tests, Beiträge bauen und senden"),
                        ("senden", "Gebaute, noch nicht gesendete Beiträge nach Telegram schicken"),
                        ("anmelden", "Gesendete Beiträge beim Briefkasten anmelden (Knöpfe in Telegram)"),
                        ("status", "Stand der Woche zeigen")]:
        s = wu.add_parser(name, help=hilfe, description=hilfe)
        s.add_argument("--woche", type=_woche_arg,
                       help="z.B. 2026-KW44 (ohne: die Woche nach dem laufenden Wochenende)")
        s.add_argument("--basis", type=Path, default=STANDARD_BASIS, help=argparse.SUPPRESS)
    j = wu.add_parser("job", help="Für launchd: Schritt nur im Zeitfenster ausführen",
                      description="Für launchd: Schritt nur im Zeitfenster ausführen")
    j.add_argument("schritt", choices=["lernen", "vorbereiten", "bauen"])
    j.add_argument("--basis", type=Path, default=STANDARD_BASIS, help=argparse.SUPPRESS)

    le_hilfe = ("Lern-Schleife jetzt: Instagram-Zahlen auswerten, learnings.md fortschreiben; "
                "zählt als Lauf dieser Woche (Fr 20:00 läuft dann nicht nochmals)")
    le = unter.add_parser("lernen", help=le_hilfe, description=le_hilfe)
    le.add_argument("--probe", action="store_true",
                    help="nur Zahlen und Bericht zeigen, learnings.md bleibt, nichts nach Telegram, zählt nicht als Lauf")
    le.add_argument("--basis", type=Path, default=STANDARD_BASIS, help=argparse.SUPPRESS)

    ei = unter.add_parser("einrichten", help="Einrichtung prüfen: Schritt für Schritt, ändert nichts",
                          description="Prüft die Einrichtung in neun Schritten (Anleitung: docs/anleitung/) und nennt den "
                                      "nächsten offenen Schritt. Liest nur, ändert nichts, zeigt keine Werte.")
    ei.add_argument("--online", action="store_true", help="zusätzlich Server, Instagram und Facebook abfragen")
    ei.add_argument("--basis", type=Path, default=STANDARD_BASIS, help=argparse.SUPPRESS)
    b = unter.add_parser("bot", help="Telegram-Bot des Fliessbands", description="Telegram-Bot des Fliessbands")
    bu = b.add_subparsers(dest="aktion", required=True)
    e = bu.add_parser("einrichten", help="Chat-ID speichern, nachdem du dem Bot /start geschickt hast",
                      description="Chat-ID speichern, nachdem du dem Bot /start geschickt hast")
    e.add_argument("--basis", type=Path, default=STANDARD_BASIS, help=argparse.SUPPRESS)

    en = unter.add_parser("entscheide", help="Entscheide aus Telegram umsetzen (launchd, alle 15 Minuten)",
                          description="Entscheide aus Telegram umsetzen (launchd, alle 15 Minuten)")
    en.add_argument("--basis", type=Path, default=STANDARD_BASIS, help=argparse.SUPPRESS)

    bk = unter.add_parser("briefkasten", help="Briefkasten auf dem Server", description="Briefkasten auf dem Server")
    bku = bk.add_subparsers(dest="aktion", required=True)
    um = bku.add_parser("umstellen", help="Ab jetzt fragt der Server Telegram ab (einmalig)",
                        description="Ab jetzt fragt der Server Telegram ab (einmalig)")
    um.add_argument("--adresse", default=STANDARD_ADRESSE, help=f"Vorgabe {STANDARD_ADRESSE}")
    um.add_argument("--basis", type=Path, default=STANDARD_BASIS, help=argparse.SUPPRESS)

    po = unter.add_parser("poster", help="Automatisches Posten auf Instagram (Server)",
                          description="Automatisches Posten auf Instagram (Server)")
    pou = po.add_subparsers(dest="aktion", required=True)
    for name, hilfe in [("ein", "Posten einschalten"), ("aus", "Posten ausschalten (Freigaben bleiben)"),
                        ("status", "Schalter, Schlüssel-Alter und nächste Posts zeigen")]:
        s = pou.add_parser(name, help=hilfe, description=hilfe)
        s.add_argument("--basis", type=Path, default=STANDARD_BASIS, help=argparse.SUPPRESS)

    fbp = unter.add_parser("facebook", help="Nach Instagram auch auf die Facebook-Seite posten (Server)",
                           description="Nach Instagram auch auf die Facebook-Seite posten (Server)")
    fbu = fbp.add_subparsers(dest="aktion", required=True)
    for name, hilfe in [("ein", "Facebook einschalten (gilt ab dem nächsten Instagram-Post)"),
                        ("aus", "Facebook ausschalten (Instagram läuft weiter)"),
                        ("status", "Schalter, Seiten-Schlüssel und letzte Facebook-Posts zeigen")]:
        s = fbu.add_parser(name, help=hilfe, description=hilfe)
        s.add_argument("--basis", type=Path, default=STANDARD_BASIS, help=argparse.SUPPRESS)
    ko = unter.add_parser("kommentare", help="START-Kommentare auf Instagram in Telegram melden (Server)",
                          description="START-Kommentare auf Instagram in Telegram melden (Server)")
    kou = ko.add_subparsers(dest="aktion", required=True)
    for name, hilfe in [("ein", "Melden einschalten (der erste Lauf speichert nur, was schon da ist)"),
                        ("aus", "Melden ausschalten"),
                        ("status", "Schalter, Anzahl Kommentare und letzte Runde zeigen")]:
        s = kou.add_parser(name, help=hilfe, description=hilfe)
        s.add_argument("--basis", type=Path, default=STANDARD_BASIS, help=argparse.SUPPRESS)
    fk = unter.add_parser("fakten", help="Faktencheck vor dem Bauen ein- oder ausschalten",
                          description="Faktencheck vor dem Bauen ein- oder ausschalten")
    fku = fk.add_subparsers(dest="aktion", required=True)
    for name, hilfe in [("ein", "Faktencheck einschalten (Standard)"),
                        ("aus", "Faktencheck ausschalten (Notausgang)"),
                        ("status", "Schalter zeigen")]:
        s = fku.add_parser(name, help=hilfe, description=hilfe)
        s.add_argument("--basis", type=Path, default=STANDARD_BASIS, help=argparse.SUPPRESS)
    tr = unter.add_parser("trends", help="Trend-Scout (Web-Themen für den Planer) ein- oder ausschalten",
                          description="Trend-Scout vor dem Planer ein- oder ausschalten (Standard aus)")
    tru = tr.add_subparsers(dest="aktion", required=True)
    for name, hilfe in [("ein", "Trend-Scout einschalten (ein Websuche-Lauf pro Woche)"),
                        ("aus", "Trend-Scout ausschalten (Standard)"),
                        ("status", "Schalter zeigen"),
                        ("jetzt", "Scout jetzt von Hand laufen lassen und die Themen zeigen (Datei bleibt für Freitag)")]:
        s = tru.add_parser(name, help=hilfe, description=hilfe)
        if name == "jetzt":
            s.add_argument("--woche", type=_woche_arg,
                           help="z.B. 2026-KW46 (ohne: die Woche nach dem laufenden Wochenende)")
        s.add_argument("--basis", type=Path, default=STANDARD_BASIS, help=argparse.SUPPRESS)
    pl = unter.add_parser("plaetze", help="Beiträge pro Woche: 4 (Standard) oder 6",
                          description="Beiträge pro Woche: 4 (Standard) oder 6 (Mo Karussell und Fr Reel dazu)")
    plu = pl.add_subparsers(dest="aktion", required=True)
    for name, hilfe in [("4", "Vier Beiträge pro Woche (Standard)"),
                        ("6", "Sechs Beiträge pro Woche (Mo Karussell und Fr Reel dazu)"),
                        ("status", "Schalter zeigen")]:
        s = plu.add_parser(name, help=hilfe, description=hilfe)
        s.add_argument("--basis", type=Path, default=STANDARD_BASIS, help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    a = _parser().parse_args(argv)
    try:
        if a.befehl == "woche":
            return _woche(a)
        if a.befehl == "lernen":
            return _lernen(a)
        if a.befehl == "einrichten":
            return _einrichten(a)
        if a.befehl == "bot":
            return _bot(a)
        if a.befehl == "entscheide":
            return _entscheide(a)
        if a.befehl == "briefkasten":
            return _briefkasten(a)
        if a.befehl == "poster":
            return _poster(a)
        if a.befehl == "facebook":
            return _facebook(a)
        if a.befehl == "kommentare":
            return _kommentare(a)
        if a.befehl == "fakten":
            return _fakten(a)
        if a.befehl == "trends":
            return _trends(a)
        if a.befehl == "plaetze":
            return _plaetze(a)
        return _baue(a)
    except KeyboardInterrupt:
        print("Abgebrochen.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
