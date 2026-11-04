"""Telegram-Bot des Fliessbands: Fragen senden, Antworten lesen und zuordnen, Videos und Alben senden.
Der Token liegt im Schlüsselbund (Dienst fliessband-telegram) und erscheint nie in Meldungen oder Logs.
Chat-ID und letzte Update-ID stehen in daten/bot.json. Telegram hält unbestätigte Updates höchstens 24 h,
darum landen Betreiber-Nachrichten sofort im lokalen Eingang daten/bot-eingang.json und werden erst dort
nach dem Speichern der Antworten entfernt."""
import functools
import http.client
import json
import mimetypes
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Callable

from lib.manifest import schreibe_json
from lib.netzgrund import netzgrund

DIENST = "fliessband-telegram"
API = "https://api.telegram.org"
MAX_TEXT = 4000                      # Telegram nimmt höchstens 4096 Zeichen pro Nachricht
MAX_ALBUM = 10                       # höchstens 10 Bilder pro Album
VERSAND_GRENZE = 50 * 1000 * 1000    # Bots dürfen höchstens 50 MB hochladen
MAX_WARTEN = 30                      # Sekunden, die der Bot bei HTTP 429 höchstens einmal wartet
FFMPEG_ZEITLIMIT = 600


class BotFehler(Exception):
    pass


