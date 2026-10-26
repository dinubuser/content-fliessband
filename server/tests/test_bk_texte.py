from briefkasten import texte


def _b(**ueber):
    b = {"nr": 3, "id": "x", "woche": "2026-KW44", "version": 1, "titel": "Mike verliert 30'000 Fr.",
         "format": "reel", "termin": "2026-10-27T19:00", "status": "offen", "neubauten": 0, "nachricht_id": 9}
    b.update(ueber)
    return b


def _knoepfe(tastatur):
    return [(k["text"], k["callback_data"]) for reihe in tastatur["inline_keyboard"] for k in reihe]


def test_knopf_text_offen_und_version():
    assert texte.knopf_text(_b()) == "Di 27.10., 19:00 · Reel\n«Mike verliert 30'000 Fr.»"
    assert texte.knopf_text(_b(version=2, format="karussell")).startswith("Di 27.10., 19:00 · Karussell · Version 2")
    assert texte.knopf_text(_b(status="freigegeben")).endswith("\n✅ Freigegeben, geht Di 27.10. um 19:00 online")
    assert texte.knopf_text(_b(), "Notiz: kürzer").endswith("\nNotiz: kürzer")


def test_tastatur_je_status():
    assert _knoepfe(texte.tastatur(_b())) == [("✅ Freigeben", "f:3:1"), ("✏️ Ändern", "a:3:1"),
                                              ("❌ Verwerfen", "v:3:1")]
    assert _knoepfe(texte.tastatur(_b(neubauten=2, version=3))) == [("✅ Freigeben", "f:3:3"),
                                                                    ("❌ Verwerfen", "v:3:3")]
    assert "schon 2-mal neu gebaut" in texte.knopf_text(_b(neubauten=2))
    assert _knoepfe(texte.tastatur(_b(status="freigegeben"))) == [("↩️ Zurücknehmen", "z:3:1")]
    for status in ("aendern_wartet", "verworfen", "verpasst"):
        assert texte.tastatur(_b(status=status)) == {"inline_keyboard": []}
    assert _knoepfe(texte.verwerfen_tastatur(_b())) == [("Ja, verwerfen", "vj:3:1"), ("Nein", "vn:3:1")]


def test_uebersicht_und_alle():
    bs = [_b(), _b(nr=4, titel="Versicherung", format="karussell", termin="2026-10-28T19:00",
                   status="freigegeben")]
    assert texte.uebersicht("2026-KW44", bs) == (
        "Freigabe 2026-KW44\n"
        "Di 27.10., 19:00 · Reel «Mike verliert 30'000 Fr.»: offen\n"
        "Mi 28.10., 19:00 · Karussell «Versicherung»: ✅ freigegeben\n\n"
        "Noch offen: 1")
    assert _knoepfe(texte.uebersicht_tastatur("2026-KW44", bs)) == [("✅ Alle offenen freigeben", "A:2026-KW44")]
    assert texte.uebersicht_tastatur("2026-KW44", bs[1:]) == {"inline_keyboard": []}
    assert texte.uebersicht("2026-KW44", bs[1:]).endswith("\n\nAlles entschieden.")
    assert _knoepfe(texte.alle_tastatur("2026-KW44")) == [("Ja, alle freigeben", "Aj:2026-KW44"),
                                                          ("Nein", "An:2026-KW44")]
    assert texte.alle_frage(2) == "Wirklich alle 2 offenen Beiträge freigeben?"


def test_einzeltexte():
    b = _b()
    assert texte.aendern_frage(b) == "Was soll ich bei «Mike verliert 30'000 Fr.» ändern? Antworte direkt auf diese Nachricht."
    assert texte.ersetzt_text(b, 2).endswith("\nErsetzt durch Version 2, siehe neue Nachricht.")
    assert texte.verpasst_text(b) == ("⏰ «Mike verliert 30'000 Fr.» (Di 27.10., 19:00) war bis zum Termin nicht "
                                      "freigegeben und wird nicht gepostet.")
    assert texte.erinnerung([b]).startswith("Erinnerung: Diese Beiträge sind noch nicht freigegeben.\nDi 27.10.")
    assert all(len(d) <= 64 for _, d in _knoepfe(texte.tastatur(_b(nr=99999, version=99))))


def test_platzhalter_nur_aendern_und_verwerfen():
    p = _b(platzhalter=True)
    assert _knoepfe(texte.tastatur(p)) == [("✏️ Ändern", "a:3:1"), ("❌ Verwerfen", "v:3:1")]
    assert _knoepfe(texte.tastatur(_b(platzhalter=True, neubauten=2))) == [("❌ Verwerfen", "v:3:1")]
    assert texte.knopf_text(p).endswith("\n⚠️ Hat noch Platzhalter, bitte per ✏️ Ändern ergänzen.")
    assert "Ändern geht nicht mehr" in texte.knopf_text(_b(platzhalter=True, neubauten=2))
    assert "Platzhalter" not in texte.knopf_text(_b(platzhalter=True, status="verworfen"))
    assert _knoepfe(texte.tastatur(_b(platzhalter=False))) == [("✅ Freigeben", "f:3:1"), ("✏️ Ändern", "a:3:1"),
                                                               ("❌ Verwerfen", "v:3:1")]
    for t in (texte.knopf_text(p), texte.zeile(p), texte.uebersicht("2026-KW44", [p])):
        assert "–" not in t and "—" not in t and "ß" not in t


