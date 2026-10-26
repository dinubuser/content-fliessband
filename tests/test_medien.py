import subprocess

import pytest

from hilfen_medien import stille_mp3
from lib import medien
from lib.medien import MedienFehler, dauer, video_info


def test_dauer_mp3(tmp_path):
    mp3 = stille_mp3(tmp_path / "a.mp3", 1.5)
    assert dauer(mp3) == pytest.approx(1.5, abs=0.06)


def test_video_info(tmp_path):
    mp4 = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=white:s=1080x1920:d=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(mp4)], check=True)
    assert video_info(mp4) == (1080, 1920, pytest.approx(1.0, abs=0.05))


def test_fehlende_datei(tmp_path):
    with pytest.raises(MedienFehler):
        dauer(tmp_path / "gibtsnicht.mp3")


@pytest.mark.parametrize("format_", [{}, {"duration": "N/A"}])
def test_dauer_fehlt_oder_unlesbar(monkeypatch, tmp_path, format_):
    monkeypatch.setattr(medien, "_probe", lambda p: {"format": format_, "streams": []})
    with pytest.raises(MedienFehler, match="Dauer"):
        dauer(tmp_path / "a.mp3")


@pytest.mark.parametrize("format_", [{}, {"duration": "N/A"}])
def test_video_info_dauer_fehlt(monkeypatch, tmp_path, format_):
    daten = {"format": format_, "streams": [{"codec_type": "video", "width": 1080, "height": 1920}]}
    monkeypatch.setattr(medien, "_probe", lambda p: daten)
    with pytest.raises(MedienFehler, match="Dauer"):
        video_info(tmp_path / "v.mp4")


def test_hat_ton(tmp_path):
    stumm = tmp_path / "stumm.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=white:s=64x64:d=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(stumm)], check=True)
    mit = tmp_path / "mit.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=white:s=64x64:d=1",
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-shortest",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(mit)], check=True)
    assert medien.hat_ton(stumm) is False
    assert medien.hat_ton(mit) is True
