"""apify_burimi.py - Sinjale nga rrjetet sociale (Reddit, X, Telegram) përmes Apify.

Postimet ruhen si artikuj me burim të gjurmueshëm ("Reddit:r/...", "X:x.com", "Telegram:kanali")
dhe kalojnë nëpër të njëjtin pipeline si lajmet. Janë SINJALE PËR SHQYRTIM: burimet sociale marrin
Admiralty F, numërohen si një origjinë (scoring.py) dhe konfirmimi vjen vetëm nga analisti.
Ruhet vetëm URL-ja, teksti, gjuha dhe data e publikimit; pa autorin, përmendjet ose email-et.

Statusi i secilës platformë është te STATUSI. Përmbajtje reale nga Apify (dataset, run, nisje)
lejohet vetëm për "aktive me leje të verifikuar"; skedarët lokalë (shembujt sintetikë) lejohen gjithmonë.
main.py dhe orari automatik s'nisin kurrë Actor-ë me pagesë.

Komandat (çelësi: APIFY_TOKEN ose ~/.apify_token; s'printohet kurrë):
  python apify_burimi.py                                         kontrollet, pa rrjet
  python apify_burimi.py statusi                                 statusi i lejes për çdo platformë
  python apify_burimi.py importo reddit --skedar shembuj/apify_reddit.json
  python apify_burimi.py importo reddit --dataset DATASET_ID [--maks 500]
  python apify_burimi.py importo reddit --run RUN_ID [--maks 500]
  python apify_burimi.py nis reddit 50                           nisje me pagesë, vetëm me komandë
  python apify_burimi.py demo demo.db                            shembujt sintetikë në bazën demo
"""
import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from collections import Counter
from contextlib import closing
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlsplit

import collector
import db

AKTIVE = "aktive me leje të verifikuar"
SINTETIKE = "e provuar vetëm me të dhëna sintetike"
PRITJE = "në pritje të lejes"
# Ndryshohet vetëm kur marrëveshja e platformës mbulon mbledhjen, ruajtjen, analizën me model
# dhe shfaqjen te FSK-ja (shih README, "Rrjetet sociale").
STATUSI = {"reddit": PRITJE, "x": SINTETIKE, "telegram": SINTETIKE}

API = "https://api.apify.com"
FAQJA = 100            # rreshta për kërkesë te dataset-i
MAKS_IMPORT = 2000     # rreshta për një import (kufiri i të dhënave)
MAKS_USD = 0.30        # kufiri financiar për një nisje me pagesë
MAKS_PER_NISJE = 200   # rreshta për një nisje me pagesë
NUMRI = Path(__file__).with_name("data") / "apify_perdorimi.json"  # të paguara dhe nisjet aktive

KERKIMET_REDDIT = ["Kosovo attack", "Kosovo Serbia army", "Kosovo KFOR", "Jarinje", "Banjska",
                   "Kosovo drone", "Ibar Lepenac", "napad Kosovo", "sulm Kosovë", "Kosovo war"]
# X: sintaksa e kërkimit të avancuar; pa përgjigje dhe ripostime (paguhen, por s'sjellin gjë të re)
PA_ZHURME = " -filter:replies -filter:retweets"
KERKIMET_X = [k + PA_ZHURME for k in (
    "Kosovo (attack OR army OR KFOR OR drone OR explosion OR troops)",
    "(Kosova OR Kosovë OR Kosovës) (sulm OR ushtri OR dron OR shpërthim OR FSK)",
    "(Kosovo OR Kosmet) (napad OR vojska OR dron OR eksplozija)",
    "(Косово OR Космет) (напад OR војска OR дрон)",
    "(Jarinje OR Banjska OR \"Ibar Lepenac\" OR Gazivode OR Zvečan)")]
