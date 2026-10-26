import wave

import numpy as np
import pytest

from hilfen_medien import stille_mp3
from lib.musik import RATE, erzeuge_bett, waehle_stueck


def _lies(pfad):
    with wave.open(str(pfad)) as w:
        daten = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).reshape(-1, 2)
        return w.getframerate(), daten


def _rms(x):
    return float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))


def test_bett_hat_laenge_und_ducking(tmp_path):
    ziel = tmp_path / "bett.wav"
    erzeuge_bett(8.0, [(3.0, 6.0)], ziel, musik_ordner=tmp_path / "leer", woche_nr=43)
    rate, d = _lies(ziel)
    assert rate == RATE
    assert len(d) == pytest.approx(8.0 * RATE, abs=2)
    still = _rms(d[int(1.5 * RATE):int(2.5 * RATE)])
    unter_stimme = _rms(d[int(4.0 * RATE):int(5.0 * RATE)])
    assert unter_stimme < still * 0.6


def test_stueck_ohne_lizenz_wird_uebersprungen(tmp_path):
    ordner = tmp_path / "musik"
    ordner.mkdir()
    stille_mp3(ordner / "ohne.mp3", 1.0)
    stille_mp3(ordner / "mit.mp3", 1.0)
    (ordner / "mit.lizenz.txt").write_text("Pixabay-Lizenz", encoding="utf-8")
    assert waehle_stueck(ordner, woche_nr=43) == ordner / "mit.mp3"


def test_kein_ordner_ergibt_none(tmp_path):
    assert waehle_stueck(tmp_path / "gibtsnicht", woche_nr=43) is None


def test_bett_aus_stueck(tmp_path):
    ordner = tmp_path / "musik"
    ordner.mkdir()
    stille_mp3(ordner / "a.mp3", 3.0)
    (ordner / "a.lizenz.txt").write_text("frei", encoding="utf-8")
    ziel = tmp_path / "bett.wav"
    erzeuge_bett(5.0, [], ziel, musik_ordner=ordner, woche_nr=1)
    _, d = _lies(ziel)
    assert len(d) == pytest.approx(5.0 * RATE, abs=2)


def test_bett_blendet_am_ende_aus(tmp_path):
    ziel = tmp_path / "bett.wav"
    erzeuge_bett(8.0, [], ziel, musik_ordner=tmp_path / "leer", woche_nr=43)
    _, d = _lies(ziel)
    assert _rms(d[-int(0.05 * RATE):]) < _rms(d[int(3 * RATE):int(4 * RATE)]) * 0.05


def test_kurzes_bett_blendet_auch_aus(tmp_path):
    ziel = tmp_path / "bett.wav"
    erzeuge_bett(1.0, [], ziel, musik_ordner=tmp_path / "leer", woche_nr=43)
    _, d = _lies(ziel)
    assert _rms(d[-int(0.02 * RATE):]) < _rms(d[int(0.5 * RATE):int(0.6 * RATE)]) * 0.1


def test_ducking_ist_bei_sprechbeginn_voll_und_danach_wieder_oben():
    from lib.musik import DUCK_PEGEL, _ducking
    g = _ducking(10 * RATE, [(3.0, 6.0)])
    assert g[int(3.0 * RATE)] == pytest.approx(DUCK_PEGEL, abs=0.01)
    assert g[int(5.99 * RATE)] == pytest.approx(DUCK_PEGEL, abs=0.01)
    assert g[int(2.6 * RATE)] > 0.5
    assert g[int(6.5 * RATE)] == pytest.approx(1.0, abs=0.01)


def test_kurzes_stueck_wird_gelooped(tmp_path):
    from lib.musik import _stueck
    ordner = tmp_path / "m"
    ordner.mkdir()
    import subprocess
    mp3 = ordner / "t.mp3"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=440:r=44100",
                    "-t", "1.0", "-c:a", "libmp3lame", str(mp3)], check=True)
    d = _stueck(mp3, 3.0)
    assert len(d) == 3 * RATE
    assert _rms(d[int(2.2 * RATE):int(2.8 * RATE)]) > 0.05


def test_kaputtes_stueck_gibt_klaren_fehler(tmp_path):
    from lib.musik import MusikFehler
    ordner = tmp_path / "m"
    ordner.mkdir()
    (ordner / "x.mp3").write_bytes(b"kein audio")
    (ordner / "x.lizenz.txt").write_text("frei", encoding="utf-8")
    with pytest.raises(MusikFehler, match="x.mp3"):
        erzeuge_bett(2.0, [], tmp_path / "b.wav", musik_ordner=ordner, woche_nr=0)


def test_leere_lizenz_zaehlt_nicht(tmp_path):
    ordner = tmp_path / "m"
    ordner.mkdir()
    stille_mp3(ordner / "a.mp3", 1.0)
    (ordner / "a.lizenz.txt").write_text("  \n", encoding="utf-8")
    assert waehle_stueck(ordner, woche_nr=0) is None


@pytest.mark.parametrize("dauer", [0, -1.0])
def test_dauer_null_oder_negativ_gibt_fehler(tmp_path, dauer):
    from lib.musik import MusikFehler
    with pytest.raises(MusikFehler, match="Dauer"):
        erzeuge_bett(dauer, [], tmp_path / "b.wav", musik_ordner=tmp_path / "leer", woche_nr=0)
