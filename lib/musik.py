"""Musikbett unter der Stimme: Stück aus musik/ (mit Lizenz-Datei) oder synthetisches Pad.
Unter der Stimme wird es leiser (Ducking ist eingebacken)."""
import subprocess
import wave
from pathlib import Path

import numpy as np

RATE = 44100
TAKT = 3.6
AKKORDE = [[50, 57, 61, 64, 66], [47, 54, 57, 62, 66], [43, 50, 54, 59, 62], [45, 52, 57, 62, 64]]
DUCK_PEGEL = 0.35
DUCK_RAMPE = 0.3
ENDUNGEN = (".mp3", ".wav")
AUSBLENDE = 2.0


class MusikFehler(Exception):
    pass


def _mtof(m: int) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def _pad(dauer: float) -> np.ndarray:
    n = int(round(dauer * RATE))
    links, rechts = np.zeros(n), np.zeros(n)
    for b in range(int(np.ceil(dauer / TAKT)) + 1):
        start, laenge = b * TAKT - 1.2, TAKT + 2.4
        i0, i1 = max(0, int(start * RATE)), min(n, int((start + laenge) * RATE))
        if i1 <= i0:
            continue
        t = np.arange(i0, i1) / RATE
        env = np.sin(np.pi * np.clip((t - start) / laenge, 0, 1)) ** 1.6
        for k, m in enumerate(AKKORDE[b % 4]):
            f, amp = _mtof(m), (0.10 if k == 0 else 0.055)
            ph = 2 * np.pi * f * t
            v = (np.sin(ph) + 0.25 * np.sin(2 * ph) + 0.08 * np.sin(3 * ph)) * amp * env
            links[i0:i1] += v * (1 + 0.02 * np.sin(ph * 1.003))
            rechts[i0:i1] += v * (1 + 0.02 * np.sin(ph * 0.997))
    return np.stack([links, rechts], axis=1)


def _stueck(pfad: Path, dauer: float) -> np.ndarray:
    try:
        lauf = subprocess.run(["ffmpeg", "-v", "error", "-i", str(pfad), "-f", "s16le", "-ac", "2",
                               "-ar", str(RATE), "-"], capture_output=True, check=True)
    except subprocess.CalledProcessError as e:
        meldung = e.stderr.decode("utf-8", "replace").strip()[:200]
        raise MusikFehler(f"Musikstück {pfad.name} nicht lesbar: {meldung}") from e
    except FileNotFoundError as e:
        raise MusikFehler("ffmpeg nicht gefunden (für Musikstücke nötig)") from e
    daten = np.frombuffer(lauf.stdout, dtype=np.int16).reshape(-1, 2).astype(np.float64) / 32768.0
    if len(daten) == 0:
        raise MusikFehler(f"Musikstück {pfad.name} ist leer")
    n = int(round(dauer * RATE))
    if len(daten) < n:
        daten = np.tile(daten, (int(np.ceil(n / len(daten))), 1))
    return daten[:n].copy()


def _ducking(n: int, sprache: list[tuple[float, float]]) -> np.ndarray:
    """1.0 ohne Sprache, DUCK_PEGEL mit Sprache, dazwischen weich (gleitender Mittelwert)."""
    maske = np.zeros(n)
    fenster = max(1, int(DUCK_RAMPE * RATE))
    halb = fenster // 2
    # Maske um die halbe Rampe weiten: bei Sprechbeginn ist voll geduckt, erst nach Sprechende geht es hoch.
    for a, e in sprache:
        maske[max(0, int(a * RATE) - halb):min(n, int(e * RATE) + halb)] = 1.0
    weich = np.convolve(maske, np.ones(fenster) / fenster, mode="same")
    return 1.0 - (1.0 - DUCK_PEGEL) * weich


def _hat_lizenz(stueck: Path) -> bool:
    lizenz = stueck.with_suffix(".lizenz.txt")
    return lizenz.is_file() and bool(lizenz.read_text(encoding="utf-8", errors="replace").strip())


def waehle_stueck(ordner: Path, woche_nr: int) -> Path | None:
    """Stück mit gleichnamiger .lizenz.txt, im Wechsel nach Kalenderwoche."""
    if not ordner.is_dir():
        return None
    stuecke = sorted(p for p in ordner.iterdir()
                     if p.suffix.lower() in ENDUNGEN and _hat_lizenz(p))
    return stuecke[woche_nr % len(stuecke)] if stuecke else None


def erzeuge_bett(dauer: float, sprache: list[tuple[float, float]], ziel: Path,
                 musik_ordner: Path, woche_nr: int) -> Path:
    if dauer <= 0:
        raise MusikFehler(f"Dauer des Musikbetts muss grösser als 0 sein (war {dauer}).")
    stueck = waehle_stueck(musik_ordner, woche_nr)
    daten = _stueck(stueck, dauer) if stueck else _pad(dauer)
    spitze = float(np.max(np.abs(daten))) or 1.0
    daten = daten / spitze * 0.9 * _ducking(len(daten), sprache)[:, None]
    aus = min(len(daten), int(min(AUSBLENDE, dauer / 2) * RATE))
    if aus > 0:
        daten[len(daten) - aus:] *= np.linspace(1, 0, aus)[:, None]
    ein = min(len(daten), int(0.6 * RATE))
    daten[:ein] *= np.linspace(0, 1, ein)[:, None]
    ziel.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(ziel), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((daten * 32767).astype(np.int16).tobytes())
    return ziel
