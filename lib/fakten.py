"""Etappe 10: prüft Zahlen und Behauptungen eines Beitrags gegen Quellen, bevor gebaut wird.

Der Agent fakten-agent liefert Funde, der Code prüft sie hart und wendet gültige Korrekturen auf die Skriptdatei an.
Ohne brauchbare Korrektur wird eine Stelle «offen» (Marker [prüfen], der Betreiber klärt sie). Die Prüfung lässt nie einen Bau
scheitern: Fällt sie aus, geht der Beitrag mit einer Warnzeile durch.
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import copy

from lib.claude_lauf import ClaudeFehler, ZeitAbgelaufen
from lib.manifest import schreibe_json
from lib.pruefungen import PLATZHALTER, RISIKO_MARKER, START

AGENT = "fakten-agent"
HOECHSTENS = 5          # Korrekturen pro Beitrag, der Rest wird offen
ZEITLIMIT = 6 * 60      # Sekunden für den Agenten-Aufruf (Websuche braucht Zeit)
WERKZEUGE = ("Read", "Write", "WebSearch", "WebFetch")
SCHALTER = Path("daten") / "fakten.json"   # relativ zur Basis, nicht in Git; fehlt die Datei, gilt «an»
LOG = Path("logs") / "fakten.log"
MARKER = " [prüfen]"
URTEILE = ("falsch", "nicht_belegbar")
VOICEOVER = re.compile(r"^## Voiceover.*?(?=^## |\Z)", re.DOTALL | re.MULTILINE)
ZAHLEN = re.compile(r"\d+(?:[.,]\d+)?")   # Dezimalzahlen sind eine Zahl
# Tausendertrenner: Apostroph oder Punkt nach 1 bis 3 Ziffern, Leerzeichen nur nach genau einer Ziffer
# («2 000» ja, «65 100» sind zwei Zahlen). «3.500» gilt als Tausender, nicht als Dezimalzahl.
TAUSENDER = re.compile(r"(?<![\d.,'’])(?<!\d )(?:\d{1,3}(?:['’.]\d{3})+|\d(?: \d{3})+)(?!\d)")
HOST = re.compile(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
MINDESTLAENGE = 8       # kürzere Stellen sind nicht eindeutig genug
UEBERSCHRIFT = re.compile(r"#{1,6} ")                       # Hashtags wie #familie sind keine Überschrift
LABEL_NAMEN = r"(?:Sprechtext|Einblendung|Grafik|Bild|Überschrift|Text):"
LABEL_ANFANG = re.compile(r"\s*" + LABEL_NAMEN + r"\s*")    # nur am Zeilenanfang ein Label, nie mitten im Satz
KOPFZEILE = ("**Szene", "**Slide")
# Eine Korrektur darf kein Gerüst einführen (Überschrift, Szenen-/Slide-Zeile, Label)
GERUEST_ANFANG = re.compile(r"\s*(?:#{1,6} |\*\*(?:Szene|Slide)|" + LABEL_NAMEN + ")")


class FaktenUebersprungen(Exception):
    """Die Prüfung konnte nicht laufen. Der Beitrag geht mit Warnzeile durch."""


@dataclass(frozen=True)
class Fund:
    stelle: str
    urteil: str     # "falsch" | "nicht_belegbar"
    korrektur: str  # ganzer neuer Wortlaut der Stelle
    quelle: str     # https-URL, bei nicht_belegbar leer
    grund: str


def pruef_text(text: str) -> str:
    """Der Text, den der Agent sieht und in dem eine Stelle genau einmal stehen muss: ohne Voiceover-Abschnitt."""
    return VOICEOVER.sub("", text)


def _quelle_ok(quelle: str) -> bool:
    u = urlparse(quelle.strip())
    return u.scheme == "https" and bool(HOST.fullmatch(u.netloc))


def _struktur_grund(stelle: str, pruef: str) -> str | None:
    """Grund, falls die (einmal vorkommende, einzeilige) Stelle in Gerüst des Skripts liegt: Überschrift, Szenenzeile,
    Label wie «Sprechtext:». Text hinter dem Label bleibt korrigierbar."""
    anfang = pruef.find(stelle)
    zeilen_start = pruef.rfind("\n", 0, anfang) + 1
    ende = pruef.find("\n", anfang)
    zeile = pruef[zeilen_start:ende if ende != -1 else len(pruef)]
    if UEBERSCHRIFT.match(zeile):
        return "Überschrift"
    if zeile.lstrip().startswith(KOPFZEILE):
        return "Szenen- oder Slidezeile"
    label = LABEL_ANFANG.match(zeile)
    if label and anfang < zeilen_start + label.end():
        return "Label"
    return None


def _geschuetzt(stelle: str) -> bool:
    """Risikohinweis und START-Einladung bleiben unangetastet."""
    return bool(START.search(stelle) or RISIKO_MARKER.search(stelle))


def _zahlen(text: str) -> set[str]:
    """Zahlen ohne Tausendertrenner: «2'500» gleich «2500». Dezimalzahlen bleiben ganz: «0.5» ist nicht «5»."""
    ohne = TAUSENDER.sub(lambda m: re.sub(r"\D", "", m.group()), text)
    return {z.replace(",", ".") for z in ZAHLEN.findall(ohne)}


