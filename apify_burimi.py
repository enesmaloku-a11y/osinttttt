"""apify_burimi.py - Postime publike nga rrjetet sociale përmes Apify (me rekomandim të FSK-së).

Platformat: Reddit dhe X (kërkim me fjalë kërcënimi) dhe kanale publike Telegram (KANALET_TELEGRAM).
Ruhet vetëm teksti, data dhe URL-ja, pa autorin, përmendjet ose email-et. Postimet kalojnë pastaj
nëpër të njëjtin pipeline si lajmet (përkthimi, nxjerrja, besueshmëria, rreziku). Burimet
"Reddit:", "X:" dhe "Telegram:" janë sociale: Admiralty F, gjithmonë për verifikim.

Çelësi: variabla APIFY_TOKEN ose skedari ~/.apify_token (jashtë repo-s). Pa çelës, anashkalohet.
Buxheti: për çdo platformë s'paguhen kurrë më shumë se "maks" postime gjithsej dhe
MAKS_PER_EKZEKUTIM për ekzekutim; Apify ndalon edhe vetë te MAKS_USD për ekzekutim.
Platformë e re (p.sh. X, Facebook): shto actor-in, hyrjen dhe funksionin e artikullit te PLATFORMAT.

Nis me:  python apify_burimi.py                 (vetëm kontrollet, pa internet)
         python apify_burimi.py reddit 20       (mbledhje e vërtetë me deri në 20 postime)
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import collector
import db

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
# Apify mban vetëm postimet që përmendin Kosovën
FILTRI = ["kosovo", "kosova", "kosovë", "kosovu", "kosmet", "косово", "косову", "космет", "kfor",
          "pristina", "prishtina", "priština", "приштина", "mitrovica", "митровица", "jarinje",
          "јариње", "banjska", "бањска"]
MAKS_PER_EKZEKUTIM = 200
MAKS_USD = 0.30
NUMRI = Path(__file__).with_name("data") / "apify_perdorimi.json"  # sa postime janë paguar për platformë


def artikull_reddit(p):
    """Postim Reddit -> dict për db.ruaj_artikull, ose None."""
    if not isinstance(p, dict) or p.get("type") != "post":
        return None
    url, titulli = p.get("url"), p.get("title")
    if not (isinstance(url, str) and url.startswith("https://www.reddit.com/r/") and isinstance(titulli, str)):
        return None
    tekst = p.get("selfText") if isinstance(p.get("selfText"), str) else ""
    sub = p.get("subreddit") if isinstance(p.get("subreddit"), str) else "reddit"
    return _artikull(url, f"Reddit:r/{sub[:40]}", titulli, f"{titulli}\n{tekst}", p.get("createdAt"))


def artikull_telegram(m):
    """Mesazh Telegram -> dict për db.ruaj_artikull, ose None."""
    if not isinstance(m, dict) or m.get("rowType") != "message":
        return None
    url, tekst = m.get("url"), m.get("text")
    if not (isinstance(url, str) and url.startswith("https://t.me/") and isinstance(tekst, str)):
        return None
    kanali = m.get("channelUsername") if isinstance(m.get("channelUsername"), str) else url.split("/")[3]
    return _artikull(url, f"Telegram:{kanali[:40]}", tekst.split("\n")[0][:200], tekst, m.get("date"))


def artikull_x(t):
    """Postim X -> dict për db.ruaj_artikull, ose None. URL-ja pa emrin e llogarisë (x.com/i/status/ID)."""
    if not isinstance(t, dict) or t.get("type") != "tweet" or t.get("isRetweet") is True:
        return None
    id_, tekst = t.get("id"), t.get("text")
    if not (isinstance(id_, str) and id_.isdigit() and isinstance(tekst, str)):
        return None
    tekst = re.sub(r"^(?:@\w+\s+)+", "", tekst)  # pa përmendjet në fillim
    try:
        data = datetime.strptime(str(t.get("createdAt")), "%a %b %d %H:%M:%S %z %Y").isoformat()
    except ValueError:
        data = None
    return _artikull(f"https://x.com/i/status/{id_}", "X:x.com", tekst.split("\n")[0][:200], tekst, data)


def _artikull(url, burimi, titulli, teksti, data):
    teksti = teksti.strip()
    if not teksti or not collector.KOSOVA.search(teksti):
        return None
    return dict(url=collector.url_normalizuar(url), burimi=burimi, titulli=titulli.strip()[:300],
                data=data if isinstance(data, str) else None, gjuha=collector.zbulo_gjuhen(teksti),
                teksti=teksti, hash_sha256=collector.gjurma(teksti))


# "maks": postime gjithsej (buxheti i $5: Reddit ~$1.15/1000, X ~$0.15/1000, Telegram ~$0.87/1000)
PLATFORMAT = {
    "reddit": {"actor": "automation-lab~reddit-scraper", "maks": 1000, "artikulli": artikull_reddit,
               "hyrja": lambda n: {"searchQueries": KERKIMET_REDDIT, "sort": "relevance", "timeFilter": "week",
                                   "maxPostsPerSource": max(1, n // len(KERKIMET_REDDIT)),
                                   "includeComments": False, "includeNsfw": False,
                                   "filterKeywords": FILTRI, "deduplicatePosts": True}},
    "x": {"actor": "xquik~x-tweet-scraper", "maks": 1000, "artikulli": artikull_x,
          "hyrja": lambda n: {"searchTerms": KERKIMET_X, "queryType": "Latest", "maxItems": n,
                              "maxItemsPerTarget": max(1, n // len(KERKIMET_X))}},
    "telegram": {"actor": "automation-lab~telegram-scraper", "maks": 2000, "artikulli": artikull_telegram,
                 "hyrja": lambda n: {"channels": KANALET_TELEGRAM, "lastNDays": 7, "keywords": FILTRI,
                                     "maxMessages": max(1, n // max(1, len(KANALET_TELEGRAM))),
                                     "includeComments": False, "includeChannelInfo": False}},
}


def celesi():
    """Çelësi nga APIFY_TOKEN ose ~/.apify_token; None kur mungon. S'printohet kurrë."""
    c = os.environ.get("APIFY_TOKEN")
    if not c:
        try:
            c = Path.home().joinpath(".apify_token").read_text(encoding="utf-8-sig")
        except OSError:
            return None
    return c.strip() or None


