import json
import stat
from datetime import date, datetime, timezone

import pytest
from hilfen_bk import Antworten

from briefkasten.instagram import Instagram, InstagramFehler, Schluessel

GEHEIM = "IGgeheim123"


@pytest.fixture
def schluessel(tmp_path):
    s = Schluessel(tmp_path / "instagram.json")
    s.speichere({"token": GEHEIM, "erstellt": "2026-10-25", "user_id": "1784"})
    return s


def _ig(schluessel, *antworten):
    a = Antworten(*antworten)
    schlaf = []
    return Instagram(schluessel, oeffne=a, schlafe=schlaf.append, uhr=lambda: len(schlaf) * 5), a, schlaf


def test_schluessel_datei_rechte_600(schluessel):
    assert stat.S_IMODE(schluessel.pfad.stat().st_mode) == 0o600
    assert schluessel.lade()["user_id"] == "1784"
    assert schluessel.alter_tage(date(2026, 12, 14)) == 50


def test_schluessel_fehlt(tmp_path):
    with pytest.raises(InstagramFehler) as e:
        Schluessel(tmp_path / "fehlt.json").lade()
    assert e.value.ungueltig


def test_karussell_container_warten_veroeffentlichen(schluessel):
    ig, a, schlaf = _ig(schluessel, {"id": "k1"}, {"id": "k2"}, {"status_code": "FINISHED"},
                        {"status_code": "IN_PROGRESS"}, {"status_code": "FINISHED"}, {"id": "c9"},
                        {"status_code": "FINISHED"}, {"id": "m5"}, {"permalink": "https://www.instagram.com/p/X/"})
    assert ig.bereite_vor("karussell", ["https://example.com/1.jpg", "https://example.com/2.jpg"], None, "Hallo") == "c9"
    assert a.anfragen[0] == ("POST", "/v26.0/1784/media", {"image_url": "https://example.com/1.jpg",
                                                            "is_carousel_item": "true"})
    assert a.anfragen[5] == ("POST", "/v26.0/1784/media", {"media_type": "CAROUSEL", "children": "k1,k2",
                                                            "caption": "Hallo"})
    assert schlaf == [5]
    assert ig.veroeffentliche("c9") == {"instagram_id": "m5", "permalink": "https://www.instagram.com/p/X/"}
    assert a.anfragen[7] == ("POST", "/v26.0/1784/media_publish", {"creation_id": "c9"})


def test_reel_mit_cover(schluessel):
    ig, a, _ = _ig(schluessel, {"id": "r1"}, {"status_code": "FINISHED"})
    assert ig.bereite_vor("reel", ["https://example.com/v.mp4"], "https://example.com/c.jpg", "Text") == "r1"
    assert a.anfragen[0][2] == {"media_type": "REELS", "video_url": "https://example.com/v.mp4",
                                "cover_url": "https://example.com/c.jpg", "caption": "Text", "share_to_feed": "true"}


def test_verarbeitung_error(schluessel):
    ig, _, _ = _ig(schluessel, {"id": "r1"}, {"status_code": "ERROR", "status": "Video zu kurz"})
    with pytest.raises(InstagramFehler, match="nicht verarbeiten.*Video zu kurz"):
        ig.bereite_vor("reel", ["u"], None, "T")


def test_verarbeitung_zeitlimit(schluessel):
    ig, _, _ = _ig(schluessel, {"id": "r1"}, *([{"status_code": "IN_PROGRESS"}] * 200))
    with pytest.raises(InstagramFehler, match="10 Minuten"):
        ig.bereite_vor("reel", ["u"], None, "T")


def test_fehler_190_ist_ungueltig_ohne_token(schluessel):
    ig, _, _ = _ig(schluessel, (400, {"error": {"message": f"Invalid token {GEHEIM}", "code": 190}}))
    with pytest.raises(InstagramFehler) as e:
        ig.bereite_vor("reel", ["u"], None, "T")
    assert e.value.ungueltig and GEHEIM not in str(e.value)


