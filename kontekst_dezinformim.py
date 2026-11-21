"""kontekst_dezinformim.py - Kontekst nga EUvsDisinfo për ngjarjet e dezinformimit.

Për çdo ngjarje me lloji == "disinformation" gjen raste të ngjashme në databazën EUvsDisinfo
dhe ia shton te detajet_json["konteksti"], me lidhje te rasti. Ngjashmëria matet me fjalë të
përbashkëta, pa model: është sugjerim për analistin, jo provë.

Licenca dhe qasja (kontrolluar më 2026-11-20):
- Kushtet: https://www.eeas.europa.eu/eeas/legal-notice_en (EUvsDisinfo është projekt i EEAS;
  euvsdisinfo.eu s'ka faqe kushtesh, dritarja e saj "Disclaimer" është bosh). Përmbledhje:
  ripërdorimi lejohet me kusht që të përmendet burimi, përveç kur thuhet ndryshe.
- Qasja: s'ka API publik; serveri MCP i EUvsDisinfo jepet vetëm me kërkesë
  (https://euvsdisinfo.eu/about/). Faqja ka eksport CSV vetëm te rezultatet e kërkimit, pas
  kontrollit anti-bot të Cloudflare, dhe te databaza s'ka buton shkarkimi. Prandaj moduli nuk
  bën asnjë kërkesë rrjeti: njeriu e merr CSV-në (eksport ose qasje MCP) dhe e ruan te
  data/euvsdisinfo.csv. Kolonat që lexohen: Title, Summary (ose Disproof), Date, URL (ose
  Link), ID; Countries/Keywords/Tags vetëm për filtrin e rajonit (Kosovo, Serbia, W. Balkans).
- Ruhen vetëm id, titulli, përmbledhja e shkurtër, data dhe URL e rastit; emrat e personave
  maskohen si te extractor.py. Çdo element ka "burimi": "EUvsDisinfo" dhe lidhjen te rasti.

Cache: data/euvsdisinfo.db rindërtohet nga CSV-ja vetëm kur mungon ose është më i vjetër se
7 ditë. Për ta marrë menjëherë një eksport të ri, fshi data/euvsdisinfo.db.
"""
import csv
import json
import re
import sqlite3
import time
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import correlator
import db
import extractor

CSV = Path("data/euvsdisinfo.csv")        # eksporti manual nga EUvsDisinfo
DB_RASTET = Path("data/euvsdisinfo.db")   # cache (*.db është te .gitignore)
MAKS_MOSHA = 7 * 24 * 3600                # sekonda; cache më i vjetër rindërtohet
BURIMI = "EUvsDisinfo"
DOMENET = {"euvsdisinfo.eu", "www.euvsdisinfo.eu"}  # URL e rastit pranohet vetëm këtu
RAJONI = re.compile(r"kosov|serbia|western balkans", re.I)

# Pikët = fjalë të përbashkëta / fjalët e ngjarjes. Teksti i ngjarjes ka edhe artikujt (deri në
# 2000 karaktere secili), ndaj ka nga 10 deri në disa qindra fjalë dalluese.
MIN_FJALE = 3   # 1-2 fjalë të përbashkëta ("water", "church") ndodhin edhe rastësisht
PRAGU = 0.02    # ngjarje e gjatë me 300 fjalë kërkon të paktën 6 të përbashkëta;
                # te ngjarjet e shkurtra vendos MIN_FJALE
MAKS_RASTE = 3
MAKS_ARTIKULL, MAKS_TITULLI, MAKS_PERMBLEDHJA = 2000, 200, 500

# Fjalë që dalin pothuajse në çdo rast të EUvsDisinfo dhe në çdo lajm për dezinformim, ndaj
# s'tregojnë që rasti dhe ngjarja flasin për të njëjtën gjë (si TE_PERGJITHSHME te correlator.py)
TE_PERGJITHSHME = {"disinfo", "disinformation", "false", "fake", "claim", "claims", "claimed",
                   "claiming", "news", "media", "social", "spread", "report", "reports",
                   "reported", "kremlin", "outlets"}


def url_zyrtare(url):
    """True vetëm për https te domeni zyrtar (pa port, pa përdorues në adresë)."""
    try:
        a = urlsplit(url)
    except ValueError:  # p.sh. "https://[::1"
        return False
    return a.scheme == "https" and a.netloc.lower() in DOMENET


