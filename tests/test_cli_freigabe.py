from datetime import datetime

import pytest

from lib import cli, woche
from lib.briefkasten import BriefkastenFehler
from lib.entscheide import EntscheidFehler
from lib.manifest import ManifestFehler, schreibe_json
from lib.umgebung import Pfade
from lib.wochenplan import PlanFehler, Wochenplan, arbeitsfelder

WOCHE = "2026-KW44"


def _echt(cls, pfade, log):
    d = object.__new__(cls)
    d.briefkasten = object()
    return d


def _thema(nr=1, slug="drei-fehler", format="reel", status="gesendet"):
    t = arbeitsfelder({"nr": nr, "format": format, "termin": "2026-10-27T19:00", "slug": slug,
                       "thema": "x", "quelle": {"art": "ideen", "detail": "x"}, "vorlage": None,
                       "weiterschick": "x", "hook_idee": "x", "frage": None})
    t["status"] = status
    return t


def test_status_zeigt_freigabe(tmp_path):
    pfade = Pfade(basis=tmp_path)
    plan = Wochenplan.lade(pfade.plan(WOCHE), WOCHE)
    plan.themen.append(_thema())
    plan.speichere()
    beitraege = {"2026-KW44-reel-drei-fehler": {"status": "freigegeben", "version": 2}}
    assert woche.status_text(plan, beitraege).splitlines()[2].endswith("gesendet · freigegeben (Version 2)")
    assert woche.status_text(plan).splitlines()[2].endswith("gesendet")


def test_status_zeigt_neubauten_und_auffaelliges(tmp_path):
    pfade = Pfade(basis=tmp_path)
    plan = Wochenplan.lade(pfade.plan(WOCHE), WOCHE)
    plan.themen.extend([_thema(1, "eins"), _thema(2, "zwei"), _thema(3, "drei", "karussell"),
                    _thema(4, "vier", "karussell", "bereit"), _thema(5, "fuenf", "karussell", "gebaut")])
    plan.themen[1]["angemeldet"] = 2
    plan.daten["schritte"]["gesendet"] = "2026-10-24T20:00"
    plan.speichere()
    beitraege = {"2026-KW44-reel-eins": {"status": "entwurf", "version": 1},
                 "2026-KW44-reel-zwei": {"status": "entwurf", "version": 2, "neubauten": 1},
                 "2026-KW44-drei": {"status": "braucht_eingabe", "version": 1}}
    z = woche.status_text(plan, beitraege, umgestellt=True).splitlines()
    assert z[2].endswith("gesendet · entwurf · nicht angemeldet")
    # angemeldet, aber noch keine Adressen beim Briefkasten (Etappe 5)
    assert z[3].endswith("gesendet · entwurf (Version 2, 1 Neubau) · Dateien nicht hochgeladen")
    assert z[4].endswith("gesendet · braucht_eingabe · Platzhalter, nur Ändern/Verwerfen · nicht angemeldet")
    assert z[5].endswith("bereit · hängt (Woche schon gesendet)")
    assert z[6].endswith("gebaut · nicht gesendet")
    # vor der Umstellung gibt es keine Anmeldung, also auch keinen Hinweis darauf
    assert "nicht angemeldet" not in woche.status_text(plan, beitraege)
    assert woche.status_text(plan, beitraege).splitlines()[4].endswith(
        "gesendet · braucht_eingabe · Platzhalter, nur Ändern/Verwerfen")
    plan.themen[2]["angemeldet"] = 1
    assert woche.status_text(plan, beitraege, umgestellt=True).splitlines()[4].endswith(
        "gesendet · braucht_eingabe · Platzhalter, nur Ändern/Verwerfen · Dateien nicht hochgeladen")
    beitraege["2026-KW44-reel-zwei"]["medien_gemeldet"] = 2
    assert woche.status_text(plan, beitraege, umgestellt=True).splitlines()[3].endswith(
        "gesendet · entwurf (Version 2, 1 Neubau)")