def test_nicht_erreichbar(schluessel):
    def kaputt(req, timeout=None):
        raise OSError("weg")
    with pytest.raises(InstagramFehler, match="nicht erreichbar"):
        Instagram(schluessel, oeffne=kaputt).letzte()


def test_tagesgrenze(schluessel):
    ig, _, _ = _ig(schluessel, {"data": [{"quota_usage": 100, "config": {"quota_total": 100}}]},
                   {"data": [{"quota_usage": 3, "config": {"quota_total": 100}}]})
    assert ig.tagesgrenze_erreicht() is True
    assert ig.tagesgrenze_erreicht() is False


def test_letzte(schluessel):
    ig, a, _ = _ig(schluessel, {"data": [{"id": "m1", "caption": "A", "timestamp": "2026-10-27T18:00:03+0000"}]})
    assert ig.letzte(10)[0]["id"] == "m1"
    assert a.anfragen[0] == ("GET", "/v26.0/1784/media", {"fields": "id,caption,timestamp,permalink", "limit": "10"})


def test_erneuern_schreibt_neuen_schluessel(schluessel):
    ig, a, _ = _ig(schluessel, {"access_token": "IGneu456", "expires_in": 5184000})
    ig.erneuere(date(2026, 12, 14))
    assert json.loads(schluessel.pfad.read_text()) == {"token": "IGneu456", "erstellt": "2026-12-14", "user_id": "1784"}
    assert a.anfragen[0] == ("GET", "/refresh_access_token", {"grant_type": "ig_refresh_token"})


def test_container_status(schluessel):
    ig, a, _ = _ig(schluessel, {"status_code": "PUBLISHED", "id": "c9"})
    assert ig.container_status("c9") == "PUBLISHED"
    assert a.anfragen == [("GET", "/v26.0/c9", {"fields": "status_code"})]


def test_container_status_fehler(schluessel):
    ig, _, _ = _ig(schluessel, (500, {"error": {"message": "kaputt"}}))
    with pytest.raises(InstagramFehler):
        ig.container_status("c9")


def test_pruefe_fragt_me_ab(schluessel):
    ig, a, _ = _ig(schluessel, {"user_id": "1784", "id": "99"})
    ig.pruefe()
    assert a.anfragen[0] == ("GET", "/v26.0/me", {"fields": "user_id"})


def test_pruefe_ungueltig_und_ohne_user_id(schluessel):
    ig, _, _ = _ig(schluessel, (400, {"error": {"message": f"Invalid OAuth access token {GEHEIM}", "code": 190}}),
                   {"id": "99"})
    with pytest.raises(InstagramFehler) as e:
        ig.pruefe()
    assert e.value.ungueltig and GEHEIM not in str(e.value)
    with pytest.raises(InstagramFehler):
        ig.pruefe()


def test_pruefe_anderes_konto(schluessel):
    ig, _, _ = _ig(schluessel, {"user_id": 999})
    with pytest.raises(InstagramFehler, match="anderen Konto") as e:
        ig.pruefe()
    assert e.value.ungueltig


def test_medien_seit_folgt_seiten_bis_grenze(schluessel):
    seite1 = {"data": [{"id": "m3", "timestamp": "2026-10-29T17:00:05+0000", "media_type": "VIDEO",
                        "media_product_type": "REELS"},
                       {"id": "m2", "timestamp": "2026-10-20T17:00:05+0000", "media_type": "CAROUSEL_ALBUM",
                        "media_product_type": "FEED"}],
              "paging": {"cursors": {"after": "AFT"}, "next": "https://graph.instagram.com/x"}}
    seite2 = {"data": [{"id": "m1", "timestamp": "2026-09-01T17:00:05+0000", "media_type": "IMAGE",
                        "media_product_type": "FEED"}],
              "paging": {"cursors": {"after": "AFT2"}, "next": "https://graph.instagram.com/x"}}
    ig, a, _ = _ig(schluessel, seite1, seite2)
    medien = ig.medien_seit(datetime(2026, 10, 2, 18, 0, tzinfo=timezone.utc))
    assert [m["id"] for m in medien] == ["m3", "m2"]
    assert a.anfragen[0] == ("GET", "/v26.0/1784/media", {
        "fields": "id,caption,media_type,media_product_type,timestamp,permalink", "limit": "50"})
    assert a.anfragen[1][2]["after"] == "AFT"
    assert len(a.anfragen) == 2   # m1 ist älter als die Grenze: keine dritte Seite


