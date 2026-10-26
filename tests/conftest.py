import base64
import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import io

import pytest
from PIL import Image
from hilfen_medien import stille_mp3  # noqa: F401  (Fixtures unten nutzen sie)

FIXTURES = Path(__file__).parent / "fixtures"
REEL_TEXT = (FIXTURES / "reel_beispiel.md").read_text(encoding="utf-8")
KARUSSELL_TEXT = (FIXTURES / "karussell_beispiel-thema_v2.md").read_text(encoding="utf-8")


def _kleines_png() -> bytes:
    """Echtes, winziges PNG: Die Attrappen-Bilder müssen sich als JPEG für Instagram umwandeln lassen (Etappe 5)."""
    puffer = io.BytesIO()
    Image.new("RGB", (4, 4), (11, 17, 30)).save(puffer, "PNG")
    return puffer.getvalue()


KLEINES_PNG = _kleines_png()


@pytest.fixture
def karussell_quelle():
    return FIXTURES / "karussell_beispiel-thema_v2.md"


@pytest.fixture
def reel_quelle():
    return FIXTURES / "reel_beispiel.md"


@pytest.fixture
def falsche_elevenlabs(tmp_path):
    """Ersatz für die ElevenLabs-Anfrage: stille MP3 (0,12 s pro Zeichen) + gleichmässige
    Zeichen-Zeitstempel. Die gesendeten Texte stehen in .aufrufe."""
    aufrufe = []

    def anfrage(text: str) -> dict:
        aufrufe.append(text)
        sek = max(0.6, 0.12 * len(text))
        mp3 = stille_mp3(tmp_path / f"_falsch_{len(aufrufe)}.mp3", sek)
        n = len(text)
        schritt = (sek - 0.2) / n
        starts = [round(0.1 + i * schritt, 3) for i in range(n)]
        enden = [round(s + schritt, 3) for s in starts]
        return {
            "audio_base64": base64.b64encode(mp3.read_bytes()).decode(),
            "alignment": {"characters": list(text),
                          "character_start_times_seconds": starts,
                          "character_end_times_seconds": enden},
        }

    anfrage.aufrufe = aufrufe
    return anfrage


# --- Schnelle Bauer: Playwright und HyperFrames ersetzt, alles andere echt ---

@pytest.fixture
def schnell(monkeypatch):
    """Ersetzt die langsamen Schritte des Reel-Bauers (Messen, Check, Render, Titelbild) durch Attrappen."""
    from lib import reel_bauer

    def skalen(szenen, hook_gruppen):
        return {s.nummer: 1.0 for s in szenen}

    def render(ordner, ziel, log):
        assert (ordner / "index.html").exists()
        ziel.write_bytes(b"mp4")
        return ziel

    def cover(einblendung, ziel):
        ziel.write_bytes(KLEINES_PNG)
        return ziel

    monkeypatch.setattr(reel_bauer, "waehle_skalen", skalen)
    monkeypatch.setattr(reel_bauer, "pruefe_komposition", lambda ordner, log: None)
    monkeypatch.setattr(reel_bauer, "rendere", render)
    monkeypatch.setattr(reel_bauer, "pruefe_video", lambda mp4, erwartet: None)
    monkeypatch.setattr(reel_bauer, "rendere_cover", cover)
    return monkeypatch


@pytest.fixture
def schnelles_karussell(monkeypatch):
    """Ersetzt Playwright im Karussell-Bauer: schreibt kleine Platzhalter-PNGs."""
    from lib import bauer

    def rendere(slides, ziel):
        ziel.mkdir(parents=True, exist_ok=True)
        pngs = []
        for s in slides:
            png = ziel / f"slide-{s.nummer:02d}.png"
            png.write_bytes(KLEINES_PNG)
            pngs.append(png)
        return pngs

    monkeypatch.setattr(bauer, "rendere_slides", rendere)
    return monkeypatch


# --- Telegram ---

