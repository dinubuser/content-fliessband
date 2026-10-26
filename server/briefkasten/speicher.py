"""SQLite-Speicher des Briefkastens: Beiträge, Ereignisse, Posts, Kommentare (Etappe 9) und Stand (Schlüssel mit JSON-Wert).
Jeder Aufruf schreibt sofort (autocommit). Mehrere Threads greifen nur hinter der Sperre von Ablauf zu."""
import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS beitraege (
  nr INTEGER PRIMARY KEY AUTOINCREMENT,
  id TEXT UNIQUE NOT NULL,
  woche TEXT NOT NULL,
  version INTEGER NOT NULL,
  titel TEXT NOT NULL,
  format TEXT NOT NULL,
  termin TEXT NOT NULL,
  status TEXT NOT NULL,
  neubauten INTEGER NOT NULL,
  nachricht_id INTEGER,
  platzhalter INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ereignisse (
  nr INTEGER PRIMARY KEY AUTOINCREMENT,
  zeit TEXT NOT NULL,
  art TEXT NOT NULL,
  beitrag TEXT,
  woche TEXT,
  version INTEGER,
  notiz TEXT,
  nachricht TEXT
);
CREATE TABLE IF NOT EXISTS posts (
  id TEXT PRIMARY KEY,
  version INTEGER NOT NULL,
  medien TEXT,
  cover TEXT,
  caption TEXT,
  post_status TEXT NOT NULL,
  manuell INTEGER NOT NULL DEFAULT 0,
  versuche INTEGER NOT NULL DEFAULT 0,
  naechster_versuch TEXT,
  grund TEXT,
  creation_id TEXT,
  instagram_id TEXT,
  permalink TEXT,
  gepostet TEXT,
  vorwarnung_id INTEGER,
  meldung_id INTEGER,
  meldung_offen TEXT,
  manuell_bis TEXT,
  nochmals INTEGER NOT NULL DEFAULT 0,
  gepostet_id INTEGER,
  fb_status TEXT,
  fb_id TEXT,
  fb_link TEXT,
  fb_versuche INTEGER NOT NULL DEFAULT 0,
  fb_naechster TEXT,
  fb_grund TEXT,
  fb_meldung_id INTEGER,
  fb_beendet INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS kommentare (
  id TEXT PRIMARY KEY,
  media_id TEXT,
  username TEXT,
  text TEXT,
  zeit TEXT,
  start INTEGER,
  gemeldet TEXT
);
CREATE INDEX IF NOT EXISTS kommentare_media ON kommentare (media_id);
CREATE TABLE IF NOT EXISTS stand (schluessel TEXT PRIMARY KEY, wert TEXT NOT NULL);
"""
FELDER = ("id", "woche", "version", "titel", "format", "termin", "status", "neubauten", "nachricht_id",
          "platzhalter")
BOOL = ("platzhalter",)   # als 0/1 gespeichert, als bool gelesen
STATUS = ("offen", "freigegeben", "aendern_wartet", "verworfen", "verpasst", "gepostet", "ausgelassen")
POST_STATUS = ("geplant", "vorgewarnt", "laeuft", "gepostet", "fehler", "verpasst_post", "ausgelassen", "unklar")
FB_STATUS = ("offen", "laeuft", "gepostet", "fehler", "ausgelassen")
POST_FELDER = ("version", "medien", "cover", "caption", "post_status", "manuell", "versuche", "naechster_versuch",
               "grund", "creation_id", "instagram_id", "permalink", "gepostet", "vorwarnung_id", "meldung_id",
               "meldung_offen", "manuell_bis", "nochmals", "gepostet_id", "fb_status", "fb_id", "fb_link",
               "fb_versuche", "fb_naechster", "fb_grund", "fb_meldung_id", "fb_beendet")
POST_BOOL = ("manuell", "nochmals", "fb_beendet")
# Spalten, die der Facebook-Zusatz (2026-10-24) nachrüstet: Name → SQL-Typ
FB_SPALTEN = {"gepostet_id": "INTEGER", "fb_status": "TEXT", "fb_id": "TEXT", "fb_link": "TEXT",
              "fb_versuche": "INTEGER NOT NULL DEFAULT 0", "fb_naechster": "TEXT", "fb_grund": "TEXT",
              "fb_meldung_id": "INTEGER", "fb_beendet": "INTEGER NOT NULL DEFAULT 0"}

MAX_KOMMENTAR = 1000   # Zeichen Kommentartext, mehr braucht niemand zum Melden


class Speicher:
    def __init__(self, pfad):
        if str(pfad) != ":memory:":
            Path(pfad).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(pfad), check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self._migriere()

    def _migriere(self) -> None:
        """Ältere Datenbank: Spalte platzhalter (vor 2026-10-23) und Facebook-Spalten (vor 2026-10-24) nachrüsten, Zeilen bleiben."""
        spalten = {r["name"] for r in self.db.execute("PRAGMA table_info(beitraege)")}
        if "platzhalter" not in spalten:
            self.db.execute("ALTER TABLE beitraege ADD COLUMN platzhalter INTEGER NOT NULL DEFAULT 0")
        posts = {r["name"] for r in self.db.execute("PRAGMA table_info(posts)")}
        for name, typ in FB_SPALTEN.items():
            if name not in posts:
                self.db.execute(f"ALTER TABLE posts ADD COLUMN {name} {typ}")

    @staticmethod
    def _zeile(r) -> dict:
        b = dict(r)
        for f in BOOL:
            b[f] = bool(b[f])
        return b

    @staticmethod
    def _wert(f: str, w):
        return int(bool(w)) if f in BOOL else w

    def beitrag(self, id: str) -> dict | None:
        r = self.db.execute("SELECT * FROM beitraege WHERE id = ?", (id,)).fetchone()
        return self._zeile(r) if r else None

    def beitrag_nr(self, nr: int) -> dict | None:
        r = self.db.execute("SELECT * FROM beitraege WHERE nr = ?", (nr,)).fetchone()
        return self._zeile(r) if r else None

    def beitraege(self, woche: str | None = None) -> list[dict]:
        if woche is None:
            rows = self.db.execute("SELECT * FROM beitraege ORDER BY termin, nr")
        else:
            rows = self.db.execute("SELECT * FROM beitraege WHERE woche = ? ORDER BY termin, nr", (woche,))
        return [self._zeile(r) for r in rows]

    def speichere_beitrag(self, b: dict) -> dict:
        """Neu anlegen oder (gleiche id) ersetzen. Die Nummer nr bleibt beim Ersetzen gleich."""
        if b["status"] not in STATUS:
            raise ValueError(f"unbekannter Status {b['status']}")
        self.db.execute(
            "INSERT INTO beitraege (id, woche, version, titel, format, termin, status, neubauten, nachricht_id, "
            "platzhalter) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET woche = excluded.woche, "
            "version = excluded.version, titel = excluded.titel, format = excluded.format, "
            "termin = excluded.termin, status = excluded.status, neubauten = excluded.neubauten, "
            "nachricht_id = excluded.nachricht_id, platzhalter = excluded.platzhalter",
            [self._wert(f, b.get(f)) for f in FELDER])
        return self.beitrag(b["id"])

    def setze(self, id: str, **felder) -> dict:
        unbekannt = set(felder) - set(FELDER[1:])
        if unbekannt:
            raise ValueError(f"unbekannte Felder {sorted(unbekannt)}")
        if "status" in felder and felder["status"] not in STATUS:
            raise ValueError(f"unbekannter Status {felder['status']}")
        zuweisung = ", ".join(f"{k} = ?" for k in felder)
        self.db.execute(f"UPDATE beitraege SET {zuweisung} WHERE id = ?",
                        [*(self._wert(k, w) for k, w in felder.items()), id])
        return self.beitrag(id)

    # --- Posts (Etappe 5): Post-Stand pro Beitrag, gilt für eine Version ---

    @staticmethod
    def _post_zeile(r) -> dict:
        p = dict(r)
        p["medien"] = json.loads(p["medien"]) if p["medien"] else None
        for f in POST_BOOL:
            p[f] = bool(p[f])
        return p

    @staticmethod
    def _post_wert(f: str, w):
        if f == "medien":
            return json.dumps(w, ensure_ascii=False) if w is not None else None
        if f in POST_BOOL:
            return int(bool(w))
        return w

    def post(self, id: str) -> dict | None:
        r = self.db.execute("SELECT * FROM posts WHERE id = ?", (id,)).fetchone()
        return self._post_zeile(r) if r else None

    def posts(self) -> list[dict]:
        return [self._post_zeile(r) for r in self.db.execute("SELECT * FROM posts ORDER BY id")]

    def neuer_post(self, id: str, version: int) -> dict:
        """Post-Stand für diese Version neu anlegen, alles andere zurück auf Anfang."""
        self.db.execute("INSERT OR REPLACE INTO posts (id, version, post_status) VALUES (?, ?, 'geplant')",
                        (id, version))
        return self.post(id)

    def setze_post(self, id: str, **felder) -> dict:
        unbekannt = set(felder) - set(POST_FELDER)
        if unbekannt:
            raise ValueError(f"unbekannte Felder {sorted(unbekannt)}")
        if "post_status" in felder and felder["post_status"] not in POST_STATUS:
            raise ValueError(f"unbekannter Post-Status {felder['post_status']}")
        if felder.get("fb_status") is not None and felder["fb_status"] not in FB_STATUS:
            raise ValueError(f"unbekannter Facebook-Status {felder['fb_status']}")
        zuweisung = ", ".join(f"{k} = ?" for k in felder)
        self.db.execute(f"UPDATE posts SET {zuweisung} WHERE id = ?",
                        [*(self._post_wert(k, w) for k, w in felder.items()), id])
        return self.post(id)

    def letzte_freigabe(self, id: str, version: int) -> str | None:
        """Zeit der letzten Freigabe dieser Version (Vorwarnung nur, wenn früh genug freigegeben)."""
        r = self.db.execute("SELECT zeit FROM ereignisse WHERE art = 'freigegeben' AND beitrag = ? AND version = ? "
                            "ORDER BY nr DESC LIMIT 1", (id, version)).fetchone()
        return r["zeit"] if r else None

    def ereignis(self, zeit: str, art: str, beitrag=None, woche=None, version=None, notiz=None,
                 nachricht=None) -> int:
        roh = json.dumps(nachricht, ensure_ascii=False) if nachricht is not None else None
        cur = self.db.execute(
            "INSERT INTO ereignisse (zeit, art, beitrag, woche, version, notiz, nachricht) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)", (zeit, art, beitrag, woche, version, notiz, roh))
        return cur.lastrowid

    def ereignisse(self, nach: int, arten) -> list[dict]:
        arten = list(arten)
        platz = ", ".join("?" * len(arten))
        rows = self.db.execute(f"SELECT * FROM ereignisse WHERE nr > ? AND art IN ({platz}) ORDER BY nr",
                               [nach, *arten])
        aus = []
        for r in rows:
            e = dict(r)
            e["nachricht"] = json.loads(e["nachricht"]) if e["nachricht"] else None
            aus.append(e)
        return aus

    def lies(self, schluessel: str, vorgabe=None):
        r = self.db.execute("SELECT wert FROM stand WHERE schluessel = ?", (schluessel,)).fetchone()
        return json.loads(r["wert"]) if r else vorgabe

    def schreibe(self, schluessel: str, wert) -> None:
        self.db.execute("INSERT INTO stand (schluessel, wert) VALUES (?, ?) "
                        "ON CONFLICT(schluessel) DO UPDATE SET wert = excluded.wert",
                        (schluessel, json.dumps(wert, ensure_ascii=False)))

    # --- Kommentare (Etappe 9): jeder Kommentar einmal, START-Kommentare einmal gemeldet ---

    @staticmethod
    def _kommentar_zeile(r) -> dict:
        k = dict(r)
        k["start"] = bool(k["start"])
        return k

    def kommentar(self, id: str) -> dict | None:
        r = self.db.execute("SELECT * FROM kommentare WHERE id = ?", (id,)).fetchone()
        return self._kommentar_zeile(r) if r else None

    def neuer_kommentar(self, k: dict) -> bool:
        """Speichert einen Kommentar, falls er noch fehlt. True: neu. Ein vorhandener bleibt unverändert.
        gemeldet: None (noch melden, falls start), 'still' (erster Lauf) oder Zeit der Meldung."""
        cur = self.db.execute(
            "INSERT OR IGNORE INTO kommentare (id, media_id, username, text, zeit, start, gemeldet) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(k["id"]), str(k["media_id"]), k.get("username"), str(k.get("text") or "")[:MAX_KOMMENTAR],
             k.get("zeit"), int(bool(k.get("start"))), k.get("gemeldet")))
        return cur.rowcount == 1

    def zu_melden(self) -> list[dict]:
        rows = self.db.execute("SELECT * FROM kommentare WHERE start = 1 AND gemeldet IS NULL ORDER BY zeit, id")
        return [self._kommentar_zeile(r) for r in rows]

    def setze_gemeldet(self, id: str, wert: str) -> None:
        self.db.execute("UPDATE kommentare SET gemeldet = ? WHERE id = ?", (wert, id))

    def start_anzahl(self) -> dict[str, int]:
        """START-Kommentare pro Instagram-Beitrag (für /zahlen)."""
        rows = self.db.execute("SELECT media_id, COUNT(*) AS n FROM kommentare WHERE start = 1 GROUP BY media_id")
        return {r["media_id"]: r["n"] for r in rows}

    def kommentar_zahlen(self) -> dict:
        r = self.db.execute("SELECT COUNT(*) AS alle, COALESCE(SUM(start), 0) AS start FROM kommentare").fetchone()
        return {"kommentare": r["alle"], "start": r["start"]}

    def abgelehnt_anzahl(self) -> int:
        """START-Kommentare, deren Telegram-Meldung dauerhaft abgelehnt wurde (gemeldet = 'abgelehnt')."""
        return self.db.execute("SELECT COUNT(*) FROM kommentare WHERE gemeldet = 'abgelehnt'").fetchone()[0]

    def post_mit_instagram(self, instagram_id: str) -> dict | None:
        """Post-Zeile des Beitrags, der als dieser Instagram-Beitrag online ging (Thema für die Meldung)."""
        r = self.db.execute("SELECT * FROM posts WHERE instagram_id = ? ORDER BY id LIMIT 1",
                            (instagram_id,)).fetchone()
        return self._post_zeile(r) if r else None
