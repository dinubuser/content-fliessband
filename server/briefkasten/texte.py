"""Texte und Inline-Knöpfe der Telegram-Nachrichten des Briefkastens.
callback_data: «f|z|a|v|vj|vn:<nr>:<version>» für einen Beitrag, «A|Aj|An:<woche>» für die Übersicht
(Telegram erlaubt höchstens 64 Bytes).
«s|n|j|l:<nr>:<version>» für Stopp, Nochmals, Jetzt posten, Auslassen (Etappe 5).
«fn|fl:<nr>:<version>» für Facebook nochmals / auslassen (Facebook-Zusatz).
Etappe 9: Meldung zu START-Kommentaren mit URL-Knopf «Profil öffnen» (kein callback_data)."""
import re
from datetime import datetime

FORMAT_NAME = {"reel": "Reel", "karussell": "Karussell"}
TAGE = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
MAX_NEUBAUTEN = 2
ZEILE = {"offen": "offen", "freigegeben": "✅ freigegeben", "aendern_wartet": "✏️ wird geändert",
         "verworfen": "❌ verworfen", "verpasst": "⏰ verpasst", "gepostet": "📲 gepostet",
         "ausgelassen": "⏭ ausgelassen"}
VERWERFEN_FRAGE = "Wirklich verwerfen? Ich baue dann ein Reserve-Thema."
LEER = {"inline_keyboard": []}
TERMIN_VORBEI = "Termin vorbei, dieser Beitrag wird nicht gepostet."
PLATZHALTER = "⚠️ Hat noch Platzhalter, bitte per ✏️ Ändern ergänzen."
PLATZHALTER_GESPERRT = "Hat noch Platzhalter, bitte zuerst ändern."


def _mit_platzhalter(b: dict) -> bool:
    """Offen, aber der Text hat noch Platzhalter: kein Freigeben, nur Ändern und Verwerfen."""
    return b["status"] == "offen" and bool(b.get("platzhalter"))


def kurz(termin: str) -> str:
    """'2026-10-27T19:00' → 'Di 27.10., 19:00'"""
    t = datetime.fromisoformat(termin)
    return f"{TAGE[t.weekday()]} {t:%d.%m.}, {t:%H:%M}"


def kopf(b: dict) -> str:
    version = f" · Version {b['version']}" if b["version"] > 1 else ""
    return f"{kurz(b['termin'])} · {FORMAT_NAME[b['format']]}{version}\n«{b['titel']}»"


def knopf_text(b: dict, zusatz: str = "") -> str:
    z = [kopf(b)]
    if b["status"] == "freigegeben":
        z.append(freigegeben_zeile(b))
    elif b["status"] != "offen":
        z.append(ZEILE[b["status"]])
    elif _mit_platzhalter(b) and b["neubauten"] >= MAX_NEUBAUTEN:
        z.append("⚠️ Hat noch Platzhalter. Ändern geht nicht mehr (schon 2-mal neu gebaut), nur noch Verwerfen.")
    elif _mit_platzhalter(b):
        z.append(PLATZHALTER)
    elif b["neubauten"] >= MAX_NEUBAUTEN:
        z.append("Ändern geht nicht mehr (schon 2-mal neu gebaut).")
    if zusatz:
        z.append(zusatz)
    return "\n".join(z)


def _knopf(text: str, daten: str) -> dict:
    return {"text": text, "callback_data": daten}


def tastatur(b: dict) -> dict:
    nr, v = b["nr"], b["version"]
    if b["status"] == "offen":
        reihe = [] if _mit_platzhalter(b) else [_knopf("✅ Freigeben", f"f:{nr}:{v}")]
        if b["neubauten"] < MAX_NEUBAUTEN:
            reihe.append(_knopf("✏️ Ändern", f"a:{nr}:{v}"))
        reihe.append(_knopf("❌ Verwerfen", f"v:{nr}:{v}"))
        return {"inline_keyboard": [reihe]}
    if b["status"] == "freigegeben":
        return {"inline_keyboard": [[_knopf("↩️ Zurücknehmen", f"z:{nr}:{v}")]]}
    return LEER


def verwerfen_tastatur(b: dict) -> dict:
    nr, v = b["nr"], b["version"]
    return {"inline_keyboard": [[_knopf("Ja, verwerfen", f"vj:{nr}:{v}"), _knopf("Nein", f"vn:{nr}:{v}")]]}


def ersetzt_text(b: dict, neue_version: int) -> str:
    return f"{kopf(b)}\nErsetzt durch Version {neue_version}, siehe neue Nachricht."


def aendern_frage(b: dict) -> str:
    return f"Was soll ich bei «{b['titel']}» ändern? Antworte direkt auf diese Nachricht."


def zeile(b: dict) -> str:
    stand = "offen, ⚠️ hat noch Platzhalter" if _mit_platzhalter(b) else ZEILE[b["status"]]
    return f"{kurz(b['termin'])} · {FORMAT_NAME[b['format']]} «{b['titel']}»: {stand}"


def uebersicht(woche: str, beitraege: list[dict]) -> str:
    offen = sum(1 for b in beitraege if b["status"] == "offen")
    schluss = f"Noch offen: {offen}" if offen else "Alles entschieden."
    return "\n".join([f"Freigabe {woche}", *(zeile(b) for b in beitraege), "", schluss])


def uebersicht_tastatur(woche: str, beitraege: list[dict]) -> dict:
    if any(b["status"] == "offen" and not _mit_platzhalter(b) for b in beitraege):
        return {"inline_keyboard": [[_knopf("✅ Alle offenen freigeben", f"A:{woche}")]]}
    return LEER


def freigebbar(b: dict) -> bool:
    """Darf «Alle offenen freigeben» diesen Beitrag freigeben?"""
    return b["status"] == "offen" and not _mit_platzhalter(b)