class FalschesTelegram:
    """Ersatz für die Telegram-Bot-API. aufrufe: (methode, felder, dateien). updates: Inhalt für getUpdates.
    scheitern_bei: Name einer Methode, die mit BotFehler scheitert (wird nicht in aufrufe vermerkt)."""

    def __init__(self):
        self.aufrufe, self.updates, self.scheitern_bei, self._id = [], [], None, 100

    def __call__(self, methode, felder, dateien=None):
        if methode == self.scheitern_bei:
            from lib.bot import BotFehler
            raise BotFehler(f"Telegram {methode}: nicht erreichbar")
        self.aufrufe.append((methode, dict(felder), dict(dateien or {})))
        if methode == "getUpdates":
            return [u for u in self.updates if u["update_id"] >= felder.get("offset", 0)]
        if methode == "sendMediaGroup":
            return [{"message_id": self._neue_id()} for _ in felder["media"]]
        return {"message_id": self._neue_id()}

    def _neue_id(self):
        self._id += 1
        return self._id

    def texte(self):
        return [f["text"] for m, f, _ in self.aufrufe if m == "sendMessage"]

    def methoden(self):
        return [m for m, _, _ in self.aufrufe]


@pytest.fixture
def telegram():
    return FalschesTelegram()


# --- Briefkasten (Server, Etappe 4) ---

class FalscherBriefkasten:
    """Ersatz für lib.briefkasten.Briefkasten. ereignisse_liste: Ereignisse wie vom Server.
    gemeldet: angemeldete Beiträge, medien_gemeldet: (id, daten), poster_an, fertig_wochen, fehler_gemeldet: (id, grund), fragen: gemeldete Fristen.
    nicht_erreichbar: jeder Aufruf scheitert mit BriefkastenFehler. medien_fehler: Ausnahme, mit der medien scheitert.
    zahlen_liste: Ergebnis von zahlen()."""

    def __init__(self):
        self.ereignisse_liste, self.gemeldet, self.fertig_wochen = [], [], []
        self.fehler_gemeldet, self.fragen = [], []
        self.medien_gemeldet, self.poster_an = [], False
        self.facebook_an = False
        self.kommentare_an = False
        self.stand = {"entscheide": 0, "nachrichten": 0}
        self.nicht_erreichbar, self.medien_fehler = False, None
        self.zahlen_liste = []

    def _pruefe(self):
        if self.nicht_erreichbar:
            from lib.briefkasten import BriefkastenFehler
            raise BriefkastenFehler("Briefkasten nicht erreichbar (URLError)")

    def melde(self, beitrag):
        self._pruefe()
        self.gemeldet.append(dict(beitrag))
        return dict(beitrag, status="offen")

    def fertig(self, woche):
        self._pruefe()
        self.fertig_wochen.append(woche)

    def fehler(self, id, grund):
        self._pruefe()
        self.fehler_gemeldet.append((id, grund))

    def fragen_offen(self, bis):
        self._pruefe()
        self.fragen.append(bis)

    def medien(self, id, daten):
        self._pruefe()
        if self.medien_fehler is not None:
            raise self.medien_fehler
        self.medien_gemeldet.append((id, dict(daten)))
        return dict(daten)

    def zahlen(self, tage=28):
        self._pruefe()
        return [dict(z) for z in self.zahlen_liste]

    def poster(self, an):
        self._pruefe()
        self.poster_an = an
        return self.poster_stand()

    def poster_stand(self):
        self._pruefe()
        return {"an": self.poster_an, "schluessel_tage": 3,
                "naechste": [{"id": "2026-KW44-reel-beispiel-reel-eins", "titel": "Thema beispiel-reel-eins",
                              "format": "reel", "termin": "2026-10-27T19:00", "post_status": "geplant",
                              "dateien": True}]}

    def facebook(self, an):
        self._pruefe()
        self.facebook_an = an
        return self.facebook_stand()

    def facebook_stand(self):
        self._pruefe()
        return {"an": self.facebook_an, "schluessel": True, "posts": [
            {"id": "2026-KW44-thema-1", "titel": "Thema 1", "termin": "2026-10-27T19:00", "fb_status": "gepostet",
             "fb_link": "https://www.facebook.com/reel/v1", "fb_grund": None}]}

    def kommentare(self, an):
        self._pruefe()
        self.kommentare_an = an
        return self.kommentare_stand()

    def kommentare_stand(self):
        self._pruefe()
        return {"an": self.kommentare_an, "seit": None, "kommentare": 12, "start": 2, "abgelehnt": 0,
                "letzte_runde": "2026-10-26T10:05:00+01:00", "problem": None}

    def ereignisse(self, art):
        self._pruefe()
        from lib.briefkasten import ARTEN
        return [e for e in self.ereignisse_liste if e["art"] in ARTEN[art] and e["nr"] > self.stand[art]]

    def merke(self, art, nr):
        self.stand[art] = max(nr, self.stand[art])

    def ereignis(self, art, beitrag=None, woche="2026-KW44", version=1, notiz=None, nachricht=None,
                 zeit="2026-10-25T09:00:00+01:00"):
        nr = len(self.ereignisse_liste) + 1
        self.ereignisse_liste.append({"nr": nr, "zeit": zeit, "art": art, "beitrag": beitrag, "woche": woche,
                                      "version": version, "notiz": notiz, "nachricht": nachricht})
        return nr


