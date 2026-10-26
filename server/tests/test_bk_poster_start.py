from datetime import date, datetime

from briefkasten.ablauf import ZONE
from briefkasten.instagram import InstagramFehler


def _laeuft(ablauf, b, creation_id):
    ablauf.s.setze_post(b["id"], post_status="laeuft", creation_id=creation_id)


def test_start_ohne_creation_id_versucht_neu(poster, frei, ablauf, uhr):
    uhr.zeit = datetime(2026, 10, 27, 19, 1, tzinfo=ZONE)
    _laeuft(ablauf, frei[0], None)
    poster.beim_start()
    p = ablauf.s.post(frei[0]["id"])
    assert p["post_status"] == "fehler" and p["naechster_versuch"] is None
    poster.takt()
    assert ablauf.s.post(frei[0]["id"])["post_status"] == "gepostet"


def test_start_findet_beitrag_online(poster, frei, ablauf, ig, uhr):
    uhr.zeit = datetime(2026, 10, 27, 19, 3, tzinfo=ZONE)
    _laeuft(ablauf, frei[0], "c7")
    ig.status["c7"] = "PUBLISHED"
    ig.letzte_liste = [{"id": "m9", "caption": "Caption 1", "timestamp": "2026-10-27T18:01:00+0000",
                        "permalink": "https://www.instagram.com/p/m9/"}]
    poster.beim_start()
    p = ablauf.s.post(frei[0]["id"])
    assert (p["post_status"], p["instagram_id"]) == ("gepostet", "m9")
    assert "veroeffentliche" not in ig.methoden()


def test_start_unklar_fragt_betreiber(poster, frei, ablauf, ig, tg, uhr):
    uhr.zeit = datetime(2026, 10, 27, 19, 3, tzinfo=ZONE)
    _laeuft(ablauf, frei[0], "c7")
    ig.status_fehler = [InstagramFehler("Instagram nicht erreichbar (URLError)")]
    poster.beim_start()
    assert ablauf.s.post(frei[0]["id"])["post_status"] == "unklar"
    letzte = [f for m, f in tg.aufrufe if m == "sendMessage"][-1]
    assert letzte["text"] == "❓ Unklar, ob «Thema 1» online ist. Bitte auf Instagram nachschauen."
    assert [k["text"] for k in letzte["reply_markup"]["inline_keyboard"][0]] == ["🔁 Jetzt posten", "❌ Auslassen"]
    poster.takt()
    assert "bereite_vor" not in ig.methoden()


def test_start_published_aber_liste_weg_trotzdem_gepostet(poster, frei, ablauf, ig, uhr):
    uhr.zeit = datetime(2026, 10, 27, 19, 3, tzinfo=ZONE)
    _laeuft(ablauf, frei[0], "c7")
    ig.status["c7"] = "PUBLISHED"

    def weg(anzahl=10):
        raise InstagramFehler("weg")
    ig.letzte = weg
    poster.beim_start()
    p = ablauf.s.post(frei[0]["id"])
    assert (p["post_status"], p["instagram_id"], p["permalink"]) == ("gepostet", None, None)


class Schluessel:
    def __init__(self, tage, fehler=None):
        self.tage, self.fehler = tage, fehler

    def alter_tage(self, heute):
        if self.fehler:
            raise self.fehler
        return self.tage


def test_schluessel_ab_50_tagen_erneuern(poster, ig):
    ig.schluessel = Schluessel(50)
    erneuert = []
    ig.erneuere = erneuert.append
    poster.takt()
    poster.takt()
    assert erneuert == [date(2026, 10, 24)]


def test_schluessel_juenger_nichts(poster, ig):
    ig.schluessel = Schluessel(49)

    def nie(heute):
        raise AssertionError("nicht erneuern")
    ig.erneuere = nie
    poster.takt()


def test_schluessel_fehlt_meldung_einmal_pro_tag(poster, ig, tg, uhr):
    ig.schluessel = Schluessel(0, InstagramFehler("Instagram-Schlüssel fehlt", ungueltig=True))
    poster.takt()
    poster.takt()
    assert len([t for t in tg.gesendet() if t.startswith("⚠️ Instagram-Schlüssel")]) == 1
    uhr.zeit = datetime(2026, 10, 25, 9, 0, tzinfo=ZONE)
    poster.takt()
    assert len([t for t in tg.gesendet() if t.startswith("⚠️ Instagram-Schlüssel")]) == 2


def test_erneuern_scheitert_meldung(poster, ig, tg):
    ig.schluessel = Schluessel(55)

    def kaputt(heute):
        raise InstagramFehler("Instagram HTTP 400: abgelaufen", ungueltig=True)
    ig.erneuere = kaputt
    poster.takt()
    assert tg.gesendet()[-1].startswith("⚠️ Instagram-Schlüssel: Instagram HTTP 400: abgelaufen.")
