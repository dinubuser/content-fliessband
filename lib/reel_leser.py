"""Liest ein Reel-Skript der Social-Media-Agentur (Abschnitt '## Szenen fürs Fliessband')."""
import re
from pathlib import Path

from lib.figuren import MAX_GEGENSTAENDE, STANDARD_HALTUNG, gegenstaende, haltungen
from lib.leser import LeserFehler, abschnitt, caption_text
from lib.reel_modell import Bild, Grafik, Reel, Szene

SZENE_KOPF = re.compile(r"^\*\*Szene (\d+)(?: \([^)]*\))?\*\*")
FELDER = ("Sprechtext", "Einblendung", "Grafik", "Bild")
FELD_ETIKETT = re.compile(r"^[A-ZÄÖÜa-zäöü][\w-]*:")
GRAFIK_TEILE = {"zahl": (2, 2), "vergleich": (2, 2), "liste": (2, 3)}
MAX_EINBLENDUNG = 6


def _sieht_aus_wie_kopf(s):
    return (s.startswith("**Szene") or re.match(r"Szene \d", s) is not None
            or (s.startswith("#") and "Szene" in s))


def _bloecke(zeilen):
    bloecke = []
    for z in zeilen:
        s = z.strip()
        m = SZENE_KOPF.match(s)
        if m:
            bloecke.append((int(m.group(1)), []))
        elif _sieht_aus_wie_kopf(s):
            raise LeserFehler(f"Szenen-Kopf nicht erkannt: '{s}' (erwartet **Szene N** oder **Szene N (Bezeichnung)**)")
        elif bloecke:
            bloecke[-1][1].append(z)
    return bloecke


def _grafik(nummer, wert):
    teile = [t.strip() for t in wert.split("|")]
    art, rest = teile[0].lower(), teile[1:]
    if not all(rest):
        raise LeserFehler(f"Szene {nummer}: Grafik hat einen leeren Teil")
    if art not in GRAFIK_TEILE:
        raise LeserFehler(f"Szene {nummer}: unbekannte Grafik '{art}' (erlaubt: zahl, vergleich, liste)")
    mini, maxi = GRAFIK_TEILE[art]
    if not mini <= len(rest) <= maxi:
        anzahl = f"{mini}" if mini == maxi else f"{mini} bis {maxi}"
        raise LeserFehler(f"Szene {nummer}: Grafik '{art}' braucht {anzahl} Teile, hat {len(rest)}")
    return Grafik(art=art, teile=rest)


UMLAUTE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue"})


def _name(text):
    """Vergleichsform eines Haltungs- oder Gegenstandsnamens: klein, ohne Umlaute, Leerraum als '-'."""
    return "-".join(text.strip().lower().translate(UMLAUTE).split())


def _bild(nummer, wert):
    """Einziger toleranter Teil des Lesers: ersetzt falsche Angaben, meldet sie und bricht nie ab."""
    if wert is None:
        return Bild(STANDARD_HALTUNG, []), [f"Szene {nummer}: keine Zeile 'Bild:', Figur steht"]
    hinweise = []
    teile = [_name(t) for t in re.split(r"[|,/]", wert)]
    haltung, rest = teile[0], [t for t in teile[1:] if t]
    if haltung not in haltungen():
        grund = f"'{haltung}' unbekannt" if haltung else "fehlt"
        hinweise.append(f"Szene {nummer}: Haltung {grund}, Figur steht")
        haltung = STANDARD_HALTUNG
    bekannt = []
    for g in rest:
        if g in bekannt:
            hinweise.append(f"Szene {nummer}: Gegenstand '{g}' doppelt, weggelassen")
        elif g in gegenstaende():
            bekannt.append(g)
        else:
            hinweise.append(f"Szene {nummer}: Gegenstand '{g}' unbekannt, weggelassen")
    if len(bekannt) > MAX_GEGENSTAENDE:
        hinweise.append(f"Szene {nummer}: {len(bekannt)} Gegenstände, nur die ersten {MAX_GEGENSTAENDE} gezeigt")
        bekannt = bekannt[:MAX_GEGENSTAENDE]
    return Bild(haltung, bekannt), hinweise


