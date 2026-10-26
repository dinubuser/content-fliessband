"""Lern-Schleife (Etappe 6), Freitag 20:00 vor der Themenplanung: holt die Instagram-Zahlen der letzten 4 Wochen
vom Server, legt Betreiber-Signale aus den Wochen-Ordnern dazu (✏️-Notizen, Verworfenes, Ausgelassenes) und lässt den
Analyse-Agenten learnings.md fortschreiben. Prüft das Ergebnis, legt sonst die alte Fassung zurück, und meldet
einen kurzen Bericht in Telegram. lauf() wirft nie: ein Ausfall darf die Planung nicht aufhalten.
Stand in daten/lernen.json: {woche, zeit, ergebnis (ok, fehler, zurueckgelegt), grund}."""
import json
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

from lib import manifest
from lib.briefkasten import BriefkastenFehler
from lib.claude_lauf import ClaudeFehler
from lib.fehler import einzeilig
from lib.freigabe import beitrag_id, manifest_pfad, titel_von
from lib.manifest import ManifestFehler, schreibe_json
from lib.umgebung import Pfade
from lib.wochenplan import PlanFehler, Wochenplan

TAGE = 28
STAND = "lernen.json"
AGENT = "analyse-agent"
WERKZEUGE = ("Read", "Write", "Edit")
ZEITLIMIT = 15 * 60
MIN_ANTEIL = 0.8   # neue learnings.md mindestens 80 % so lang wie die alte
OHNE_EINLADUNG = "ohne Einladung (vor Etappe 9)"
OHNE_BERICHT = "📈 Lern-Schleife gelaufen, Bericht fehlt. learnings.md ist fortgeschrieben."


class LernFehler(Exception):
    pass


LERN_FEHLER = (LernFehler, BriefkastenFehler, ClaudeFehler, ManifestFehler, OSError, ValueError, KeyError, TypeError)


def _stand_pfad(pfade: Pfade) -> Path:
    return pfade.daten / STAND


