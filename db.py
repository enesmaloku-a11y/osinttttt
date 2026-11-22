"""db.py - Ruajtja në SQLite: artikujt dhe ngjarjet."""
import json
import os
import sqlite3
from contextlib import closing

DB_PATH = os.environ.get("OSINT_DB", "osint.db")  # p.sh. OSINT_DB=demo.db për demon

# Skema: emrat e kolonave pa "ë" që të jenë të lehta për SQL.
SKEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    url               TEXT UNIQUE NOT NULL,   -- URL e burimit (unike = pa dublikatë)
    burimi            TEXT NOT NULL,          -- p.sh. "Koha", "GDELT:balkaninsight.com"
    titulli           TEXT,
    data              TEXT NOT NULL,          -- data më e mirë për renditje/përpunim (ISO)
    published_at      TEXT,                   -- publikimi i deklaruar nga burimi, kur njihet
    gjuha             TEXT NOT NULL,          -- sq / sr / en / ...
    teksti            TEXT,
    teksti_perkthyer  TEXT,                   -- mbushet më vonë nga processor.py
    perpunuar         INTEGER NOT NULL DEFAULT 0,  -- 0 = jo, 1 = po
    rezultati_json    TEXT,                   -- cache: JSON-i i nxjerrë nga modeli
    mbledhur_me       TEXT DEFAULT (datetime('now')),
    hash_sha256       TEXT,
    raw_text          TEXT,
    lloji_tekstit     TEXT                    -- plote / permbledhje / deshtoi, nga mbledhësi
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

-- Vendimet e analistit. Ruhen veçmas sepse correlator.py e rindërton events çdo herë.
-- Çelësi është URL-ja e artikullit më të hershëm të ngjarjes.
CREATE TABLE IF NOT EXISTS vendimet (
    url_kryesor  TEXT PRIMARY KEY,
    statusi      TEXT NOT NULL CHECK (statusi IN
                 ('e konfirmuar', 'e pakonfirmuar', 'e hedhur poshtë')),
    shenimi      TEXT,
    koha         TEXT DEFAULT (datetime('now'))
);
"""

STATUSET = ["e pakonfirmuar", "e konfirmuar", "e hedhur poshtë"]


def lidhu():
    """Kthen një lidhje me bazën dhe krijon tabelat nëse mungojnë."""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        con.executescript(SKEMA)
        shtesat = ("hash_sha256", "raw_text", "published_at", "lloji_tekstit")
        kolonat = {r["name"] for r in con.execute("PRAGMA table_info(articles)")}
        if not set(shtesat) <= kolonat:
            with con:
                # Dy procese mund të hapin të njëjtën bazë të vjetër në të njëjtën kohë.
                con.execute("BEGIN IMMEDIATE")
                kolonat = {r["name"] for r in con.execute("PRAGMA table_info(articles)")}
                for kolona in shtesat:
                    if kolona not in kolonat:
                        con.execute(f"ALTER TABLE articles ADD COLUMN {kolona} TEXT")
                if "raw_text" not in kolonat:
                    con.execute("UPDATE articles SET raw_text = teksti WHERE teksti_perkthyer IS NULL")
    except BaseException:
        con.close()
        raise
    return con


def ekziston_url(url):
    """True nëse artikulli është ruajtur më parë (që të mos e shkarkojmë sërish)."""
    with closing(lidhu()) as con:
        return con.execute("SELECT 1 FROM articles WHERE url = ?", (url,)).fetchone() is not None


def ruaj_artikull(url, burimi, titulli, data, gjuha, teksti, hash_sha256=None, *,
                  published_at=None, lloji_tekstit=None):
    """Ruan artikullin; kthen True nëse ishte i ri, False nëse ishte dublikatë.
    hash_sha256 = gjurma e tekstit bruto kur u mblodh (prova nëse faqja ndryshon më vonë)."""
    with closing(lidhu()) as con, con:
        cur = con.execute(
            "INSERT OR IGNORE INTO articles (url, burimi, titulli, data, gjuha, teksti, raw_text, "
            "hash_sha256, published_at, lloji_tekstit) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (url, burimi, titulli, data, gjuha, teksti, teksti, hash_sha256, published_at, lloji_tekstit),
        )
        return cur.rowcount == 1


def plotreso_hash(funksioni_hash):
    """Hash për artikujt e vjetër që s'e kanë, nga teksti bruto (raw_text). Kthen numrin."""
    with closing(lidhu()) as con, con:
        rreshtat = con.execute("SELECT id, raw_text FROM articles WHERE hash_sha256 IS NULL "
                               "AND raw_text IS NOT NULL").fetchall()
        for r in rreshtat:
            con.execute("UPDATE articles SET hash_sha256 = ? WHERE id = ?",
                        (funksioni_hash(r["raw_text"]), r["id"]))
        return len(rreshtat)


def ruaj_vendimin(url_kryesor, statusi, shenimi=""):
    """Ruan (ose zëvendëson) vendimin e analistit për një ngjarje."""
    if statusi not in STATUSET:
        raise ValueError(f"Status i panjohur: {statusi}")
    with closing(lidhu()) as con, con:
        con.execute("INSERT OR REPLACE INTO vendimet (url_kryesor, statusi, shenimi, koha) "
                    "VALUES (?, ?, ?, datetime('now'))", (url_kryesor, statusi, shenimi))


def vendimet():
    """Kthen {url_kryesor: {statusi, shenimi, koha}}."""
    with closing(lidhu()) as con:
        return {r["url_kryesor"]: dict(r) for r in con.execute("SELECT * FROM vendimet")}