def _szene(nummer, zeilen):
    felder, aktuell, doppelt = {}, None, []
    for z in zeilen:
        s = z.strip()
        if not s or s == "---":
            continue
        name = next((n for n in FELDER if s.startswith(f"{n}:")), None)
        if name is None and s[:5].lower() == "bild:":
            name = "Bild"  # nur Bild: Gross/klein egal, die Zeile schreibt ein LLM
        if name == "Bild" and name in felder:
            # Toleranz: die erste Bild-Zeile gilt, Folgezeilen der zweiten fallen weg
            doppelt.append(f"Szene {nummer}: 'Bild:' doppelt, erste genommen")
            felder["_verworfen"], aktuell = "", "_verworfen"
        elif name:
            if name in felder:
                raise LeserFehler(f"Szene {nummer}: '{name}:' doppelt")
            felder[name], aktuell = s[len(name) + 1:].strip(), name
        elif FELD_ETIKETT.match(s):
            raise LeserFehler(f"Szene {nummer}: unbekanntes Feld '{FELD_ETIKETT.match(s).group()}'")
        elif aktuell is None:
            raise LeserFehler(f"Szene {nummer}: Zeile ohne Feld: '{s}'")
        else:
            # Folgezeile gehört zum Feld darüber
            felder[aktuell] = f"{felder[aktuell]} {s}".strip()
    for pflicht in ("Sprechtext", "Einblendung"):
        if not felder.get(pflicht):
            raise LeserFehler(f"Szene {nummer}: '{pflicht}:' fehlt")
    woerter = len(felder["Einblendung"].split())
    if woerter > MAX_EINBLENDUNG:
        raise LeserFehler(f"Szene {nummer}: Einblendung hat {woerter} Wörter (höchstens {MAX_EINBLENDUNG})")
    if nummer == 1 and felder.get("Grafik"):
        raise LeserFehler("Szene 1: der Hook zeigt keine Grafik, bitte 'Grafik:' entfernen")
    grafik = _grafik(nummer, felder["Grafik"]) if felder.get("Grafik") else None
    if nummer == 1:
        # Der Hook zeigt nur die grossen Wörter, eine Bild-Zeile dort wird ignoriert
        bild, hinweise = None, []
    else:
        bild, hinweise = _bild(nummer, felder.get("Bild"))
        hinweise = doppelt + hinweise
    return Szene(nummer=nummer, hook=(nummer == 1), sprechtext=felder["Sprechtext"],
                 einblendung=felder["Einblendung"], grafik=grafik, bild=bild, bild_hinweise=hinweise)


def lese_reel(pfad: Path) -> Reel:
    zeilen = Path(pfad).read_text(encoding="utf-8").splitlines()

    szenen_zeilen = abschnitt(zeilen, "Szenen fürs Fliessband")
    if szenen_zeilen is None:
        raise LeserFehler("Abschnitt '## Szenen fürs Fliessband' fehlt")
    bloecke = _bloecke(szenen_zeilen)
    if not bloecke:
        raise LeserFehler("Keine Szenen gefunden (erwartet: **Szene N**)")
    for erwartet, (nummer, _) in enumerate(bloecke, 1):
        if nummer != erwartet:
            vorher = f"Szene {erwartet - 1}" if erwartet > 1 else "dem Anfang"
            raise LeserFehler(f"Szene {nummer} folgt auf {vorher}, erwartet Szene {erwartet}")

    caption_zeilen = abschnitt(zeilen, "Caption")
    if caption_zeilen is None:
        raise LeserFehler("Abschnitt '## Caption' fehlt")
    caption = caption_text(caption_zeilen)
    if not caption:
        raise LeserFehler("Abschnitt '## Caption' ist leer")

    return Reel(szenen=[_szene(n, b) for n, b in bloecke], caption=caption)