def test_medien_seit_ohne_naechste_seite(schluessel):
    ig, a, _ = _ig(schluessel, {"data": [{"id": "m1", "timestamp": "2026-10-29T17:00:05+0000"}]})
    assert [m["id"] for m in ig.medien_seit(datetime(2026, 10, 1, tzinfo=timezone.utc))] == ["m1"]
    assert len(a.anfragen) == 1


def test_zahlen_reel_in_einem_aufruf(schluessel):
    antwort = {"data": [{"name": "views", "values": [{"value": 120}]},
                        {"name": "reach", "values": [{"value": 90}]},
                        {"name": "reels_skip_rate", "total_value": {"value": 61.5}}]}
    ig, a, _ = _ig(schluessel, antwort)
    werte = ig.zahlen("m3", reel=True)
    assert a.anfragen[0] == ("GET", "/v26.0/m3/insights", {
        "metric": "views,reach,shares,saved,comments,likes,total_interactions,ig_reels_avg_watch_time,reels_skip_rate"})
    assert werte["views"] == 120 and werte["reach"] == 90 and werte["reels_skip_rate"] == 61.5
    assert werte["shares"] is None and set(werte) == {"views", "reach", "shares", "saved", "comments", "likes",
                                                      "total_interactions", "ig_reels_avg_watch_time", "reels_skip_rate"}


def test_zahlen_karussell_einzeln_nach_fehler(schluessel):
    fehler = (400, {"error": {"message": "metric not supported", "code": 100}})
    einzeln = [{"data": [{"name": m, "values": [{"value": i}]}]} for i, m in enumerate(
        ["views", "reach", "shares", "saved", "comments", "likes"])]
    ig, a, _ = _ig(schluessel, fehler, *einzeln, fehler)
    werte = ig.zahlen("m2", reel=False)
    assert "ig_reels_avg_watch_time" not in werte
    assert werte["views"] == 0 and werte["likes"] == 5 and werte["total_interactions"] is None
    assert [f["metric"] for _, _, f in a.anfragen[1:]] == ["views", "reach", "shares", "saved", "comments", "likes",
                                                           "total_interactions"]


def test_zahlen_ungueltiger_schluessel_bricht_ab(schluessel):
    ig, _, _ = _ig(schluessel, (400, {"error": {"message": f"bad token {GEHEIM}", "code": 190}}))
    with pytest.raises(InstagramFehler) as e:
        ig.zahlen("m3", reel=True)
    assert e.value.ungueltig and GEHEIM not in str(e.value)


def _netz_aus(*vorher):
    """Öffner: erst die Antworten `vorher` (wie Antworten), dann Netzausfall."""
    a = Antworten(*vorher)

    def offen(req, timeout=None):
        if a.antworten:
            return a(req, timeout)
        a.anfragen.append((req.get_method(), None, None))
        raise OSError("weg")
    return offen, a


def _ig_netz(schluessel, *vorher):
    offen, a = _netz_aus(*vorher)
    return Instagram(schluessel, oeffne=offen, schlafe=lambda s: None, uhr=lambda: 0), a


def test_medien_seit_bricht_nach_max_seiten_ab(schluessel):
    from briefkasten.instagram import MAX_SEITEN
    seite = {"data": [{"id": "m", "timestamp": "2026-10-29T17:00:05+0000"}],
             "paging": {"cursors": {"after": "A"}, "next": "https://graph.instagram.com/x"}}
    ig, a, _ = _ig(schluessel, *[seite] * (MAX_SEITEN + 3))
    assert len(ig.medien_seit(datetime(2026, 1, 1, tzinfo=timezone.utc))) == MAX_SEITEN
    assert len(a.anfragen) == MAX_SEITEN


