import io
import json
import urllib.error
from datetime import date, datetime

import pytest
from hilfen_bk import Antworten

from briefkasten.ablauf import ZONE
from briefkasten.facebook import Facebook, FacebookFehler, FbSchluessel

GEHEIM = "EAAgeheim123"


@pytest.fixture
def schluessel(tmp_path):
    p = tmp_path / "facebook.json"
    p.write_text(json.dumps({"token": GEHEIM, "page_id": "777", "erstellt": "2026-10-28"}), encoding="utf-8")
    return FbSchluessel(p)


def _fb(schluessel, *antworten):
    a = Antworten(*antworten)
    schlaf = []
    return Facebook(schluessel, oeffne=a, schlafe=schlaf.append, uhr=lambda: len(schlaf) * 5), a, schlaf


def test_schluessel_fehlt_oder_unvollstaendig(tmp_path):
    with pytest.raises(FacebookFehler) as e:
        FbSchluessel(tmp_path / "fehlt.json").lade()
    assert e.value.ungueltig
    assert FbSchluessel(tmp_path / "fehlt.json").da() is False
    p = tmp_path / "halb.json"
    p.write_text(json.dumps({"token": "x"}), encoding="utf-8")
    with pytest.raises(FacebookFehler):
        FbSchluessel(p).lade()


def test_fehler_ohne_token_und_ungueltig(schluessel):
    fb, _, _ = _fb(schluessel, (400, {"error": {"message": f"Token {GEHEIM} abgelaufen", "code": 190}}))
    with pytest.raises(FacebookFehler) as e:
        fb.starte_reel()
    assert e.value.ungueltig and GEHEIM not in str(e.value)
    assert str(e.value).startswith("Facebook HTTP 400")


def test_nicht_erreichbar(schluessel):
    def weg(req, timeout=None):
        raise urllib.error.URLError("weg")
    with pytest.raises(FacebookFehler) as e:
        Facebook(schluessel, oeffne=weg).starte_reel()
    assert str(e.value) == "Facebook nicht erreichbar (URLError)" and not e.value.ungueltig


def test_karussell(schluessel):
    fb, a, _ = _fb(schluessel, {"id": "f1"}, {"id": "f2"}, {"id": "777_9"},
                   {"permalink_url": "https://www.facebook.com/beispielseite/posts/9"})
    assert fb.poste_karussell(["https://example.com/1.jpg", "https://example.com/2.jpg"], "Text") == {
        "id": "777_9", "link": "https://www.facebook.com/beispielseite/posts/9"}
    assert a.anfragen[0] == ("POST", "/v26.0/777/photos", {"url": "https://example.com/1.jpg", "published": "false"})
    assert a.anfragen[1] == ("POST", "/v26.0/777/photos", {"url": "https://example.com/2.jpg", "published": "false"})
    assert a.anfragen[2] == ("POST", "/v26.0/777/feed", {"message": "Text",
                                                         "attached_media[0]": '{"media_fbid": "f1"}',
                                                         "attached_media[1]": '{"media_fbid": "f2"}'})
    assert a.anfragen[3] == ("GET", "/v26.0/777_9", {"fields": "permalink_url"})


def test_karussell_ohne_link_bleibt_gepostet(schluessel):
    fb, _, _ = _fb(schluessel, {"id": "f1"}, {"id": "f2"}, {"id": "777_9"}, (500, {}))
    assert fb.poste_karussell(["https://example.com/1.jpg", "https://example.com/2.jpg"], "T") == {"id": "777_9", "link": None}


def test_schon_gepostet(schluessel):
    seit = datetime(2026, 10, 28, 18, 55, tzinfo=ZONE)   # 17:55 UTC
    fb, a, _ = _fb(schluessel, {"data": [
        {"id": "777_1", "message": "Alt", "created_time": "2026-10-28T18:00:00+0000"},
        {"id": "777_2", "message": "Text", "created_time": "2026-10-28T18:00:05+0000",
         "permalink_url": "https://www.facebook.com/x"}]})
    assert fb.schon_gepostet("Text\n", seit) == {"id": "777_2", "link": "https://www.facebook.com/x"}
    assert a.anfragen[0] == ("GET", "/v26.0/777/published_posts",
                             {"fields": "id,message,created_time,permalink_url", "limit": "10"})
    fb, _, _ = _fb(schluessel, {"data": [{"id": "777_2", "message": "Text", "created_time": "2026-10-28T17:00:00+0000"},
                                        {"id": "777_3", "message": "Text", "created_time": "kaputt"}]})
    assert fb.schon_gepostet("Text", seit) is None


