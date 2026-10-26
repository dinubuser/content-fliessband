import json
import re

from lib.komposition import baue_komposition
from lib.reel_modell import Aufnahme, Bild, Grafik, Reel, Szene, Wort
from lib.zeitplan import plane


def _daten(tmp_path):
    reel = Reel([Szene(1, True, "Keine Zeit? Kenn ich.", "Keine Zeit? Kenn ich."),
                 Szene(2, False, "Du startest mit Übungsgeld.", "Schritt 1: Demokonto",
                       Grafik("vergleich", ["Übungsgeld", "Haushaltsbudget"]))], "Caption")
    ton = tmp_path / "ton_quelle"
    ton.mkdir()
    a = []
    for nr, woerter in [(1, ["Keine", "Zeit?", "Kenn", "ich."]), (2, ["Du", "startest", "mit", "Übungsgeld."])]:
        mp3 = ton / f"szene-{nr:02d}.mp3"
        mp3.write_bytes(b"x")
        a.append(Aufnahme(nr, mp3, 2.0, [Wort(w, i * 0.4, i * 0.4 + 0.3) for i, w in enumerate(woerter)]))
    bett = ton / "bett.wav"
    bett.write_bytes(b"x")
    return reel, a, plane(a), bett


def test_ordner_und_dateien(tmp_path):
    reel, a, plan, bett = _daten(tmp_path)
    ziel = baue_komposition(reel, a, plan, {1: 1.0, 2: 0.9}, bett, tmp_path / "komp")
    for name in ["index.html", "daten.js", "gsap.min.js", "stil.css",
                 "fonts/InterVariable.ttf", "ton/szene-01.mp3", "ton/szene-02.mp3", "ton/bett.wav"]:
        assert (ziel / name).exists(), name


def test_root_und_clips(tmp_path):
    reel, a, plan, bett = _daten(tmp_path)
    ziel = baue_komposition(reel, a, plan, {1: 1.0, 2: 0.9}, bett, tmp_path / "komp")
    h = (ziel / "index.html").read_text(encoding="utf-8")
    assert 'data-composition-id="reel"' in h
    assert f'data-duration="{plan.gesamt}"' in h
    assert re.search(r'class="szene clip" id="sz-2"[^>]*data-start="2.35"', h)
    assert 'style="--s:0.9"' in h
    assert re.search(r'src="ton/szene-02.mp3" data-start="2.35"', h)
    assert 'src="ton/bett.wav"' in h
    assert 'id="hk-0"' in h and 'id="ut-0-0"' in h
    assert "Haushaltsbudget" in h
    # Zeitleiste steht inline, sonst findet der statische Lint von hyperframes die Registrierung nicht
    assert 'window.__timelines["reel"] = tl;' in h
    assert '<script src="zeitleiste.js">' not in h


def test_daten_js(tmp_path):
    reel, a, plan, bett = _daten(tmp_path)
    ziel = baue_komposition(reel, a, plan, {1: 1.0, 2: 1.0}, bett, tmp_path / "komp")
    roh = (ziel / "daten.js").read_text(encoding="utf-8")
    d = json.loads(roh.removeprefix("window.REEL = ").removesuffix(";\n"))
    assert d["gesamt"] == plan.gesamt
    assert [g["index"] for g in d["hook"]] == [0, 1]
    assert d["ut"][0]["woerter"][0]["start"] == plan.szenen[1].start
    assert all(g["start"] >= plan.szenen[1].start for g in d["ut"])


def _daten_mit_bild(tmp_path):
    reel, a, _, bett = _daten(tmp_path)
    reel.szenen[1].bild = Bild("winkt", ["uhr"])       # Szene 2 hat eine Grafik
    reel.szenen.append(Szene(3, False, "Dann der Notgroschen.", "Notgroschen zuerst",
                             bild=Bild("zeigt", ["waage", "notgroschen"])))
    mp3 = tmp_path / "ton_quelle" / "szene-03.mp3"
    mp3.write_bytes(b"x")
    a.append(Aufnahme(3, mp3, 2.0, [Wort(w, i * 0.4, i * 0.4 + 0.3)
                                    for i, w in enumerate(["Dann", "der", "Notgroschen."])]))
    return reel, a, plane(a), bett


def test_figurenszene_im_markup(tmp_path):
    reel, a, plan, bett = _daten_mit_bild(tmp_path)
    ziel = baue_komposition(reel, a, plan, {1: 1.0, 2: 1.0, 3: 1.0}, bett, tmp_path / "komp")
    h = (ziel / "index.html").read_text(encoding="utf-8")
    sz1 = h[h.index('id="sz-1"'):h.index('id="sz-2"')]
    sz2 = h[h.index('id="sz-2"'):h.index('id="sz-3"')]
    sz3 = h[h.index('id="sz-3"'):h.index("</section>", h.index('id="sz-3"'))]
    assert "figur" not in sz1                                        # Hook ohne Figur
    assert re.search(r'class="szene clip" id="sz-2"', h)              # mit Grafik: oberer Block bleibt hoch
    assert '<div class="figur klein">' in sz2 and "platz-1" not in sz2
    assert re.search(r'class="szene clip mit-figur" id="sz-3"', h)
    assert '<div class="figur">' in sz3 and "platz-2" in sz3
    # figuren.js steht inline vor der Zeitleiste
    assert h.index("window.FIGUREN") < h.index('window.__timelines["reel"] = tl;')


def test_figurdaten_in_daten_js(tmp_path):
    reel, a, plan, bett = _daten_mit_bild(tmp_path)
    ziel = baue_komposition(reel, a, plan, {1: 1.0, 2: 1.0, 3: 1.0}, bett, tmp_path / "komp")
    roh = (ziel / "daten.js").read_text(encoding="utf-8")
    d = json.loads(roh.removeprefix("window.REEL = ").removesuffix(";\n"))
    s1, s2, s3 = d["szenen"]
    assert s1["figur"] is None
    assert s2["figur"]["haltung"]["name"] == "zeigt" and s2["figur"]["gegenstaende"] == []
    assert [g["name"] for g in s3["figur"]["gegenstaende"]] == ["waage", "notgroschen"]