def test_status_zeigt_gepostet_mit_link():
    from lib.woche import _freigabe_text
    t = {"status": "gesendet", "angemeldet": 1}
    b = {"status": "gepostet", "version": 1, "permalink": "https://www.instagram.com/reel/A/"}
    assert _freigabe_text(t, b, True, True) == " · gepostet · https://www.instagram.com/reel/A/"
    b = {"status": "freigegeben", "version": 1}
    assert "Dateien nicht hochgeladen" in _freigabe_text(t, b, True, True)
    assert "Dateien nicht hochgeladen" not in _freigabe_text(t, dict(b, medien_gemeldet=1), True, True)
    assert "Dateien nicht hochgeladen" not in _freigabe_text(t, b, True, False)


def test_cli_status_liest_manifest(tmp_path, capsys):
    pfade = Pfade(basis=tmp_path)
    plan = Wochenplan.lade(pfade.plan(WOCHE), WOCHE)
    plan.themen.append(_thema())
    plan.speichere()
    schreibe_json(pfade.woche(WOCHE) / "manifest.json",
                  {"woche": WOCHE, "beitraege": [{"id": "2026-KW44-reel-drei-fehler", "status": "verworfen"}]})
    assert cli.main(["woche", "status", "--woche", WOCHE, "--basis", str(tmp_path)]) == 0
    assert "gesendet · verworfen" in capsys.readouterr().out