def data_iso(s):
    """'YYYY-MM-DD' nga 'YYYY-MM-DD...' ose 'DD.MM.YYYY'; None nëse data s'është e vlefshme."""
    for formati in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(s[:10], formati).date().isoformat()
        except ValueError:
            pass
    return None


def valido(rreshti):
    """Rasti {id, titulli, permbledhja, data, url} nga një rresht i CSV-së, ose None nëse rreshti
    s'vlen ose s'lidhet me Kosovën/rajonin. Pranohen vetëm tekste; data e pavlefshme -> None."""
    if not isinstance(rreshti, dict):
        return None
    # "Date of publication" -> "dateofpublication"; vlerat jo-tekst (kolona të tepërta) bien
    r = {re.sub(r"[^a-z]", "", str(k).lower()): " ".join(v.split())
         for k, v in rreshti.items() if isinstance(v, str)}

    def merr(*emrat):
        return next((r[e] for e in emrat if r.get(e)), "")

    titulli, permbledhja, url = merr("title"), merr("summary", "disproof"), merr("url", "link")
    if not titulli or (url and not url_zyrtare(url)):
        return None
    # Tema nga titulli, përmbledhja dhe vendet/fjalët kyçe (jo gjuha ose mediumi)
    tema = " ".join([titulli, permbledhja] + [v for k, v in r.items()
                                              if any(s in k for s in ("countr", "keyword", "tag"))])
    if not RAJONI.search(tema):
        return None
    return {"id": (merr("id") or url or titulli)[:MAKS_TITULLI],
            "titulli": extractor.fshi_emrat(titulli)[:MAKS_TITULLI],
            "permbledhja": extractor.fshi_emrat(permbledhja)[:MAKS_PERMBLEDHJA],
            "data": data_iso(merr("date", "dateofpublication")), "url": url or None}


def lexo_csv(skedari):
    """Kthen (rastet e vlefshme për rajonin, numri i rreshtave të anashkaluar)."""
    with open(skedari, encoding="utf-8-sig", newline="") as f:
        rreshtat = list(csv.DictReader(f))
    rastet = [r for r in map(valido, rreshtat) if r]
    return rastet, len(rreshtat) - len(rastet)


def ruaj_cache(rastet):
    with closing(sqlite3.connect(DB_RASTET)) as con, con:
        con.execute("CREATE TABLE IF NOT EXISTS rastet (id TEXT PRIMARY KEY, titulli TEXT NOT NULL, "
                    "permbledhja TEXT, data TEXT, url TEXT)")
        con.execute("DELETE FROM rastet")
        con.executemany("INSERT OR REPLACE INTO rastet VALUES (:id, :titulli, :permbledhja, :data, :url)",
                        rastet)


def dalluese(teksti):
    return correlator.fjalet(teksti) - TE_PERGJITHSHME


def lexo_rastet():
    """Rastet nga cache, më të rejat së pari (kjo renditje vendos kur pikët janë të barabarta)."""
    if not DB_RASTET.exists():
        return []
    with closing(sqlite3.connect(DB_RASTET)) as con:
        con.row_factory = sqlite3.Row
        rastet = [dict(r) for r in con.execute("SELECT * FROM rastet ORDER BY data DESC, id")]
    for r in rastet:
        r["fjalet"] = dalluese(f"{r['titulli']} {r['permbledhja'] or ''}")
    return rastet


def perditeso():
    """Rindërton data/euvsdisinfo.db nga CSV-ja kur cache mungon ose është më i vjetër se 7 ditë.
    Kthen numrin e rasteve në cache. S'hedh exception: për gabime printon një rresht."""
    try:
        DB_RASTET.parent.mkdir(exist_ok=True)
        if DB_RASTET.exists() and time.time() - DB_RASTET.stat().st_mtime < MAKS_MOSHA:
            return len(lexo_rastet())
        if not CSV.exists():
            print(f"EUvsDisinfo: mungon {CSV}; vendose me dorë (shih docstring-un e këtij moduli)")
        else:
            rastet, anashkaluar = lexo_csv(CSV)
            if rastet:
                ruaj_cache(rastet)
            print(f"EUvsDisinfo: {len(rastet)} raste për Kosovën/rajonin nga {CSV}, "
                  f"{anashkaluar} rreshta u anashkaluan (jashtë rajonit ose të pavlefshëm)")
        return len(lexo_rastet())
    except Exception as e:  # pipeline-i s'duhet të bjerë kurrë për shkak të këtij moduli
        print(f"EUvsDisinfo: përditësimi dështoi ({type(e).__name__}: {e})")
        return 0