# Kanale publike (media, institucione, aktorë shtetërorë; jo individë). I miraton ekipi/FSK-ja.
KANALET_TELEGRAM = []
FILTRI = ["kosovo", "kosova", "kosovë", "kosovu", "kosmet", "косово", "косову", "космет", "kfor",
          "pristina", "prishtina", "priština", "приштина", "mitrovica", "митровица", "jarinje",
          "јариње", "banjska", "бањска"]
ID_APIFY = re.compile(r"^[A-Za-z0-9~._-]{1,100}$")  # dataset/run/actor: pa "/" që të mos dalë nga shtegu


class GabimApify(Exception):
    """Gabim i lexueshëm për operatorin (pa token dhe pa URL)."""


# ---------------- Normalizimi: një postim -> (artikull, None) ose (None, arsyeja) ----------------
def data_iso(vlera):
    """ISO 8601 nga formatet e Actor-ëve; None kur mungon ose s'lexohet (data s'shpiket)."""
    if not isinstance(vlera, str) or not vlera.strip():
        return None
    v = vlera.strip()
    try:
        if "T" in v:
            return datetime.fromisoformat(v.replace("Z", "+00:00")).isoformat()
        return datetime.strptime(v, "%Y-%m-%d").date().isoformat()  # vetëm datë: ora mbetet e panjohur
    except ValueError:
        pass
    try:
        return datetime.strptime(v, "%a %b %d %H:%M:%S %z %Y").isoformat()  # formati i X-it
    except ValueError:
        return None


def _artikull(platforma, url, burimi, titulli, teksti, data):
    if urlsplit(url).hostname not in PLATFORMAT[platforma]["hostet"]:
        return None, "URL jashtë platformës"
    teksti = teksti.strip()
    if not teksti:
        return None, "pa tekst"
    data = data_iso(data)
    if data is None:
        return None, "pa datë publikimi të vlefshme"
    if not collector.KOSOVA.search(teksti):
        return None, "pa lidhje me Kosovën"
    return dict(url=collector.url_normalizuar(url), burimi=burimi, titulli=titulli.strip()[:300], data=data,
                gjuha=collector.zbulo_gjuhen(teksti), teksti=teksti, hash_sha256=collector.gjurma(teksti)), None


def artikull_reddit(p):
    if not isinstance(p, dict) or p.get("type") != "post":
        return None, "jo postim"
    url, titulli = p.get("url"), p.get("title")
    if not (isinstance(url, str) and isinstance(titulli, str)):
        return None, "pa URL ose titull"
    tekst = p.get("selfText") if isinstance(p.get("selfText"), str) else ""
    sub = p.get("subreddit") if isinstance(p.get("subreddit"), str) else "reddit"
    return _artikull("reddit", url, f"Reddit:r/{sub[:40]}", titulli, f"{titulli}\n{tekst}", p.get("createdAt"))


def artikull_telegram(m):
    if not isinstance(m, dict) or m.get("rowType") != "message":
        return None, "jo mesazh"
    url, tekst = m.get("url"), m.get("text")
    if not (isinstance(url, str) and isinstance(tekst, str)):
        return None, "pa URL ose tekst"
    pjeset = urlsplit(url).path.strip("/").split("/")
    kanali = m.get("channelUsername") if isinstance(m.get("channelUsername"), str) else pjeset[0]
    return _artikull("telegram", url, f"Telegram:{kanali[:40]}", tekst.split("\n")[0][:200], tekst, m.get("date"))


def artikull_x(t):
    """URL-ja pa emrin e llogarisë (x.com/i/status/ID); pa përmendjet në fillim."""
    if not isinstance(t, dict) or t.get("type") != "tweet" or t.get("isRetweet") is True:
        return None, "jo postim origjinal"
    id_, tekst = t.get("id"), t.get("text")
    if not (isinstance(id_, str) and id_.isdigit() and isinstance(tekst, str)):
        return None, "pa ID ose tekst"
    tekst = re.sub(r"^(?:@\w+\s+)+", "", tekst)
    return _artikull("x", f"https://x.com/i/status/{id_}", "X:x.com", tekst.split("\n")[0][:200], tekst,
                     t.get("createdAt"))