def _schneidet(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _korrigierbar(f: Fund) -> bool:
    if not f.korrektur.strip() or f.korrektur == f.stelle or "\n" in f.korrektur:
        return False
    if PLATZHALTER.search(f.korrektur) or _geschuetzt(f.korrektur) or GERUEST_ANFANG.match(f.korrektur):
        return False
    if f.urteil == "falsch":
        return _quelle_ok(f.quelle)
    return _zahlen(f.korrektur) <= _zahlen(f.stelle)   # nicht belegbar: keine neue Zahl


def _text(wert) -> str:
    return wert if isinstance(wert, str) else ""


def gueltige_funde(roh, text: str) -> tuple[list[Fund], list[Fund], list[str]]:
    """(korrigiert, offen, verworfen). Verworfen (mit Grund fürs Log): Stelle nicht eindeutig auffindbar, geschützt,
    doppelt, kaputt. Offen: Stelle gefunden, aber ohne sichere Korrektur oder über dem Limit."""
    if not (isinstance(roh, dict) and isinstance(roh.get("funde"), list)
            and isinstance(roh.get("geprueft"), int) and not isinstance(roh.get("geprueft"), bool)):
        raise FaktenUebersprungen("Antwort ohne 'geprueft' und Liste 'funde'")
    pruef = pruef_text(text)
    korrigiert, offen, verworfen, gesehen, bereiche = [], [], [], set(), []

    def bereich(stelle: str) -> tuple[int, int]:   # Zeichenbereich im Prüftext (die Stelle kommt dort genau einmal vor)
        anfang = pruef.find(stelle)
        return anfang, anfang + len(stelle)

    for f in roh["funde"]:
        if not isinstance(f, dict):
            verworfen.append(f"{f!r}: kein Eintrag")
            continue
        stelle = f.get("stelle")
        if not isinstance(stelle, str) or not stelle.strip():
            verworfen.append(f"{stelle!r}: keine Stelle")
        elif f.get("urteil") not in URTEILE:
            verworfen.append(f"{stelle!r}: unbekanntes Urteil {f.get('urteil')!r}")
        elif len(stelle.strip()) < MINDESTLAENGE:
            verworfen.append(f"{stelle!r}: zu kurz")
        elif "\n" in stelle:
            verworfen.append(f"{stelle!r}: mehrzeilig")
        elif pruef.count(stelle) != 1:
            verworfen.append(f"{stelle!r}: kommt nicht genau einmal im Text vor")
        elif stelle in gesehen:
            verworfen.append(f"{stelle!r}: doppelt")
        elif _geschuetzt(stelle):
            verworfen.append(f"{stelle!r}: geschützter Text")
        elif _struktur_grund(stelle, pruef):
            verworfen.append(f"{stelle!r}: geschützter Text ({_struktur_grund(stelle, pruef)})")
        elif any(_schneidet(bereich(stelle), b) for b in bereiche):
            verworfen.append(f"{stelle!r}: überlappt mit einer früheren Stelle")
        else:
            gesehen.add(stelle)
            bereiche.append(bereich(stelle))
            fund = Fund(stelle, f["urteil"], _text(f.get("korrektur")), _text(f.get("quelle")), _text(f.get("grund")))
            if _korrigierbar(fund) and len(korrigiert) < HOECHSTENS:
                korrigiert.append(fund)
            else:
                offen.append(fund)
    return korrigiert, offen, verworfen


def wende_an(text: str, korrigiert: list[Fund], offen: list[Fund], markiere: bool = True) -> tuple[str, list[str]]:
    """Ersetzt in der ganzen Datei (auch in der Voiceover-Kopie). Liefert (neuer Text, nicht mehr gefundene Stellen),
    z.B. wenn eine frühere Ersetzung die Stelle verändert hat. Offene Stellen bekommen den Marker, nie doppelt."""
    uebersprungen = []
    for f in korrigiert:
        if f.stelle in text:
            text = text.replace(f.stelle, f.korrektur)
        else:
            uebersprungen.append(f.stelle)
    rest = pruef_text(text)   # nur dort zählt eine Stelle als vorhanden, nicht in der Voiceover-Kopie
    for f in offen:
        if f.stelle not in rest:
            uebersprungen.append(f.stelle)
    if markiere and offen:
        # Marker nur ausserhalb des Voiceover-Abschnitts (dessen Text geht an ElevenLabs), nie doppelt
        teile, pos = [], 0
        for m in VOICEOVER.finditer(text):
            teile.append((False, text[pos:m.start()]))
            teile.append((True, m.group()))
            pos = m.end()
        teile.append((False, text[pos:]))
        for f in offen:
            muster = re.compile(re.escape(f.stelle.removesuffix(MARKER)) + "(?!" + re.escape(MARKER) + ")")
            teile = [(vo, t if vo else muster.sub(lambda m: m.group() + MARKER, t)) for vo, t in teile]
        text = "".join(t for _, t in teile)
    return text, uebersprungen


def _s(wert) -> str:
    return wert if isinstance(wert, str) else ""


def _kurz(text: str, n: int = 60) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n - 1] + "…"