def alle_frage(n: int) -> str:
    return f"Wirklich alle {n} offenen Beiträge freigeben?"


def alle_tastatur(woche: str) -> dict:
    return {"inline_keyboard": [[_knopf("Ja, alle freigeben", f"Aj:{woche}"), _knopf("Nein", f"An:{woche}")]]}


def erinnerung(offen: list[dict]) -> str:
    return "\n".join(["Erinnerung: Diese Beiträge sind noch nicht freigegeben.", *(zeile(b) for b in offen), "",
                      "Ohne Freigabe wird nichts gepostet."])


def verpasst_text(b: dict) -> str:
    return (f"⏰ «{b['titel']}» ({kurz(b['termin'])}) war bis zum Termin nicht freigegeben "
            "und wird nicht gepostet.")


def freigegeben_zeile(b: dict) -> str:
    t = datetime.fromisoformat(b["termin"])
    return f"✅ Freigegeben, geht {TAGE[t.weekday()]} {t:%d.%m.} um {t:%H:%M} online"


DATEIEN_FEHLEN = "⚠️ Die Dateien fehlen noch. Kommen sie nicht bis zum Termin, wird nicht gepostet."


def vorwarnung(b: dict, dateien_fehlen: bool = False) -> str:
    """dateien_fehlen nur beim Senden der Vorwarnung. Spätere Bearbeitungen (gestoppt, online, verpasst,
    Dateien nachgereicht) zeigen den Text ohne Zusatz."""
    text = f"⏰ Um {datetime.fromisoformat(b['termin']):%H:%M} geht «{b['titel']}» online."
    return f"{text}\n{DATEIEN_FEHLEN}" if dateien_fehlen else text


def vorwarnung_tastatur(b: dict) -> dict:
    return {"inline_keyboard": [[_knopf("⏸ Stopp", f"s:{b['nr']}:{b['version']}")]]}


def gepostet(b: dict, link: str | None, facebook: str | None = None) -> str:
    text = f"✅ Gepostet: «{b['titel']}»" + (f"\n{link}" if link else "")
    return text + (f"\nFacebook: {facebook}" if facebook else "")


def nicht_gepostet(b: dict, grund: str) -> str:
    return f"⚠️ Nicht gepostet: «{b['titel']}», Grund: {grund}"


def nochmals_gescheitert(b: dict, zeit: datetime, grund: str) -> str:
    return f"⚠️ Nicht gepostet: «{b['titel']}»\nNochmals gescheitert ({zeit:%H:%M}): {grund}"


def nochmals_tastatur(b: dict) -> dict:
    return {"inline_keyboard": [[_knopf("🔁 Nochmals versuchen", f"n:{b['nr']}:{b['version']}")]]}


def verpasst_post(b: dict, grund: str) -> str:
    return f"⚠️ Verpasst: «{b['titel']}» (geplant {kurz(b['termin'])}). Grund: {grund}"


def nachholen_tastatur(b: dict) -> dict:
    nr, v = b["nr"], b["version"]
    return {"inline_keyboard": [[_knopf("🔁 Jetzt posten", f"j:{nr}:{v}"), _knopf("❌ Auslassen", f"l:{nr}:{v}")]]}


FRIST_VORBEI = "Jetzt posten hat nicht innert 30 Minuten geklappt"


def unklar(b: dict) -> str:
    return f"❓ Unklar, ob «{b['titel']}» online ist. Bitte auf Instagram nachschauen."


def schluessel_meldung(grund: str) -> str:
    return (f"⚠️ Instagram-Schlüssel: {grund}. Bis ein neuer da ist, wird nichts gepostet. "
            "Bitte Instagram neu verbinden (README der Agentur, Schritte 7 und 8), dann server/instagram.sh.")


def fb_nicht_gepostet(b: dict, grund: str) -> str:
    return f"⚠️ Facebook nicht gepostet: «{b['titel']}», Grund: {grund}\nAuf Instagram ist der Beitrag online."


def fb_tastatur(b: dict) -> dict:
    nr, v = b["nr"], b["version"]
    return {"inline_keyboard": [[_knopf("🔁 Nochmals", f"fn:{nr}:{v}"), _knopf("⏭ Auslassen", f"fl:{nr}:{v}")]]}


def fb_nachgeholt(b: dict) -> str:
    return f"✅ Facebook nachgeholt: «{b['titel']}»"


def fb_schluessel_meldung(grund: str) -> str:
    return (f"⚠️ Facebook-Schlüssel: {grund}. Bis ein neuer da ist, geht nichts auf Facebook (Instagram läuft "
            "weiter). Bitte den Seiten-Schlüssel neu holen und server/facebook.sh ausführen.")


# --- Etappe 9: START-Kommentare ---

NUTZERNAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._]{0,29}")   # so sehen Instagram-Namen aus
KOMMENTARE_HINWEIS = "⚠️ Kommentare lesen geht nicht: Instagram neu verbinden"


def kommentar_meldung(username, art: str, titel: str) -> str:
    wer = f"@{username}" if username else "Jemand"
    return f"💬 {wer} hat START kommentiert · {art} ‹{titel}›"


def profil_tastatur(username) -> dict | None:
    """Knopf mit Link aufs Profil. Ohne gültigen Namen kein Knopf."""
    if not isinstance(username, str) or not NUTZERNAME.fullmatch(username):
        return None
    return {"inline_keyboard": [[{"text": "Profil öffnen", "url": f"https://instagram.com/{username}"}]]}


def kommentare_hinweis(grund: str) -> str:
    return (f"{KOMMENTARE_HINWEIS} (Berechtigung für Kommentare nötig), danach server/instagram.sh. "
            f"Grund: {grund}")