def test_medien_seit_ueberspringt_kaputte_eintraege(schluessel):
    daten = [{"timestamp": "2026-10-29T17:00:05+0000"}, {"id": "a"}, {"id": "b", "timestamp": "gestern"},
             "kein dict", {"id": "ok", "timestamp": "2026-10-28T17:00:05+0000"}]
    ig, _, _ = _ig(schluessel, {"data": daten})
    assert [m["id"] for m in ig.medien_seit(datetime(2026, 10, 1, tzinfo=timezone.utc))] == ["ok"]


def test_medien_seit_cursor_ohne_next_endet(schluessel):
    ig, a, _ = _ig(schluessel, {"data": [{"id": "m1", "timestamp": "2026-10-29T17:00:05+0000"}],
                                "paging": {"cursors": {"after": "A"}}})
    assert len(ig.medien_seit(datetime(2026, 1, 1, tzinfo=timezone.utc))) == 1
    assert len(a.anfragen) == 1


def test_zahlen_values_leer_nutzt_total_value(schluessel):
    ig, _, _ = _ig(schluessel, {"data": [{"name": "views", "values": [], "total_value": {"value": 7}}]})
    assert ig.zahlen("m", reel=False)["views"] == 7


def test_zahlen_kaputte_struktur(schluessel):
    antwort = {"data": ["x", {"values": [{"value": 1}]}, {"name": "views", "values": ["kein dict"]},
                        {"name": "reach", "values": [{"value": 5}]}]}
    ig, _, _ = _ig(schluessel, antwort)
    werte = ig.zahlen("m", reel=False)
    assert werte["views"] is None and werte["reach"] == 5


def test_zahlen_code_190_in_einzelphase_bricht_ab(schluessel):
    ig, _, _ = _ig(schluessel, (400, {"error": {"message": "x", "code": 100}}),
                   (400, {"error": {"message": f"token {GEHEIM}", "code": 190}}))
    with pytest.raises(InstagramFehler) as e:
        ig.zahlen("m", reel=False)
    assert e.value.ungueltig and GEHEIM not in str(e.value)


def test_zahlen_netzfehler_im_sammelaufruf_wirft(schluessel):
    ig, a = _ig_netz(schluessel)
    with pytest.raises(InstagramFehler) as e:
        ig.zahlen("m", reel=True)
    assert e.value.netz and not e.value.ungueltig
    assert len(a.anfragen) == 1   # keine Einzelabfragen


def test_zahlen_netzfehler_in_einzelphase_wirft(schluessel):
    ig, a = _ig_netz(schluessel, (400, {"error": {"message": "x", "code": 100}}),
                     {"data": [{"name": "views", "values": [{"value": 1}]}]})
    with pytest.raises(InstagramFehler) as e:
        ig.zahlen("m", reel=False)
    assert e.value.netz
    assert len(a.anfragen) == 3


def test_kommentare_folgen_seiten(schluessel):
    seite1 = {"data": [{"id": "k1", "text": "START", "username": "anna_beispiel", "timestamp": "2026-10-27T18:10:00+0000"},
                       {"id": "k2", "text": "Super", "from": {"id": "9", "username": "beat.b"},
                        "timestamp": "2026-10-27T18:11:00+0000"},
                       {"text": "ohne id"}, "kaputt"],
              "paging": {"cursors": {"after": "AFT"}, "next": "https://graph.instagram.com/x"}}
    seite2 = {"data": [{"id": "k3", "text": None, "from": "kaputt"}], "paging": {"cursors": {"after": "AFT2"}}}
    ig, a, _ = _ig(schluessel, seite1, seite2)
    assert ig.kommentare("m1") == [
        {"id": "k1", "text": "START", "username": "anna_beispiel", "zeit": "2026-10-27T18:10:00+0000"},
        {"id": "k2", "text": "Super", "username": "beat.b", "zeit": "2026-10-27T18:11:00+0000"},
        {"id": "k3", "text": "", "username": None, "zeit": None}]
    assert a.anfragen[0] == ("GET", "/v26.0/m1/comments", {"fields": "id,text,username,from,timestamp",
                                                            "limit": "50"})
    assert a.anfragen[1][2]["after"] == "AFT"
    assert len(a.anfragen) == 2   # Seite 2 ohne next: Ende


