"""Etappe 8: findet vor dem Vertonen Wörter, die die KI-Stimme vermutlich falsch spricht.

Der Agent aussprache-agent schlägt Ersatzwörter vor, der Code prüft sie hart. Gültige Funde landen in
daten/aussprache-auto.txt (gleiches Format wie aussprache.txt) und gelten ab dann für jedes Reel.
Die Prüfung lässt nie einen Bau scheitern.
"""
import json
from datetime import date
from pathlib import Path
from typing import Callable

from lib.claude_lauf import ClaudeFehler
from lib.pruefungen import SATZZEICHEN, AusspracheFehler, lade_aussprache

AGENT = "aussprache-agent"
HOECHSTENS = 5  # Funde pro Reel
ZEITLIMIT = 3 * 60  # Sekunden für den Agenten-Aufruf
AUTO_DATEI = Path("daten") / "aussprache-auto.txt"  # relativ zur Basis des Fliessbands, nicht in Git
KOPF = "# Automatisch gefundene Einträge (Etappe 8). Format wie aussprache.txt, aussprache.txt gewinnt.\n"


class AusspracheUebersprungen(Exception):
    """Die Prüfung konnte nicht laufen. Der Bau geht mit der bisherigen Liste weiter."""


def kerne(szenen) -> set[str]:
    """Alle Wörter der Sprechtexte ohne Satzzeichen am Rand (so ersetzt auch sprechbar)."""
    return {SATZZEICHEN.match(t).group(2) for s in szenen for t in s.sprechtext.split()}


def _ein_wort(text) -> bool:
    return (isinstance(text, str) and len(text.split()) == 1 and "→" not in text
            and SATZZEICHEN.match(text).group(2) == text)