def url_i_vendimit(burimet, vendimet):
    """Çelësi i vendimit për një ngjarje me këto URL burimesh.
    correlator.py rindërton ngjarjet, ndaj një artikull më i hershëm mund të bëhet burimet[0];
    vendimi gjendet te cilado URL e ngjarjes (më i riu, nëse ka disa), përndryshe burimet[0]."""
    me_vendim = [u for u in burimet if u in vendimet]
    return max(me_vendim, key=lambda u: vendimet[u]["koha"] or "") if me_vendim else burimet[0]


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
            "SELECT id, burimi, data, published_at, gjuha, titulli, teksti, teksti_perkthyer FROM articles "
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


def fillimi_i_mbledhjes():
    """Kur u mblodh artikulli i parë (për patterns.py: sa histori kemi)."""
    with closing(lidhu()) as con:
        return con.execute("SELECT MIN(mbledhur_me) FROM articles").fetchone()[0]


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
    with closing(lidhu()) as con, con:
        return _ruaj_ngjarje(con, titulli, data, gjuha, burimet, boshllequet, lloji, vendi,
                             lat, lon, besueshmeria, detajet)


def _ruaj_ngjarje(con, titulli, data, gjuha, burimet, boshllequet, lloji=None, vendi=None,
                  lat=None, lon=None, besueshmeria=None, detajet=None):
    if not burimet:
        raise ValueError("Çdo ngjarje duhet të ketë të paktën një URL burimi")
    cur = con.execute(
        "INSERT INTO events (titulli, lloji, data, vendi, lat, lon, gjuha, burimet, "
        "besueshmeria, boshllequet, detajet_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (titulli, lloji, data, vendi, lat, lon, gjuha,
         json.dumps(burimet, ensure_ascii=False), besueshmeria,
         json.dumps(boshllequet, ensure_ascii=False),
         json.dumps(detajet or {}, ensure_ascii=False)),
    )
    return cur.lastrowid


def zevendeso_ngjarjet(rreshtat):
    """Publikon grupet e reja së bashku. Një gabim ruan grupet e mëparshme dhe vendimet."""
    with closing(lidhu()) as con, con:
        con.execute("DELETE FROM events")
        for rreshti in rreshtat:
            _ruaj_ngjarje(con, **rreshti)


def numero_sipas_burimit():
    """Kthen [(burimi, numri)] për raportim."""
    with closing(lidhu()) as con:
        return con.execute(
            "SELECT burimi, COUNT(*) AS n FROM articles GROUP BY burimi ORDER BY n DESC"
        ).fetchall()


if __name__ == "__main__":
    # Vendimi s'humbet kur një artikull më i hershëm hyn në ngjarje
    v = {"b": {"koha": "2026-11-20 10:00"}}
    assert url_i_vendimit(["a", "b"], v) == "b" and url_i_vendimit(["a"], v) == "a"
    # Dy ngjarje me vendim u bashkuan: fiton vendimi më i ri
    v["c"] = {"koha": "2026-11-21 09:00"}
    assert url_i_vendimit(["a", "b", "c"], v) == "c"
    # Migrimi: bazë e vjetër pa raw_text -> kolona shtohet, të papërkthyerit marrin tekstin
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        DB_PATH = f"{d}/vjeter.db"
        with closing(sqlite3.connect(DB_PATH)) as c:
            c.execute("CREATE TABLE articles (id INTEGER PRIMARY KEY, url TEXT UNIQUE, burimi TEXT, "
                      "titulli TEXT, data TEXT, gjuha TEXT, teksti TEXT, teksti_perkthyer TEXT, "
                      "perpunuar INTEGER DEFAULT 0, rezultati_json TEXT, mbledhur_me TEXT)")
            c.executemany("INSERT INTO articles (url, burimi, data, gjuha, teksti, teksti_perkthyer) "
                          "VALUES (?, 'x', '2026-11-20', 'sq', ?, ?)",
                          [("a", "bruto", None), ("b", "e pastruar", "translated")])
            c.commit()
        ruaj_artikull("c", "x", "t", "2026-11-21", "sq", "i ri",
                      published_at="2026-11-21", lloji_tekstit="plote")
        ruaj_perkthimin(3, "i ri i pastruar", "new")
        with closing(lidhu()) as c:
            raw = dict(c.execute("SELECT url, raw_text FROM articles").fetchall())
            datat = dict(c.execute("SELECT url, published_at FROM articles").fetchall())
        assert raw == {"a": "bruto", "b": None, "c": "i ri"}, raw  # përkthimi s'e prek raw_text
        assert datat == {"a": None, "b": None, "c": "2026-11-21"}, datat
        vjeter = dict(titulli="Ngjarja e vjetër", data="2026-11-20", gjuha="sq", burimet=["a"], boshllequet=[])
        e_re = dict(vjeter, titulli="Ngjarja e re", burimet=["b"])
        zevendeso_ngjarjet([vjeter])
        ruaj_vendimin("a", "e konfirmuar")
        try:
            zevendeso_ngjarjet([e_re, dict(e_re, burimet=[])])
        except ValueError:
            pass
        else:
            raise AssertionError("Gabimi në rreshtin e dytë duhej të anashkalonte zëvendësimin")
        assert [r["titulli"] for r in ngjarjet()] == [vjeter["titulli"]]
        zevendeso_ngjarjet([e_re])
        assert [r["titulli"] for r in ngjarjet()] == [e_re["titulli"]]
        assert vendimet()["a"]["statusi"] == "e konfirmuar"
    print("Kontrollet e db.py kaluan.")
