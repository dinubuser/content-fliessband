import pytest
from PIL import Image

from lib.instagram_medien import InstagramPruefung, caption, dateien, pruefe


def _karussell(ordner, n=3, text="Caption #eins #zwei"):
    ordner.mkdir(parents=True)
    for i in range(1, n + 1):
        Image.new("RGB", (1080, 1350), (248, 246, 242)).save(ordner / f"slide-{i:02d}.png")
    (ordner / "caption.txt").write_text(text + "\n", encoding="utf-8")
    return ordner


def _reel(ordner, cover=True):
    ordner.mkdir(parents=True)
    (ordner / "reel.mp4").write_bytes(b"mp4")
    if cover:
        Image.new("RGBA", (1080, 1920), (11, 17, 30, 255)).save(ordner / "cover.png")
    (ordner / "caption.txt").write_text("Reel-Text", encoding="utf-8")
    return ordner


def test_karussell_als_jpeg(tmp_path):
    liste = dateien("karussell", _karussell(tmp_path / "k"), tmp_path / "ziel")
    assert [(p.name, teil) for p, teil in liste] == [("01.jpg", "01"), ("02.jpg", "02"), ("03.jpg", "03")]
    with Image.open(liste[0][0]) as im:
        assert (im.format, im.mode, im.size) == ("JPEG", "RGB", (1080, 1350))


def test_reel_video_und_cover(tmp_path):
    ordner = _reel(tmp_path / "r")
    liste = dateien("reel", ordner, tmp_path / "ziel")
    assert [(p.name, teil) for p, teil in liste] == [("reel.mp4", "video"), ("cover.jpg", "cover")]
    assert liste[0][0] == ordner / "reel.mp4"


def test_reel_ohne_cover(tmp_path):
    assert [teil for _, teil in dateien("reel", _reel(tmp_path / "r", cover=False), tmp_path / "z")] == ["video"]


def test_caption_ohne_rand(tmp_path):
    assert caption(_karussell(tmp_path / "k", text="  Hallo  ")) == "Hallo"


def test_pruefung_gut(tmp_path):
    pruefe("karussell", _karussell(tmp_path / "k"))
    pruefe("reel", _reel(tmp_path / "r"))


@pytest.mark.parametrize("n,text,grund", [
    (11, "Text", "höchstens 10 Bilder"),
    (1, "Text", "mindestens 2 Bilder"),
    (3, "x" * 2201, "Caption zu lang"),
    (3, " ".join(f"#t{i}" for i in range(31)), "zu viele Hashtags"),
])
def test_pruefung_verstoesse(tmp_path, n, text, grund):
    with pytest.raises(InstagramPruefung, match=grund):
        pruefe("karussell", _karussell(tmp_path / "k", n=n, text=text))


def test_reel_ohne_video(tmp_path):
    ordner = _reel(tmp_path / "r")
    (ordner / "reel.mp4").unlink()
    with pytest.raises(InstagramPruefung, match="reel.mp4 fehlt"):
        pruefe("reel", ordner)
