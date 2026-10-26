"""Feste Prüfungen vor dem Rendern: Schreibweise, Platzhalter, Risikohinweis."""
import re
from pathlib import Path

from lib.modell import Beitrag
from lib.reel_modell import Reel

RISIKO_STANDARD = "Trading birgt Verlustrisiken. Keine Anlageberatung."
START = re.compile(r"\bSTART\b")   # Etappe 9: Stichwort der Einladung, ganzes Wort in Grossbuchstaben
START_STANDARD = "Kommentiere START, dann erzähl ich dir mehr."

TRADING_WOERTER = re.compile(r"trading|trade|börse", re.IGNORECASE)
RISIKO_MARKER = re.compile(r"verlustrisik", re.IGNORECASE)
PLATZHALTER = re.compile(r"\[[^\]]+\]")
SATZZEICHEN = re.compile(r"^(\W*)(.*?)(\W*)$")
STRICH = re.compile(r"[–—]")
STRICH_ZAHLEN = re.compile(r"(\d)[ \t]*[–—][ \t]*(\d)")
STRICH_ZEILENANFANG = re.compile(r"^[ \t]*[–—][ \t]*", re.MULTILINE)
STRICH_VOR_ENDE = re.compile(r"[ \t]*[–—][ \t]*(?=[.,!?:;]|$)", re.MULTILINE)
STRICH_TEXT = re.compile(r"[ \t]*[–—][ \t]*")


def korrigiere_schreibweise(text: str) -> tuple[str, int]:
    """ß → ss, Gedankenstrich → 'bis' (zwischen Zahlen), weg (Zeilenanfang, vor Satzzeichen/Zeilenende) oder Komma. Gibt (text, anzahl) zurück."""
    anzahl = text.count("ß") + len(STRICH.findall(text))
    neu = text.replace("ß", "ss")
    neu = STRICH_ZAHLEN.sub(r"\1 bis \2", neu)
    neu = STRICH_ZEILENANFANG.sub("", neu)
    neu = STRICH_VOR_ENDE.sub("", neu)
    neu = STRICH_TEXT.sub(", ", neu)
    return neu, anzahl


def _vor_hashtags_einfuegen(caption: str, satz: str) -> str:
    zeilen = caption.rstrip().splitlines()
    i = len(zeilen)
    while i > 0 and zeilen[i - 1].lstrip().startswith("#"):
        i -= 1
    if i < len(zeilen):
        block = "\n".join(z.rstrip() for z in zeilen[i:])
        return "\n".join(zeilen[:i]).rstrip() + f"\n\n{satz}\n\n" + block
    return caption.rstrip() + f"\n\n{satz}"


def ergaenze_start(caption: str) -> tuple[str, bool]:
    """Etappe 9: Fehlt START in der Caption, kommt der Standardsatz vor die Hashtags. Liefert (caption, ergänzt)."""
    if START.search(caption):
        return caption, False
    return _vor_hashtags_einfuegen(caption, START_STANDARD), True


def pruefe(beitrag: Beitrag) -> dict:
    """Korrigiert den Beitrag direkt und liefert das Feld 'pruefungen' fürs Manifest."""
    korrekturen = 0
    for s in beitrag.slides:
        s.ueberschrift, a = korrigiere_schreibweise(s.ueberschrift)
        korrekturen += a
        s.text, a = korrigiere_schreibweise(s.text)
        korrekturen += a
    beitrag.caption, a = korrigiere_schreibweise(beitrag.caption)
    korrekturen += a

    platzhalter = []
    for s in beitrag.slides:
        for fund in PLATZHALTER.findall(f"{s.ueberschrift} {s.text}"):
            platzhalter.append(f"Slide {s.nummer}: {fund}")
    for fund in PLATZHALTER.findall(beitrag.caption):
        platzhalter.append(f"Caption: {fund}")

    alles = " ".join([f"{s.ueberschrift} {s.text}" for s in beitrag.slides] + [beitrag.caption])
    trading = bool(TRADING_WOERTER.search(alles))
    ergaenzt = []
    if trading:
        letzte = beitrag.slides[-1]
        if not RISIKO_MARKER.search(f"{letzte.ueberschrift} {letzte.text}"):
            letzte.hinweis = RISIKO_STANDARD
            ergaenzt.append("slide")
        if not RISIKO_MARKER.search(beitrag.caption):
            beitrag.caption = _vor_hashtags_einfuegen(beitrag.caption, RISIKO_STANDARD)
            ergaenzt.append("caption")

    letzte = beitrag.slides[-1]
    start_schluss_fehlt = not START.search(f"{letzte.ueberschrift} {letzte.text}")
    beitrag.caption, start_ergaenzt = ergaenze_start(beitrag.caption)
    return {
        "risikohinweis": trading,
        "start_ergaenzt": start_ergaenzt,
        "start_schluss_fehlt": start_schluss_fehlt,
        "risikohinweis_ergaenzt": ergaenzt,
        "platzhalter": platzhalter,
        "schreibweise_korrekturen": korrekturen,
    }