def _seite(woerter: list[str], von: int, bis: int, vor: int, nach: int) -> str:
    """Mittelteil [von, bis) mit `vor` Wörtern davor und `nach` danach; «…» wo Text wegfällt."""
    anfang, ende = max(0, von - vor), min(len(woerter), bis + nach)
    teile = (["…"] if anfang > 0 else []) + woerter[anfang:ende] + (["…"] if ende < len(woerter) else [])
    return " ".join(teile)


def _aenderung(stelle: str, korrektur: str) -> tuple[str, str]:
    """Nur die geänderte Stelle mit etwas Umfeld, auf Wortebene. Ersetzung: 1 Wort davor, 0 danach. Reine Einfügung
    oder Streichung: 2 davor, 1 danach. Erst danach greift das Sicherheitsnetz von `_kurz` (80 Zeichen)."""
    a, b = stelle.split(), korrektur.split()
    p = 0
    while p < min(len(a), len(b)) and a[p] == b[p]:
        p += 1
    s = 0
    while s < min(len(a), len(b)) - p and a[-1 - s] == b[-1 - s]:
        s += 1
    if p == len(a) == len(b):   # identisch
        return _kurz(stelle, 80), _kurz(korrektur, 80)
    vor, nach = (2, 1) if p + s in (len(a), len(b)) else (1, 0)
    return (_kurz(_seite(a, p, len(a) - s, vor, nach), 80), _kurz(_seite(b, p, len(b) - s, vor, nach), 80))