def _st(video, phase):
    return {"status": {"video_status": video, "publishing_phase": {"status": phase}}}


VIDEO = b"\x00\x01fake-mp4\xff" * 10
VIDEO_URL = "https://example.com/v.mp4"


class Weiche:
    """Öffner: GET auf VIDEO_URL liefert Videobytes (oder fehler = HTTP-Code), alles andere kommt aus Antworten."""

    def __init__(self, *antworten, video=VIDEO, fehler=None):
        self.rest, self.video, self.fehler, self.aufrufe = list(antworten), video, fehler, []

    def __call__(self, req, timeout=None):
        self.aufrufe.append((req.get_method(), req.full_url, req.data, req, timeout))
        if req.full_url == VIDEO_URL:
            if self.fehler:
                raise urllib.error.HTTPError(req.full_url, self.fehler, "Fehler", {}, io.BytesIO(b""))
            return io.BytesIO(self.video)
        a = self.rest.pop(0)
        if isinstance(a, tuple):
            raise urllib.error.HTTPError(req.full_url, a[0], "Fehler", {}, io.BytesIO(json.dumps(a[1]).encode()))
        return io.BytesIO(json.dumps(a).encode())


def test_reel_ganzer_weg(schluessel):
    w = Weiche({"video_id": "v1", "upload_url": "https://rupload.facebook.com/x"},
               {"success": True}, {"success": True},
               _st("processing", "in_progress"), _st("ready", "complete"),
               {"permalink_url": "/reel/v1/"})
    schlaf = []
    fb = Facebook(schluessel, oeffne=w, schlafe=schlaf.append, uhr=lambda: len(schlaf) * 5)
    vid = fb.starte_reel()
    fb.lade_reel(vid, VIDEO_URL)
    fb.beende_reel(vid, "Text")
    fb.warte_reel(vid)
    assert fb.link(vid) == "https://www.facebook.com/reel/v1/"
    urls = [(m, u.split("?")[0]) for m, u, *_ in w.aufrufe]
    assert urls[0] == ("POST", "https://graph.facebook.com/v26.0/777/video_reels")
    assert urls[1] == ("GET", VIDEO_URL)
    assert urls[2] == ("POST", "https://rupload.facebook.com/video-upload/v26.0/v1")
    assert urls[3] == ("POST", "https://graph.facebook.com/v26.0/777/video_reels")
    assert schlaf == [5]


def test_reel_upload_kopfzeilen(schluessel):
    w = Weiche({"success": True})
    Facebook(schluessel, oeffne=w).lade_reel("v1", VIDEO_URL)
    (m1, u1, d1, _, t1), (m2, u2, d2, req, _) = w.aufrufe
    assert (m1, u1, t1) == ("GET", VIDEO_URL, 120)
    assert (m2, u2) == ("POST", "https://rupload.facebook.com/video-upload/v26.0/v1")
    assert d2 == VIDEO
    assert req.get_header("Authorization") == f"OAuth {GEHEIM}"
    assert req.get_header("Offset") == "0"
    assert req.get_header("File_size") == str(len(VIDEO))
    assert req.get_header("Content-type") == "application/octet-stream"
    assert req.get_header("File_url") is None


def test_reel_upload_ohne_erfolg(schluessel):
    with pytest.raises(FacebookFehler, match="nicht angenommen"):
        Facebook(schluessel, oeffne=Weiche({"success": False})).lade_reel("v1", VIDEO_URL)


def test_reel_download_403(schluessel):
    w = Weiche(fehler=403)
    with pytest.raises(FacebookFehler, match=r"Video nicht abrufbar \(.*403") as e:
        Facebook(schluessel, oeffne=w).lade_reel("v1", VIDEO_URL)
    assert GEHEIM not in str(e.value)
    assert len(w.aufrufe) == 1


def test_reel_download_netzfehler(schluessel):
    def weg(req, timeout=None):
        raise TimeoutError("zu langsam")
    with pytest.raises(FacebookFehler, match=r"Video nicht abrufbar \(TimeoutError\)"):
        Facebook(schluessel, oeffne=weg).lade_reel("v1", VIDEO_URL)


def test_reel_download_zu_gross(schluessel, monkeypatch):
    import briefkasten.facebook as modul
    monkeypatch.setattr(modul, "MAX_VIDEO", 10)
    w = Weiche(video=b"x" * 11)
    with pytest.raises(FacebookFehler, match="Video nicht abrufbar"):
        Facebook(schluessel, oeffne=w).lade_reel("v1", VIDEO_URL)
    assert len(w.aufrufe) == 1