def test_cli_status_kaputtes_manifest_einzeilig(tmp_path, capsys):
    pfade = Pfade(basis=tmp_path)
    Wochenplan.lade(pfade.plan(WOCHE), WOCHE).speichere()
    (pfade.woche(WOCHE) / "manifest.json").write_text("{kaputt", encoding="utf-8")
    assert cli.main(["woche", "status", "--woche", WOCHE, "--basis", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("Fehler: ") and err.count("\n") == 1


def test_cli_entscheide(monkeypatch, tmp_path):
    gesehen = []
    monkeypatch.setattr(cli, "entscheide", lambda pfade, dienste, log: gesehen.append(pfade.basis) or 2)
    monkeypatch.setattr(cli.Dienste, "echt", classmethod(_echt))
    assert cli.main(["entscheide", "--basis", str(tmp_path)]) == 0
    assert gesehen == [tmp_path]
    assert "2 Entscheid(e) umgesetzt" in (tmp_path / "logs" / "entscheide.log").read_text(encoding="utf-8")


def test_cli_entscheide_fehler(monkeypatch, tmp_path):
    def kaputt(pfade, dienste, log):
        raise BriefkastenFehler("Briefkasten nicht erreichbar (URLError)")
    monkeypatch.setattr(cli, "entscheide", kaputt)
    monkeypatch.setattr(cli.Dienste, "echt", classmethod(_echt))
    assert cli.main(["entscheide", "--basis", str(tmp_path)]) == 1
    assert "Fehler: Briefkasten nicht erreichbar" in (tmp_path / "logs" / "entscheide.log").read_text(encoding="utf-8")


@pytest.mark.parametrize("fehler", [EntscheidFehler("Briefkasten nicht eingerichtet"), PlanFehler("Plan kaputt"),
                                    ManifestFehler("Manifest\nkaputt"), woche.SperreBelegt("Läuft bereits")])
def test_cli_entscheide_bekannte_fehler_einzeilig(fehler, monkeypatch, tmp_path, capsys):
    def kaputt(pfade, dienste, log):
        raise fehler
    monkeypatch.setattr(cli, "entscheide", kaputt)
    monkeypatch.setattr(cli.Dienste, "echt", classmethod(_echt))
    assert cli.main(["entscheide", "--basis", str(tmp_path)]) == 1
    zeilen = (tmp_path / "logs" / "entscheide.log").read_text(encoding="utf-8").splitlines()
    assert len(zeilen) == 1 and "Fehler: " in zeilen[0]
    assert "Traceback" not in capsys.readouterr().err


def test_cli_entscheide_programmierfehler_nicht_verschluckt(monkeypatch, tmp_path):
    def kaputt(pfade, dienste, log):
        raise KeyError("woche")
    monkeypatch.setattr(cli, "entscheide", kaputt)
    monkeypatch.setattr(cli.Dienste, "echt", classmethod(_echt))
    with pytest.raises(KeyError):
        cli.main(["entscheide", "--basis", str(tmp_path)])


def test_cli_entscheide_ohne_briefkasten_still(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "entscheide", lambda *a: pytest.fail("darf nicht laufen"))
    monkeypatch.setattr(cli.Dienste, "echt", classmethod(lambda cls, pfade, log: object.__new__(cls)))
    assert cli.main(["entscheide", "--basis", str(tmp_path)]) == 0
    zeilen = (tmp_path / "logs" / "entscheide.log").read_text(encoding="utf-8").splitlines()
    assert len(zeilen) == 1 and "nicht eingerichtet" in zeilen[0]


def test_cli_umstellen_nennt_naechsten_schritt(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "umstellen", lambda daten, adresse, bot: 41)
    monkeypatch.setattr(cli, "uhr", lambda: datetime(2026, 10, 25, 10, 0))
    plan = Wochenplan.lade(Pfade(basis=tmp_path).plan(WOCHE), WOCHE)
    plan.daten["schritte"]["gesendet"] = "2026-10-24T22:00"
    plan.speichere()
    assert cli.main(["briefkasten", "umstellen", "--basis", str(tmp_path)]) == 0
    assert "Als Nächstes: fliessband woche anmelden --woche 2026-KW44" in capsys.readouterr().out


def test_cli_umstellen_naechster_schritt_ohne_plan(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "umstellen", lambda daten, adresse, bot: 41)
    monkeypatch.setattr(cli, "uhr", lambda: datetime(2026, 10, 27, 10, 0))
    assert cli.main(["briefkasten", "umstellen", "--basis", str(tmp_path)]) == 0
    assert "Als Nächstes: fliessband woche anmelden --woche 2026-KW45" in capsys.readouterr().out


def test_cli_umstellen(monkeypatch, tmp_path, capsys):
    gesehen = []
    monkeypatch.setattr(cli, "umstellen", lambda daten, adresse, bot: gesehen.append((daten, adresse)) or 41)
    assert cli.main(["briefkasten", "umstellen", "--basis", str(tmp_path)]) == 0
    assert gesehen == [(tmp_path / "daten", "http://your-server-ip:8096")]
    assert "ab Update 42" in capsys.readouterr().out


def test_cli_umstellen_fehler_einzeilig(monkeypatch, tmp_path, capsys):
    def kaputt(daten, adresse, bot):
        raise BriefkastenFehler("Umgestellt, aber der Server fragt ab update_id 7 statt 5 ab\n(bitte prüfen)")
    monkeypatch.setattr(cli, "umstellen", kaputt)
    assert cli.main(["briefkasten", "umstellen", "--adresse", "http://x:1", "--basis", str(tmp_path)]) == 1
    assert capsys.readouterr().err == ("Fehler: Umgestellt, aber der Server fragt ab update_id 7 statt 5 ab "
                                       "(bitte prüfen)\n")


def test_cli_bot_einrichten_nach_umstellung(tmp_path, monkeypatch, capsys):
    class FalscherBot:
        def __init__(self, stand):
            pass

        def einrichten(self):
            raise AssertionError("darf Telegram nicht mehr abfragen")
    monkeypatch.setattr(cli, "Bot", FalscherBot)
    schreibe_json(tmp_path / "daten" / "briefkasten.json", {"adresse": "http://x:1"})
    assert cli.main(["bot", "einrichten", "--basis", str(tmp_path)]) == 1
    assert "schon umgestellt" in capsys.readouterr().err


def test_anmelden_ohne_briefkasten(wochen_umgebung, agentur_attrappe):
    u = wochen_umgebung
    woche.vorbereiten(WOCHE, u.pfade, u.dienste(agentur_attrappe(fragen=0)), lambda t: None)
    log = []
    assert woche.fuehre_aus("anmelden", WOCHE, u.pfade, u.dienste(agentur_attrappe()), log.append) == 1
    assert any("nicht eingerichtet" in z for z in log)


def test_anmelden_woche_noch_nicht_gesendet(wochen_umgebung, agentur_attrappe, briefkasten):
    u = wochen_umgebung
    woche.vorbereiten(WOCHE, u.pfade, u.dienste(agentur_attrappe(fragen=0)), lambda t: None)
    log = []
    assert woche.fuehre_aus("anmelden", WOCHE, u.pfade, u.dienste(agentur_attrappe(), briefkasten=briefkasten),
                            log.append) == 1
    assert any("Woche noch nicht gesendet" in z for z in log)
    assert briefkasten.gemeldet == []