def konteksti(teksti, data_ngjarjes, rastet):
    """Elementet EUvsDisinfo për një ngjarje: deri në 3 raste të ngjashme dhe një statistikë."""
    fe = dalluese(teksti)
    gjetje = []
    for r in rastet:
        te_perbashketa = fe & r["fjalet"]
        pike = len(te_perbashketa) / len(fe) if fe else 0.0
        if len(te_perbashketa) >= MIN_FJALE and pike >= PRAGU:
            gjetje.append((pike, r, te_perbashketa))
    gjetje.sort(key=lambda g: g[0], reverse=True)  # sort i qëndrueshëm: barazimet sipas datës
    elementet = [{"burimi": BURIMI, "lloji": "rast_i_ngjashem", "titulli": r["titulli"],
                  "url": r["url"], "data": r["data"], "ngjashmeria": round(pike, 2),
                  "arsyeja": "fjalë të përbashkëta: " + ", ".join(sorted(tp)[:10])}
                 for pike, r, tp in gjetje[:MAKS_RASTE]]
    d = date.fromisoformat(data_ngjarjes[:10])
    fillimi = (d - timedelta(days=365)).isoformat()
    n = sum(1 for r in rastet if r["data"] and fillimi < r["data"] <= d.isoformat())
    if n:
        elementet.append({"burimi": BURIMI, "lloji": "statistike",
                          "titulli": f"EUvsDisinfo: {n} {'rast' if n == 1 else 'raste'} për Kosovën "
                                     f"dhe rajonin në 12 muajt deri më {d}",
                          "url": None, "data": None, "ngjashmeria": None,
                          "arsyeja": f"raste me datë pas {fillimi} deri më {d} në skedarin lokal "
                                     "të EUvsDisinfo"})
    return elementet


def teksti_i_ngjarjes(con, e):
    """Përmbledhja (anglisht) plus përkthimet e artikujve të ngjarjes, deri në 2000 karaktere secili."""
    urls = json.loads(e["burimet"])
    vendet = ",".join("?" * len(urls))
    rreshtat = con.execute(f"SELECT teksti_perkthyer FROM articles WHERE url IN ({vendet})",
                           urls).fetchall() if urls else []
    return " ".join([e["titulli"]] + [(r["teksti_perkthyer"] or "")[:MAKS_ARTIKULL] for r in rreshtat])


def eshte_dezinformim(e):
    """Ngjarje dezinformimi sipas llojit të vjetër ose sipas kategorisë së taksonomisë (K3)."""
    if e["lloji"] == "disinformation":
        return True
    try:
        det = json.loads(e["detajet_json"] or "{}")
    except ValueError:
        return False
    return isinstance(det, dict) and det.get("kategoria") == "dezinformim"


def pasuro_te_gjitha():
    """Shton kontekstin EUvsDisinfo te çdo ngjarje dezinformimi. Kthen numrin e ngjarjeve që morën
    të paktën një rast. Kur mungojnë të dhënat ose ka gabim printon një rresht dhe kthen 0."""
    try:
        perditeso()
        rastet = lexo_rastet()
        if not rastet:
            print("EUvsDisinfo: s'ka raste në cache, konteksti u anashkalua")
            return 0
        ngjarjet = [e for e in db.ngjarjet() if eshte_dezinformim(e)]
        with closing(db.lidhu()) as con:
            tekstet = {e["id"]: teksti_i_ngjarjes(con, e) for e in ngjarjet}
        me_rast = 0
        for e in ngjarjet:
            det = json.loads(e["detajet_json"] or "{}")
            te_rejat = konteksti(tekstet[e["id"]], e["data"], rastet)
            # Fshi vetëm elementet tona të vjetra; ato të moduleve të tjera (p.sh. EuRepoC) mbeten
            te_vjetrat = det.get("konteksti") if isinstance(det.get("konteksti"), list) else []
            det["konteksti"] = [x for x in te_vjetrat
                                if not (isinstance(x, dict) and x.get("burimi") == BURIMI)] + te_rejat
            db.ruaj_besueshmerine(e["id"], e["besueshmeria"], det)  # besueshmëria s'ndryshon
            me_rast += any(x["lloji"] == "rast_i_ngjashem" for x in te_rejat)
        return me_rast
    except Exception as e:  # pipeline-i s'duhet të bjerë kurrë për shkak të këtij moduli
        print(f"EUvsDisinfo: konteksti u anashkalua ({type(e).__name__}: {e})")
        return 0


