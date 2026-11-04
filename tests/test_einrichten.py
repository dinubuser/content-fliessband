"""./fliessband einrichten: reine Prüfung der Einrichtung in neun Schritten. Liest nur, ändert nichts, zeigt nie einen Wert."""
import json
from pathlib import Path

import pytest

from lib import cli, einrichten
from lib.briefkasten import BriefkastenFehler
from lib.einrichten import Umfeld, exitcode, naechster_schritt, pruefe, text

ANLEITUNG = Path(__file__).resolve().parent.parent / "docs" / "anleitung"
AGENTEN = ["content-agent", "trend-agent", "follower-agent", "viral-agent", "analyse-agent",
           "aussprache-agent", "fakten-agent", "trend-scout"]
ENV = {"FLIESSBAND_HANDLE": "@meinkonto", "ELEVENLABS_VOICE_ID": "voice-abc123", "FLIESSBAND_WP_URL": "https://meine-seite.ch",
       "FLIESSBAND_WP_KONTO": "redakteur", "FLIESSBAND_BRIEFKASTEN_URL": "http://100.64.0.9:8096",
       "FLIESSBAND_SERVER": "root@100.64.0.9", "FLIESSBAND_SSH_KEY": "SCHLUESSELDATEI"}


class FakeBriefkasten:
    def __init__(self, poster=None, facebook=None, fehler=None):
        self._poster = poster if poster is not None else {"an": True, "schluessel_tage": 12, "naechste": []}
        self._facebook = facebook if facebook is not None else {"an": False, "schluessel": True, "posts": []}
        self.fehler = fehler

    def poster_stand(self):
        if self.fehler:
            raise self.fehler
        return self._poster

    def facebook_stand(self):
        if self.fehler:
            raise self.fehler
        return self._facebook


def gut(tmp_path, env=None, schluessel=None, **kw) -> Umfeld:
    """Eine vollständig eingerichtete Umgebung in tmp_path. Tests brechen genau eine Sache."""
    home, basis = tmp_path / "home", tmp_path / "fb"
    skill, agentur = home / ".claude" / "skills" / "agentur", home / "meine-agentur"
    for p in (skill / "tools", agentur, basis / "daten", home / ".claude" / "agents", basis / "node_modules", basis / ".venv" / "bin"):
        p.mkdir(parents=True, exist_ok=True)
    (basis / ".venv" / "bin" / "python").write_text("")
    for name in ("profil.md", "stimme.md", "learnings.md"):
        (agentur / name).write_text("x")
    for a in AGENTEN:
        (home / ".claude" / "agents" / f"{a}.md").write_text("x")
    (basis / "daten" / "bot.json").write_text(json.dumps({"chat_id": 4711, "letzte_update_id": 1}))
    (basis / "daten" / "briefkasten.json").write_text(json.dumps({"adresse": "http://x", "nachrichten_bis": 0}))
    ssh = home / ".ssh" / "schluessel"
    ssh.parent.mkdir(parents=True)
    ssh.write_text("x")
    werte = {**ENV, "FLIESSBAND_SSH_KEY": str(ssh), **(env or {})}
    vorhanden = schluessel if schluessel is not None else {("fliessband-telegram", None), ("elevenlabs-api", None),
                                                          ("fliessband-wp", "redakteur"), ("fliessband-briefkasten", "fliessband")}
    felder = dict(
        basis=basis, home=home, skill=skill, agentur=agentur, agentur_python=home / "py" / "python",
        python=(3, 12), finde=lambda p: f"/usr/bin/{p}", befehl=lambda a: "v22.5.0\n",
        wert=lambda n: werte.get(n, ""), schluessel=lambda d, k=None: (d, k) in vorhanden or (d, None) in vorhanden and k is None,
        launchd=lambda: "".join(f"-\t0\tcom.example.fliessband-{j}\n" for j in ("lernen", "vorbereiten", "bauen", "entscheide")),
        briefkasten=lambda: FakeBriefkasten())
    (home / "py").mkdir()
    (home / "py" / "python").write_text("")
    felder.update(kw)
    return Umfeld(**felder)


