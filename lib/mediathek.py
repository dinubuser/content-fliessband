"""Mediathek von example.com (WordPress-REST, Benutzer aus FLIESSBAND_WP_KONTO, Rolle Redakteur). Lädt Bilder und Videos für
Instagram hoch (Meta verlangt öffentliche Adressen) und löscht nie gepostete wieder. Das Anwendungspasswort liegt
im Schlüsselbund (Dienst aus FLIESSBAND_WP_DIENST, Konto aus FLIESSBAND_WP_KONTO) und erscheint nie in Meldungen oder Logs."""
import base64
import functools
import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from lib.konfig import wert
from lib.netzgrund import netzgrund

ADRESSE = wert("FLIESSBAND_WP_URL", "https://example.com").rstrip("/") + "/wp-json/wp/v2/media"
DIENST, KONTO = wert("FLIESSBAND_WP_DIENST", "fliessband-wp"), wert("FLIESSBAND_WP_KONTO", "your-wp-user")
TYPEN = {".jpg": "image/jpeg", ".mp4": "video/mp4"}
ZEITLIMIT = 180
MAX_GRUND = 200


VORUEBERGEHEND = (404, 408, 429)


class MediathekFehler(Exception):
    """code: HTTP-Code oder None. dauerhaft: Wiederholen hilft nicht (HTTP 4xx ausser 404, 408, 429, fehlendes
    Passwort, unbekannter Dateityp). Nicht erreichbar und 5xx sind vorübergehend."""

    def __init__(self, text: str, code: int | None = None, dauerhaft: bool | None = None):
        super().__init__(text)
        self.code = code
        if dauerhaft is None:
            dauerhaft = code is not None and 400 <= code < 500 and code not in VORUEBERGEHEND
        self.dauerhaft = dauerhaft


@functools.lru_cache(maxsize=1)
def _passwort() -> str:
    r = subprocess.run(["security", "find-generic-password", "-a", KONTO, "-s", DIENST, "-w"],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        raise MediathekFehler("Passwort für example.com fehlt im Schlüsselbund (Dienst fliessband-wp)", dauerhaft=True)
    return r.stdout.strip()


class Mediathek:
    def __init__(self, passwort: Callable[[], str] = _passwort, oeffne=urllib.request.urlopen, adresse: str = ADRESSE):
        self.passwort, self.oeffne, self.adresse = passwort, oeffne, adresse

    def _rufe(self, req: urllib.request.Request) -> dict:
        pw = self.passwort()
        req.add_header("Authorization", "Basic " + base64.b64encode(f"{KONTO}:{pw}".encode()).decode())
        try:
            with self.oeffne(req, timeout=ZEITLIMIT) as r:
                antwort = json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                koerper = json.loads(e.read())
                grund = str(koerper.get("message", "")) if isinstance(koerper, dict) else ""
            except Exception:
                grund = ""
            grund = grund.replace(pw, "…")[:MAX_GRUND]
            raise MediathekFehler(f"Mediathek {req.get_method()}: HTTP {e.code} {grund}".strip(), code=e.code) from None
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise MediathekFehler(f"Mediathek nicht erreichbar ({type(e).__name__}: {netzgrund(e)})") from None
        if not isinstance(antwort, dict):
            raise MediathekFehler("Mediathek: unerwartete Antwort")
        return antwort

    def lade_hoch(self, datei: Path, name: str) -> dict:
        typ = TYPEN.get(Path(datei).suffix.lower())
        if typ is None:
            raise MediathekFehler(f"Dateityp {Path(datei).suffix} wird nicht hochgeladen", dauerhaft=True)
        req = urllib.request.Request(self.adresse, data=Path(datei).read_bytes(), method="POST",
                                     headers={"Content-Type": typ,
                                              "Content-Disposition": f'attachment; filename="{name}"'})
        antwort = self._rufe(req)
        if not antwort.get("id") or not str(antwort.get("source_url", "")).startswith("https://"):
            raise MediathekFehler("Mediathek: Antwort ohne id oder Adresse")
        return {"wp_id": int(antwort["id"]), "url": antwort["source_url"]}

    def loesche(self, wp_id: int) -> None:
        """Endgültig löschen (force). Schon weg (404) gilt als gelöscht."""
        req = urllib.request.Request(f"{self.adresse}/{int(wp_id)}?force=true", method="DELETE")
        try:
            self._rufe(req)
        except MediathekFehler as e:
            if e.code != 404:
                raise
