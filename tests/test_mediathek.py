import base64
import io
import json
import urllib.error

import pytest

from lib.mediathek import KONTO, Mediathek, MediathekFehler

GEHEIM = "abcd efgh ijkl"


class Netz:
    def __init__(self, *antworten):
        self.antworten, self.anfragen = list(antworten), []

    def __call__(self, req, timeout=None):
        self.anfragen.append(req)
        a = self.antworten.pop(0)
        if isinstance(a, tuple):
            raise urllib.error.HTTPError(req.full_url, a[0], "x", {}, io.BytesIO(json.dumps(a[1]).encode()))
        return io.BytesIO(json.dumps(a).encode())


def test_hochladen(tmp_path):
    datei = tmp_path / "01.jpg"
    datei.write_bytes(b"\xff\xd8bild")
    netz = Netz({"id": 77, "source_url": "https://example.com/wp-content/uploads/2026/10/x-01.jpg"})
    m = Mediathek(passwort=lambda: GEHEIM, oeffne=netz)
    assert m.lade_hoch(datei, "fliessband-x-v1-01.jpg") == {
        "wp_id": 77, "url": "https://example.com/wp-content/uploads/2026/10/x-01.jpg"}
    req = netz.anfragen[0]
    assert req.get_method() == "POST" and req.full_url == "https://example.com/wp-json/wp/v2/media"
    assert req.data == b"\xff\xd8bild"
    assert req.get_header("Content-type") == "image/jpeg"
    assert req.get_header("Content-disposition") == 'attachment; filename="fliessband-x-v1-01.jpg"'
    assert req.get_header("Authorization") == "Basic " + base64.b64encode(f"{KONTO}:{GEHEIM}".encode()).decode()


def test_video_typ(tmp_path):
    datei = tmp_path / "reel.mp4"
    datei.write_bytes(b"mp4")
    netz = Netz({"id": 1, "source_url": "https://example.com/v.mp4"})
    Mediathek(passwort=lambda: GEHEIM, oeffne=netz).lade_hoch(datei, "v.mp4")
    assert netz.anfragen[0].get_header("Content-type") == "video/mp4"


def test_unbekannte_endung(tmp_path):
    datei = tmp_path / "a.png"
    datei.write_bytes(b"x")
    with pytest.raises(MediathekFehler):
        Mediathek(passwort=lambda: GEHEIM, oeffne=Netz()).lade_hoch(datei, "a.png")


def test_http_fehler_ohne_passwort(tmp_path):
    datei = tmp_path / "01.jpg"
    datei.write_bytes(b"x")
    netz = Netz((401, {"code": "rest_cannot_create", "message": f"Nicht erlaubt {GEHEIM}"}))
    with pytest.raises(MediathekFehler) as e:
        Mediathek(passwort=lambda: GEHEIM, oeffne=netz).lade_hoch(datei, "a.jpg")
    assert "HTTP 401" in str(e.value) and GEHEIM not in str(e.value)


def test_nicht_erreichbar(tmp_path):
    datei = tmp_path / "01.jpg"
    datei.write_bytes(b"x")

    def weg(req, timeout=None):
        raise OSError("weg")
    with pytest.raises(MediathekFehler, match="nicht erreichbar"):
        Mediathek(passwort=lambda: GEHEIM, oeffne=weg).lade_hoch(datei, "a.jpg")


def test_loeschen_und_schon_weg():
    netz = Netz({"deleted": True}, (404, {"code": "rest_post_invalid_id"}))
    m = Mediathek(passwort=lambda: GEHEIM, oeffne=netz)
    m.loesche(77)
    m.loesche(78)
    assert netz.anfragen[0].get_method() == "DELETE"
    assert netz.anfragen[0].full_url == "https://example.com/wp-json/wp/v2/media/77?force=true"


def test_fehler_mit_code_und_dauerhaft(tmp_path):
    datei = tmp_path / "01.jpg"
    datei.write_bytes(b"x")
    for code, dauerhaft in ((401, True), (413, True), (404, False), (408, False), (429, False), (500, False)):
        with pytest.raises(MediathekFehler) as e:
            Mediathek(passwort=lambda: GEHEIM, oeffne=Netz((code, {"message": "x"}))).lade_hoch(datei, "a.jpg")
        assert e.value.code == code and e.value.dauerhaft is dauerhaft

    def weg(req, timeout=None):
        raise OSError("weg")
    with pytest.raises(MediathekFehler) as e:
        Mediathek(passwort=lambda: GEHEIM, oeffne=weg).lade_hoch(datei, "a.jpg")
    assert e.value.code is None and e.value.dauerhaft is False


def test_passwort_fehlt_ist_dauerhaft(monkeypatch):
    import subprocess
    from lib import mediathek
    monkeypatch.setattr(mediathek.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 44, stdout="", stderr=""))
    with pytest.raises(MediathekFehler) as e:
        mediathek._passwort.__wrapped__()
    assert e.value.dauerhaft is True and e.value.code is None
