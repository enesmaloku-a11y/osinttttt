"""db.py - Ruajtja në SQLite: artikujt dhe ngjarjet."""
import json
import sqlite3
from contextlib import closing

DB_PATH = "osint.db"

# Skema: emrat e kolonave pa "ë" që të jenë të lehta për SQL.
SKEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    url               TEXT UNIQUE NOT NULL,   -- URL e burimit (unike = pa dublikatë)
    burimi            TEXT NOT NULL,          -- p.sh. "Koha", "GDELT:balkaninsight.com"
    titulli           TEXT,
    data              TEXT NOT NULL,          -- data e publikimit (ISO)
    gjuha             TEXT NOT NULL,          -- sq / sr / en / ...
    teksti            TEXT,
    teksti_perkthyer  TEXT,                   -- mbushet më vonë nga processor.py
    perpunuar         INTEGER NOT NULL DEFAULT 0,  -- 0 = jo, 1 = po
    rezultati_json    TEXT,                   -- cache: JSON-i i nxjerrë nga modeli
    mbledhur_me       TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    titulli         TEXT NOT NULL,
    lloji           TEXT,                 -- p.sh. "protestë", "incident kufitar"
    data            TEXT NOT NULL,
    vendi           TEXT,
    lat             REAL,
    lon             REAL,
    gjuha           TEXT NOT NULL,        -- gjuha e burimit kryesor
    burimet         TEXT NOT NULL,        -- listë JSON me URL-të e burimeve
    besueshmeria    REAL,                 -- llogaritet me rregulla në scoring.py
    boshllequet     TEXT NOT NULL DEFAULT '[]',  -- listë JSON, p.sh. ["vetëm një burim"]
    detajet_json    TEXT,
    krijuar_me      TEXT DEFAULT (datetime('now'))
);
"""


def lidhu():
    """Kthen një lidhje me bazën dhe krijon tabelat nëse mungojnë."""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SKEMA)
    return con


def ekziston_url(url):
    """True nëse artikulli është ruajtur më parë (që të mos e shkarkojmë sërish)."""
    with closing(lidhu()) as con:
        return con.execute("SELECT 1 FROM articles WHERE url = ?", (url,)).fetchone() is not None


def ruaj_artikull(url, burimi, titulli, data, gjuha, teksti):
    """Ruan artikullin; kthen True nëse ishte i ri, False nëse ishte dublikatë."""
    with closing(lidhu()) as con, con:
        cur = con.execute(
            "INSERT OR IGNORE INTO articles (url, burimi, titulli, data, gjuha, teksti) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (url, burimi, titulli, data, gjuha, teksti),
        )
        return cur.rowcount == 1


def artikuj_te_paperpunuar(limit=100):
    """Artikujt që ende s'janë kaluar nga processor/extractor."""
    with closing(lidhu()) as con:
        return con.execute(
            "SELECT * FROM articles WHERE perpunuar = 0 ORDER BY data DESC LIMIT ?", (limit,)
        ).fetchall()


def artikuj_pa_perkthim(limit=50):
    """Artikujt që processor.py nuk i ka kaluar ende (teksti_perkthyer bosh)."""
    with closing(lidhu()) as con:
        return con.execute(
            "SELECT id, gjuha, titulli, teksti FROM articles "
            "WHERE teksti_perkthyer IS NULL ORDER BY data DESC LIMIT ?", (limit,)
        ).fetchall()


def ruaj_perkthimin(article_id, teksti, teksti_perkthyer):
    """Ruan tekstin e pastruar dhe përkthimin anglisht."""
    with closing(lidhu()) as con, con:
        con.execute("UPDATE articles SET teksti = ?, teksti_perkthyer = ? WHERE id = ?",
                    (teksti, teksti_perkthyer, article_id))


def artikuj_per_nxjerrje(limit=50):
    """Artikujt që extractor.py s'i ka parë ende (më të rinjtë së pari)."""
    with closing(lidhu()) as con:
        return con.execute(
            "SELECT id, burimi, data, gjuha, titulli, teksti, teksti_perkthyer FROM articles "
            "WHERE perpunuar = 0 ORDER BY data DESC LIMIT ?", (limit,)
        ).fetchall()


def artikuj_te_nxjerre():
    """Artikujt e përpunuar bashkë me JSON-in e ruajtur (për correlator.py)."""
    with closing(lidhu()) as con:
        return con.execute(
            "SELECT id, url, burimi, data, gjuha, rezultati_json FROM articles "
            "WHERE perpunuar = 1 AND rezultati_json IS NOT NULL ORDER BY data"
        ).fetchall()


def ngjarjet():
    with closing(lidhu()) as con:
        return con.execute("SELECT * FROM events").fetchall()


def ruaj_besueshmerine(event_id, pike, detajet):
    """Ruan pikët nga scoring.py bashkë me arsyetimin (te detajet_json)."""
    with closing(lidhu()) as con, con:
        con.execute("UPDATE events SET besueshmeria = ?, detajet_json = ? WHERE id = ?",
                    (pike, json.dumps(detajet, ensure_ascii=False), event_id))


def fshi_ngjarjet():
    """correlator.py i rindërton ngjarjet nga e para në çdo ekzekutim."""
    with closing(lidhu()) as con, con:
        con.execute("DELETE FROM events")


def sheno_perpunuar(article_id, rezultati, teksti_perkthyer=None):
    """Ruan JSON-in e modelit (cache) dhe e shënon artikullin si të përpunuar."""
    with closing(lidhu()) as con, con:
        con.execute(
            "UPDATE articles SET perpunuar = 1, rezultati_json = ?, "
            "teksti_perkthyer = COALESCE(?, teksti_perkthyer) WHERE id = ?",
            (json.dumps(rezultati, ensure_ascii=False), teksti_perkthyer, article_id),
        )


def ruaj_ngjarje(titulli, data, gjuha, burimet, boshllequet, lloji=None, vendi=None,
                 lat=None, lon=None, besueshmeria=None, detajet=None):
    """Ruan një ngjarje. 'burimet' (URL) dhe 'boshllequet' janë të detyrueshme."""
    if not burimet:
        raise ValueError("Çdo ngjarje duhet të ketë të paktën një URL burimi")
    with closing(lidhu()) as con, con:
        cur = con.execute(
            "INSERT INTO events (titulli, lloji, data, vendi, lat, lon, gjuha, burimet, "
            "besueshmeria, boshllequet, detajet_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (titulli, lloji, data, vendi, lat, lon, gjuha,
             json.dumps(burimet, ensure_ascii=False), besueshmeria,
             json.dumps(boshllequet, ensure_ascii=False),
             json.dumps(detajet or {}, ensure_ascii=False)),
        )
        return cur.lastrowid


def numero_sipas_burimit():
    """Kthen [(burimi, numri)] për raportim."""
    with closing(lidhu()) as con:
        return con.execute(
            "SELECT burimi, COUNT(*) AS n FROM articles GROUP BY burimi ORDER BY n DESC"
        ).fetchall()