def gueltige_funde(roh, szenen, liste: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Übernommene Einträge {wort: ersatz} und verworfene Funde mit Grund (fürs Log)."""
    if not isinstance(roh, dict) or not isinstance(roh.get("funde"), list):
        raise AusspracheUebersprungen("Antwort ohne Liste 'funde'")
    vorhanden = kerne(szenen)
    neu, verworfen = {}, []
    for f in roh["funde"]:
        if not isinstance(f, dict):
            verworfen.append(f"{f!r}: kein Eintrag")
            continue
        wort, ersatz = f.get("wort"), f.get("ersatz")
        if not (_ein_wort(wort) and _ein_wort(ersatz)):
            grund = "nicht genau ein Wort ohne Satzzeichen am Rand"
        elif wort == ersatz:
            grund = "Ersatz gleich wie Wort"
        elif wort in liste or wort in neu:
            grund = "steht schon auf der Liste"
        elif wort not in vorhanden:
            grund = "kommt im Sprechtext nicht vor"
        elif len(neu) >= HOECHSTENS:
            grund = f"mehr als {HOECHSTENS} Funde"
        else:
            neu[wort] = ersatz
            continue
        verworfen.append(f"{wort!r} → {ersatz!r}: {grund}")
    return neu, verworfen


def _einzeilig(e: BaseException) -> str:
    return " ".join(str(e).split()) or type(e).__name__


def logzeile(log: Path, text: str) -> None:
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(f"=== aussprache === {text}\n")
    except OSError:
        pass   # das Log darf den Bau nie stoppen


def haenge_an(pfad: Path, funde: dict[str, str], heute: date, slug: str) -> None:
    """Hängt die Funde mit Datum und Reel an. Ohne Funde bleibt die Datei unberührt."""
    if not funde:
        return
    pfad.parent.mkdir(parents=True, exist_ok=True)
    kopf = ""
    if not pfad.exists():
        kopf = KOPF
    elif pfad.stat().st_size and not pfad.read_bytes().endswith(b"\n"):
        kopf = "\n"
    slug = " ".join(slug.split())
    zeilen = [f"# {heute.isoformat()}, {slug}"] + [f"{w} → {e}" for w, e in funde.items()]
    with pfad.open("a", encoding="utf-8") as f:
        f.write(kopf + "\n".join(zeilen) + "\n")


def lade_listen(hand: Path, auto: Path, log: Path) -> dict[str, str]:
    """aussprache.txt (Fehler brechen ab wie bisher) plus Auto-Liste (kaputt = ignoriert). Hand gewinnt."""
    liste = lade_aussprache(hand)
    if not auto.exists():
        return liste
    try:
        gefunden = lade_aussprache(auto)
    except (AusspracheFehler, OSError) as e:
        logzeile(log, f"{auto.name} ignoriert: {_einzeilig(e)}")
        return liste
    return {**gefunden, **liste}


def hinweis(funde) -> str | None:
    """Telegram-Zeile nach der Caption, nur bei Funden."""
    if not funde:
        return None
    return "🗣 Neu für die Stimme: " + ", ".join(f"{w} → {e}" for w, e in funde)


def auftrag(szenen, liste: dict[str, str], ausgabe: Path) -> str:
    texte = "\n".join(f"Szene {s.nummer}: {s.sprechtext}" for s in szenen)
    bekannt = ", ".join(sorted(liste)) or "(leer)"
    return f"""Prüfe die Sprechtexte eines Reels auf Wörter, die eine deutsche KI-Stimme (ElevenLabs, Hochdeutsch)
vermutlich falsch ausspricht. Schlage für jedes einen Ersatz vor, den die Stimme richtig spricht.

Sprechtexte:
{texte}

Schon auf der Liste (nicht nochmals melden): {bekannt}

Regeln:
- Melde nur Wörter, die genau so im Sprechtext stehen (ohne Satzzeichen am Anfang oder Ende).
- Der Ersatz ist genau ein Wort (Bindestriche erlaubt), ohne Leerzeichen und ohne Satzzeichen am Rand.
- Der Ersatz behält den Sinn. Im Zweifel nichts melden.
- Höchstens {HOECHSTENS} Funde.

Schreibe nur diese eine Datei: {ausgabe}
Inhalt genau so (JSON):
{{"funde": [{{"wort": "Trottoir", "ersatz": "Gehweg", "grund": "Helvetismus aus dem Französischen"}}]}}
Ohne Funde: {{"funde": []}}
"""


def pruefer(lauf: Callable, ordner: Path) -> Callable:
    """Echter Prüfer (szenen, liste) -> (neu, verworfen). `lauf` wie ClaudeLauf; `ordner` für die Antwort."""
    def pruefe(szenen, liste):
        ordner.mkdir(parents=True, exist_ok=True)
        ausgabe = ordner / "aussprache.json"
        ausgabe.unlink(missing_ok=True)   # eine alte Antwort darf nie als neue gelten
        try:
            lauf(AGENT, auftrag(szenen, liste, ausgabe), ausgabe, werkzeuge=("Write",), ordner=(ordner,),
                 zeitlimit=ZEITLIMIT)
            roh = json.loads(ausgabe.read_text(encoding="utf-8"))
        except ClaudeFehler as e:
            raise AusspracheUebersprungen(_einzeilig(e)) from None
        except (OSError, ValueError) as e:
            raise AusspracheUebersprungen(f"Antwort unlesbar ({type(e).__name__})") from None
        return gueltige_funde(roh, szenen, liste)
    return pruefe


def ergaenze(liste: dict[str, str], szenen, pruefer_: Callable, auto: Path, slug: str, heute: date,
             log: Path) -> list[list[str]]:
    """Holt neue Einträge, übernimmt sie in `liste` (für diesen Bau) und merkt sie in der Auto-Liste.
    Scheitert nie: jeder Fehler wird geloggt, dann geht der Bau mit der bisherigen Liste weiter."""
    try:
        neu, verworfen = pruefer_(szenen, dict(liste))
    except Exception as e:
        logzeile(log, f"Aussprache-Prüfung übersprungen: {_einzeilig(e)}")
        return []
    for v in verworfen:
        logzeile(log, f"Aussprache-Fund verworfen: {v}")
    liste.update(neu)
    try:
        haenge_an(auto, neu, heute, slug)
    except OSError as e:
        logzeile(log, f"{auto.name} nicht geschrieben: {_einzeilig(e)}")
    if neu:
        logzeile(log, "Aussprache neu: " + ", ".join(f"{w} → {e}" for w, e in neu.items()))
    return [[w, e] for w, e in neu.items()]