def _domain(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def hinweis(e: dict | None) -> str | None:
    """Telegram-Zeile nach der Caption. Nichts geprüft und nichts gefunden: keine Zeile."""
    if not e:
        return None
    if not e.get("lief"):
        return "⚠️ Faktencheck nicht gelaufen, bitte selbst prüfen"
    n = e.get("geprueft") or 0
    k = [f for f in (e.get("korrigiert") or []) if isinstance(f, dict)]
    o = [f for f in (e.get("offen") or []) if isinstance(f, dict)]
    if n == 0 and not k and not o:
        return None
    zeile = f"🔎 Faktencheck: {n} {'Aussage' if n == 1 else 'Aussagen'} geprüft"
    if not k and not o:
        return zeile + ", alles belegt"
    if k:
        zeile += f", {len(k)} korrigiert: " + "; ".join(
            "{} → {} ({})".format(*_aenderung(_s(f.get("stelle")), _s(f.get("korrektur"))),
                                  _domain(_s(f.get("quelle"))) or "nicht belegbar") for f in k)
    if o:
        marker = "" if e.get("markiert") is False else " [prüfen]"   # Neubau: kein Marker in der Datei
        zeile += f", {len(o)} offen: " + "; ".join(_kurz(_s(f.get("stelle"))) for f in o) + marker + ", bitte selbst klären"
    return zeile


def ist_an(basis: Path) -> bool:
    """Standard «an». Fehlende oder kaputte Datei gilt als an (der Check ist das Sicherheitsnetz)."""
    try:
        return bool(json.loads((Path(basis) / SCHALTER).read_text(encoding="utf-8")).get("an", True))
    except (OSError, ValueError, AttributeError):
        return True


def setze(basis: Path, an: bool) -> None:
    schreibe_json(Path(basis) / SCHALTER, {"an": an})


def schalter_text(basis: Path) -> str:
    return f"Faktencheck: {'an' if ist_an(basis) else 'aus'}"


def _einzeilig(e: BaseException) -> str:
    return " ".join(str(e).split()) or type(e).__name__


def _logzeile(log: Path, text: str) -> None:
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(f"=== fakten === {text}\n")
    except OSError:
        pass   # das Log darf den Bau nie stoppen


def auftrag(text: str, ausgabe: Path) -> str:
    return f"""Prüfe dieses Skript eines Instagram-Beitrags auf Sachfehler (Zahlen, Beträge, Fristen, Gesetze, Studien, Zitate).
Suche Quellen im Web und halte dich an deine Regeln als fakten-agent.

Skript:
-----
{text}
-----

Schreibe nur diese eine Datei: {ausgabe}
Inhalt genau so (JSON):
{{"geprueft": 6, "funde": [{{"stelle": "wörtlicher Auszug", "urteil": "falsch", "korrektur": "ganzer neuer Wortlaut der Stelle", "quelle": "https://www.bag.admin.ch/...", "grund": "kurz"}}]}}
`geprueft` ist die Zahl aller geprüften Aussagen, auch der belegten. Ohne Funde: "funde": [].
Höchstens {HOECHSTENS} Funde mit Korrektur, weitere ohne brauchbare Korrektur sind erlaubt.
"""


def frage(lauf: Callable, text: str, ordner: Path):
    """Ruft den Agenten und liefert die rohe JSON-Antwort. Jeder Fehler wird zu FaktenUebersprungen."""
    ordner.mkdir(parents=True, exist_ok=True)
    ausgabe = ordner / "fakten.json"
    ausgabe.unlink(missing_ok=True)   # eine alte Antwort darf nie als neue gelten
    try:
        lauf(AGENT, auftrag(pruef_text(text), ausgabe), ausgabe, werkzeuge=WERKZEUGE, ordner=(ordner,),
             zeitlimit=ZEITLIMIT)
        return json.loads(ausgabe.read_text(encoding="utf-8"))
    except ZeitAbgelaufen:
        raise   # die Gesamtfrist des Schritts gilt für alle, sie darf nicht verschluckt werden
    except ClaudeFehler as e:
        raise FaktenUebersprungen(_einzeilig(e)) from None
    except (OSError, ValueError) as e:
        raise FaktenUebersprungen(f"Antwort unlesbar ({type(e).__name__})") from None


def schreibgeschuetzt(claude, agentur: Path):
    """Kopie des Laufs, in der der Agent die Agentur (Skripte, profil.md, learnings.md) nur lesen darf. Andere Läufe
    (Texter, Aussprache, Lernen) behalten ihre Rechte. Attrappen ohne `nur_lesen` bleiben unverändert."""
    if not hasattr(claude, "nur_lesen"):
        return claude
    kopie = copy.copy(claude)
    kopie.nur_lesen = tuple(claude.nur_lesen) + (Path(agentur),)
    return kopie


def _lese(format: str, pfad: Path) -> None:
    """Der Bauer muss die korrigierte Datei weiter lesen können."""
    if format == "reel":
        from lib.reel_leser import lese_reel
        lese_reel(pfad)
    else:
        from lib.leser import lese_beitrag
        lese_beitrag(pfad)


def _lege_zurueck(pfad: Path, original: str, log: Path) -> bool:
    """True, wenn die Skriptdatei nicht mehr dem Original entsprach (dann wieder hergestellt)."""
    try:
        if pfad.read_text(encoding="utf-8") == original:
            return False
    except (OSError, ValueError):
        pass
    try:
        pfad.write_text(original, encoding="utf-8")
    except OSError as e:
        _logzeile(log, f"{pfad.name}: Skript nicht wiederhergestellt: {_einzeilig(e)}")
    return True


def pruefe_beitrag(pfad: Path, format: str, lauf: Callable, basis: Path, markiere_offen: bool = True) -> dict | None:
    """Prüft die Skriptdatei, korrigiert sie und liefert das Ergebnis fürs Telegram:
    {"lief", "geprueft", "korrigiert": [{stelle, korrektur, quelle, urteil}], "offen": [{stelle, grund}]}.
    None bei ausgeschaltetem Schalter. Scheitert nie, ausser an ZeitAbgelaufen (Gesamtfrist des Schritts): jeder Fehler wird geloggt, `lief` ist dann False.
    Eine Korrektur, nach der der Bauer die Datei nicht mehr lesen kann, wird zurückgenommen."""
    basis, pfad = Path(basis), Path(pfad)
    if not ist_an(basis):
        return None
    log = basis / LOG
    ergebnis = {"lief": False, "geprueft": 0, "korrigiert": [], "offen": []}
    try:
        original = pfad.read_text(encoding="utf-8")
        try:
            roh = frage(lauf, original, basis / "zwischenspeicher" / "fakten")
        finally:   # der Agent darf die Skriptdatei nie verändern (Prompt-Injection), sonst zurücklegen
            veraendert = _lege_zurueck(pfad, original, log)
        if veraendert:
            raise FaktenUebersprungen(f"Agent hat {pfad.name} verändert, zurückgelegt")
        korrigiert, offen, verworfen = gueltige_funde(roh, original)
        neu, uebersprungen = wende_an(original, korrigiert, offen, markiere_offen)
        if neu != original:
            pfad.write_text(neu, encoding="utf-8")
            try:
                _lese(format, pfad)
            except Exception as e:
                pfad.write_text(original, encoding="utf-8")
                raise FaktenUebersprungen(f"Korrektur machte {pfad.name} unlesbar ({_einzeilig(e)}), zurückgesetzt") from None
    except ZeitAbgelaufen:
        raise
    except FaktenUebersprungen as e:
        _logzeile(log, f"{pfad.name}: Prüfung übersprungen: {_einzeilig(e)}")
        return ergebnis
    except OSError as e:
        _logzeile(log, f"{pfad.name}: Datei nicht lesbar oder schreibbar: {_einzeilig(e)}")
        return ergebnis
    except Exception as e:   # äusserster Rand: die Prüfung darf den Bau nie kippen
        _logzeile(log, f"{pfad.name}: unerwarteter Fehler ({type(e).__name__}): {_einzeilig(e)}")
        return ergebnis
    for v in verworfen:
        _logzeile(log, f"{pfad.name}: Fund verworfen: {v}")
    for s in uebersprungen:
        _logzeile(log, f"{pfad.name}: Stelle nicht mehr vorhanden, nicht angewendet oder markiert: {s!r}")
    angewendet = [f for f in korrigiert if f.stelle not in uebersprungen]
    ergebnis.update(
        lief=True, geprueft=roh["geprueft"], markiert=markiere_offen,
        korrigiert=[{"stelle": f.stelle, "korrektur": f.korrektur, "quelle": f.quelle, "urteil": f.urteil}
                    for f in angewendet],
        offen=[{"stelle": f.stelle, "grund": f.grund} for f in offen])
    for f in ergebnis["korrigiert"]:
        _logzeile(log, f"{pfad.name}: korrigiert: {f['stelle']!r} → {f['korrektur']!r} ({f['quelle'] or 'nicht belegbar'})")
    return ergebnis
