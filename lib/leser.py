"""Liest einen Karussell-Beitrag der Social-Media-Agentur (Markdown)."""
import re
from pathlib import Path

from lib.modell import Beitrag, Slide


class LeserFehler(Exception):
    pass


SLIDE_KOPF = re.compile(r"^\*\*Slide (\d+)(?: \([^)]*\))?\*\*")
SCHRITT = re.compile(r"^(\d+)\.\s+(.*)$")


def abschnitt(zeilen, titel):
    """Zeilen unter '## titel' (auch '## titel (Zusatz)') bis zur nächsten '## '-Überschrift, sonst None."""
    kopf = re.compile(rf"## {re.escape(titel)}(?: \(.*\))?")
    for i, z in enumerate(zeilen):
        if kopf.fullmatch(z.strip()):
            rest = zeilen[i + 1:]
            for j, r in enumerate(rest):
                if r.startswith("## "):
                    return rest[:j]
            return rest
    return None


def caption_text(zeilen):
    """Caption aus den Zeilen des Abschnitts. Mit Codeblock: nur der Inhalt des ersten Blocks.
    Sonst der Abschnitt ohne '---'-Zeilen."""
    start = next((i for i, z in enumerate(zeilen) if z.strip().startswith("```")), None)
    if start is not None:
        inhalt = []
        for z in zeilen[start + 1:]:
            if z.strip().startswith("```"):
                break
            inhalt.append(z)
        return "\n".join(inhalt).strip()
    return "\n".join(z for z in zeilen if z.strip() != "---").strip()


def _slide_bloecke(zeilen):
    bloecke = []
    for z in zeilen:
        m = SLIDE_KOPF.match(z.strip())
        if m:
            bloecke.append((int(m.group(1)), []))
        elif bloecke:
            bloecke[-1][1].append(z)
    return bloecke


def _felder(nummer, zeilen):
    ueberschrift, text_zeilen, im_text, leer = None, [], False, False
    for z in zeilen:
        s = z.strip()
        if s.startswith("Überschrift:"):
            ueberschrift = s[len("Überschrift:"):].strip()
            im_text = False
        elif s.startswith("Text:"):
            text_zeilen = [s[len("Text:"):].strip()]
            im_text, leer = True, False
        elif s == "---":
            im_text = False
        elif not s:
            leer = im_text
        elif im_text:
            # Zeile nach einer Leerzeile beginnt einen neuen Absatz
            if leer:
                text_zeilen.append("")
                leer = False
            text_zeilen.append(s)
    if not ueberschrift:
        raise LeserFehler(f"Slide {nummer}: 'Überschrift:' fehlt")
    return ueberschrift, "\n".join(text_zeilen).strip()


def _typ(index, gesamt, ueberschrift):
    """Gibt (typ, titel, schritt) zurück. Schritt-Nummer wird vom Titel abgetrennt."""
    if index == 0:
        return "hook", ueberschrift, None
    if index == gesamt - 1:
        return "schluss", ueberschrift, None
    m = SCHRITT.match(ueberschrift)
    if m:
        return "schritt", m.group(2), int(m.group(1))
    return "text", ueberschrift, None


def lese_beitrag(pfad: Path) -> Beitrag:
    zeilen = Path(pfad).read_text(encoding="utf-8").splitlines()

    slide_zeilen = abschnitt(zeilen, "Slides")
    if slide_zeilen is None:
        raise LeserFehler("Abschnitt '## Slides' fehlt")
    bloecke = _slide_bloecke(slide_zeilen)
    if not bloecke:
        raise LeserFehler("Keine Slides gefunden (erwartet: **Slide N**)")

    caption_zeilen = abschnitt(zeilen, "Caption")
    if caption_zeilen is None:
        raise LeserFehler("Abschnitt '## Caption' fehlt")
    caption = caption_text(caption_zeilen)
    if not caption:
        raise LeserFehler("Abschnitt '## Caption' ist leer")

    slides = []
    for i, (nummer, block) in enumerate(bloecke):
        ueberschrift, text = _felder(nummer, block)
        typ, titel, schritt = _typ(i, len(bloecke), ueberschrift)
        slides.append(Slide(nummer=nummer, typ=typ, ueberschrift=titel, text=text, schritt=schritt))
    return Beitrag(slides=slides, caption=caption)