class AusspracheFehler(Exception):
    pass


def lade_aussprache(pfad: Path) -> dict[str, str]:
    """Liest 'Wort → Ersatz' pro Zeile. Leerzeilen und #-Kommentare werden übersprungen."""
    liste = {}
    for nr, zeile in enumerate(Path(pfad).read_text(encoding="utf-8").splitlines(), 1):
        z = zeile.strip()
        if not z or z.startswith("#"):
            continue
        teile = [t.strip() for t in z.split("→")]
        if len(teile) != 2 or any(len(t.split()) != 1 for t in teile):
            raise AusspracheFehler(f"aussprache.txt Zeile {nr}: erwartet 'Wort → Ersatz' mit je einem Wort")
        if any(SATZZEICHEN.match(t).group(2) != t for t in teile):
            raise AusspracheFehler(f"aussprache.txt Zeile {nr}: Wort und Ersatz ohne Satzzeichen am Anfang oder Ende")
        liste[teile[0]] = teile[1]
    return liste


def sprechbar(text: str, liste: dict[str, str]) -> str:
    """Ersetzt ganze Wörter gemäss Aussprache-Liste, Satzzeichen bleiben stehen. Wortzahl bleibt gleich."""
    neu = []
    for token in text.split():
        vor, kern, nach = SATZZEICHEN.match(token).groups()
        neu.append(f"{vor}{liste.get(kern, kern)}{nach}")
    return " ".join(neu)


def pruefe_reel(reel: Reel) -> dict:
    """Wie pruefe() fürs Karussell: korrigiert das Reel direkt, liefert 'pruefungen' fürs Manifest."""
    korrekturen = 0
    for s in reel.szenen:
        s.sprechtext, a = korrigiere_schreibweise(s.sprechtext)
        korrekturen += a
        s.einblendung, a = korrigiere_schreibweise(s.einblendung)
        korrekturen += a
        if s.grafik:
            for i, teil in enumerate(s.grafik.teile):
                s.grafik.teile[i], a = korrigiere_schreibweise(teil)
                korrekturen += a
    reel.caption, a = korrigiere_schreibweise(reel.caption)
    korrekturen += a

    def felder(s):
        return [s.sprechtext, s.einblendung] + (s.grafik.teile if s.grafik else [])

    platzhalter = []
    for s in reel.szenen:
        for fund in PLATZHALTER.findall(" ".join(felder(s))):
            platzhalter.append(f"Szene {s.nummer}: {fund}")
    for fund in PLATZHALTER.findall(reel.caption):
        platzhalter.append(f"Caption: {fund}")

    alles = " ".join([" ".join(felder(s)) for s in reel.szenen] + [reel.caption])
    trading = bool(TRADING_WOERTER.search(alles))
    ergaenzt = []
    if trading:
        # Auf dem Bild immer, egal was gesprochen wird (Wörter wie «risikolos» täuschen)
        reel.szenen[-1].hinweis = RISIKO_STANDARD
        ergaenzt.append("szene")
        if not RISIKO_MARKER.search(reel.caption):
            reel.caption = _vor_hashtags_einfuegen(reel.caption, RISIKO_STANDARD)
            ergaenzt.append("caption")

    letzte_szene = reel.szenen[-1]
    start_schluss_fehlt = not START.search(f"{letzte_szene.sprechtext} {letzte_szene.einblendung}")
    reel.caption, start_ergaenzt = ergaenze_start(reel.caption)
    return {
        "risikohinweis": trading,
        "start_ergaenzt": start_ergaenzt,
        "start_schluss_fehlt": start_schluss_fehlt,
        "risikohinweis_ergaenzt": ergaenzt,
        "platzhalter": platzhalter,
        "schreibweise_korrekturen": korrekturen,
        "bild_hinweise": [h for s in reel.szenen for h in s.bild_hinweise],
    }