# K5: burimet që përhapin dezinformim. Emri i kolonës së mediave te eksporti s'është verifikuar,
# ndaj pranohen këto variante (pas normalizimit si te valido)
KOLONAT_MEDIAT = ("outlets", "outlet", "mediaoutlets", "media")
DOMEN = re.compile(r"^[a-z0-9.-]+\.[a-z]{2,}$")
# Platformat sociale: (domenet, emri, domeni kanonik). Kanalet/llogaritë s'ruhen me emër,
# grupohen në një hyrje për platformë, që të mos profilohet asnjë llogari individuale.
PLATFORMAT = [(("t.me", "telegram.me"), "Telegram", "t.me"),
              (("youtube.com", "youtu.be"), "YouTube", "youtube.com"),
              (("facebook.com", "fb.com"), "Facebook", "facebook.com"),
              (("vk.com",), "VK", "vk.com"),
              (("x.com", "twitter.com"), "X", "x.com")]
PA_DOMEN = "pa domen (të tjera)"


def burimi_i(x):
    """(emri, platforma, domeni) për një element të kolonës së mediave."""
    x = x.strip()[:200]
    if re.match(r"https?://", x, re.I):
        try:
            domeni = (urlsplit(x).hostname or "").lower()
        except ValueError:
            domeni = ""
    else:
        domeni = x.lower() if DOMEN.match(x.lower()) else ""
    domeni = domeni.removeprefix("www.")
    if not domeni:
        # Pa domen (p.sh. "News Front"): pa emër, që të mos ruhet tekst i lirë i paverifikuar
        return PA_DOMEN, "web", None
    for domenet, platforma, kanonik in PLATFORMAT:
        if any(domeni == d or domeni.endswith("." + d) for d in domenet):
            return f"{platforma} (kanale të ndryshme)", platforma, kanonik
    return domeni, "web", domeni


def burimet_e_dezinformimit(skedari=None):
    """Lista e burimeve që përhapin dezinformim për Kosovën/rajonin sipas rasteve EUvsDisinfo:
    [{"emri","platforma","domeni","raste","rasti_i_fundit","url_shembull"}], renditur sipas
    "raste". Lexon CSV-në drejtpërdrejt (jo cache-in). S'hedh exception: në gabim kthen []."""
    skedari = Path(skedari or CSV)
    try:
        if not skedari.exists():
            print(f"EUvsDisinfo: mungon {skedari}; s'ka listë burimesh")
            return []
        with open(skedari, encoding="utf-8-sig", newline="") as f:
            rreshtat = list(csv.DictReader(f))
        grupet = {}
        for rreshti in rreshtat:
            rasti = valido(rreshti)
            if not rasti or not isinstance(rreshti, dict):
                continue
            r = {re.sub(r"[^a-z]", "", str(k).lower()): v for k, v in rreshti.items() if isinstance(v, str)}
            kolona = next((r[k] for k in KOLONAT_MEDIAT if k in r), None)
            if kolona is None:
                print("EUvsDisinfo: CSV-ja s'ka kolonë mediash (outlets/media); s'ka listë burimesh")
                return []
            for x in re.split(r"[,;\n]", kolona):
                if not x.strip():
                    continue
                emri, platforma, domeni = burimi_i(x)
                g = grupet.setdefault((platforma, domeni or emri), {
                    "emri": emri, "platforma": platforma, "domeni": domeni, "ids": set(), "rastet": []})
                if rasti["id"] not in g["ids"]:
                    g["ids"].add(rasti["id"])
                    g["rastet"].append(rasti)
        dalja = []
        for g in grupet.values():
            me_date = [r for r in g["rastet"] if r["data"]]
            i_fundit = max(me_date, key=lambda r: r["data"]) if me_date else None
            dalja.append({"emri": g["emri"], "platforma": g["platforma"], "domeni": g["domeni"],
                          "raste": len(g["ids"]),
                          "rasti_i_fundit": i_fundit["data"] if i_fundit else None,
                          "url_shembull": i_fundit["url"] if i_fundit else None})
        return sorted(dalja, key=lambda b: (-b["raste"], b["emri"]))
    except Exception as e:  # pipeline-i s'duhet të bjerë kurrë për shkak të këtij moduli
        print(f"EUvsDisinfo: lista e burimeve dështoi ({type(e).__name__}: {e})")
        return []