def status(schritte):
    return {s.nr: s.status for s in schritte}


def test_alles_gut_offline(tmp_path):
    s = pruefe(gut(tmp_path), online=False)
    assert [x.nr for x in s] == list(range(1, 10))
    assert status(s) == {1: "ok", 2: "ok", 3: "ok", 4: "ok", 5: "ok", 6: "ok", 7: "uebersprungen", 8: "ok", 9: "manuell"}
    assert exitcode(s) == 0 and naechster_schritt(s) is None


def test_alles_gut_online(tmp_path):
    s = pruefe(gut(tmp_path), online=True)
    assert status(s)[6] == "ok" and status(s)[7] == "ok"
    assert exitcode(s) == 0


@pytest.mark.parametrize("aenderung,wort", [
    ({"python": (3, 11)}, "Python"),
    ({"finde": lambda p: None if p == "claude" else f"/usr/bin/{p}"}, "claude"),
    ({"finde": lambda p: None if p == "ffmpeg" else f"/usr/bin/{p}"}, "ffmpeg"),
    ({"befehl": lambda a: "v20.1.0\n"}, "Node"),
    ({"befehl": lambda a: None}, "Node"),
])
def test_schritt_1_voraussetzungen(tmp_path, aenderung, wort):
    s = pruefe(gut(tmp_path, **aenderung))
    assert status(s)[1] == "offen"
    assert wort in text(s)


def test_schritt_1_ohne_venv_oder_node_pakete(tmp_path):
    u = gut(tmp_path)
    (u.basis / ".venv" / "bin" / "python").unlink()
    assert status(pruefe(u))[1] == "offen" and "install.sh" in text(pruefe(u))
    u = gut(tmp_path / "zwei")
    (u.basis / "node_modules").rmdir()
    assert status(pruefe(u))[1] == "offen"


def test_schritt_2_agentur(tmp_path):
    u = gut(tmp_path)
    (u.agentur / "profil.md").unlink()
    (u.home / ".claude" / "agents" / "fakten-agent.md").unlink()
    s = pruefe(u)
    assert status(s)[2] == "offen"
    t = text(s)
    assert "profil.md" in t and "fakten-agent" in t
    u2 = gut(tmp_path / "b", env={"FLIESSBAND_HANDLE": "@dein.konto"})
    assert status(pruefe(u2))[2] == "offen" and "FLIESSBAND_HANDLE" in text(pruefe(u2))
    u3 = gut(tmp_path / "c")
    u3.skill.rmdir() if not list(u3.skill.iterdir()) else None
    import shutil
    shutil.rmtree(u3.skill)
    assert status(pruefe(u3))[2] == "offen"


@pytest.mark.parametrize("schritt,env", [(3, {"ELEVENLABS_VOICE_ID": "your-elevenlabs-voice-id"}), (3, {"ELEVENLABS_VOICE_ID": ""}),
                                         (5, {"FLIESSBAND_WP_URL": "https://example.com"}), (5, {"FLIESSBAND_WP_URL": "http://meine-seite.ch"}),
                                         (5, {"FLIESSBAND_WP_KONTO": "your-wp-user"}),
                                         (6, {"FLIESSBAND_SERVER": "root@your-server-ip"}), (6, {"FLIESSBAND_BRIEFKASTEN_URL": "http://your-server-ip:8096"})])
def test_platzhalter_und_fehlende_werte(tmp_path, schritt, env):
    s = pruefe(gut(tmp_path, env=env))
    assert status(s)[schritt] == "offen"
    assert next(k for k in env) in text(s)