def test_uebersicht_mit_platzhalter():
    p = _b(platzhalter=True)
    frei = _b(nr=4, titel="Versicherung", format="karussell", termin="2026-10-28T19:00")
    assert texte.zeile(p) == "Di 27.10., 19:00 · Reel «Mike verliert 30'000 Fr.»: offen, ⚠️ hat noch Platzhalter"
    assert texte.uebersicht("2026-KW44", [p]).endswith("\n\nNoch offen: 1")
    assert texte.uebersicht_tastatur("2026-KW44", [p]) == {"inline_keyboard": []}
    assert _knoepfe(texte.uebersicht_tastatur("2026-KW44", [p, frei])) == [("✅ Alle offenen freigeben",
                                                                            "A:2026-KW44")]


def test_freigegeben_zeigt_termin():
    b = _b(status="freigegeben", termin="2026-10-27T19:00")
    assert texte.knopf_text(b).endswith("\n✅ Freigegeben, geht Di 27.10. um 19:00 online")


def test_gepostet_und_ausgelassen_ohne_knoepfe():
    assert texte.knopf_text(_b(status="gepostet")).endswith("\n📲 gepostet")
    assert texte.tastatur(_b(status="gepostet")) == texte.LEER
    assert texte.knopf_text(_b(status="ausgelassen")).endswith("\n⏭ ausgelassen")


def test_vorwarnung():
    b = _b(status="freigegeben", termin="2026-10-27T19:00", titel="Mike verliert 30'000 Fr.")
    assert texte.vorwarnung(b) == "⏰ Um 19:00 geht «Mike verliert 30'000 Fr.» online."
    assert _knoepfe(texte.vorwarnung_tastatur(b)) == [("⏸ Stopp", "s:3:1")]


def test_ergebnis_und_fehler():
    b = _b(titel="X", termin="2026-10-27T19:00")
    assert texte.gepostet(b, "https://www.instagram.com/p/A/") == "✅ Gepostet: «X»\nhttps://www.instagram.com/p/A/"
    assert texte.gepostet(b, None) == "✅ Gepostet: «X»"
    assert texte.nicht_gepostet(b, "Instagram nicht erreichbar (URLError)") == \
        "⚠️ Nicht gepostet: «X», Grund: Instagram nicht erreichbar (URLError)"
    assert _knoepfe(texte.nochmals_tastatur(b)) == [("🔁 Nochmals versuchen", "n:3:1")]
    assert texte.verpasst_post(b, "Dateien fehlen") == \
        "⚠️ Verpasst: «X» (geplant Di 27.10., 19:00). Grund: Dateien fehlen"
    assert _knoepfe(texte.nachholen_tastatur(b)) == [("🔁 Jetzt posten", "j:3:1"), ("❌ Auslassen", "l:3:1")]
    assert texte.unklar(b) == "❓ Unklar, ob «X» online ist. Bitte auf Instagram nachschauen."
    assert "Instagram neu verbinden" in texte.schluessel_meldung("Instagram-Schlüssel fehlt")


def test_facebook_texte():
    from briefkasten import texte
    b = {"nr": 3, "version": 2, "titel": "T", "termin": "2026-10-28T19:00", "format": "karussell"}
    assert texte.gepostet(b, "https://ig/p") == "✅ Gepostet: «T»\nhttps://ig/p"
    assert texte.gepostet(b, "https://ig/p", "https://fb/p") == "✅ Gepostet: «T»\nhttps://ig/p\nFacebook: https://fb/p"
    assert texte.gepostet(b, None, "online") == "✅ Gepostet: «T»\nFacebook: online"
    assert texte.fb_nicht_gepostet(b, "weg") == (
        "⚠️ Facebook nicht gepostet: «T», Grund: weg\nAuf Instagram ist der Beitrag online.")
    knoepfe = texte.fb_tastatur(b)["inline_keyboard"][0]
    assert [(k["text"], k["callback_data"]) for k in knoepfe] == [("🔁 Nochmals", "fn:3:2"), ("⏭ Auslassen", "fl:3:2")]
    assert texte.fb_nachgeholt(b) == "✅ Facebook nachgeholt: «T»"
    assert "server/facebook.sh" in texte.fb_schluessel_meldung("Facebook-Schlüssel fehlt")
    assert "Instagram läuft weiter" in texte.fb_schluessel_meldung("x")
