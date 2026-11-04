"""Die Zeitzone des Servers ist einstellbar (FLIESSBAND_ZEITZONE), Standard Europe/Zurich."""
from zoneinfo import ZoneInfo

import pytest

from briefkasten.ablauf import zeitzone


def test_standard_ist_zuerich(monkeypatch):
    monkeypatch.delenv("FLIESSBAND_ZEITZONE", raising=False)
    assert zeitzone() == ZoneInfo("Europe/Zurich")


def test_eigene_zeitzone(monkeypatch):
    monkeypatch.setenv("FLIESSBAND_ZEITZONE", "Europe/Berlin")
    assert zeitzone() == ZoneInfo("Europe/Berlin")


def test_unbekannte_zeitzone_nennt_die_einstellung(monkeypatch):
    monkeypatch.setenv("FLIESSBAND_ZEITZONE", "Mars/Olympus")
    with pytest.raises(ValueError, match="FLIESSBAND_ZEITZONE"):
        zeitzone()