def test_schritt_3_und_4_und_5_und_6_brauchen_ihren_schluessel(tmp_path):
    for fehlt, schritt in [(("elevenlabs-api", None), 3), (("fliessband-telegram", None), 4),
                           (("fliessband-wp", "redakteur"), 5), (("fliessband-briefkasten", "fliessband"), 6)]:
        alle = {("fliessband-telegram", None), ("elevenlabs-api", None), ("fliessband-wp", "redakteur"),
                ("fliessband-briefkasten", "fliessband")}
        s = pruefe(gut(tmp_path / str(schritt), schluessel=alle - {fehlt}))
        assert status(s)[schritt] == "offen", schritt
        assert "Schlüsselbund" in text(s)


def test_elevenlabs_schluessel_darf_in_env_local_oder_umgebung_stehen(tmp_path):
    ohne = {("fliessband-telegram", None), ("fliessband-wp", "redakteur"), ("fliessband-briefkasten", "fliessband")}
    u = gut(tmp_path, schluessel=ohne)
    assert status(pruefe(u))[3] == "offen"
    (u.basis / ".env.local").write_text("ELEVENLABS_API_KEY=\n")   # leer zählt nicht
    assert status(pruefe(u))[3] == "offen"
    (u.basis / ".env.local").write_text("# Kommentar\nELEVENLABS_API_KEY=sk_geheim_123\n")
    s = pruefe(u)
    assert status(s)[3] == "ok" and "sk_geheim_123" not in text(s)
    u2 = gut(tmp_path / "b", env={"ELEVENLABS_API_KEY": "sk_geheim_456"}, schluessel=ohne)
    assert status(pruefe(u2))[3] == "ok"


def test_schritt_4_telegram_chat_id(tmp_path):
    u = gut(tmp_path)
    (u.basis / "daten" / "bot.json").write_text(json.dumps({"letzte_update_id": 3}))
    assert status(pruefe(u))[4] == "offen" and "bot einrichten" in text(pruefe(u))
    (u.basis / "daten" / "bot.json").write_text("kaputt")
    assert status(pruefe(u))[4] == "offen"
    (u.basis / "daten" / "bot.json").unlink()
    assert status(pruefe(u))[4] == "offen"


def test_schritt_6_server(tmp_path):
    u = gut(tmp_path)
    (u.basis / "daten" / "briefkasten.json").unlink()
    s = pruefe(u)
    assert status(s)[6] == "offen" and "umstellen" in text(s)
    u2 = gut(tmp_path / "b", env={"FLIESSBAND_SSH_KEY": str(tmp_path / "gibt-es-nicht")})
    assert status(pruefe(u2))[6] == "offen" and "FLIESSBAND_SSH_KEY" in text(pruefe(u2))


def test_online_server_nicht_erreichbar(tmp_path):
    u = gut(tmp_path, briefkasten=lambda: FakeBriefkasten(fehler=BriefkastenFehler("Briefkasten nicht erreichbar (URLError: Zeitüberschreitung)")))
    s = pruefe(u, online=True)
    assert status(s)[6] == "offen" and "nicht erreichbar" in text(s)
    assert status(s)[7] == "offen" and "Schritt 6" in text(s)


def test_online_instagram_schluessel(tmp_path):
    def mit(tage):
        return gut(tmp_path / str(tage), briefkasten=lambda: FakeBriefkasten(poster={"an": True, "schluessel_tage": tage}))
    assert status(pruefe(mit(30), online=True))[7] == "ok"
    s = pruefe(mit(55), online=True)
    assert status(s)[7] == "ok" and "läuft bald ab" in text(s)
    assert status(pruefe(mit(60), online=True))[7] == "offen"
    assert status(pruefe(mit(None), online=True))[7] == "offen"