# Kostot e Actor-ëve (Apify Store, 2026-11-21): Reddit ~$1.15/1000, X ~$0.15/1000, Telegram ~$0.87/1000
PLATFORMAT = {
    "reddit": {"actor": "automation-lab~reddit-scraper", "maks": 1000, "artikulli": artikull_reddit,
               "hostet": {"www.reddit.com", "reddit.com", "old.reddit.com"},
               "hyrja": lambda n: {"searchQueries": KERKIMET_REDDIT, "sort": "relevance", "timeFilter": "week",
                                   "maxPostsPerSource": max(1, n // len(KERKIMET_REDDIT)),
                                   "includeComments": False, "includeNsfw": False,
                                   "filterKeywords": FILTRI, "deduplicatePosts": True}},
    "x": {"actor": "xquik~x-tweet-scraper", "maks": 1000, "artikulli": artikull_x,
          "hostet": {"x.com"},
          "hyrja": lambda n: {"searchTerms": KERKIMET_X, "queryType": "Latest", "maxItems": n,
                              "maxItemsPerTarget": max(1, n // len(KERKIMET_X))}},
    "telegram": {"actor": "automation-lab~telegram-scraper", "maks": 2000, "artikulli": artikull_telegram,
                 "hostet": {"t.me"},
                 "hyrja": lambda n: {"channels": KANALET_TELEGRAM, "lastNDays": 7, "keywords": FILTRI,
                                     "maxMessages": max(1, n // max(1, len(KANALET_TELEGRAM))),
                                     "includeComments": False, "includeChannelInfo": False}},
}


def ruaj(platforma, rreshtat):
    """Normalizon dhe ruan; kthen statistikat. Një rresht i keq s'e ndal importin."""
    st, arsyet = Counter(), Counter()
    for r in rreshtat:
        st["lexuar"] += 1
        a, arsye = PLATFORMAT[platforma]["artikulli"](r)
        if a is None:
            st["refuzuar"] += 1
            arsyet[arsye] += 1
        elif db.ruaj_artikull(**a):  # INSERT OR IGNORE sipas URL-së: riimporti s'krijon dublikatë
            st["ruajtur"] += 1
        else:
            st["perseritur"] += 1
    return {"lexuar": st["lexuar"], "ruajtur": st["ruajtur"], "perseritur": st["perseritur"],
            "refuzuar": st["refuzuar"], "arsyet": dict(arsyet)}


# ---------------- Apify API ----------------
def celesi():
    """Çelësi nga APIFY_TOKEN ose ~/.apify_token; None kur mungon."""
    c = os.environ.get("APIFY_TOKEN")
    if not c:
        try:
            c = Path.home().joinpath(".apify_token").read_text(encoding="utf-8-sig")
        except OSError:
            return None
    return c.strip() or None


def kerko(metoda, shtegu, celes, trupi=None, timeout=60):
    """Kërkesë te Apify me token në header. Gabimet kthehen në GabimApify pa token dhe pa URL."""
    req = urllib.request.Request(API + shtegu, method=metoda,
                                 data=None if trupi is None else json.dumps(trupi).encode(),
                                 headers={"Authorization": f"Bearer {celes}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise GabimApify({401: "401: token i pavlefshëm", 403: "403: s'ka qasje në këtë burim",
                          404: "404: dataset/run/Actor nuk u gjet",
                          429: "429: kufi kuote ose ritmi; provo më vonë"}.get(e.code, f"HTTP {e.code}")) from None
    except (TimeoutError, urllib.error.URLError, OSError):
        raise GabimApify("timeout ose gabim rrjeti") from None
    except ValueError:
        raise GabimApify("përgjigje e pavlefshme (jo JSON)") from None


def rreshtat_e_dataset(dataset_id, celes, maks=MAKS_IMPORT):
    """Lexon dataset-in faqe pas faqeje (limit/offset) deri te maks."""
    if not ID_APIFY.match(str(dataset_id)):
        raise GabimApify("dataset_id i pavlefshëm")
    offset, maks = 0, min(maks, MAKS_IMPORT)
    while offset < maks:
        n = min(FAQJA, maks - offset)
        faqja = kerko("GET", f"/v2/datasets/{quote(dataset_id)}/items?format=json&clean=1"
                             f"&limit={n}&offset={offset}", celes)
        if not isinstance(faqja, list):
            raise GabimApify("përgjigje e pavlefshme (s'është listë)")
        yield from faqja
        if len(faqja) < n:
            return
        offset += len(faqja)


def dataset_i_run(run_id, celes):
    """defaultDatasetId i një ekzekutimi të përfunduar me sukses."""
    if not ID_APIFY.match(str(run_id)):
        raise GabimApify("run_id i pavlefshëm")
    run = (kerko("GET", f"/v2/actor-runs/{quote(run_id)}", celes) or {}).get("data") or {}
    if run.get("status") != "SUCCEEDED":
        raise GabimApify(f"ekzekutimi s'ka përfunduar me sukses (statusi: {run.get('status') or 'i panjohur'})")
    if not ID_APIFY.match(str(run.get("defaultDatasetId") or "")):
        raise GabimApify("ekzekutimi s'ka dataset")
    return run["defaultDatasetId"]


# ---------------- Gjendja: të paguara dhe nisjet aktive ----------------
def gjendja():
    try:
        d = json.loads(NUMRI.read_text(encoding="utf-8"))
    except FileNotFoundError:
        d = {}
    except (OSError, ValueError):
        d = None
    if not isinstance(d, dict):  # skedar i prishur: buxheti konsiderohet i mbaruar, s'paguhet më
        return {"paguara": {p: v["maks"] for p, v in PLATFORMAT.items()}, "aktive": {}}
    paguara = d.get("paguara", {k: v for k, v in d.items() if type(v) is int})  # formati i vjetër
    return {"paguara": {k: v for k, v in paguara.items() if type(v) is int and v >= 0},
            "aktive": {k: v for k, v in (d.get("aktive") or {}).items() if isinstance(v, str)}}


def ruaj_gjendjen(g):
    NUMRI.parent.mkdir(exist_ok=True)
    NUMRI.write_text(json.dumps(g), encoding="utf-8")


# ---------------- Komandat ----------------
def importo(platforma, *, skedar=None, dataset=None, run=None, maks=MAKS_IMPORT):
    """Importon nga skedar lokal (gjithmonë), ose nga dataset/run ekzistues (vetëm platformë aktive)."""
    if platforma not in PLATFORMAT:
        raise GabimApify(f"platformë e panjohur: {platforma}")
    if skedar:
        rreshtat = json.loads(Path(skedar).read_text(encoding="utf-8"))
        if not isinstance(rreshtat, list):
            raise GabimApify("skedari duhet të jetë listë JSON, si dataset-i i Apify-t")
        return ruaj(platforma, rreshtat[:maks])
    if STATUSI[platforma] != AKTIVE:
        raise GabimApify(f"{platforma}: {STATUSI[platforma]}; përmbajtja reale s'importohet")
    celes = celesi()
    if not celes:
        raise GabimApify("s'ka token (APIFY_TOKEN ose ~/.apify_token)")
    if run:
        dataset = dataset_i_run(run, celes)
    rezultati = ruaj(platforma, rreshtat_e_dataset(dataset, celes, maks))
    g = gjendja()
    if run and g["aktive"].get(platforma) == run:  # nisja aktive u importua: lejohet një e re
        del g["aktive"][platforma]
        ruaj_gjendjen(g)
    return rezultati


def nis(platforma, limiti):
    """Nisje me pagesë, vetëm me komandë. S'nis një të dytë kur e para s'është importuar ose s'dihet."""
    p = PLATFORMAT.get(platforma)
    if p is None:
        raise GabimApify(f"platformë e panjohur: {platforma}")
    if STATUSI[platforma] != AKTIVE:
        raise GabimApify(f"{platforma}: {STATUSI[platforma]}; s'niset")
    if platforma == "telegram" and not KANALET_TELEGRAM:
        raise GabimApify("lista KANALET_TELEGRAM është bosh")
    g = gjendja()
    if g["aktive"].get(platforma):
        raise GabimApify(f"një nisje e mëparshme ({g['aktive'][platforma]}) s'është importuar; "
                         f"importo me --run ose kontrolloje te Apify Console")
    limiti = min(limiti, MAKS_PER_NISJE, p["maks"] - g["paguara"].get(platforma, 0))
    if limiti <= 0:
        raise GabimApify(f"buxheti prej {p['maks']} rreshtash u arrit")
    celes = celesi()
    if not celes:
        raise GabimApify("s'ka token (APIFY_TOKEN ose ~/.apify_token)")
    # Shënohet para kërkesës: nëse përgjigjja humbet, s'niset automatikisht një e dytë
    g["aktive"][platforma] = "pa-pergjigje"
    g["paguara"][platforma] = g["paguara"].get(platforma, 0) + limiti  # maksimumi që mund të paguhet
    ruaj_gjendjen(g)
    run = (kerko("POST", f"/v2/acts/{p['actor']}/runs?maxItems={limiti}&maxTotalChargeUsd={MAKS_USD}"
                         f"&waitForFinish=60", celes, trupi=p["hyrja"](limiti), timeout=90) or {}).get("data") or {}
    if not ID_APIFY.match(str(run.get("id") or "")):
        raise GabimApify("Apify s'ktheu ID ekzekutimi; kontrolloje te Apify Console para një nisjeje të re")
    g["aktive"][platforma] = run["id"]
    ruaj_gjendjen(g)
    if run.get("status") != "SUCCEEDED":
        return {"run": run["id"], "statusi": run.get("status")}
    return {"run": run["id"], **importo(platforma, run=run["id"], maks=limiti)}


def demo(shtegu):
    """Shton shembujt sintetikë (shembuj/apify_*.json) në një bazë demo dhe i kalon pa model:
    fusha "_demo" e çdo shembulli jep nxjerrjen. Pa rrjet, pa token."""
    import correlator
    import rreziku
    import scoring
    shtegu = Path(shtegu)
    if shtegu.name == "osint.db":
        raise GabimApify("demo s'e prek osint.db")
    if not shtegu.exists():
        raise GabimApify(f"{shtegu} mungon; krijoje më parë me: python demo.py")
    with closing(sqlite3.connect(shtegu)) as con:  # vetëm bazë demo (me artikujt gold), kurrë bazë pune
        if not con.execute("SELECT 1 FROM articles WHERE url LIKE 'gold://%' LIMIT 1").fetchone():
            raise GabimApify(f"{shtegu} s'është bazë demo (krijoje me: python demo.py)")
    vjeter, db.DB_PATH = db.DB_PATH, str(shtegu)
    try:
        rezultatet, datat = {}, []
        for platforma in PLATFORMAT:
            rreshtat = json.loads((Path(__file__).with_name("shembuj") / f"apify_{platforma}.json")
                                  .read_text(encoding="utf-8"))
            rezultatet[platforma] = ruaj(platforma, rreshtat)
            for r in rreshtat:
                a, _ = PLATFORMAT[platforma]["artikulli"](r)
                if a and isinstance(r.get("_demo"), dict):
                    with closing(db.lidhu()) as con:
                        aid = con.execute("SELECT id FROM articles WHERE url = ?", (a["url"],)).fetchone()[0]
                    db.sheno_perpunuar(aid, {"is_security_event": True, "relevante": True, "demo": True,
                                             "event_date": a["data"][:10], "date_precision": "exact",
                                             "actors": [], "killed": None, "injured": None, "arrested": None,
                                             **r["_demo"]})
                    datat.append(a["data"][:10])
        correlator.korrelo()
        scoring.vlereso_te_gjitha()
        rreziku.vlereso_te_gjitha(sot=max(datat))
        return rezultatet
    finally:
        db.DB_PATH = vjeter


# ---------------- Kontrollet (pa rrjet, me SQLite të përkohshëm) ----------------
def kontrollet():
    import tempfile
    import scoring
    global kerko, FAQJA, NUMRI
    r = {"type": "post", "url": "https://www.reddit.com/r/kosovo/comments/sint01/x/", "title": "Drone near Jarinje",
         "selfText": "Serbian army near the Kosovo boundary", "subreddit": "kosovo",
         "createdAt": "2026-11-21T10:00:00.000Z", "author": "dikush"}
    t = {"rowType": "message", "url": "https://t.me/kanal_sintetik/12", "channelUsername": "kanal_sintetik",
         "text": "ХИТНО: војска код Јариња, Косово\nдетаљи", "date": "2026-11-21T09:00:00+00:00",
         "author": "dikush", "mentions": ["@dikush"], "emails": ["a@b.c"]}
    x = {"type": "tweet", "id": "1000000000000000001", "text": "@a @b Kosovo army drill near Jarinje",
         "createdAt": "Sat Nov 21 18:20:49 +0000 2026", "url": "https://x.com/llogaria/status/1000000000000000001"}
    for f, rr, burimi in ((artikull_reddit, r, "Reddit:r/kosovo"), (artikull_telegram, t, "Telegram:kanal_sintetik"),
                          (artikull_x, x, "X:x.com")):
        a, arsye = f(rr)
        assert a and arsye is None and a["burimi"] == burimi and a["data"].startswith("2026-11-21"), (burimi, arsye)
        assert not {"dikush", "llogaria", "a@b.c"} & set(re.findall(r"[\w@.]+", json.dumps(a))), a
    assert artikull_x(x)[0]["url"] == "https://x.com/i/status/1000000000000000001"
    assert artikull_telegram(t)[0]["gjuha"] == "sr" and artikull_reddit(r)[0]["gjuha"] == "en"
    # Rreshta të pavlefshëm: arsye e qartë, data s'shpiket
    assert artikull_reddit({**r, "createdAt": None}) == (None, "pa datë publikimi të vlefshme")
    assert artikull_x({**x, "createdAt": "dje"}) == (None, "pa datë publikimi të vlefshme")
    assert artikull_reddit({**r, "createdAt": "2026-11-21"})[0]["data"] == "2026-11-21"  # ora e panjohur
    assert artikull_reddit({**r, "url": "https://evil.example/r/x"}) == (None, "URL jashtë platformës")
    assert artikull_telegram({**t, "url": "https://t.me.evil.example/x/1"}) == (None, "URL jashtë platformës")
    assert artikull_reddit({**r, "title": "Football", "selfText": "match"}) == (None, "pa lidhje me Kosovën")
    for keq in (None, [], {**x, "type": "reply"}, {**x, "isRetweet": True}, {**x, "id": "../x"}):
        assert artikull_x(keq)[0] is None, keq

    vjeter, numri, faqja, kerko_vjeter = db.DB_PATH, NUMRI, FAQJA, kerko
    with tempfile.TemporaryDirectory() as d:
        db.DB_PATH, NUMRI = str(Path(d) / "prove.db"), Path(d) / "data" / "numri.json"
        try:
            # Skedar lokal: secila platformë; riimporti s'shton dublikata; rreshti i keq s'e ndal importin
            for platforma, rr in (("reddit", r), ("telegram", t), ("x", x)):
                sk = Path(d) / f"{platforma}.json"
                sk.write_text(json.dumps([rr, {"x": 1}, {**rr, "title": None, "text": None, "id": None}]),
                              encoding="utf-8")
                s1, s2 = importo(platforma, skedar=sk), importo(platforma, skedar=sk)
                assert (s1["lexuar"], s1["ruajtur"], s1["refuzuar"]) == (3, 1, 2), (platforma, s1)
                assert (s2["ruajtur"], s2["perseritur"]) == (0, 1), (platforma, s2)
            # Ripostim në dy platforma (i njëjti pretendim): një origjinë
            assert scoring.burimet_e_pavarura([artikull_reddit(r)[0]["url"], artikull_x(x)[0]["url"]])[0] == 1
            # Pa leje: përmbajtja reale s'importohet dhe s'niset; pjesa tjetër vazhdon
            for platforma in PLATFORMAT:
                for thirrja in (lambda: importo(platforma, dataset="abc"), lambda: nis(platforma, 10)):
                    try:
                        thirrja()
                        raise AssertionError("u lejua pa leje")
                    except GabimApify as e:
                        assert STATUSI[platforma] in str(e), e
            # Dataset me dy faqe (API e simuluar): çdo rresht lexohet një herë
            STATUSI["reddit"], FAQJA = AKTIVE, 2
            os.environ["APIFY_TOKEN"] = "token-prove"
            rreshtat = [{**r, "url": f"https://www.reddit.com/r/kosovo/comments/sint{i}/x/"} for i in range(3)]
            kerkesat = []

            def kerko_prove(metoda, shtegu, celes, trupi=None, timeout=60):
                kerkesat.append((metoda, shtegu))
                assert celes == "token-prove" and "token" not in shtegu
                if shtegu.startswith("/v2/actor-runs/"):
                    return {"data": {"status": "SUCCEEDED", "defaultDatasetId": "ds1"}}
                if shtegu.startswith("/v2/acts/"):
                    raise GabimApify("timeout ose gabim rrjeti")
                off = int(re.search(r"offset=(\d+)", shtegu).group(1))
                lim = int(re.search(r"limit=(\d+)", shtegu).group(1))
                return rreshtat[off:off + lim]
            kerko = kerko_prove
            s = importo("reddit", run="run1")
            assert (s["lexuar"], s["ruajtur"]) == (3, 3) and sum("items" in k[1] for k in kerkesat) == 2, s
            # Timeout pas nisjes: status i qartë dhe asnjë nisje e dytë automatike
            for pritet in ("timeout", "s'është importuar"):
                try:
                    nis("reddit", 10)
                    raise AssertionError("pa gabim")
                except GabimApify as e:
                    assert pritet in str(e), e
            assert sum(k[0] == "POST" for k in kerkesat) == 1
        finally:
            kerko, db.DB_PATH, NUMRI, FAQJA = kerko_vjeter, vjeter, numri, faqja
            STATUSI["reddit"] = PRITJE
            os.environ.pop("APIFY_TOKEN", None)
    print("Kontrollet kaluan: apify_burimi (normalizimi, dublikatat, ripostimet, faqet, lejet, timeout).")


def main(args):
    if not args:
        return kontrollet()
    try:
        if args[0] == "statusi":
            for p, s in STATUSI.items():
                print(f"  {p}: {s}")
            return
        if args[0] == "importo" and len(args) >= 4 and args[2] in ("--skedar", "--dataset", "--run"):
            maks = int(args[args.index("--maks") + 1]) if "--maks" in args else MAKS_IMPORT
            s = importo(args[1], maks=maks, **{args[2][2:]: args[3]})
        elif args[0] == "nis" and len(args) == 3:
            s = nis(args[1], int(args[2]))
        elif args[0] == "demo" and len(args) == 2:
            for p, s in demo(args[1]).items():
                print(f"  {p}: {s}")
            print(f'Hap:  $env:OSINT_DB="{args[1]}"; python -m streamlit run dashboard.py')
            return
        else:
            sys.exit(__doc__)
        print(f"  {args[1]}: {s}")
    except GabimApify as e:
        sys.exit(f"  {args[1] if len(args) > 1 else ''}: joaktiv / gabim: {e}")


if __name__ == "__main__":
    main(sys.argv[1:])