@pytest.fixture
def briefkasten():
    return FalscherBriefkasten()


# --- Mediathek von example.com (Etappe 5) ---

class FalscheMediathek:
    """Ersatz für lib.mediathek.Mediathek. hochgeladen: (name, datei), geloescht: wp_id. nicht_erreichbar: jeder
    Aufruf scheitert. fehler: Ausnahme, mit der lade_hoch scheitert."""

    def __init__(self):
        self.hochgeladen, self.geloescht, self.nicht_erreichbar, self.fehler = [], [], False, None

    def _pruefe(self):
        if self.nicht_erreichbar:
            from lib.mediathek import MediathekFehler
            raise MediathekFehler("Mediathek nicht erreichbar (URLError)")

    def lade_hoch(self, datei, name):
        self._pruefe()
        if self.fehler is not None:
            raise self.fehler
        self.hochgeladen.append((name, datei))
        return {"wp_id": 100 + len(self.hochgeladen), "url": f"https://example.com/wp-content/uploads/2026/10/{name}"}

    def loesche(self, wp_id):
        self._pruefe()
        self.geloescht.append(wp_id)


@pytest.fixture
def mediathek():
    return FalscheMediathek()


# --- Agentur: Claude-Agenten und Werkzeuge (personas.py, auswertung.py, apify.py) ---

APIFY_ERGEBNIS = {"gestartet": True, "status": "SUCCEEDED", "accounts_auswertung": {
    "konto.0": {"reels": 6, "median_aufrufe": 9000, "fehler": None, "ausreisser": [
        {"datum": "2026-10-20", "aufrufe": 48000, "caption": "Drei Fehler beim Start",
         "link": "https://www.instagram.com/reel/A1/"}]},
    "konto.1": {"reels": 0, "median_aufrufe": 0, "fehler": None, "ausreisser": []}}}


def themen_json(woche="2026-KW44", fragen=1, notiz=True, konkurrenz=False):
    """Gültige Planer-Ausgabe (synthetische Werte). Thema 1 kommt aus der Apple-Notiz, Thema 3 auf Wunsch
    aus dem Ausreisser von konto.0."""
    from lib.kalender import termine

    def thema(nr, termin, format, slug):
        return {"nr": nr, "format": format, "termin": termin, "slug": slug, "thema": f"Thema {slug}",
                "quelle": {"art": "ideen", "detail": "ideen/2026-10-15_ideen.md, Idee 2"}, "vorlage": None,
                "weiterschick": "an den Kollegen aus dem Team", "hook_idee": "Ein Hook", "frage": None,
                "einstieg": f"Moment zu {slug}"}

    slugs = ["beispiel-reel-eins", "notgroschen-beispiel", "drei-fehler", "demokonto-woche"]
    themen = [thema(t["nr"], t["termin"], t["format"], s) for t, s in zip(termine(woche), slugs)]
    if notiz:
        themen[0]["quelle"] = {"art": "notiz", "detail": "Die Sätze aus dem Teamraum"}
    if konkurrenz:
        themen[2]["quelle"] = {"art": "konkurrenz", "detail": "@konto.0, 48000 Aufrufe"}
        themen[2]["vorlage"] = {"url": "https://www.instagram.com/reel/A1/"}
    if fragen >= 1:
        themen[0]["frage"] = "Welche Sätze hörst du im Alltag, wenn du Trading erwähnst?"
    if fragen >= 2:
        themen[2]["frage"] = "Was war dein erster Fehler beim Traden?"
    reserve = [thema(None, None, "reel", "reserve-reel"), thema(None, None, "karussell", "reserve-karussell")]
    return {"themen": themen, "reserve": reserve}


