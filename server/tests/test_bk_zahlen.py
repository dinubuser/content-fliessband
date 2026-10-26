from datetime import timedelta

import pytest
from hilfen_bk import FalschesInstagram

from briefkasten.instagram import InstagramFehler
from briefkasten.poster import Poster

LANG = "Satz " * 30


def test_zahlen_mit_art_und_caption_anfang(ablauf):
    ig = FalschesInstagram()
    ig.medien_liste = [
        {"id": "m3", "timestamp": "2026-10-27T18:00:05+0000", "media_type": "VIDEO", "media_product_type": "REELS",
         "permalink": "https://www.instagram.com/reel/A/", "caption": LANG},
        {"id": "m2", "timestamp": "2026-10-21T17:00:05+0000", "media_type": "CAROUSEL_ALBUM",
         "media_product_type": "FEED", "permalink": "https://www.instagram.com/p/B/", "caption": None},
        {"id": "m1", "timestamp": "2026-10-20T17:00:05+0000", "media_type": "IMAGE", "media_product_type": "FEED"}]
    ig.werte = {"m3": {"reach": 90}, "m2": {"reach": 40}}
    poster = Poster(ablauf, ig)
    d = poster.zahlen(28)
    assert ("medien_seit", (ablauf.jetzt() - timedelta(days=28),)) in ig.aufrufe
    assert ("zahlen", ("m3", True)) in ig.aufrufe and ("zahlen", ("m2", False)) in ig.aufrufe
    assert [b["art"] for b in d["beitraege"]] == ["reel", "karussell", "bild"]
    assert d["beitraege"][0] == {"ig_id": "m3", "zeit": "2026-10-27T18:00:05+0000", "art": "reel",
                                 "link": "https://www.instagram.com/reel/A/", "caption_anfang": LANG[:80],
                                 "werte": {"reach": 90}, "start_kommentare": 0}
    assert d["beitraege"][1]["caption_anfang"] == "" and d["beitraege"][2]["werte"] == {}


def _poster(ablauf, ig, *ids):
    ig.medien_liste = [{"id": i, "timestamp": "2026-10-27T18:00:05+0000", "media_type": "IMAGE"} for i in ids]
    return Poster(ablauf, ig)


def test_http_fehler_bei_einem_beitrag_gibt_werte_none(ablauf):
    ig = FalschesInstagram()
    ig.werte = {"a": {"reach": 1}, "c": {"reach": 3}}
    ig.werte_fehler = {"b": InstagramFehler("Instagram HTTP 400: gelöscht")}
    d = _poster(ablauf, ig, "a", "b", "c").zahlen(28)
    assert [b["werte"] for b in d["beitraege"]] == [{"reach": 1}, None, {"reach": 3}]


def test_netzfehler_bei_einem_beitrag_wirft(ablauf):
    ig = FalschesInstagram()
    ig.werte_fehler = {"b": InstagramFehler("Instagram nicht erreichbar (OSError)", netz=True)}
    with pytest.raises(InstagramFehler):
        _poster(ablauf, ig, "a", "b").zahlen(28)


def test_ungueltiger_schluessel_bei_einem_beitrag_wirft(ablauf):
    ig = FalschesInstagram()
    ig.werte_fehler = {"a": InstagramFehler("Schlüssel", ungueltig=True)}
    with pytest.raises(InstagramFehler):
        _poster(ablauf, ig, "a").zahlen(28)


def test_zahlen_mit_start_kommentaren(ablauf):
    ig = FalschesInstagram()
    for i, (media, start) in enumerate([("a", True), ("a", True), ("a", False), ("b", False)]):
        ablauf.s.neuer_kommentar({"id": f"k{i}", "media_id": media, "username": "x", "text": "START",
                                  "zeit": None, "start": start})
    d = _poster(ablauf, ig, "a", "b", "c").zahlen(28)
    assert [b["start_kommentare"] for b in d["beitraege"]] == [2, 0, 0]