def test_fehlertext_aus_debug_info(schluessel):
    fb, _, _ = _fb(schluessel, (422, {"debug_info": {"retriable": False, "type": "FileUrlProcessingError",
                                                     "message": f"Unable to fetch media {GEHEIM}"}}))
    with pytest.raises(FacebookFehler, match="HTTP 422.*Unable to fetch media") as e:
        fb.starte_reel()
    assert GEHEIM not in str(e.value)


@pytest.mark.parametrize("antwort, stand", [
    (_st("ready", "complete"), "fertig"),
    (_st("processing", "in_progress"), "laeuft"),
    (_st("processing", "not_started"), "offen"),
    ({"status": {"video_status": "upload_complete"}}, "offen"),
    (_st("error", "not_started"), "fehler"),
    (_st("processing", "error"), "fehler"),
    ({"status": {"video_status": "processing", "processing_phase": {
        "status": "not_started", "error": {"message": "Resolution too low"}}}}, "fehler"),
    ({"status": {"video_status": "uploading", "uploading_phase": {"status": "error"}}}, "fehler"),
    ({"status": {"video_status": "uploading", "uploading_phase": {"status": "in_progress"}}}, "offen"),
])
def test_reel_stand(schluessel, antwort, stand):
    fb, _, _ = _fb(schluessel, antwort)
    assert fb.reel_stand("v1") == stand


def test_warte_reel_fehler_und_zeitlimit(schluessel):
    fb, _, _ = _fb(schluessel, _st("error", "not_started"))
    with pytest.raises(FacebookFehler, match="nicht verarbeiten"):
        fb.warte_reel("v1")
    fb, _, schlaf = _fb(schluessel, *[_st("processing", "in_progress")] * 121)
    with pytest.raises(FacebookFehler, match="10 Minuten"):
        fb.warte_reel("v1")
    assert len(schlaf) == 120


def test_warte_reel_meldet_grund_von_facebook(schluessel):
    fb, _, _ = _fb(schluessel, {"status": {"video_status": "processing", "processing_phase": {
        "status": "not_started", "error": {"message": f"Resolution too low {GEHEIM}"}}}})
    with pytest.raises(FacebookFehler) as e:
        fb.warte_reel("v1")
    assert str(e.value) == "Facebook konnte das Video nicht verarbeiten (Resolution too low …)"
    fb, _, _ = _fb(schluessel, {"status": {"video_status": "uploading", "uploading_phase": {"status": "error"}}})
    with pytest.raises(FacebookFehler) as e:
        fb.warte_reel("v1")
    assert str(e.value) == "Facebook konnte das Video nicht verarbeiten"


def test_token_wird_vor_dem_kuerzen_ersetzt(schluessel):
    fb, _, _ = _fb(schluessel, (400, {"error": {"message": "x" * 295 + GEHEIM, "code": 1}}))
    with pytest.raises(FacebookFehler) as e:
        fb.starte_reel()
    assert "EAAg" not in str(e.value)


def test_schon_gepostet_zeitzone_und_id(schluessel):
    fb, _, _ = _fb(schluessel)
    with pytest.raises(ValueError, match="Zeitzone"):
        fb.schon_gepostet("T", datetime(2026, 10, 28, 18, 0))
    seit = datetime(2026, 10, 28, 18, 55, tzinfo=ZONE)
    fb, _, _ = _fb(schluessel, {"data": [{"message": "T", "created_time": "2026-10-28T18:00:05+0000"}]})
    assert fb.schon_gepostet("T", seit) is None


def test_konto_seite(schluessel):
    fb, a, _ = _fb(schluessel,
                   {"followers_count": 156, "link": "https://www.facebook.com/dein.konto", "id": "777"},
                   {"data": [{"name": "page_media_view", "period": "day", "values": [
                       {"value": 20, "end_time": "2026-10-26T07:00:00+0000"},
                       {"value": 30, "end_time": "2026-10-27T07:00:00+0000"},
                       {"value": 40, "end_time": "2026-10-28T07:00:00+0000"}]}]})
    werte = fb.konto(2, date(2026, 10, 28))
    assert werte == {"follower": 156, "aufrufe_30t": 90,
                     "aufrufe_tage": {"2026-10-26": 30, "2026-10-27": 40},
                     "link": "https://www.facebook.com/dein.konto"}
    assert a.anfragen[0] == ("GET", "/v26.0/777", {"fields": "followers_count,link"})
    assert a.anfragen[1][1] == "/v26.0/777/insights" and a.anfragen[1][2]["metric"] == "page_media_view"
