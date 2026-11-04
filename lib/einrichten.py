"""./fliessband einrichten: Prüfung der Einrichtung in neun Schritten, je Schritt ein Kapitel in docs/anleitung/.

Der Assistent LIEST nur: Er ändert nichts, legt keine Konten an, schreibt keine Schlüssel und zeigt nie einen Wert
(auch keinen Wert aus der .env). Im Schlüsselbund fragt er nur, ob ein Eintrag da ist, nie nach dem Inhalt.
Mit --online fragt er zusätzlich den Server ab (Briefkasten, Instagram- und Facebook-Schlüssel).
"""
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from lib import konfig
from lib.briefkasten import Briefkasten, BriefkastenFehler
from lib.fehler import einzeilig
from lib.umgebung import Pfade

PLATZHALTER = re.compile(r"your[-_]|dein\.konto|example\.com")
AGENTEN = ("content-agent", "trend-agent", "follower-agent", "viral-agent", "analyse-agent",
           "aussprache-agent", "fakten-agent", "trend-scout")
JOBS = ("lernen", "vorbereiten", "bauen", "entscheide")
JOB_PRAEFIX = "com.example.fliessband-"
SCHLUESSEL_WARNUNG, SCHLUESSEL_ABLAUF = 50, 60   # Instagram-Schlüssel gilt 60 Tage, die Agentur erinnert ab Tag 50
KAPITEL = "docs/anleitung/"
TITEL = {
    1: ("Voraussetzungen", "01-voraussetzungen.md"),
    2: ("Agentur und Konto", "02-agentur.md"),
    3: ("Stimme (ElevenLabs)", "03-elevenlabs.md"),
    4: ("Telegram", "04-telegram.md"),
    5: ("WordPress-Mediathek", "05-wordpress.md"),
    6: ("Server und Briefkasten", "06-server.md"),
    7: ("Instagram und Facebook", "07-instagram-facebook.md"),
    8: ("Jobs (launchd)", "08-jobs.md"),
    9: ("Erster Lauf", "09-erster-lauf.md"),
}


