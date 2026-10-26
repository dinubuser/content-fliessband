import subprocess

import pytest

from hilfen_medien import stille_mp3
from lib.komposition import baue_komposition
from lib.medien import video_info
from lib.musik import erzeuge_bett
from lib.reel_modell import Aufnahme, Bild, Grafik, Reel, Szene, Wort
from lib import reel_renderer
from lib.reel_renderer import RenderFehler, pruefe_komposition, pruefe_video, rendere
from lib.zeitplan import plane


def _komposition(tmp_path):
    reel = Reel([Szene(1, True, "Kein Geld? Kenn ich.", "Kein Geld? Kenn ich."),
                 Szene(2, False, "Du startest mit Übungsgeld.", "Schritt 1: Demokonto",
                       Grafik("liste", ["Demokonto", "Feste Zeiten"]), bild=Bild("steht", [])),
                 Szene(3, False, "Der Notgroschen bleibt.", "Notgroschen bleibt",
                       bild=Bild("zeigt", ["waage", "notgroschen"]))], "Caption")
    a = []
    for nr, woerter in [(1, ["Kein", "Geld?", "Kenn", "ich."]), (2, ["Du", "startest", "mit", "Übungsgeld."]),
                        (3, ["Der", "Notgroschen", "bleibt."])]:
        mp3 = stille_mp3(tmp_path / f"s{nr}.mp3", 1.6)
        a.append(Aufnahme(nr, mp3, 1.6, [Wort(w, 0.1 + i * 0.35, 0.4 + i * 0.35) for i, w in enumerate(woerter)]))
    plan = plane(a)
    bett = erzeuge_bett(plan.gesamt, [], tmp_path / "bett.wav", tmp_path / "keine-musik", 43)
    return baue_komposition(reel, a, plan, {1: 1.0, 2: 1.0, 3: 1.0}, bett, tmp_path / "komp"), plan


@pytest.mark.langsam
def test_check_ist_gruen(tmp_path):
    ordner, _ = _komposition(tmp_path)
    pruefe_komposition(ordner, tmp_path / "check.log")


@pytest.mark.langsam
def test_render_ergibt_mp4(tmp_path):
    ordner, plan = _komposition(tmp_path)
    mp4 = rendere(ordner, tmp_path / "reel.mp4", tmp_path / "render.log")
    b, h, d = video_info(mp4)
    assert (b, h) == (1080, 1920)
    assert d == pytest.approx(plan.gesamt, abs=0.5)


def test_pruefe_video_falsche_laenge(tmp_path):
    mp4 = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=white:s=1080x1920:d=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(mp4)], check=True)
    with pytest.raises(RenderFehler, match="Länge"):
        pruefe_video(mp4, erwartet=5.0)


@pytest.mark.langsam
def test_check_fehler_nennt_protokoll(tmp_path):
    kaputt = tmp_path / "kaputt"
    kaputt.mkdir()
    (kaputt / "index.html").write_text("<html><body>nichts</body></html>", encoding="utf-8")
    with pytest.raises(RenderFehler, match="check.log"):
        pruefe_komposition(kaputt, tmp_path / "check.log")


def _mp4(pfad, mit_ton):
    ton = ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-shortest", "-c:a", "aac"] if mit_ton else []
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=white:s=1080x1920:d=1",
                    *ton, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(pfad)], check=True)
    return pfad


def test_pruefe_video_ohne_ton(tmp_path):
    with pytest.raises(RenderFehler, match="Video ohne Ton"):
        pruefe_video(_mp4(tmp_path / "v.mp4", False), erwartet=1.0)


def test_pruefe_video_mit_ton_ist_ok(tmp_path):
    pruefe_video(_mp4(tmp_path / "v.mp4", True), erwartet=1.0)


@pytest.fixture
def _hyperframes(tmp_path, monkeypatch):
    fake = tmp_path / "hyperframes"
    fake.write_text("")
    monkeypatch.setattr(reel_renderer, "HYPERFRAMES", fake)
    return fake


@pytest.mark.parametrize("schritt", ["check", "render"])
def test_timeout_wird_zu_renderfehler(schritt, tmp_path, _hyperframes, monkeypatch):
    def langsam(*a, **k):
        raise subprocess.TimeoutExpired(a[0], k["timeout"])
    monkeypatch.setattr(reel_renderer.subprocess, "run", langsam)
    log = tmp_path / "x.log"
    with pytest.raises(RenderFehler, match=rf"{schritt}.*Zeit.*{log.name}"):
        if schritt == "check":
            pruefe_komposition(tmp_path, log)
        else:
            rendere(tmp_path, tmp_path / "r.mp4", log)


def test_timeouts_sind_gesetzt(tmp_path, _hyperframes, monkeypatch):
    gesehen = []

    def merke(befehl, **k):
        gesehen.append((befehl[1], k["timeout"]))
        return subprocess.CompletedProcess(befehl, 0)
    monkeypatch.setattr(reel_renderer.subprocess, "run", merke)
    pruefe_komposition(tmp_path, tmp_path / "x.log")
    (tmp_path / "r.mp4").write_bytes(b"x")
    rendere(tmp_path, tmp_path / "r.mp4", tmp_path / "x.log")
    assert gesehen == [("check", reel_renderer.CHECK_TIMEOUT), ("render", reel_renderer.RENDER_TIMEOUT)]
    assert reel_renderer.CHECK_TIMEOUT == 180 and reel_renderer.RENDER_TIMEOUT == 900


def test_log_behaelt_check_und_render(tmp_path, _hyperframes, monkeypatch):
    def schreibe(befehl, stdout, **k):
        stdout.write(f"ausgabe {befehl[1]}\n")
        return subprocess.CompletedProcess(befehl, 0)
    monkeypatch.setattr(reel_renderer.subprocess, "run", schreibe)
    log = tmp_path / "x.log"
    pruefe_komposition(tmp_path, log)
    (tmp_path / "r.mp4").write_bytes(b"x")
    rendere(tmp_path, tmp_path / "r.mp4", log)
    text = log.read_text(encoding="utf-8")
    assert "ausgabe check" in text and "ausgabe render" in text
    assert text.index("ausgabe check") < text.index("ausgabe render")
