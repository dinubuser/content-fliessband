"""Baut den HyperFrames-Projektordner fürs Reel: index.html + daten.js + feste Zeitleiste."""
import html
import json
import shutil
from pathlib import Path

from lib.figuren import figur_daten, hat_figur
from lib.reel_bilder import SCHRIFT, VORLAGE_ORDNER, szene_html
from lib.reel_modell import Aufnahme, Reel
from lib.zeitplan import Gruppe, Plan, gruppiere

PROJEKT = Path(__file__).resolve().parent.parent
GSAP = PROJEKT / "node_modules" / "gsap" / "dist" / "gsap.min.js"
UT = {"max_woerter": 5, "max_zeichen": 28, "brueche": ".?!:;"}
HOOK = {"max_woerter": 3, "max_zeichen": 18, "brueche": ".?!:;,"}
MUSIK_LAUTSTAERKE = 0.25


def hook_gruppen(aufnahmen: list[Aufnahme], plan: Plan) -> list[Gruppe]:
    """Wortgruppen der Hook-Szene (immer Szene 1)."""
    z = plan.szenen[0]
    return gruppiere(aufnahmen[0].woerter, versatz=z.start, ende=z.start + z.dauer, **HOOK)


def _ut_gruppen(reel: Reel, aufnahmen: list[Aufnahme], plan: Plan) -> list[tuple[int, Gruppe]]:
    """(Szenen-Nummer, Gruppe) für alle Szenen ausser dem Hook."""
    alle = []
    for s, a, z in zip(reel.szenen, aufnahmen, plan.szenen):
        if not s.hook:
            alle += [(s.nummer, g) for g in gruppiere(a.woerter, versatz=z.start, ende=z.start + z.dauer, **UT)]
    return alle


def _kopiere_dateien(aufnahmen: list[Aufnahme], bett: Path, ziel: Path) -> None:
    if not GSAP.exists():
        raise FileNotFoundError(f"{GSAP} fehlt, im Projektordner 'npm install' ausführen")
    (ziel / "fonts").mkdir(parents=True, exist_ok=True)
    (ziel / "ton").mkdir(exist_ok=True)
    shutil.copy(SCHRIFT, ziel / "fonts" / "InterVariable.ttf")
    shutil.copy(VORLAGE_ORDNER / "stil.css", ziel / "stil.css")
    shutil.copy(GSAP, ziel / "gsap.min.js")
    for a in aufnahmen:
        shutil.copy(a.datei, ziel / "ton" / f"szene-{a.nummer:02d}.mp3")
    shutil.copy(bett, ziel / "ton" / "bett.wav")


def baue_komposition(reel: Reel, aufnahmen: list[Aufnahme], plan: Plan, skalen: dict[int, float],
                     bett: Path, ziel: Path) -> Path:
    _kopiere_dateien(aufnahmen, bett, ziel)
    # Inline, weil der statische Lint von hyperframes nur index.html liest (window.__timelines)
    zeitleiste = "".join((VORLAGE_ORDNER / n).read_text(encoding="utf-8") for n in ("figuren.js", "zeitleiste.js"))
    hook = hook_gruppen(aufnahmen, plan)
    ut = _ut_gruppen(reel, aufnahmen, plan)

    szenen_html = []
    for s, z in zip(reel.szenen, plan.szenen):
        attr = f'data-start="{z.start}" data-duration="{z.dauer}" data-track-index="1"'
        zeilen = []
        for i, (nr, g) in enumerate(ut):
            if nr != s.nummer:
                continue
            woerter = " ".join(f'<span id="ut-{i}-{j}">{html.escape(w.wort)}</span>' for j, w in enumerate(g.woerter))
            zeilen.append(f'<div class="ut" id="ut-{i}">{woerter}</div>')
        ut_html = f'<div class="untertitel">{"".join(zeilen)}</div>' if zeilen else ""
        gruppen_text = [" ".join(w.wort for w in g.woerter) for g in hook] if s.hook else None
        markup = szene_html(s, skalen[s.nummer], gruppen_text, szenen_attr=attr, ut_html=ut_html)
        szenen_html.append(markup.replace('class="szene', 'class="szene clip', 1))

    audio = [f'<audio id="vo-{a.nummer}" src="ton/szene-{a.nummer:02d}.mp3" data-start="{z.start}" '
             f'data-track-index="{10 + a.nummer}" data-volume="1"></audio>'
             for a, z in zip(aufnahmen, plan.szenen)]
    audio.append(f'<audio id="musik" src="ton/bett.wav" data-start="0" data-duration="{plan.gesamt}" '
                 f'data-track-index="40" data-volume="{MUSIK_LAUTSTAERKE}"></audio>')

    (ziel / "index.html").write_text(f"""<!doctype html>
<html lang="de-CH">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=1080, height=1920">
<title>Reel</title>
<link rel="stylesheet" href="stil.css">
<script src="gsap.min.js"></script>
<script src="daten.js"></script>
</head>
<body>
<div id="root" data-composition-id="reel" data-start="0" data-width="1080" data-height="1920" data-duration="{plan.gesamt}">
{chr(10).join(szenen_html)}
{chr(10).join(audio)}
</div>
<script>
{zeitleiste}</script>
</body>
</html>
""", encoding="utf-8")

    daten = {
        "gesamt": plan.gesamt,
        "szenen": [{"nummer": s.nummer, "hook": s.hook, "start": z.start, "dauer": z.dauer,
                    "figur": figur_daten(s.bild, mit_grafik=s.grafik is not None) if hat_figur(s) else None}
                   for s, z in zip(reel.szenen, plan.szenen)],
        "hook": [{"index": i, "start": g.start, "ende": g.ende} for i, g in enumerate(hook)],
        "ut": [{"index": i, "start": g.start, "ende": g.ende, "woerter": [{"start": w.start} for w in g.woerter]}
               for i, (_, g) in enumerate(ut)],
    }
    (ziel / "daten.js").write_text(f"window.REEL = {json.dumps(daten, ensure_ascii=False)};\n", encoding="utf-8")
    return ziel
