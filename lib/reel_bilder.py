"""Markup einer Reel-Szene, Schriftgrösse wählen (Playwright misst Überlauf) und Titelbild rendern."""
import html
import re
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

from lib.figuren import figur_html, hat_figur
from lib.reel_modell import Grafik, Szene
from lib.reel_renderer import RenderFehler
from lib.konfig import wert
from lib.renderer import ZuLangFehler  # noqa: F401 (ZuLangFehler wird weitergereicht)

VORLAGE_ORDNER = Path(__file__).resolve().parent.parent / "vorlagen" / "reel-a"
SCHRIFT = Path(__file__).resolve().parent.parent / "vorlagen" / "karussell-a" / "fonts" / "InterVariable.ttf"
# Eigener Familienname wie in stil.css: sonst ersetzt HyperFrames "Inter" durch Google-Fonts-Dateien,
# und Messen und Rendern liefen mit verschiedenen Schriften.
SCHRIFT_FAMILIE = "InterLokal"
SCHRIFT_GELADEN_JS = f"""() => [...document.fonts].some(
  f => f.family.replace(/"/g, '') === '{SCHRIFT_FAMILIE}' && f.status === 'loaded')"""
HANDLE = wert("FLIESSBAND_HANDLE", "@dein.konto")
BREITE, HOEHE = 1080, 1920
SKALEN = [1.0, 0.9, 0.8, 0.7]
# Lange Komposita (z.B. «Altersvorsorgeplanung») dürfen kleiner werden, statt den Bau abzubrechen.
SKALEN_EINBLENDUNG = SKALEN + [0.6]
SKALEN_HOOK = SKALEN + [0.6, 0.5]

PASST_JS = """(sel) => [...document.querySelectorAll(sel)].every(
  e => e.scrollHeight <= e.clientHeight + 1 && e.scrollWidth <= e.clientWidth + 1)"""


def kern(wort: str) -> str:
    return re.sub(r"[^\w']", "", wort).lower()


def markiere(text: str, schluessel: set[str]) -> str:
    """Escaped Text; Wörter aus 'schluessel' mit mindestens 4 Buchstaben werden orange."""
    teile = []
    for w in text.split():
        e = html.escape(w)
        teile.append(f'<span class="hl">{e}</span>' if len(kern(w)) >= 4 and kern(w) in schluessel else e)
    return " ".join(teile)


def grafik_html(g: Grafik | None) -> str:
    if g is None:
        return ""
    t = [html.escape(x) for x in g.teile]
    if g.art == "zahl":
        inner = f'<div class="kachel">{t[0]}</div><div class="pfeil">↓</div><div class="kachel orange">{t[1]}</div>'
    elif g.art == "vergleich":
        inner = f'<div class="kachel orange">{t[0]}</div><div class="statt">statt</div><div class="kachel">{t[1]}</div>'
    else:
        inner = "".join(f'<div class="punkt"><div class="marke">{i}</div><div>{x}</div></div>'
                        for i, x in enumerate(t, 1))
    return f'<div class="grafik grafik-{g.art}">{inner}</div>'


def szene_html(s: Szene, skala: float, hook_gruppen: list[str] | None = None,
               szenen_attr: str = "", ut_html: str = "") -> str:
    """Markup einer Szene. Die Komposition gibt data-Attribute (szenen_attr) und Untertitel mit."""
    if s.hook:
        schluessel = {kern(w) for w in s.einblendung.split()}
        gruppen = "".join(f'<div class="hookgruppe" id="hk-{i}">{markiere(g, schluessel)}</div>'
                          for i, g in enumerate(hook_gruppen or [s.sprechtext]))
        oben = f'<div class="hook">{gruppen}</div>'
    else:
        oben = (f'<div class="oben"><div class="balken"></div>'
                f'<div class="einblendung">{html.escape(s.einblendung)}</div>{grafik_html(s.grafik)}</div>')
    figur = figur_html(s.bild, mit_grafik=s.grafik is not None) if hat_figur(s) else ""
    klasse = "szene mit-figur" if figur and s.grafik is None else "szene"
    hinweis = f'<div class="hinweis">{html.escape(s.hinweis)}</div>' if s.hinweis else ""
    return (f'<section class="{klasse}" id="sz-{s.nummer}" style="--s:{skala}" {szenen_attr}>'
            f'{oben}{figur}{ut_html}{hinweis}<div class="fuss">{HANDLE}</div></section>')


def _seite(body: str) -> str:
    css = (VORLAGE_ORDNER / "stil.css").as_uri()
    return (f'<!doctype html><html lang="de-CH"><head><meta charset="utf-8">'
            f'<link rel="stylesheet" href="{css}">'
            f'<style>@font-face{{font-family:"{SCHRIFT_FAMILIE}";src:url("{SCHRIFT.as_uri()}") format("truetype");'
            f'font-weight:100 900}}</style></head><body><div id="root">{body}</div></body></html>')


def _laden(seite, html_text: str, ordner: Path) -> None:
    datei = ordner / "_messen.html"
    datei.write_text(html_text, encoding="utf-8")
    seite.goto(datei.as_uri())
    seite.evaluate("document.fonts.ready.then(() => true)")
    if not seite.evaluate(SCHRIFT_GELADEN_JS):
        raise RenderFehler(f"Schrift {SCHRIFT_FAMILIE} wurde nicht geladen (vorlagen/karussell-a/fonts/)")


def _passt(seite, s: Szene, skala: float, gruppen: list[str], ordner: Path) -> bool:
    if not s.hook:
        _laden(seite, _seite(szene_html(s, skala)), ordner)
        return seite.evaluate(PASST_JS, ".oben")
    # Hook-Gruppen erscheinen nacheinander, also jede einzeln messen
    for g in gruppen:
        _laden(seite, _seite(szene_html(s, skala, [g])), ordner)
        if not seite.evaluate(PASST_JS, ".hook"):
            return False
    return True


def waehle_skalen(szenen: list[Szene], hook_gruppen: dict[int, list[str]]) -> dict[int, float]:
    """Grösste Schriftstufe pro Szene, bei der nichts überläuft. Sonst ZuLangFehler mit Szene."""
    ergebnis = {}
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            seite = browser.new_page(viewport={"width": BREITE, "height": HOEHE})
            for s in szenen:
                gruppen = hook_gruppen.get(s.nummer, [s.sprechtext])
                skalen = SKALEN_HOOK if s.hook else SKALEN_EINBLENDUNG
                skala = next((k for k in skalen if _passt(seite, s, k, gruppen, Path(tmp))), None)
                if skala is None:
                    raise ZuLangFehler(f"Szene {s.nummer}: Text passt auch bei kleinster Schrift nicht")
                ergebnis[s.nummer] = skala
        finally:
            browser.close()
    return ergebnis


def rendere_cover(einblendung: str, ziel: Path) -> Path:
    ziel.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            seite = browser.new_page(viewport={"width": BREITE, "height": HOEHE})
            for skala in SKALEN_EINBLENDUNG:
                body = (f'<section class="szene cover" style="--s:{skala}"><div class="oben">'
                        f'<div class="balken"></div><div class="einblendung">{html.escape(einblendung)}</div>'
                        f'</div><div class="fuss">{HANDLE}</div></section>')
                _laden(seite, _seite(body), ziel.parent)
                if seite.evaluate(PASST_JS, ".oben"):
                    seite.screenshot(path=str(ziel))
                    return ziel
            raise ZuLangFehler("Titelbild: Hook-Einblendung passt nicht")
        finally:
            browser.close()
            (ziel.parent / "_messen.html").unlink(missing_ok=True)