def test_facebook_ist_optional(tmp_path):
    t = text(pruefe(gut(tmp_path), online=True))
    assert "Facebook" in t and "optional" in t
    u = gut(tmp_path / "b", env={"FLIESSBAND_FB_APP_ID": "123", "FLIESSBAND_FB_SEITE": "Meine Seite"})
    assert status(pruefe(u, online=True))[7] == "offen"   # App-Geheimcode fehlt im Schlüsselbund
    alle = {("fliessband-telegram", None), ("elevenlabs-api", None), ("fliessband-wp", "redakteur"),
            ("fliessband-briefkasten", "fliessband"), ("fliessband-facebook-app", "fliessband")}
    u2 = gut(tmp_path / "c", env={"FLIESSBAND_FB_APP_ID": "123", "FLIESSBAND_FB_SEITE": "Meine Seite"}, schluessel=alle)
    assert status(pruefe(u2, online=True))[7] == "ok"
    u3 = gut(tmp_path / "d", env={"FLIESSBAND_FB_APP_ID": "123", "FLIESSBAND_FB_SEITE": "Meine Seite"}, schluessel=alle,
             briefkasten=lambda: FakeBriefkasten(facebook={"an": False, "schluessel": False}))
    assert status(pruefe(u3, online=True))[7] == "offen"


def test_schritt_8_jobs(tmp_path):
    u = gut(tmp_path, launchd=lambda: "-\t0\tcom.example.fliessband-lernen\n")
    s = pruefe(u)
    assert status(s)[8] == "offen" and "bauen" in text(s) and "install.sh --launchd" in text(s)
    assert status(pruefe(gut(tmp_path / "b", launchd=lambda: None)))[8] == "offen"


def test_schritt_9_erster_lauf(tmp_path):
    u = gut(tmp_path)
    assert status(pruefe(u))[9] == "manuell"
    (u.basis / "wochen" / "2026-KW46").mkdir(parents=True)
    (u.basis / "wochen" / "2026-KW46" / "plan.json").write_text("{}")
    assert status(pruefe(u))[9] == "ok"


def test_naechster_schritt_und_exitcode(tmp_path):
    s = pruefe(gut(tmp_path, env={"ELEVENLABS_VOICE_ID": ""}, launchd=lambda: ""))
    assert naechster_schritt(s).nr == 3
    t = text(s)
    assert "Nächster Schritt: 3" in t and "docs/anleitung/03-elevenlabs.md" in t
    assert exitcode(s) == 1


def test_zeigt_nie_einen_wert(tmp_path):
    u = gut(tmp_path, env={"ELEVENLABS_VOICE_ID": "voice-GEHEIM123", "FLIESSBAND_WP_URL": "http://seite-GEHEIM123.ch"})
    t = text(pruefe(u))
    assert "GEHEIM123" not in t


def test_schluessel_pruefung_liest_den_wert_nie():
    aufrufe = []

    class R:
        returncode = 0
        stdout = "geheimer-wert"

    einrichten.schluessel_vorhanden("fliessband-wp", "redakteur", runner=lambda args, **k: aufrufe.append(args) or R())
    einrichten.schluessel_vorhanden("elevenlabs-api", None, runner=lambda args, **k: aufrufe.append(args) or R())
    assert aufrufe[0] == ["security", "find-generic-password", "-s", "fliessband-wp", "-a", "redakteur"]
    assert aufrufe[1] == ["security", "find-generic-password", "-s", "elevenlabs-api"]
    assert all("-w" not in a and "-g" not in a for a in aufrufe)


def test_cli_einrichten(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(einrichten.Umfeld, "echt", classmethod(lambda cls, basis: gut(tmp_path)))
    assert cli.main(["einrichten"]) == 0
    assert "Einrichtung" in capsys.readouterr().out
    monkeypatch.setattr(einrichten.Umfeld, "echt", classmethod(lambda cls, basis: gut(tmp_path / "b", env={"ELEVENLABS_VOICE_ID": ""})))
    assert cli.main(["einrichten", "--online"]) == 1


def test_jedes_kapitel_der_pruefung_gibt_es(tmp_path):
    for s in pruefe(gut(tmp_path)):
        assert (ANLEITUNG / Path(s.kapitel).name).is_file(), s.kapitel
