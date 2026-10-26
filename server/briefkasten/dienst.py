"""Startpunkt des Dienstes fliessband-briefkasten (systemd): API-Thread, Zeitgeber-Thread, Poster-Thread, Kommentar-Thread (Etappe 9), Abhol-Schleife.
Ausgaben gehen ins Journal (journalctl -u fliessband-briefkasten). Schlüssel erscheinen nie: Fehler werden
nur mit Typname und str(e) geloggt, nie mit Traceback (die Telegram-URL enthält den Token)."""
import logging
import os
import signal
import sys
import threading
import time
from pathlib import Path

from briefkasten.ablauf import Ablauf
from briefkasten.api import baue_server
from briefkasten.facebook import Facebook, FbSchluessel
from briefkasten.instagram import Instagram, Schluessel
from briefkasten.kommentare import Kommentare
from briefkasten.poster import Poster
from briefkasten.speicher import Speicher
from briefkasten.telegram import TelegramFehler, telegram

HOST, PORT = "127.0.0.1", 8096   # Bind-Adresse per FLIESSBAND_HOST auf die Tailscale-IP setzen, nie 0.0.0.0
MAX_PAUSE = 300
POSTER_TAKT = 30
KOMMENTAR_TAKT = 300   # Etappe 9: Kommentare alle 5 Minuten
NOETIG = ("TELEGRAM_TOKEN", "CHAT_ID", "API_SCHLUESSEL")


def log(text: str) -> None:
    print(text, flush=True)


def _kurz(e: Exception) -> str:
    return f"{type(e).__name__}: {e}"


def lade_env(pfad: Path) -> dict:
    werte = {}
    for zeile in Path(pfad).read_text(encoding="utf-8").splitlines():
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#") or "=" not in zeile:
            continue
        k, _, v = zeile.partition("=")
        werte[k.strip()] = v.strip().strip('"')
    fehlend = [k for k in NOETIG if not werte.get(k)]
    if fehlend:
        raise SystemExit(f"In {pfad} fehlt: {', '.join(fehlend)}")
    return werte


def abhol_schleife(ablauf, schlafe=time.sleep, runden=None) -> None:
    """Holt Telegram-Updates ab (nur dieser eine Thread ruft abholen auf). None: noch nicht umgestellt, 30 s
    warten. Fehler: Pause max(retry_after, Backoff), Backoff 1, 2, 4 … bis 300 s, nach Erfolg zurück auf 1."""
    pause, n = 1, 0
    while runden is None or n < runden:
        n += 1
        try:
            if ablauf.abholen() is None:
                schlafe(30)
            pause = 1
        except TelegramFehler as e:
            log(f"Abholen gescheitert: {e}")
            schlafe(max(e.warten or 0, pause))
            pause = min(pause * 2, MAX_PAUSE)
        except Exception as e:
            log(f"Fehler beim Abholen: {_kurz(e)}")
            schlafe(pause)
            pause = min(pause * 2, MAX_PAUSE)


def zeitgeber_schleife(ablauf, schlafe=time.sleep, runden=None) -> None:
    n = 0
    while runden is None or n < runden:
        n += 1
        try:
            ablauf.zeitgeber()
        except TelegramFehler as e:
            log(f"Zeitgeber: {e}")
        except Exception as e:
            log(f"Fehler im Zeitgeber: {_kurz(e)}")
        schlafe(60)


def poster_schleife(poster, schlafe=time.sleep, runden=None) -> None:
    """Poster alle 30 s. Ein Reel kann bis 10 Minuten in der Verarbeitung hängen, darum ein eigener Thread
    (Zeitgeber und Abholen laufen weiter)."""
    n = 0
    while runden is None or n < runden:
        n += 1
        try:
            poster.takt()
        except Exception as e:
            log(f"Fehler im Poster: {_kurz(e)}")
        schlafe(POSTER_TAKT)


def kommentar_schleife(kommentare, schlafe=time.sleep, runden=None) -> None:
    """START-Kommentare alle 5 Minuten (Etappe 9). Eigener Thread, damit Instagram-Aufrufe nichts aufhalten.
    Unerwartete Fehler nur mit Typname ins Journal (Token-Schutz)."""
    n = 0
    while runden is None or n < runden:
        n += 1
        try:
            kommentare.runde()
        except Exception as e:
            log(f"Fehler bei den Kommentaren: {type(e).__name__}")
        schlafe(KOMMENTAR_TAKT)


def _beenden(signum, frame):
    raise SystemExit(0)


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(levelname)s %(name)s: %(message)s")
    env = lade_env(Path(os.environ.get("FLIESSBAND_ENV", "/etc/fliessband/geheim.env")))
    speicher = Speicher(Path(os.environ.get("FLIESSBAND_DB", "/var/lib/fliessband/briefkasten.db")))
    ablauf = Ablauf(speicher, telegram(env["TELEGRAM_TOKEN"]), int(env["CHAT_ID"]))
    schluessel = Schluessel(Path(os.environ.get("FLIESSBAND_INSTAGRAM", "/var/lib/fliessband/instagram.json")))
    fb_schluessel = FbSchluessel(Path(os.environ.get("FLIESSBAND_FACEBOOK", "/var/lib/fliessband/facebook.json")))
    instagram = Instagram(schluessel)
    poster = Poster(ablauf, instagram, Facebook(fb_schluessel))
    kommentare = Kommentare(ablauf, instagram)
    try:
        poster.beim_start()
    except Exception as e:
        log(f"Abgleich beim Start gescheitert: {_kurz(e)}")
    server = baue_server(ablauf, env["API_SCHLUESSEL"], (os.environ.get("FLIESSBAND_HOST", HOST), PORT))
    signal.signal(signal.SIGTERM, _beenden)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=zeitgeber_schleife, args=(ablauf,), daemon=True).start()
    threading.Thread(target=poster_schleife, args=(poster,), daemon=True).start()
    threading.Thread(target=kommentar_schleife, args=(kommentare,), daemon=True).start()
    log(f"Briefkasten läuft auf {server.server_address[0]}:{PORT}")
    try:
        abhol_schleife(ablauf)
    finally:
        server.shutdown()
        server.server_close()
        log("Briefkasten beendet")


if __name__ == "__main__":
    main()