def schluessel_vorhanden(dienst: str, konto: str | None = None, runner=subprocess.run) -> bool:
    """Ist der Eintrag im Schlüsselbund da? Ohne -w und -g: der Inhalt wird nie gelesen."""
    args = ["security", "find-generic-password", "-s", dienst] + (["-a", konto] if konto else [])
    try:
        return runner(args, capture_output=True, text=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _befehl(args: list[str]) -> str | None:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


@dataclass
class Umfeld:
    """Alles, was die Prüfung von aussen liest. Tests tauschen die Funktionen aus."""
    basis: Path
    home: Path
    skill: Path
    agentur: Path
    agentur_python: Path
    python: tuple
    finde: Callable[[str], str | None]
    befehl: Callable[[list[str]], str | None]
    wert: Callable[[str], str]
    schluessel: Callable[..., bool]
    launchd: Callable[[], str | None]
    briefkasten: Callable[[], object | None]

    @classmethod
    def echt(cls, basis: Path) -> "Umfeld":
        pfade = Pfade(basis=Path(basis))
        return cls(basis=Path(basis), home=Path.home(), skill=pfade.skill, agentur=pfade.agentur,
                   agentur_python=pfade.agentur_python, python=tuple(sys.version_info[:2]), finde=shutil.which,
                   befehl=_befehl, wert=lambda n: konfig.wert(n), schluessel=schluessel_vorhanden,
                   launchd=lambda: _befehl(["launchctl", "list"]),
                   briefkasten=lambda: Briefkasten.lade(Path(basis) / "daten"))


@dataclass
class Schritt:
    nr: int
    titel: str
    kapitel: str
    status: str = "ok"     # ok, offen, uebersprungen, manuell
    zeilen: list = field(default_factory=list)   # (True ok, False fehlt, None Hinweis), Text

    def pruefung(self, ok, text: str) -> bool:
        self.zeilen.append((ok, text))
        if ok is False:
            self.status = "offen"
        return ok is not False


def _schritt(nr: int) -> Schritt:
    titel, datei = TITEL[nr]
    return Schritt(nr, titel, KAPITEL + datei)


def _gesetzt(u: Umfeld, name: str) -> bool:
    v = (u.wert(name) or "").strip()
    return bool(v) and not PLATZHALTER.search(v)


def _wert_pruefen(s: Schritt, u: Umfeld, name: str, was: str) -> bool:
    return s.pruefung(True if _gesetzt(u, name) else False,
                      f"{name} ist gesetzt" if _gesetzt(u, name) else f"{name} fehlt oder ist noch ein Platzhalter ({was})")


def _schluessel_pruefen(s: Schritt, u: Umfeld, dienst: str, konto: str | None, wofuer: str) -> bool:
    ok = bool(u.schluessel(dienst, konto)) if konto else bool(u.schluessel(dienst))
    return s.pruefung(ok, f"Schlüsselbund: {dienst} ist da" if ok else
                      f"Schlüsselbund: Eintrag {dienst}{f' (Konto {konto})' if konto else ''} fehlt ({wofuer})")


def _voraussetzungen(u: Umfeld) -> Schritt:
    s = _schritt(1)
    a, b = u.python[:2]
    s.pruefung((a, b) >= (3, 12), f"Python {a}.{b}" if (a, b) >= (3, 12) else f"Python {a}.{b} ist zu alt, nötig ist 3.12")
    node = u.befehl(["node", "--version"]) if u.finde("node") else None
    m = re.match(r"v(\d+)", (node or "").strip())
    s.pruefung(bool(m) and int(m.group(1)) >= 22,
               f"Node {node.strip()}" if m and int(m.group(1)) >= 22 else "Node 22 oder neuer fehlt")
    for programm in ("ffmpeg", "claude"):
        s.pruefung(bool(u.finde(programm)), f"{programm} gefunden" if u.finde(programm) else f"{programm} fehlt (nicht im PATH)")
    ok = (u.basis / ".venv" / "bin" / "python").exists()
    s.pruefung(ok, ".venv da" if ok else ".venv fehlt: ./install.sh ausführen")
    ok = (u.basis / "node_modules").is_dir()
    s.pruefung(ok, "Node-Pakete da" if ok else "Node-Pakete fehlen: ./install.sh ausführen")
    return s


def _agentur(u: Umfeld) -> Schritt:
    s = _schritt(2)
    s.pruefung(u.skill.is_dir(), "Agentur-Skill da" if u.skill.is_dir() else f"Agentur-Skill fehlt: {u.skill}")
    s.pruefung(u.agentur_python.exists(), "Agentur-Python da" if u.agentur_python.exists() else f"Agentur-Python fehlt: {u.agentur_python}")
    fehlend = [n for n in ("profil.md", "stimme.md", "learnings.md") if not (u.agentur / n).is_file()]
    s.pruefung(not fehlend, "Agentur-Daten da (profil.md, stimme.md, learnings.md)" if not fehlend
               else f"In {u.agentur} fehlt: {', '.join(fehlend)}")
    fehlend = [a for a in AGENTEN if not (u.home / ".claude" / "agents" / f"{a}.md").is_file()]
    s.pruefung(not fehlend, f"Agenten da ({len(AGENTEN)})" if not fehlend
               else f"Agenten fehlen in ~/.claude/agents: {', '.join(fehlend)} (Agentur installieren, ./install.sh)")
    _wert_pruefen(s, u, "FLIESSBAND_HANDLE", "dein Instagram-Handle")
    return s


def _elevenlabs_schluessel_lokal(u: Umfeld) -> bool:
    """Wie lib/stimme.py: erst Umgebung, dann .env.local im Projekt, sonst der Schlüsselbund. Nur ob etwas da ist."""
    if (u.wert("ELEVENLABS_API_KEY") or "").strip():
        return True
    try:
        zeilen = (u.basis / ".env.local").read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    return any(z.strip().startswith("ELEVENLABS_API_KEY=") and z.split("=", 1)[1].strip().strip("\"'") for z in zeilen)


def _stimme(u: Umfeld) -> Schritt:
    s = _schritt(3)
    _wert_pruefen(s, u, "ELEVENLABS_VOICE_ID", "Stimmen-ID aus ElevenLabs")
    if _elevenlabs_schluessel_lokal(u):
        s.pruefung(True, "ElevenLabs-Schlüssel in .env.local oder der Umgebung da")
    else:
        _schluessel_pruefen(s, u, "elevenlabs-api", None, "ElevenLabs-API-Schlüssel, alternativ ELEVENLABS_API_KEY in .env.local")
    return s


def _telegram(u: Umfeld) -> Schritt:
    s = _schritt(4)
    _schluessel_pruefen(s, u, "fliessband-telegram", None, "Token des Bots von @BotFather")
    try:
        chat = json.loads((u.basis / "daten" / "bot.json").read_text(encoding="utf-8")).get("chat_id")
    except (OSError, ValueError, AttributeError):
        chat = None
    s.pruefung(bool(chat), "Chat-ID gespeichert (daten/bot.json)" if chat else
               "Chat-ID fehlt: dem Bot /start schreiben, dann ./fliessband bot einrichten")
    return s


def _wordpress(u: Umfeld) -> Schritt:
    s = _schritt(5)
    url_ok = _gesetzt(u, "FLIESSBAND_WP_URL")
    if url_ok and not u.wert("FLIESSBAND_WP_URL").strip().startswith("https://"):
        url_ok = False
        s.pruefung(False, "FLIESSBAND_WP_URL muss mit https:// beginnen")
    elif url_ok:
        s.pruefung(True, "FLIESSBAND_WP_URL ist gesetzt")
    else:
        _wert_pruefen(s, u, "FLIESSBAND_WP_URL", "Adresse deiner WordPress-Seite")
    if _wert_pruefen(s, u, "FLIESSBAND_WP_KONTO", "WordPress-Benutzer"):
        dienst = (u.wert("FLIESSBAND_WP_DIENST") or "fliessband-wp").strip()
        _schluessel_pruefen(s, u, dienst, u.wert("FLIESSBAND_WP_KONTO").strip(), "WordPress-Anwendungspasswort")
    return s


def _server(u: Umfeld, online: bool) -> tuple[Schritt, bool]:
    """(Schritt, Server antwortet). Der zweite Wert ist nur mit online=True aussagekräftig."""
    s = _schritt(6)
    _wert_pruefen(s, u, "FLIESSBAND_SERVER", "SSH-Ziel, z.B. root@<Tailscale-IP>")
    _wert_pruefen(s, u, "FLIESSBAND_BRIEFKASTEN_URL", "Adresse des Briefkastens")
    if _wert_pruefen(s, u, "FLIESSBAND_SSH_KEY", "SSH-Schlüssel für den Server"):
        ok = Path(u.wert("FLIESSBAND_SSH_KEY").strip()).expanduser().is_file()
        s.pruefung(ok, "SSH-Schlüsseldatei da" if ok else "FLIESSBAND_SSH_KEY zeigt auf eine Datei, die es nicht gibt")
    _schluessel_pruefen(s, u, "fliessband-briefkasten", "fliessband", "von server/zugang.sh angelegt")
    umgestellt = (u.basis / "daten" / "briefkasten.json").exists()
    s.pruefung(umgestellt, "Briefkasten umgestellt" if umgestellt else
               "Briefkasten noch nicht umgestellt: ./fliessband briefkasten umstellen")
    antwortet = False
    if online:
        bk = u.briefkasten()
        if bk is None:
            s.pruefung(None, "Server nicht abgefragt (Briefkasten noch nicht umgestellt)")
        else:
            try:
                bk.poster_stand()
                antwortet = True
                s.pruefung(True, "Server antwortet")
            except BriefkastenFehler as e:
                s.pruefung(False, f"Server antwortet nicht: {einzeilig(e)[:200]}")
    return s, antwortet


def _instagram(u: Umfeld, online: bool, server_ok: bool) -> Schritt:
    s = _schritt(7)
    fb_gestartet = _gesetzt(u, "FLIESSBAND_FB_APP_ID")
    if not online:
        s.status = "uebersprungen"
        s.pruefung(None, "Braucht den Server: mit ./fliessband einrichten --online prüfen")
        s.pruefung(None, "Facebook (optional): mit --online geprüft" if fb_gestartet else "Facebook (optional): nicht eingerichtet")
        return s
    if not server_ok:
        s.pruefung(False, "Zuerst Schritt 6 klären, ohne Server kein Blick auf Instagram")
        return s
    bk = u.briefkasten()
    try:
        poster = bk.poster_stand()
    except BriefkastenFehler as e:
        s.pruefung(False, f"Server antwortet nicht: {einzeilig(e)[:200]}")
        return s
    tage = poster.get("schluessel_tage")
    if tage is None:
        s.pruefung(False, "Instagram-Schlüssel fehlt oder ist ungültig: server/instagram.sh ausführen")
    elif tage >= SCHLUESSEL_ABLAUF:
        s.pruefung(False, f"Instagram-Schlüssel ist {tage} Tage alt und abgelaufen: in der Agentur neu verbinden, dann server/instagram.sh")
    elif tage >= SCHLUESSEL_WARNUNG:
        s.pruefung(True, f"Instagram-Schlüssel läuft bald ab ({tage} von {SCHLUESSEL_ABLAUF} Tagen): in der Agentur erneuern, dann server/instagram.sh")
    else:
        s.pruefung(True, f"Instagram-Schlüssel {tage} Tage alt")
    s.pruefung(None, f"Poster ist {'an' if poster.get('an') else 'aus'} (Schalter: ./fliessband poster ein|aus)")
    if not fb_gestartet:
        s.pruefung(None, "Facebook (optional): nicht eingerichtet")
        return s
    _wert_pruefen(s, u, "FLIESSBAND_FB_SEITE", "Name der Facebook-Seite")
    _schluessel_pruefen(s, u, "fliessband-facebook-app", (u.wert("FLIESSBAND_FB_KONTO") or "fliessband").strip(), "App-Geheimcode der Meta-App")
    try:
        fb = bk.facebook_stand()
        s.pruefung(bool(fb.get("schluessel")), "Facebook: Seiten-Schlüssel da" if fb.get("schluessel") else
                   "Facebook: Seiten-Schlüssel fehlt oder ungültig: server/facebook.sh ausführen")
    except BriefkastenFehler as e:
        s.pruefung(False, f"Facebook-Stand nicht lesbar: {einzeilig(e)[:200]}")
    return s


def _jobs(u: Umfeld) -> Schritt:
    s = _schritt(8)
    ausgabe = u.launchd()
    if ausgabe is None:
        s.pruefung(False, "launchctl ist nicht lesbar")
    else:
        fehlend = [j for j in JOBS if f"{JOB_PRAEFIX}{j}" not in ausgabe]
        s.pruefung(not fehlend, f"Jobs geladen ({', '.join(JOBS)})" if not fehlend else
                   f"Jobs fehlen: {', '.join(fehlend)}. Erst .env vollständig, dann ./install.sh --launchd")
    s.pruefung(None, "Wecker Fr und Sa 21:55 setzt du selbst: sudo pmset repeat wakeorpoweron FS 21:55:00 (prüfen: pmset -g sched)")
    return s


def _erster_lauf(u: Umfeld) -> Schritt:
    s = _schritt(9)
    wochen = sorted(p.parent.name for p in (u.basis / "wochen").glob("*/plan.json")) if (u.basis / "wochen").is_dir() else []
    if wochen:
        s.pruefung(True, f"Es gibt schon eine Woche: {wochen[-1]}")
        return s
    s.status = "manuell"
    s.pruefung(None, "Noch keine Woche geplant. Von Hand prüfen:")
    for befehl in (".venv/bin/pytest -q -m \"not langsam\"", "./fliessband karussell <beitrag.md>", "./fliessband woche status"):
        s.pruefung(None, befehl)
    return s


def pruefe(u: Umfeld, online: bool = False) -> list[Schritt]:
    server, antwortet = _server(u, online)
    return [_voraussetzungen(u), _agentur(u), _stimme(u), _telegram(u), _wordpress(u), server,
            _instagram(u, online, antwortet), _jobs(u), _erster_lauf(u)]


def naechster_schritt(schritte: list[Schritt]) -> Schritt | None:
    return next((s for s in schritte if s.status == "offen"), None)


def exitcode(schritte: list[Schritt]) -> int:
    return 1 if naechster_schritt(schritte) else 0


MARKE = {"ok": "[OK]", "offen": "[OFFEN]", "uebersprungen": "[ÜBERSPRUNGEN]", "manuell": "[VON HAND]"}
ZEICHEN = {True: "✓", False: "✗", None: "·"}


def text(schritte: list[Schritt]) -> str:
    z = ["Einrichtung Content-Fliessband", "Nur eine Prüfung: nichts wird geändert und kein Wert angezeigt.", ""]
    for s in schritte:
        z.append(f"{MARKE[s.status]} {s.nr}. {s.titel}")
        z += [f"    {ZEICHEN[ok]} {t}" for ok, t in s.zeilen]
    z.append("")
    n = naechster_schritt(schritte)
    if n:
        z.append(f"Nächster Schritt: {n.nr}. {n.titel}")
        z.append(f"Anleitung: {n.kapitel}")
    else:
        z.append("Alle Pflichtschritte sind erledigt.")
    if any(s.status == "uebersprungen" for s in schritte):
        z.append("Mit ./fliessband einrichten --online prüft der Assistent zusätzlich Server und Instagram.")
    return "\n".join(z)