URTEIL = {"persona_id": "p001", "stehen_geblieben": True, "bis_ende": True, "absprung_stelle": "",
          "gespeichert": False, "geteilt": True, "geteilt_an": "Kollege", "kommentiert": False, "kategorie": "stark",
          "grund": "passt", "zitat": "genau so"}


class FalscheAgentur:
    """Ersatz für die Claude-Agenten und die Werkzeuge der Agentur. Schreibt die erwarteten Dateien.
    quoten: (wegwisch, teilen) pro Follower-Test, danach immer GUT. abbruch_bei: Teil eines Ausgabe-Namens,
    bei dem der Lauf mit KeyboardInterrupt abbricht (Absturz mitten im Schritt)."""
    GUT = (0.3, 0.1)
    SCHWACH = (0.6, 0.0)

    def __init__(self, woche="2026-KW44", quoten=(), fragen=1, notiz=True, konkurrenz=False,
                 apify_rest=4.2, viral_text=None, abbruch_bei=None):
        self.woche, self.quoten, self.fragen = woche, list(quoten), fragen
        self.notiz, self.konkurrenz = notiz, konkurrenz
        self.apify_rest, self.viral_text, self.abbruch_bei = apify_rest, viral_text, abbruch_bei
        self.aufrufe = []     # (Agent oder Werkzeug, Ausgabe-Name oder erstes Argument)
        self.auftraege = []   # (Agent, Auftrag)
        self.aussprache_funde = []   # Antwort des aussprache-agent (Etappe 8)

    def claude(self, agent, auftrag, ausgabe, werkzeuge=("Read", "Write"), ordner=(), zeitlimit=900):
        ausgabe = Path(ausgabe)
        self.aufrufe.append((agent, ausgabe.name))
        self.auftraege.append((agent, auftrag))
        if self.abbruch_bei and self.abbruch_bei in ausgabe.name:
            raise KeyboardInterrupt
        if agent == "trend-agent" and ausgabe.name == "themen.json":
            inhalt = json.dumps(themen_json(self.woche, self.fragen, self.notiz, self.konkurrenz), ensure_ascii=False)
        elif agent == "trend-agent":
            inhalt = json.dumps({"accounts": [{"name": f"neu.{i}", "grund": "Beispiel-Account mit Reels"} for i in range(8)]})
        elif agent == "follower-agent":
            inhalt = json.dumps([URTEIL])
        elif agent == "aussprache-agent":
            inhalt = json.dumps({"funde": self.aussprache_funde}, ensure_ascii=False)
        elif agent == "viral-agent" and self.viral_text is not None:
            inhalt = self.viral_text
        else:
            inhalt = REEL_TEXT if "_reel_" in ausgabe.name else KARUSSELL_TEXT
        ausgabe.parent.mkdir(parents=True, exist_ok=True)
        ausgabe.write_text(inhalt, encoding="utf-8")
        return ausgabe

    def werkzeug(self, name, argumente, zeitlimit):
        self.aufrufe.append((name, argumente[0] if argumente else ""))
        ausgabe = ""
        if name == "personas.py":
            ziel = Path(argumente[argumente.index("--ziel") + 1])
            ziel.mkdir(parents=True, exist_ok=True)
            for nr in ("01", "02"):
                (ziel / f"personas_{nr}.json").write_text("[]", encoding="utf-8")
        elif name == "auswertung.py":
            ordner = Path(argumente[argumente.index("--ordner") + 1])
            wegwisch, teilen = self.quoten.pop(0) if self.quoten else self.GUT
            quoten = {"wegwisch": wegwisch, "ende": 0.3, "speichern": 0.1, "teilen": teilen, "kommentieren": 0.0}
            (ordner / "ergebnis.json").write_text(json.dumps({"quoten": quoten}), encoding="utf-8")
        elif name == "apify.py" and argumente[0] == "check":
            ausgabe = json.dumps({"verbleibend_usd": self.apify_rest})
        elif name == "apify.py":
            Path(argumente[argumente.index("--ausgabe") + 1]).write_text(json.dumps(APIFY_ERGEBNIS), encoding="utf-8")
        return subprocess.CompletedProcess([name, *argumente], 0, ausgabe, "")

    def anzahl(self, name):
        return sum(1 for wer, _ in self.aufrufe if wer == name)


