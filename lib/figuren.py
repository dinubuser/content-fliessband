"""Baukasten der Reel-Figuren: Katalog lesen, SVGs inline einsetzen, Bewegungsdaten, Musterseite.
Der Katalog (vorlagen/reel-a/figuren/katalog.json) ist die einzige Quelle der erlaubten Namen."""
import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

from lib.reel_modell import Bild, Szene

ORDNER = Path(__file__).resolve().parent.parent / "vorlagen" / "reel-a" / "figuren"
VORLAGE = ORDNER.parent
PROJEKT = VORLAGE.parent.parent
SCHRIFT = PROJEKT / "vorlagen" / "karussell-a" / "fonts" / "InterVariable.ttf"
GSAP = PROJEKT / "node_modules" / "gsap" / "dist" / "gsap.min.js"
BEWEGUNGEN = ("atmen", "zeigen", "winken", "wippen", "wachsen", "fallen", "drehen", "pulsieren")
STANDARD_HALTUNG = "steht"
HALTUNG_BEI_GRAFIK = "zeigt"
MAX_GEGENSTAENDE = 2


class FigurenFehler(Exception):
    """Fehler im Baukasten selbst (Katalog oder SVG), nie im Skript."""


@lru_cache(maxsize=1)
def katalog() -> dict:
    pfad = ORDNER / "katalog.json"
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
        return {"haltungen": dict(daten["haltungen"]), "gegenstaende": dict(daten["gegenstaende"])}
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
        raise FigurenFehler(f"{pfad} nicht lesbar: {e}") from None


def haltungen() -> list[str]:
    return list(katalog()["haltungen"])


def gegenstaende() -> list[str]:
    return list(katalog()["gegenstaende"])


def namen_text() -> str:
    """Erlaubte Namen für den Auftrag an den Content-Agenten."""
    return f"Haltungen: {', '.join(haltungen())}\nGegenstände: {', '.join(gegenstaende())}"


def _eintrag(art: str, name: str) -> dict:
    try:
        return katalog()[art][name]
    except KeyError:
        raise FigurenFehler(f"unbekannte Figur {art}/{name}") from None


ID = re.compile(r'\sid="([^"]+)"')


@lru_cache(maxsize=None)
def svg_inline(art: str, name: str) -> str:
    """SVG ohne XML-Kopf. Jede id wird zu data-teil, damit mehrere Szenen dieselben Teile zeigen dürfen."""
    pfad = ORDNER / _eintrag(art, name)["datei"]
    try:
        text = pfad.read_text(encoding="utf-8")
        ET.fromstring(text)
    except (OSError, ET.ParseError) as e:
        raise FigurenFehler(f"Figur {name}: {pfad.name} ungültig ({e})") from None
    text = re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", text)
    return ID.sub(r' data-teil="\1"', text).strip()


def hat_figur(s: Szene) -> bool:
    return not s.hook and s.bild is not None


def _auswahl(bild: Bild, mit_grafik: bool) -> tuple[str, list[str]]:
    # Neben einer Grafik zeigt Figur klein auf die Grafik, ohne Gegenstände
    if mit_grafik:
        return HALTUNG_BEI_GRAFIK, []
    return bild.haltung, bild.gegenstaende


def figur_html(bild: Bild, mit_grafik: bool) -> str:
    haltung, dinge = _auswahl(bild, mit_grafik)
    teile = [f'<div class="haltung">{svg_inline("haltungen", haltung)}</div>']
    teile += [f'<div class="gegenstand platz-{i}">{svg_inline("gegenstaende", g)}</div>'
              for i, g in enumerate(dinge, 1)]
    klasse = "figur klein" if mit_grafik else "figur"
    return f'<div class="{klasse}">{"".join(teile)}</div>'


def _bewegung(art: str, name: str) -> dict:
    e = _eintrag(art, name)
    return {"name": name, "bewegung": e["bewegung"], "teile": list(e["teile"]), "ursprung": e["ursprung"]}


def figur_daten(bild: Bild, mit_grafik: bool) -> dict:
    """Bewegungsdaten für daten.js (liest figuren.js)."""
    haltung, dinge = _auswahl(bild, mit_grafik)
    return {"haltung": _bewegung("haltungen", haltung),
            "gegenstaende": [_bewegung("gegenstaende", g) for g in dinge]}


MUSTER_CSS = """
@font-face { font-family: "InterLokal"; src: url("%s") format("truetype"); font-weight: 100 900; }
body { margin: 0; padding: 40px; background: #F8F6F2; color: #0B111E; font-family: "InterLokal", sans-serif; }
h1 { font-size: 28px; margin: 0 0 70px; }
.raster { display: flex; flex-wrap: wrap; gap: 70px; }
.zelle { margin: 0; }
.box { width: 200px; height: 200px; }
.haltungen .box { height: 300px; }
.box svg { display: block; width: 100%%; height: 100%%; overflow: visible; }
figcaption { margin-top: 40px; font-size: 18px; text-align: center; }
"""


def musterseite_html(bewegt: bool = True, schrift: str = "fonts/InterVariable.ttf") -> str:
    """Alle Haltungen und Gegenstände auf einer Seite: bewegt für die Abnahme durch den Betreiber, still für den Render-Test."""
    zellen = []
    for art in ("haltungen", "gegenstaende"):
        for name in katalog()[art]:
            zellen.append(f'<figure class="zelle {art}" data-art="{art}" data-name="{name}">'
                          f'<div class="box">{svg_inline(art, name)}</div><figcaption>{name}</figcaption></figure>')
    skript = ""
    if bewegt:
        daten = {art: {n: _bewegung(art, n) for n in katalog()[art]} for art in ("haltungen", "gegenstaende")}
        figuren_js = (VORLAGE / "figuren.js").read_text(encoding="utf-8")
        skript = f"""<script src="gsap.min.js"></script>
<script>{figuren_js}
var M = {json.dumps(daten, ensure_ascii=False)};
var tl = gsap.timeline({{ repeat: -1 }});
document.querySelectorAll(".zelle").forEach(function (z) {{
  var f = M[z.dataset.art][z.dataset.name];
  if (z.dataset.art === "haltungen") FIGUREN.bewege(tl, z, FIGUREN.KOERPER, 0, 6);
  FIGUREN.bewege(tl, z, f, 0.3, 5.7);
}});
tl.set({{}}, {{}}, 6);
</script>"""
    return (f'<!doctype html><html lang="de-CH"><head><meta charset="utf-8"><title>Figuren-Baukasten</title>'
            f'<style>{MUSTER_CSS % schrift}</style></head><body><h1>Figuren-Baukasten: '
            f'{len(haltungen())} Haltungen, {len(gegenstaende())} Gegenstände</h1>'
            f'<div class="raster">{"".join(zellen)}</div>{skript}</body></html>')


def schreibe_musterseite(ordner: Path) -> Path:
    ordner = Path(ordner)
    (ordner / "fonts").mkdir(parents=True, exist_ok=True)
    shutil.copy(SCHRIFT, ordner / "fonts" / "InterVariable.ttf")
    shutil.copy(GSAP, ordner / "gsap.min.js")
    index = ordner / "index.html"
    index.write_text(musterseite_html(bewegt=True), encoding="utf-8")
    return index


if __name__ == "__main__":
    print(schreibe_musterseite(Path(sys.argv[1]).expanduser()))