@functools.lru_cache(maxsize=1)
def _token() -> str:
    r = subprocess.run(["security", "find-generic-password", "-s", DIENST, "-w"], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        raise BotFehler("Telegram-Token fehlt im Schlüsselbund (Dienst fliessband-telegram)")
    return r.stdout.strip()


def _feldwert(wert) -> str:
    if isinstance(wert, bool):
        return "true" if wert else "false"
    if isinstance(wert, (list, dict)):
        return json.dumps(wert, ensure_ascii=False)
    return str(wert)


def multipart(felder: dict[str, str], dateien: dict[str, Path]) -> tuple[bytes, str]:
    """multipart/form-data für Datei-Uploads (Video, Bilder)."""
    grenze = uuid.uuid4().hex
    teile = []
    for name, wert in felder.items():
        teile.append(f'--{grenze}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{wert}\r\n'.encode())
    for name, pfad in dateien.items():
        pfad = Path(pfad)
        typ = mimetypes.guess_type(pfad.name)[0] or "application/octet-stream"
        kopf = (f'--{grenze}\r\nContent-Disposition: form-data; name="{name}"; filename="{pfad.name}"\r\n'
                f"Content-Type: {typ}\r\n\r\n")
        teile.append(kopf.encode() + pfad.read_bytes() + b"\r\n")
    teile.append(f"--{grenze}--\r\n".encode())
    return b"".join(teile), f"multipart/form-data; boundary={grenze}"


def _fehlerkoerper(e: urllib.error.HTTPError) -> dict:
    try:
        koerper = json.loads(e.read())
    except (ValueError, AttributeError, OSError, http.client.HTTPException):
        return {}
    return koerper if isinstance(koerper, dict) else {}


def _wartezeit(koerper: dict) -> float:
    try:
        sekunden = float((koerper.get("parameters") or {}).get("retry_after", 1))
    except (TypeError, ValueError, AttributeError):
        sekunden = 1.0
    return min(max(sekunden, 0.0), MAX_WARTEN)


def telegram_anfrage(methode: str, felder: dict, dateien: dict | None = None, warte: Callable = time.sleep):
    """Echte Anfrage an die Bot-API. Liefert 'result'. Fehler kommen als BotFehler, nie mit Token.
    Bei HTTP 429 wartet sie einmal (retry_after, höchstens 30 s) und versucht es nochmals."""
    token = _token()
    werte = {k: _feldwert(v) for k, v in felder.items() if v is not None}
    if dateien:
        daten, typ = multipart(werte, dateien)
    else:
        daten, typ = urllib.parse.urlencode(werte).encode(), "application/x-www-form-urlencoded"
    req = urllib.request.Request(f"{API}/bot{token}/{methode}", data=daten, method="POST",
                                 headers={"Content-Type": typ})
    for versuch in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                antwort = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            koerper = _fehlerkoerper(e)
            if e.code == 429 and versuch == 1:
                warte(_wartezeit(koerper))
                continue
            beschreibung = str(koerper.get("description", ""))
            raise BotFehler(f"Telegram {methode} {e.code}: {beschreibung}".replace(token, "***")[:200]) from None
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as e:
            raise BotFehler(f"Telegram nicht erreichbar ({type(e).__name__}: {netzgrund(e)})") from None
        except json.JSONDecodeError:
            raise BotFehler(f"Telegram {methode}: Antwort ist kein JSON") from None
    if not antwort.get("ok"):
        raise BotFehler(f"Telegram {methode}: {antwort.get('description', '')}".replace(token, "***")[:200])
    return antwort["result"]


def _teile(text: str, laenge: int = MAX_TEXT) -> list[str]:
    """Teilt lange Texte an Zeilenumbrüchen. Leere oder nur aus Leerraum bestehende Teile fallen weg."""
    teile, rest = [], text
    while len(rest) > laenge:
        schnitt = rest.rfind("\n", 0, laenge)
        if schnitt <= 0:
            schnitt = laenge
        teile.append(rest[:schnitt])
        rest = rest[schnitt:].lstrip("\n")
    return [t for t in teile + [rest] if t.strip()]


class Bot:
    """Telegram-Bot mit Stand in daten/bot.json. Alles wird ohne Ton gesendet (disable_notification)."""

    def __init__(self, stand: Path, anfrage: Callable = telegram_anfrage, briefkasten=None,
                 log: Callable[[str], None] = print):
        """briefkasten: lib.briefkasten.Briefkasten nach der Umstellung (Etappe 4). Dann holt sammle die
        Nachrichten beim Server ab und fragt Telegram nie selbst ab. Fehler kommen dann als BriefkastenFehler.
        log: Hinweise, z.B. verworfene doppelte Nachrichten."""
        self.stand, self.anfrage, self.briefkasten, self.log = Path(stand), anfrage, briefkasten, log
        self.eingang = self.stand.with_name(f"{self.stand.stem}-eingang.json")

    def _lade(self) -> dict:
        if not self.stand.exists():
            return {}
        try:
            return json.loads(self.stand.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raise BotFehler(f"{self.stand} ist kaputt, neu mit «fliessband bot einrichten»") from None

    def _lade_eingang(self) -> list[dict]:
        """Lokaler Eingang: [{"update_id": …, "message": {…}}], aufsteigend nach update_id."""
        if not self.eingang.exists():
            return []
        try:
            return list(json.loads(self.eingang.read_text(encoding="utf-8"))["nachrichten"])
        except (json.JSONDecodeError, KeyError, TypeError):
            raise BotFehler(f"{self.eingang} ist kaputt, bitte prüfen (enthält Antworten vom Betreiber)") from None

    @property
    def chat_id(self) -> int:
        stand = self._lade()
        if "chat_id" not in stand:
            raise BotFehler("Bot nicht eingerichtet, zuerst «fliessband bot einrichten»")
        return stand["chat_id"]

    @property
    def letzte_update_id(self) -> int:
        return self._lade().get("letzte_update_id", 0)

    def einrichten(self) -> int:
        """Nach /start vom Betreiber: Chat-ID speichern, ältere Updates überspringen, Bestätigung senden."""
        updates = self.anfrage("getUpdates", {"timeout": 0, "allowed_updates": ["message"]})
        starts = [u["message"] for u in updates
                  if (u.get("message") or {}).get("text", "").startswith("/start")
                  and u["message"].get("chat", {}).get("type") == "private"]
        if not starts:
            raise BotFehler("Keine /start-Nachricht gefunden. Schick dem Bot in Telegram /start und versuch es nochmals.")
        chat = starts[-1]["chat"]["id"]
        schreibe_json(self.stand, {"chat_id": chat, "letzte_update_id": max(u["update_id"] for u in updates)})
        self.sende_text("Fliessband-Bot eingerichtet. Hier kommen ab jetzt die Fragen am Freitag "
                        "und das Wochenpaket am Samstag.")
        return chat

    def sende_text(self, text: str) -> int:
        """Sendet Text, lange Texte in Teilen. Liefert die ID der ersten Nachricht."""
        chat, teile = self.chat_id, _teile(text)
        if not teile:
            raise BotFehler("Telegram-Nachricht ist leer")
        ids = [self.anfrage("sendMessage", {"chat_id": chat, "text": teil, "disable_notification": True})["message_id"]
               for teil in teile]
        return ids[0]

    def sende_video(self, pfad: Path) -> int:
        r = self.anfrage("sendVideo", {"chat_id": self.chat_id, "disable_notification": True,
                                       "supports_streaming": True}, {"video": Path(pfad)})
        return r["message_id"]

    def sende_album(self, bilder: list[Path]) -> None:
        chat = self.chat_id
        for start in range(0, len(bilder), MAX_ALBUM):
            gruppe = [Path(b) for b in bilder[start:start + MAX_ALBUM]]
            if len(gruppe) == 1:
                self.anfrage("sendPhoto", {"chat_id": chat, "disable_notification": True}, {"photo": gruppe[0]})
                continue
            media = [{"type": "photo", "media": f"attach://bild{i}"} for i in range(len(gruppe))]
            self.anfrage("sendMediaGroup", {"chat_id": chat, "media": media, "disable_notification": True},
                         {f"bild{i}": p for i, p in enumerate(gruppe)})

    def sammle(self) -> int:
        """Holt neue Updates von Telegram, legt Textnachrichten aus Betreiber-Chat im lokalen Eingang ab
        und bestätigt sie danach sofort bei Telegram. Fremde Chats fallen weg. Liefert die Anzahl neu abgelegter."""
        if self.briefkasten is not None:
            return self._sammle_briefkasten()
        stand, chat = self._lade(), self.chat_id
        letzte = stand.get("letzte_update_id", 0)
        updates = self.anfrage("getUpdates", {"offset": letzte + 1, "timeout": 0, "allowed_updates": ["message"]})
        if not updates:
            return 0
        eingang = self._lade_eingang()
        bekannt = {e["update_id"] for e in eingang}
        neu = [{"update_id": u["update_id"], "message": u["message"]} for u in updates
               if (u.get("message") or {}).get("chat", {}).get("id") == chat and u["message"].get("text")
               and u["update_id"] not in bekannt]
        if neu:
            schreibe_json(self.eingang, {"nachrichten": sorted(eingang + neu, key=lambda e: e["update_id"])})
        hoechste = max(letzte, *(u["update_id"] for u in updates))
        stand["letzte_update_id"] = hoechste
        schreibe_json(self.stand, stand)
        try:   # Bestätigen; scheitert es, bestätigt der nächste Abruf (offset), die Nachrichten sind schon lokal
            self.anfrage("getUpdates", {"offset": hoechste + 1, "timeout": 0, "allowed_updates": ["message"]})
        except BotFehler:
            pass
        return len(neu)

    def _sammle_briefkasten(self) -> int:
        """Wie sammle, aber aus den Ereignissen «nachricht» des Briefkastens (Etappe 4). Abholen gilt
        «mindestens einmal»: schon im Eingang liegende oder schon bestätigte Nachrichten fallen weg."""
        ereignisse = self.briefkasten.ereignisse("nachrichten")
        if not ereignisse:
            return 0
        chat, bestaetigt = self.chat_id, self.letzte_update_id
        eingang = self._lade_eingang()
        bekannt = {e["update_id"] for e in eingang}
        neu, verworfen = [], 0
        for e in ereignisse:
            u = e.get("nachricht") or {}
            m = u.get("message") or {}
            uid = u.get("update_id")
            if (m.get("chat", {}).get("id") == chat and m.get("text") and isinstance(uid, int)
                    and uid > bestaetigt and uid not in bekannt):
                neu.append({"update_id": uid, "message": m})
                bekannt.add(uid)
            elif isinstance(uid, int) and (uid <= bestaetigt or uid in bekannt):
                verworfen += 1
        if verworfen:
            self.log(f"Briefkasten: {verworfen} Nachricht{'en' if verworfen > 1 else ''} "
                     "schon bestätigt oder doppelt, verworfen")
        if neu:
            schreibe_json(self.eingang, {"nachrichten": sorted(eingang + neu, key=lambda e: e["update_id"])})
        self.briefkasten.merke("nachrichten", ereignisse[-1]["nr"])
        return len(neu)

    def neue_nachrichten(self, sammeln: bool = True) -> tuple[list[dict], int | None]:
        """Holt neue Nachrichten (sammle) und liefert alle noch nicht bestätigten aus dem lokalen Eingang:
        (Nachrichten, höchste Update-ID). Erst nach dem Speichern der Antworten bestaetige(höchste) aufrufen,
        sonst kommen sie beim nächsten Aufruf nochmals. sammeln=False: nur der lokale Eingang (Briefkasten
        nicht erreichbar)."""
        if sammeln:
            self.sammle()
        eingang = self._lade_eingang()
        if not eingang:
            return [], None
        bestaetigt = self._lade().get("letzte_update_id", 0)   # alles bis hier liegt schon im Eingang
        return [e["message"] for e in eingang], max(bestaetigt, *(e["update_id"] for e in eingang))

    def bestaetige(self, update_id: int | None) -> None:
        """Entfernt die Nachrichten bis update_id aus dem lokalen Eingang. Später gesammelte bleiben."""
        if update_id is None:
            return
        eingang = self._lade_eingang()
        rest = [e for e in eingang if e["update_id"] > update_id]
        if self.eingang.exists() and rest != eingang:
            schreibe_json(self.eingang, {"nachrichten": rest})
        stand = self._lade()
        if stand.get("letzte_update_id", 0) < update_id:
            stand["letzte_update_id"] = update_id
            schreibe_json(self.stand, stand)


def verkleinere(quelle: Path, ziel: Path, ausfuehren=subprocess.run, grenze: int = VERSAND_GRENZE) -> Path:
    """Verkleinert ein Reel für den Versand (720 px breit, Ton bleibt). Das Original bleibt unverändert."""
    ziel.parent.mkdir(parents=True, exist_ok=True)
    for crf in ("28", "32"):
        try:
            r = ausfuehren(["ffmpeg", "-y", "-loglevel", "error", "-i", str(quelle), "-vf", "scale=720:-2",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", crf, "-c:a", "aac", "-b:a", "96k",
                            "-movflags", "+faststart", str(ziel)], capture_output=True, text=True,
                           timeout=FFMPEG_ZEITLIMIT)
        except FileNotFoundError:
            raise BotFehler("ffmpeg nicht gefunden (PATH prüfen, /opt/homebrew/bin)") from None
        except subprocess.TimeoutExpired:
            raise BotFehler(f"ffmpeg: Zeitlimit ({FFMPEG_ZEITLIMIT} s) beim Verkleinern von {quelle.name}") from None
        if r.returncode != 0:
            zeilen = [z.strip() for z in (r.stderr or "").splitlines() if z.strip()]
            letzte = f": {zeilen[-1][:200]}" if zeilen else ""
            raise BotFehler(f"ffmpeg konnte {quelle.name} nicht verkleinern{letzte}")
        if ziel.stat().st_size <= grenze:
            return ziel
    raise BotFehler(f"{quelle.name} ist auch verkleinert über {grenze // 1_000_000} MB")


NUMMER = re.compile(
    r"^\s*(?:frage\s*)?(?:(\d+)\s*(?:[:)](?!\d)|\.(?=\s|$))|(eins|zwei|drei)\s*[:)])\s*", re.IGNORECASE)
ZAHLWORT = {"eins": 1, "zwei": 2, "drei": 3}


def _nummer(text: str, nach_index: dict[int, int]) -> tuple[int, str] | None:
    """(Themen-Nr, Rest ohne Nummer), wenn der Text mit einer gültigen Fragennummer samt Trennzeichen beginnt."""
    treffer = NUMMER.match(text)
    if not treffer:
        return None
    zahl = int(treffer.group(1)) if treffer.group(1) else ZAHLWORT[treffer.group(2).lower()]
    if zahl not in nach_index:
        return None
    return nach_index[zahl], text[treffer.end():].strip()


def ordne_zu(nachrichten: list[dict], fragen: list[dict]) -> tuple[dict[int, list[str]], int]:
    """Ordnet Telegram-Nachrichten den gesendeten Fragen zu. Der Text wird nur gekürzt, wenn er mit einer
    Fragennummer beginnt, sonst bleibt er unverändert (er geht wörtlich an den Content-Agenten).
    fragen: [{"nr": Themen-Nr, "index": Fragennummer ab 1, "nachricht": message_id der Frage}].
    Liefert ({Themen-Nr: [Texte in Reihenfolge]}, Anzahl nicht zugeordneter Nachrichten).

    Nachrichten laufen nach message_id. Nicht gezählt werden: Befehle («/start»), Nachrichten ohne Buchstabe
    oder Ziffer (nur Emoji) und Nachrichten, die nicht neuer als die erste Frage sind. Für jede Nachricht gilt
    die erste passende Regel:
    1. «Antworten» auf eine Fragen-Nachricht: diese Frage, Text unverändert.
    2. Fragennummer mit Trennzeichen am Anfang («1:», «1)», «1. », «Frage 1:», «Eins:»): diese Frage, die
       Nummer wird abgeschnitten. «1 Kinder» (ohne Trennzeichen), «1.5» oder «1:30» sind keine Nummer. Nur die
       Nummer ohne Text («1:») ist selbst keine Antwort, sie legt die Frage für die folgenden Nachrichten fest.
    3. «Antworten» auf eine eigene, schon zugeordnete Nachricht: deren Frage.
    4. Fortsetzung: die Frage der unmittelbar vorherigen zugeordneten Nachricht.
    5. Noch keine Zuordnung davor: die einzige Frage, die per Regel 1/2 keine Antwort hat, sonst die einzige
       gesendete Frage, sonst nicht zugeordnet."""
    nach_id = {f["nachricht"]: f["nr"] for f in fragen if f.get("nachricht")}
    nach_index = {f["index"]: f["nr"] for f in fragen}
    erste_frage = min(nach_id) if nach_id else None
    gueltig = []
    for m in sorted(nachrichten, key=lambda m: m["message_id"]):
        text = (m.get("text") or "").strip()
        if not any(z.isalnum() for z in text) or text.startswith("/"):
            continue
        if erste_frage is not None and m["message_id"] <= erste_frage:
            continue
        bezug = (m.get("reply_to_message") or {}).get("message_id")
        gueltig.append((m["message_id"], bezug, text))
    beantwortet = set()
    for _, bezug, text in gueltig:
        if bezug in nach_id:
            beantwortet.add(nach_id[bezug])
        elif nummer := _nummer(text, nach_index):
            beantwortet.add(nummer[0])
    ohne_antwort = [f["nr"] for f in fragen if f["nr"] not in beantwortet]
    einzige = ohne_antwort[0] if len(ohne_antwort) == 1 else (fragen[0]["nr"] if len(fragen) == 1 else None)

    antworten: dict[int, list[str]] = {}
    frage_von: dict[int, int] = {}
    aktuell, nicht = None, 0
    for mid, bezug, text in gueltig:
        nummer = None if bezug in nach_id else _nummer(text, nach_index)
        if bezug in nach_id:
            nr = nach_id[bezug]
        elif nummer:
            nr, text = nummer
            if not text:
                aktuell = nr
                continue
        elif bezug in frage_von:
            nr = frage_von[bezug]
        elif aktuell is not None:
            nr = aktuell
        else:
            nr = einzige
        if nr is None:
            nicht += 1
            continue
        frage_von[mid] = aktuell = nr
        antworten.setdefault(nr, []).append(text)
    return antworten, nicht
