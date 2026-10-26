"""Baut das HTML einer Slide im Look A."""
import html
import re
from pathlib import Path

from lib.konfig import wert
from lib.modell import Slide

VORLAGE_ORDNER = Path(__file__).resolve().parent.parent / "vorlagen" / "karussell-a"
HANDLE = wert("FLIESSBAND_HANDLE", "@dein.konto")


def _markiere(text: str) -> str:
    """==wort== → orange Hervorhebung (Text ist schon escaped)."""
    return re.sub(r"==(.+?)==", r'<span class="hl">\1</span>', text)


def _absaetze(text: str) -> str:
    return "<br>".join(html.escape(z) for z in text.split("\n"))


def baue_html(slide: Slide, gesamt: int, skala: float) -> str:
    css = (VORLAGE_ORDNER / "stil.css").as_uri()
    oben = {
        "hook": '<div class="balken"></div>',
        "schritt": f'<div class="nummer">{slide.schritt}</div>',
    }.get(slide.typ, "")
    text = f'<div class="text">{_markiere(_absaetze(slide.text))}</div>' if slide.text else ""
    hinweis = f'<div class="hinweis">{html.escape(slide.hinweis)}</div>' if slide.hinweis else ""
    rechts = "wischen →" if slide.typ == "hook" else f"{slide.nummer} / {gesamt}"
    return f"""<!doctype html>
<html lang="de-CH"><head><meta charset="utf-8">
<link rel="stylesheet" href="{css}">
</head><body>
<div class="slide typ-{slide.typ}" style="--s:{skala}">
  <div class="inhalt">
    {oben}
    <div class="titel">{_markiere(html.escape(slide.ueberschrift))}</div>
    {text}
    {hinweis}
  </div>
  <div class="fuss"><span>{HANDLE}</span><span>{rechts}</span></div>
</div>
</body></html>
"""