@pytest.fixture
def agentur_attrappe():
    """Die Klasse FalscheAgentur (Tests bauen sich je eine mit eigenen Quoten)."""
    return FalscheAgentur


# --- Woche: Pfade, Bot mit Chat 42, Konkurrenz-Liste und Dienste mit Attrappen ---

@pytest.fixture
def wochen_umgebung(tmp_path, telegram, falsche_elevenlabs):
    from lib.bot import Bot
    from lib.manifest import schreibe_json
    from lib.umgebung import Pfade
    from lib.woche import Dienste

    pfade = Pfade(basis=tmp_path / "fb", agentur=tmp_path / "agentur", skill=tmp_path / "skill",
                  agentur_python=tmp_path / "kein-python")
    schreibe_json(pfade.daten / "bot.json", {"chat_id": 42, "letzte_update_id": 0})
    schreibe_json(pfade.daten / "konkurrenz.json", {
        "erneuert": "2026-10-02",
        "accounts": [{"name": f"konto.{i}", "grund": "Erklärer-Account DACH", "seit": "2026-10-02",
                      "leere_wochen": 0} for i in range(8)]})

    def dienste(agentur, jetzt=datetime(2026, 10, 23, 22, 0),
                notiz="Content-Ideen\nDie Sätze aus dem Teamraum\n", rest=30000, uhr=time.monotonic,
                briefkasten=None, mediathek=None):
        lesen = notiz if callable(notiz) else (lambda skript: notiz)
        return Dienste(claude=agentur.claude, werkzeug=agentur.werkzeug, notiz=lesen,
                       bot=Bot(pfade.daten / "bot.json", anfrage=telegram, briefkasten=briefkasten),
                       elevenlabs_rest=lambda: rest, stimme=falsche_elevenlabs, jetzt=lambda: jetzt, uhr=uhr,
                       briefkasten=briefkasten, mediathek=mediathek)

    return SimpleNamespace(pfade=pfade, telegram=telegram, dienste=dienste)


# --- Gesendete und angemeldete Woche KW44 (Etappe 4/5) ---

@pytest.fixture
def gesendet(wochen_umgebung, agentur_attrappe, briefkasten, schnell, schnelles_karussell):
    """Gesendete und angemeldete Woche KW44 (Bau mit echten Bauern, schnell). Karussell-Texte ohne [Platzhalter],
    sonst wären sie braucht_eingabe und ohne Knöpfe."""
    from lib import woche
    WOCHE = "2026-KW44"

    class OhnePlatzhalter(agentur_attrappe):
        def claude(self, agent, auftrag, ausgabe, *args, **kwargs):
            pfad = super().claude(agent, auftrag, ausgabe, *args, **kwargs)
            if pfad.suffix == ".md" and "_reel_" not in pfad.name:
                pfad.write_text(re.sub(r"\[[^\]]+\]", "", pfad.read_text(encoding="utf-8")), encoding="utf-8")
            return pfad

    u = wochen_umgebung
    a = OhnePlatzhalter(fragen=0)
    for schritt, jetzt in (("job-vorbereiten", datetime(2026, 10, 23, 22, 0)),
                           ("job-bauen", datetime(2026, 10, 24, 22, 0))):
        assert woche.fuehre_aus(schritt, WOCHE, u.pfade, u.dienste(a, jetzt=jetzt, briefkasten=briefkasten),
                                lambda t: None) == 0
    u.telegram.aufrufe.clear()
    briefkasten.gemeldet.clear()
    return u, a