if __name__ == "__main__":
    import tempfile

    # 1) Validimi i të dhënave të jashtme (rreshta të shpikur, pa rrjet)
    uji = {"ID": "101", "Title": "Claims that Kosovo's water supply was poisoned are false",
           "Summary": "Pro-Kremlin outlets claimed that the water supply in Prizren and other towns "
                      "had been poisoned. No such poisoning was recorded.",
           "Date": "2026-03-02", "Countries": "Kosovo",
           "URL": "https://euvsdisinfo.eu/report/kosovo-water-supply-poisoned/"}
    nato = {**uji, "ID": "102", "Title": "NATO is preparing a new war against Serbia", "Summary": "",
            "Date": "2025-06-10", "URL": "https://euvsdisinfo.eu/report/nato-new-war-serbia/"}
    assert valido(uji) == {"id": "101", "titulli": uji["Title"], "permbledhja": uji["Summary"],
                           "data": "2026-03-02", "url": uji["URL"]}, valido(uji)
    for keq in ({**uji, "URL": "http://euvsdisinfo.eu/report/x/"},             # jo https
                {**uji, "URL": "https://euvsdisinfo.eu.evil.example/report/x/"},  # domen tjetër
                {**uji, "URL": "https://evil.example@euvsdisinfo.eu/report/x/"},  # përdorues në adresë
                {**uji, "URL": "https://[::1"},                                 # URL e prishur
                {**uji, "Title": "   "},                                        # pa titull
                {**uji, "Title": "Ukraine is run by a junta", "Countries": "Ukraine"},  # jashtë rajonit
                ["jo", "dict"]):
        assert valido(keq) is None, keq
    assert valido({**uji, "Date": "2026-02-30"})["data"] is None    # datë e pavlefshme -> null
    assert valido({**uji, "Date": "02.03.2026"})["data"] == "2026-03-02"
    assert valido({**uji, "URL": ""})["url"] is None
    assert len(valido({**uji, "Title": "Kosovo " * 100})["titulli"]) == MAKS_TITULLI
    assert valido({**uji, None: ["kolonë e tepërt"], "Summary": None})["permbledhja"] == ""
    assert valido({**uji, "Title": "Filan Fisteku poisoned the water"})["titulli"] == \
        "[person] poisoned the water"                                  # pa emra personash

    # 2) Përputhja dhe shkrimi në një bazë të përkohshme (osint.db dhe data/ s'preken)
    origjinalet = CSV, DB_RASTET, db.DB_PATH
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        CSV, DB_RASTET, db.DB_PATH = Path(tmp, "e.csv"), Path(tmp, "data", "e.db"), str(Path(tmp, "o.db"))
        assert pasuro_te_gjitha() == 0  # pa CSV: printon një rresht, s'hedh exception
        with open(CSV, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(uji))
            w.writeheader()
            w.writerows([uji, nato, {**uji, "ID": "103", "URL": "http://euvsdisinfo.eu/report/x/"}])
        assert perditeso() == 2  # rreshti me http u anashkalua
        rastet = lexo_rastet()

        titulli_uji = "False reports of poisoned water spread on social media in Prizren"
        teksti_uji = (f"{titulli_uji} {titulli_uji} Messages claiming that Prizren's water supply had "
                      "been poisoned spread quickly on social media on Tuesday. The water utility and "
                      "municipal health officials said tests showed the water was safe and called the "
                      "claims fake news.")
        kibernetik = ("Hackers publish data from the servers of a public energy company. A group of "
                      "hackers published online data stolen from the servers of a public energy "
                      "company. The company said it had notified the relevant authorities.")
        festivali = ("Documentary film festival opens in Prizren. A new edition of an international "
                     "documentary film festival opened today in Prizren, with more than 200 films "
                     "from 50 countries. The festival lasts a week and screenings are free.")
        k = konteksti(teksti_uji, "2026-11-17", rastet)
        assert [x["url"] for x in k if x["lloji"] == "rast_i_ngjashem"] == [uji["URL"]], k
        assert k[0]["arsyeja"] == "fjalë të përbashkëta: poisoned, prizren, supply, water", k
        assert k[-1]["lloji"] == "statistike" and k[-1]["titulli"].startswith("EUvsDisinfo: 1 rast "), k
        for teksti in (kibernetik, festivali):
            assert not [x for x in konteksti(teksti, "2026-11-18", rastet)
                        if x["lloji"] == "rast_i_ngjashem"], teksti

        eurepoc = {"burimi": "EuRepoC", "lloji": "incident", "titulli": "test", "url": None}
        with closing(db.lidhu()) as con, con:
            con.executemany("INSERT INTO articles (url, burimi, data, gjuha, teksti_perkthyer) "
                            "VALUES (?, ?, ?, ?, ?)",
                            [("test://uji", "Balkan Insight", "2026-11-17", "en", teksti_uji),
                             ("test://kib", "Telegrafi", "2026-11-18", "sq", kibernetik)])
        id_uji = db.ruaj_ngjarje(titulli_uji, "2026-11-17", "en", ["test://uji"], [],
                                 lloji="disinformation", besueshmeria=0.5,
                                 detajet={"mediat": ["Balkan Insight"], "konteksti": [eurepoc]})
        id_kib = db.ruaj_ngjarje("Hackers publish data from a public energy company", "2026-11-18",
                                 "sq", ["test://kib"], [], lloji="cyber", besueshmeria=0.4)
        assert pasuro_te_gjitha() == 1
        para = [tuple(e) for e in db.ngjarjet()]
        assert pasuro_te_gjitha() == 1 and [tuple(e) for e in db.ngjarjet()] == para  # idempotent
        ngj = {e["id"]: e for e in db.ngjarjet()}
        det = json.loads(ngj[id_uji]["detajet_json"])
        assert ngj[id_uji]["besueshmeria"] == 0.5 and det["mediat"] == ["Balkan Insight"]
        assert det["konteksti"][0] == eurepoc  # elementi i EuRepoC i paprekur
        assert [x["lloji"] for x in det["konteksti"]] == ["incident", "rast_i_ngjashem", "statistike"]
        assert ngj[id_kib]["detajet_json"] == "{}"  # ngjarjet e tjera s'preken
    CSV, DB_RASTET, db.DB_PATH = origjinalet

    # 3) K5: burimet e dezinformimit nga një CSV sintetike (shtegu i përkohshëm jepet shprehimisht)
    assert eshte_dezinformim({"lloji": "other", "detajet_json": '{"kategoria": "dezinformim"}'})
    assert not eshte_dezinformim({"lloji": "cyber", "detajet_json": "{bosh"})
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        assert burimet_e_dezinformimit(Path(tmp, "mungon.csv")) == []
        s1 = {**uji, "ID": "201", "Date": "2026-01-05", "Outlets": "sputniknews.com",
              "URL": "https://euvsdisinfo.eu/report/a/"}
        s2 = {**s1, "ID": "202", "Date": "2026-04-09", "Outlets": "https://www.sputniknews.com/x; News Front",
              "URL": "https://euvsdisinfo.eu/report/b/"}
        tg = {**s1, "ID": "203", "Date": "2026-02-01", "Outlets": "https://t.me/kanali_x",
              "URL": "https://euvsdisinfo.eu/report/c/"}
        jashte = {**s1, "ID": "204", "Title": "Ukraine is run by a junta", "Countries": "Ukraine",
                  "Summary": "", "Outlets": "rt.com"}
        http = {**s1, "ID": "205", "Outlets": "rt.com", "URL": "http://euvsdisinfo.eu/report/d/"}
        skedari = Path(tmp, "burimet.csv")
        with open(skedari, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(s1))
            w.writeheader()
            w.writerows([s1, s2, tg, jashte, http])
        b = burimet_e_dezinformimit(skedari)
        assert [(x["emri"], x["platforma"], x["domeni"], x["raste"]) for x in b] == [
            ("sputniknews.com", "web", "sputniknews.com", 2),
            ("Telegram (kanale të ndryshme)", "Telegram", "t.me", 1),
            (PA_DOMEN, "web", None, 1)], b
        assert b[0]["rasti_i_fundit"] == "2026-04-09" and b[0]["url_shembull"] == s2["URL"]
        teksti = json.dumps(b, ensure_ascii=False)
        assert "kanali_x" not in teksti and "[person]" not in teksti and "News Front" not in teksti
        assert "rt.com" not in teksti  # jashtë rajonit dhe http s'numërohen
        # CSV pa kolonë mediash -> []
        with open(skedari, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(uji))
            w.writeheader()
            w.writerow(uji)
        assert burimet_e_dezinformimit(skedari) == []
    print("Kontrollet kaluan.")

    # 3) Të dhënat reale: data/euvsdisinfo.csv dhe osint.db
    print(f"Raste në cache: {perditeso()}")
    print(f"Ngjarje dezinformimi që morën të paktën një rast: {pasuro_te_gjitha()}")
