"""Rendert Slides mit headless Chromium als PNG (1080 × 1350)."""
from pathlib import Path

from playwright.sync_api import sync_playwright

from lib.modell import Slide
from lib.vorlage import baue_html

BREITE, HOEHE = 1080, 1350
SKALEN = [1.0, 0.9, 0.8, 0.7]

PASST_JS = """() => {
  const e = document.querySelector('.inhalt');
  return e.scrollHeight <= e.clientHeight && e.scrollWidth <= e.clientWidth;
}"""
INTER_GELADEN_JS = """() => [...document.fonts].some(
  f => f.family.replace(/"/g, '') === 'Inter' && f.status === 'loaded')"""


class ZuLangFehler(Exception):
    pass


def _rendere_eine(seite, slide: Slide, gesamt: int, ziel: Path) -> Path:
    html_datei = ziel / f"_slide-{slide.nummer:02d}.html"
    try:
        for skala in SKALEN:
            html_datei.write_text(baue_html(slide, gesamt, skala), encoding="utf-8")
            seite.goto(html_datei.as_uri())
            seite.evaluate("document.fonts.ready.then(() => true)")
            if not seite.evaluate(INTER_GELADEN_JS):
                raise RuntimeError("Schrift Inter wurde nicht geladen (vorlagen/karussell-a/fonts/)")
            if seite.evaluate(PASST_JS):
                png = ziel / f"slide-{slide.nummer:02d}.png"
                seite.screenshot(path=str(png))
                return png
        raise ZuLangFehler(f"Slide {slide.nummer}: Text passt auch bei kleinster Schrift nicht")
    finally:
        html_datei.unlink(missing_ok=True)


def rendere_slides(slides: list[Slide], ziel: Path) -> list[Path]:
    ziel.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            seite = browser.new_page(viewport={"width": BREITE, "height": HOEHE})
            return [_rendere_eine(seite, s, len(slides), ziel) for s in slides]
        finally:
            browser.close()