def faellig(pfade: Pfade, woche: str) -> bool:
    """Noch kein Lauf für diese Woche. Auch ein Fehlschlag zählt als Lauf (genau einmal pro Woche)."""
    try:
        d = json.loads(_stand_pfad(pfade).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    return not isinstance(d, dict) or d.get("woche") != woche


def schreibe_stand(pfade: Pfade, woche: str, jetzt: datetime, ergebnis: str, grund: str | None = None) -> None:
    schreibe_json(_stand_pfad(pfade), {"woche": woche, "zeit": jetzt.isoformat(timespec="seconds"),
                                       "ergebnis": ergebnis, "grund": grund})


def fliessband_beitraege(pfade: Pfade, jetzt: datetime) -> list[dict]:
    """Beiträge des Fliessbands mit Termin in den letzten 28 Tagen bis jetzt, aus Plan und Manifest jeder Woche.
    Kaputte oder unvollständige Wochen werden übersprungen."""
    grenze, liste = jetzt - timedelta(days=TAGE), []
    ordner = pfade.basis / "wochen"
    wochen = sorted(p.name for p in ordner.iterdir() if p.is_dir()) if ordner.is_dir() else []
    for w in wochen:
        if not pfade.plan(w).exists() or not manifest_pfad(pfade, w).exists():
            continue
        try:
            themen = Wochenplan.lade(pfade.plan(w), w).themen
            eintraege = {b["id"]: b for b in manifest.lade(manifest_pfad(pfade, w), w)["beitraege"]
                         if isinstance(b, dict) and "id" in b}
        except (PlanFehler, ManifestFehler, OSError, KeyError, ValueError, TypeError, AttributeError):
            continue
        if not isinstance(themen, list):
            continue
        for t in themen:
            try:
                termin = datetime.fromisoformat(t["termin"])
                if not grenze <= termin <= jetzt:
                    continue
                id = beitrag_id(w, t)
                b = eintraege.get(id, {})
                liste.append({"id": id, "woche": w, "titel": titel_von(t), "format": t["format"],
                              "termin": t["termin"], "hook_idee": t.get("hook_idee"),
                              "quelle": (t.get("quelle") or {}).get("art"),
                              "status": b.get("status", t.get("status")),
                              "notizen": [n.get("text") for n in b.get("notizen", []) if isinstance(n, dict)],
                              "instagram_id": b.get("instagram_id"),
                              "laenge": t.get("laenge") or ("lang (vor Etappe 7)" if t["format"] == "reel" else None),
                              "dauer_s": b.get("dauer_s"),
                              "einstieg": t.get("einstieg"),
                              "einladung": "START" if t.get("einstieg") else OHNE_EINLADUNG})
            except (KeyError, ValueError, TypeError, AttributeError):
                continue   # ein kaputtes Thema bricht die Lern-Schleife nicht ab
    return liste


def verbinde(zahlen: list[dict], beitraege: list[dict]) -> list[dict]:
    """Hängt an jeden Instagram-Beitrag den Fliessband-Beitrag mit derselben instagram_id (sonst None)."""
    nach_ig = {b["instagram_id"]: b for b in beitraege if isinstance(b, dict) and b.get("instagram_id")}
    return [dict(z, fliessband=nach_ig.get(z.get("ig_id"))) for z in zahlen if isinstance(z, dict)]


def _ueberschriften(text: str) -> list[str]:
    return [z.strip() for z in text.splitlines() if z.startswith("## ")]


def pruefe(alt: str, neu: str, heute: date) -> str | None:
    """Grund, warum die neue learnings.md nicht taugt, sonst None."""
    vorhanden = set(_ueberschriften(neu))
    for u in _ueberschriften(alt):
        if u not in vorhanden:
            return f"Überschrift fehlt: {u}"
    if len(neu) < MIN_ANTEIL * len(alt):
        return "neue learnings.md ist zu kurz"
    if f"## Stand {heute:%d.%m.%Y}" not in neu:
        return f"Abschnitt «Stand {heute:%d.%m.%Y}» fehlt"
    return None


def auftrag(pfade: Pfade, daten: Path, ziel: Path, bericht: Path, heute: date) -> str:
    tag = f"{heute:%d.%m.%Y}"
    return f"""Lern-Schleife des Content-Fliessbands für @dein.konto, Lauf vom {tag}.

Lies zuerst: {ziel} (bisherige Learnings), {pfade.regelwerk} und {pfade.agentur / 'profil.md'}.
Daten: {daten}
- "instagram": alle Beiträge des Accounts der letzten 28 Tage. werte: views, reach, shares, saved, comments, likes,
  total_interactions, bei Reels ig_reels_avg_watch_time (Millisekunden) und reels_skip_rate (Prozent). null = Wert fehlt.
  "fliessband" ist gesetzt, wenn der Beitrag vom Fliessband stammt (Thema, Hook-Idee, Quelle).
  start_kommentare: Anzahl Kommentare mit dem Stichwort START (Leute, die mit dem Betreiber reden wollen).
  Gezählt wird erst ab dem Einschalten der Kommentar-Meldung (Etappe 9) und nur für Beiträge der letzten 14 Tage.
  Bei älteren Beiträgen oder «ohne Einladung (vor Etappe 9)» heisst 0 «nicht erfasst», nicht «keine Resonanz».
- "fliessband": alle Fliessband-Beiträge mit Termin in dieser Zeit, auch nicht gepostete. status: gepostet,
  verworfen (der Betreiber wollte das Thema nicht), ausgelassen, verpasst, freigegeben und andere. notizen: Änderungswünsche des Betreibers zum Entwurf (✏️).
  laenge (nur Reels): kurz (Ziel 20 bis 30 s), mittel (30 bis 45 s) oder «lang (vor Etappe 7)»; dauer_s: echte Länge.
  einstieg: persönlicher Moment des Betreibers am Anfang; einladung: «START» (endet mit «Kommentiere START») oder
  «{OHNE_EINLADUNG}».

Aufgabe:
1. Tabelle je Instagram-Beitrag: Datum, Thema, Format, Hook-Muster, Aufrufe, Reichweite, geteilt, gespeichert,
   Kommentare, START-Kommentare, Likes, bei Reels Weiterwisch-Rate und Ø Wiedergabe in Sekunden. Teil-Quote = geteilt ÷ Reichweite × 1000.
2. Median der Reichweite aller Beiträge. Gewinner ≥ 2× Median, Verlierer ≤ 0,5× Median.
3. Muster nur mit Beleg (Thema, Hook-Muster, Format). Unter 8 Belegen pro Muster nur «Hinweis», keine «Regel».
   Vergleiche Reels nach laenge getrennt (kurz, mittel, lang vor Etappe 7): Reichweite, Weiterwisch-Rate, Ø Wiedergabe.
   Vergleiche, welche Themen und Einstiege START-Kommentare bringen. Beiträge «{OHNE_EINLADUNG}» zählen dafür nicht.
   Korrelation ist kein Beweis. Beiträge jünger als 48 Stunden als «vorläufig» markieren und in einer Woche erneut prüfen.
4. Schreibe {ziel} fort. Alles Bisherige bleibt mit allen Überschriften stehen. Hänge unten einen neuen Abschnitt
   an. Seine Überschrift muss genau so, mit "## " am Zeilenanfang, in der Datei stehen:
## Stand {tag} (Lern-Schleife)
   Darunter: Tabelle, Beobachtungen mit Beleg, Hinweise oder Regeln, nächste Prüfpunkte.
   Ältere Erkenntnisse, die die Zahlen widerlegen, markierst du dort als **widerlegt** (Datum, Beleg). Nie löschen.
5. Abschnitt "## Aus Betreiber-Änderungen" (anlegen, falls er fehlt, sonst ergänzen): wiederkehrende Wünsche aus den
   notizen und was die verworfenen Themen gemeinsam haben. Ab 2 gleichartigen Notizen schreibst du eine feste
   Vorgabe für den Texter, mit Datum und den Notizen als Beleg.
6. Kein Wochenplan, keine Trial-Reels (die Themen plant der Planer).
7. Schreibe zuletzt {bericht} als JSON, sonst nichts darin:
   {{"erkenntnisse": ["3 kurze Sätze"], "bester": {{"titel": "…", "grund": "…"}},
    "schwaechster": {{"titel": "…", "grund": "…"}}, "aenderungen": ["was in learnings.md neu ist, je ein Satz"]}}

Schreibe ausschliesslich {ziel} und {bericht}. Ändere keine andere Datei.
Regeln: Keine Zahl erfinden oder schätzen, fehlende Werte als «–». Deutsch, [BEISPIEL: Schreibweise des Betreibers, z.B. ss statt ß],
kurze Sätze, keine Gedankenstriche.
"""


def _saetze(wert) -> list[str] | None:
    if not isinstance(wert, list) or not all(isinstance(s, str) for s in wert):
        return None
    return wert


def bericht_text(bericht) -> str:
    """Telegram-Text aus dem Bericht des Agenten. Ungültig oder ohne Erkenntnisse: Ersatztext."""
    if not isinstance(bericht, dict) or not _saetze(bericht.get("erkenntnisse")):
        return OHNE_BERICHT
    zeilen = ["📈 Lern-Schleife", "", "Wichtigste Erkenntnisse:"] + [f"• {s}" for s in bericht["erkenntnisse"][:3]]
    for schluessel, name in (("bester", "Bester Beitrag"), ("schwaechster", "Schwächster Beitrag")):
        e = bericht.get(schluessel)
        if isinstance(e, dict) and e.get("titel"):
            zeilen += ["", f"{name}: «{e['titel']}»"] + ([str(e["grund"])] if e.get("grund") else [])
    aenderungen = _saetze(bericht.get("aenderungen"))
    if aenderungen:
        zeilen += ["", "Neu in learnings.md:"] + [f"• {s}" for s in aenderungen]
    return "\n".join(zeilen)


def _lies_bericht(pfad: Path):
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _merke_agentur(agentur: Path) -> dict[str, str]:
    """Inhalt aller *.md direkt in der Agentur (nicht rekursiv), unlesbare Dateien fehlen."""
    stand = {}
    for p in agentur.glob("*.md"):
        try:
            stand[p.name] = p.read_text(encoding="utf-8")
        except (OSError, ValueError):
            pass
    return stand


def _schuetze_agentur(agentur: Path, vorher: dict[str, str], ziel: Path, log) -> list[str]:
    """Stellt geänderte oder gelöschte *.md ausser dem Ziel wieder her. Liefert deren Namen. Neue Dateien bleiben."""
    geaendert = []
    for name, text in vorher.items():
        if agentur / name == ziel:
            continue
        try:
            if (agentur / name).read_text(encoding="utf-8") == text:
                continue
        except (OSError, ValueError):
            pass
        geaendert.append(name)
        try:
            (agentur / name).write_text(text, encoding="utf-8")
        except OSError as e:
            log(f"{name} nicht wiederhergestellt: {einzeilig(e)}")
    neu = sorted(p.name for p in agentur.glob("*.md") if p.name not in vorher and agentur / p.name != ziel)
    if neu:
        log(f"Agent hat neue Dateien angelegt: {', '.join(neu)}")
    return geaendert


def _lerne(pfade: Pfade, dienste, jetzt: datetime, alt: str, probe: bool, log) -> tuple[Path, object]:
    """Zahlen holen, Daten ablegen, sichern, Agent laufen lassen. Liefert (geschriebene Datei, Bericht oder None)."""
    heute, ordner = jetzt.date(), pfade.daten / "lernen"
    beitraege = fliessband_beitraege(pfade, jetzt)
    daten = ordner / f"daten-{heute}.json"
    schreibe_json(daten, {"erstellt": jetzt.isoformat(timespec="seconds"),
                          "instagram": verbinde(dienste.briefkasten.zahlen(TAGE), beitraege), "fliessband": beitraege})
    learnings = pfade.agentur / "learnings.md"
    if probe:
        ziel = ordner / "probe-learnings.md"
        ziel.write_text(alt, encoding="utf-8")
    else:
        ziel = learnings
        sicherung = learnings.with_name(f"learnings.{heute}.md")
        if not sicherung.exists():
            shutil.copy2(learnings, sicherung)
    bericht = ordner / f"bericht-{heute}.json"
    bericht.unlink(missing_ok=True)
    vorher = _merke_agentur(pfade.agentur)
    try:
        dienste.claude(AGENT, auftrag(pfade, daten, ziel, bericht, heute), bericht, werkzeuge=WERKZEUGE,
                       ordner=(pfade.skill, ordner), zeitlimit=ZEITLIMIT)
    finally:   # auch nach einem Fehler des Agenten: fremde Dateien zurücklegen
        geaendert = _schuetze_agentur(pfade.agentur, vorher, ziel, log)
    if geaendert:
        raise LernFehler(f"Agent hat {', '.join(geaendert)} geändert, zurückgelegt")
    return ziel, _lies_bericht(bericht)


def _legezurueck(pfade: Pfade, alt: str, jetzt: datetime) -> str | None:
    """Legt learnings.md zurück. Liefert None bei Erfolg, sonst den Telegram-Text für den Notfall."""
    try:
        (pfade.agentur / "learnings.md").write_text(alt, encoding="utf-8")
        return None
    except OSError:
        sicherung = f"learnings.{jetzt.date()}.md"
        hinweis = f"Sicherung: {sicherung}" if (pfade.agentur / sicherung).exists() else "keine Sicherung vorhanden"
        return f"⚠️ Lern-Schleife: learnings.md konnte nicht zurückgelegt werden, {hinweis}"


def lauf(pfade: Pfade, dienste, woche: str, log, probe: bool = False) -> str:
    """Eine Lern-Runde. Liefert 'ok', 'zurueckgelegt', 'fehler' oder 'uebersprungen', im Probelauf den Bericht-Text.
    Wirft nie. Probe: ändert learnings.md nicht, schreibt keinen Stand, sendet nichts."""
    if dienste.briefkasten is None:
        log("Lern-Schleife übersprungen: Briefkasten nicht eingerichtet")
        return "uebersprungen"
    try:
        jetzt = dienste.jetzt()
    except Exception:
        jetzt = datetime.now()
    alt, grund = None, None
    try:
        try:
            alt = (pfade.agentur / "learnings.md").read_text(encoding="utf-8")
        except OSError:
            raise LernFehler("learnings.md fehlt") from None
        ziel, bericht = _lerne(pfade, dienste, jetzt, alt, probe, log)
        grund = pruefe(alt, ziel.read_text(encoding="utf-8"), jetzt.date())
        if grund:
            ergebnis, text = "zurueckgelegt", f"⚠️ Lern-Schleife: learnings.md zurückgelegt, {grund}"
        else:
            ergebnis, text = "ok", bericht_text(bericht)
    except LERN_FEHLER as e:
        grund = einzeilig(e)
        ergebnis, text = "fehler", f"⚠️ Lern-Schleife ausgefallen: {grund}"
    except Exception as e:   # lauf() wirft nie
        grund = f"{type(e).__name__}: {einzeilig(e)}"
        ergebnis, text = "fehler", f"⚠️ Lern-Schleife ausgefallen: {grund}"
    if ergebnis != "ok" and alt is not None and not probe:
        notfall = _legezurueck(pfade, alt, jetzt)
        if notfall:
            ergebnis, text = "fehler", notfall
            log(notfall)
    log(f"Lern-Schleife: {ergebnis}" + (f" ({grund})" if grund else ""))
    if probe:
        log(text)
        return text
    try:
        schreibe_stand(pfade, woche, jetzt, ergebnis, grund)
    except Exception as e:
        log(f"Stand nicht geschrieben: {einzeilig(e)}")
    try:
        dienste.bot.sende_text(text)
    except Exception as e:
        log(f"Bericht nicht gesendet: {einzeilig(e)}")
    return ergebnis
