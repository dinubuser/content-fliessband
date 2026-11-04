from pathlib import Path

from lib import fakten
from tests.test_woche_bauen import _bauen, _plan, _vorbereitet, gebaut  # noqa: F401  (Fixture gebaut)


def _sprechtext(auftrag):
    for z in auftrag.splitlines():
        if z.startswith("Sprechtext: "):
            return z[len("Sprechtext: "):]
    return None


def _antwort(auftrag):
    stelle = _sprechtext(auftrag)
    if stelle is None:
        return {"geprueft": 2, "funde": []}
    return {"geprueft": 5, "funde": [{"stelle": stelle, "urteil": "falsch", "korrektur": stelle + " (laut BAG)",
                                      "quelle": "https://www.bag.admin.ch/x", "grund": "Test"}]}


def test_bau_ruft_check_und_speichert_ergebnis(wochen_umgebung, agentur_attrappe, gebaut):
    u, a = wochen_umgebung, agentur_attrappe(fragen=0)
    a.fakten_antwort = {"geprueft": 3, "funde": []}
    _vorbereitet(u, a, fragen=False)
    _bauen(u, a)
    gebaute = [t for t in _plan(u).aktive() if t["status"] in ("gebaut", "gesendet")]
    assert gebaute and all(t["fakten"] == {"lief": True, "geprueft": 3, "korrigiert": [], "offen": [], "markiert": True} for t in gebaute)
    assert a.anzahl("fakten-agent") == len(gebaute)


def test_korrektur_landet_im_skript_und_in_der_telegram_zeile(wochen_umgebung, agentur_attrappe, gebaut):
    u, a = wochen_umgebung, agentur_attrappe(fragen=0)
    a.fakten_antwort = _antwort
    _vorbereitet(u, a, fragen=False)
    _bauen(u, a)
    reels = [t for t in _plan(u).aktive() if t["format"] == "reel"]
    assert reels
    for t in reels:
        assert len(t["fakten"]["korrigiert"]) == 1
        assert "(laut BAG)" in Path(t["beitrag"]).read_text(encoding="utf-8")
    texte = u.telegram.texte()
    assert any(z.startswith("🔎 Faktencheck: 5 Aussagen geprüft, 1 korrigiert:") and "(bag.admin.ch)" in z for z in texte)


def test_ausfall_zeigt_warnzeile_und_baut_trotzdem(wochen_umgebung, agentur_attrappe, gebaut):
    u, a = wochen_umgebung, agentur_attrappe(fragen=0)
    a.fakten_antwort = "kein json"   # gültiges JSON, aber ohne 'geprueft' und 'funde'
    _vorbereitet(u, a, fragen=False)
    _bauen(u, a)
    assert len(gebaut) > 0
    assert u.telegram.texte().count("⚠️ Faktencheck nicht gelaufen, bitte selbst prüfen") == len(gebaut)


def test_schalter_aus_ruft_keinen_agenten_und_sendet_keine_zeile(wochen_umgebung, agentur_attrappe, gebaut):
    u, a = wochen_umgebung, agentur_attrappe(fragen=0)
    fakten.setze(u.pfade.basis, False)
    _vorbereitet(u, a, fragen=False)
    _bauen(u, a)
    assert a.anzahl("fakten-agent") == 0
    assert not any("Faktencheck" in z for z in u.telegram.texte())
    assert all(t.get("fakten") is None for t in _plan(u).aktive())


def test_gespeichertes_ergebnis_wird_bei_wiederaufnahme_nicht_neu_geprueft(wochen_umgebung, agentur_attrappe, gebaut,
                                                                          monkeypatch):
    import pytest
    from lib import woche
    u = wochen_umgebung
    a = agentur_attrappe(fragen=0)
    a.fakten_antwort = {"geprueft": 3, "funde": []}
    _vorbereitet(u, a, fragen=False)
    echt = woche.baue_reel

    def abbruch(quelle, **kw):
        if "drei-fehler" in str(quelle):
            raise KeyboardInterrupt
        return echt(quelle, **kw)
    monkeypatch.setattr(woche, "baue_reel", abbruch)
    with pytest.raises(KeyboardInterrupt):
        _bauen(u, agentur_attrappe(fragen=0))
    gespeichert = next(t for t in _plan(u).aktive() if "drei-fehler" in t["beitrag"])
    assert gespeichert["fakten"]["lief"] is True       # schon vor dem Absturz gespeichert
    monkeypatch.setattr(woche, "baue_reel", echt)
    a2 = agentur_attrappe(fragen=0)
    a2.fakten_antwort = {"geprueft": 3, "funde": []}
    _bauen(u, a2)
    pruefer = [n for ag, n in a2.aufrufe if ag == "fakten-agent"]
    assert a2.anzahl("fakten-agent") == 1 and not any("drei-fehler" in n for n in pruefer)
    assert sum(1 for z in u.telegram.texte() if z.startswith("🔎 Faktencheck: 3 Aussagen geprüft")) >= 1
    nach = next(t for t in _plan(u).aktive() if "drei-fehler" in t["beitrag"])
    assert nach["fakten"]["lief"] is True