def test_kommentare_hoechstens_zehn_seiten(schluessel):
    seite = {"data": [], "paging": {"cursors": {"after": "A"}, "next": "https://graph.instagram.com/x"}}
    ig, a, _ = _ig(schluessel, *[seite] * 12)
    assert ig.kommentare("m1") == []
    assert len(a.anfragen) == 10


@pytest.mark.parametrize("code", [10, 200, 230])
def test_fehlende_berechtigung(schluessel, code):
    ig, _, _ = _ig(schluessel, (403, {"error": {"message": f"Application does not have permission {GEHEIM}",
                                                "code": code}}))
    with pytest.raises(InstagramFehler) as e:
        ig.kommentare("m1")
    assert e.value.berechtigung and not e.value.ungueltig and GEHEIM not in str(e.value)


def test_anderer_fehler_ist_keine_berechtigung(schluessel):
    ig, _, _ = _ig(schluessel, (400, {"error": {"message": "kaputt", "code": 100}}))
    with pytest.raises(InstagramFehler) as e:
        ig.kommentare("m1")
    assert not e.value.berechtigung


def test_eigener_name(schluessel):
    ig, a, _ = _ig(schluessel, {"username": "example.com", "id": "1"}, {"id": "1"})
    assert ig.eigener_name() == "example.com"
    assert a.anfragen[0] == ("GET", "/v26.0/me", {"fields": "username"})
    assert ig.eigener_name() is None


def test_pruefe_mit_kommentaren(schluessel):
    ig, a, _ = _ig(schluessel, {"user_id": "1784"}, {"data": [{"id": "m9"}]}, {"data": []})
    assert ig.pruefe(kommentare=True) == {"kommentare": True}
    assert a.anfragen[1] == ("GET", "/v26.0/1784/media", {"fields": "id", "limit": "1"})
    assert a.anfragen[2] == ("GET", "/v26.0/m9/comments", {"fields": "id", "limit": "1"})


def test_pruefe_kommentare_ohne_berechtigung_oder_ohne_beitrag(schluessel):
    ig, _, _ = _ig(schluessel, {"user_id": "1784"}, {"data": [{"id": "m9"}]},
                   (403, {"error": {"message": "no", "code": 10}}),
                   {"user_id": "1784"}, {"data": []})
    assert ig.pruefe(kommentare=True) == {"kommentare": False}
    assert ig.pruefe(kommentare=True) == {"kommentare": None}


def test_pruefe_ohne_kommentare_wie_bisher(schluessel):
    ig, a, _ = _ig(schluessel, {"user_id": "1784"})
    assert ig.pruefe() == {}
    assert len(a.anfragen) == 1


def test_konto_follower_und_aufrufe(schluessel):
    ig, a, _ = _ig(schluessel,
                   {"followers_count": 412, "username": "dein.konto", "id": "1784"},
                   {"data": [{"name": "views", "period": "day", "total_value": {"value": 160}}]},
                   {"data": [{"name": "views", "period": "day", "total_value": {"value": 143}}]},
                   {"data": [{"name": "views", "period": "day", "total_value": {"value": 4812}}]})
    werte = ig.konto(2, date(2026, 10, 28))
    assert werte == {"follower": 412, "aufrufe_30t": 4812,
                     "aufrufe_tage": {"2026-10-27": 160, "2026-10-26": 143},
                     "link": "https://www.instagram.com/dein.konto/"}
    assert a.anfragen[0] == ("GET", "/v26.0/1784", {"fields": "followers_count,username"})
    assert a.anfragen[1][1] == "/v26.0/1784/insights"
    assert a.anfragen[1][2]["metric"] == "views" and a.anfragen[1][2]["metric_type"] == "total_value"


def test_konto_schluessel_ungueltig(schluessel):
    ig, _, _ = _ig(schluessel, (400, {"error": {"code": 190, "message": f"abgelaufen {GEHEIM}"}}))
    with pytest.raises(InstagramFehler) as e:
        ig.konto(1, date(2026, 10, 28))
    assert e.value.ungueltig and GEHEIM not in str(e.value)