def te_paguara():
    """{platforma: postime të paguara}; skedar i prishur = buxheti mbaroi (më mirë ndal se paguaj)."""
    try:
        d = json.loads(NUMRI.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        d = None
    if not isinstance(d, dict) or not all(type(v) is int and v >= 0 for v in d.values()):
        return {p: v["maks"] for p, v in PLATFORMAT.items()}
    return d


def shto_te_paguara(platforma, n):
    d = te_paguara()
    d[platforma] = d.get(platforma, 0) + n
    NUMRI.parent.mkdir(exist_ok=True)
    NUMRI.write_text(json.dumps(d), encoding="utf-8")


def thirr_apify(actor, hyrja, limiti, celes):
    """Ekzekuton actor-in dhe kthen listën e rreshtave (Apify ndalon te limiti dhe te MAKS_USD)."""
    url = (f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"
           f"?maxItems={limiti}&maxTotalChargeUsd={MAKS_USD}&timeout=240")
    # Çelësi në header, jo në URL, që të mos dalë në log
    req = urllib.request.Request(url, data=json.dumps(hyrja).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {celes}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        te_dhenat = json.load(r)
    return te_dhenat if isinstance(te_dhenat, list) else []


def mblidh_platformen(platforma, limiti=MAKS_PER_EKZEKUTIM, celes=None):
    """Mbledh nga një platformë brenda buxhetit. Kthen numrin e artikujve të rinj."""
    p = PLATFORMAT[platforma]
    emri = platforma.capitalize()
    if platforma == "telegram" and not KANALET_TELEGRAM:
        print(f"  {emri} (Apify): lista KANALET_TELEGRAM është bosh, u anashkalua")
        return 0
    celes = celes or celesi()
    if not celes:
        print(f"  {emri} (Apify): s'ka çelës (APIFY_TOKEN ose ~/.apify_token), u anashkalua")
        return 0
    limiti = min(limiti, MAKS_PER_EKZEKUTIM, p["maks"] - te_paguara().get(platforma, 0))
    if limiti <= 0:
        print(f"  {emri} (Apify): buxheti prej {p['maks']} postimesh u arrit, u anashkalua")
        return 0
    try:
        rreshtat = thirr_apify(p["actor"], p["hyrja"](limiti), limiti, celes)
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"  {emri} (Apify): gabim ({type(e).__name__})")  # pa mesazhin: mund të ketë URL
        return 0
    shto_te_paguara(platforma, len(rreshtat))
    te_reja = sum(db.ruaj_artikull(**a) for a in map(p["artikulli"], rreshtat) if a)
    print(f"  {emri} (Apify): {len(rreshtat)} postime të paguara, {te_reja} të rinj për Kosovën "
          f"(gjithsej të paguara: {te_paguara().get(platforma, 0)}/{p['maks']})")
    return te_reja


def mblidh():
    """Të gjitha platformat; e thërret main.py. Kthen numrin e artikujve të rinj."""
    celes = celesi()
    return sum(mblidh_platformen(p, celes=celes) for p in PLATFORMAT)


def kontrollet():
    r = {"type": "post", "url": "https://www.reddit.com/r/kosovo/comments/abc/x/", "title": "Drone near Jarinje",
         "selfText": "Serbian army near the Kosovo boundary", "subreddit": "kosovo",
         "createdAt": "2026-11-21T10:00:00.000Z", "author": "dikush"}
    a = artikull_reddit(r)
    assert a["burimi"] == "Reddit:r/kosovo" and a["data"] == r["createdAt"] and a["hash_sha256"]
    assert "dikush" not in json.dumps(a)  # autori s'ruhet
    for keq in ({**r, "type": "comment"}, {**r, "url": "https://evil.example/r/x"},
                {**r, "title": "Football", "selfText": "match tonight"}, {**r, "title": None}, None, []):
        assert artikull_reddit(keq) is None, keq
    assert artikull_reddit({**r, "selfText": None})["teksti"] == "Drone near Jarinje"
    t = {"rowType": "message", "url": "https://t.me/kanali_x/12", "channelUsername": "kanali_x",
         "text": "ХИТНО: војска код Јариња\nдетаљи", "date": "2026-11-21T09:00:00+00:00",
         "author": "dikush", "mentions": ["@dikush"], "emails": ["a@b.c"]}
    a = artikull_telegram(t)
    assert a["burimi"] == "Telegram:kanali_x" and a["titulli"] == "ХИТНО: војска код Јариња"
    assert "dikush" not in json.dumps(a) and "a@b.c" not in json.dumps(a)
    for keq in ({**t, "rowType": "comment"}, {**t, "url": "https://evil.example/x"},
                {**t, "text": "Fudbal večeras"}, {**t, "text": None}, None):
        assert artikull_telegram(keq) is None, keq
    x = {"type": "tweet", "id": "2124206414336049646", "text": "@a @b Kosovo army drill near Jarinje\nmore",
         "createdAt": "Sat Nov 21 18:20:49 +0000 2026", "url": "https://x.com/llogaria/status/2124206414336049646",
         "author": {"userName": "llogaria"}}
    a = artikull_x(x)
    assert a["url"] == "https://x.com/i/status/2124206414336049646" and a["burimi"] == "X:x.com"
    assert a["titulli"] == "Kosovo army drill near Jarinje" and a["data"] == "2026-11-21T18:20:49+00:00"
    assert "llogaria" not in json.dumps(a) and "@a" not in a["teksti"]
    assert artikull_x({**x, "createdAt": "dje"})["data"] is None
    for keq in ({**x, "type": "reply"}, {**x, "isRetweet": True}, {**x, "id": "../x"}, {**x, "text": "Fudbal"}, None):
        assert artikull_x(keq) is None, keq
    assert set(PLATFORMAT) == {"reddit", "x", "telegram"}
    assert all(callable(p["hyrja"]) and callable(p["artikulli"]) and p["maks"] > 0 for p in PLATFORMAT.values())
    print("Kontrollet kaluan: apify_burimi (pa internet).")


if __name__ == "__main__":
    if len(sys.argv) > 2:
        mblidh_platformen(sys.argv[1], int(sys.argv[2]))
    else:
        kontrollet()
