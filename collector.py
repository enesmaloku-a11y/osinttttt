"""collector.py - Mbledh artikuj nga RSS dhe GDELT dhe i ruan në SQLite pa dublikatë."""
import hashlib
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import feedparser
import trafilatura
from langdetect import DetectorFactory, detect

import db

DetectorFactory.seed = 0  # rezultat i qëndrueshëm nga langdetect

# Burimet RSS (URL-të u verifikuan më 2026-11-19)
FEEDS = {
    "RTK": "https://www.rtklive.com/sq/feed",
    "Koha": "https://www.koha.net/rss",
    "Kallxo": "https://kallxo.com/feed/",
    "Telegrafi": "https://telegrafi.com/feed/",
    "Gazeta Express": "https://www.gazetaexpress.com/feed/",
    "N1 Serbia": "https://n1info.rs/feed/",
    "Balkan Insight": "https://balkaninsight.com/feed/",
}

AGENT = "Mozilla/5.0 (osint-prototype)"
ROBOT = "osint-prototype"  # emri që kërkohet te "User-agent:" në robots.txt
PUNETORE = 8  # sa shkarkime paralele
# Ruhet vetëm fragmenti i fillimit (paragrafë të plotë) + URL; teksti i plotë vetëm me OSINT_FULL_TEXT=1.
# Ngjarja zakonisht është në paragrafët e parë; extractor.py lexon deri në 2500 karaktere.
MAKS_FRAGMENTI = 1200
TEKST_I_PLOTE = os.environ.get("OSINT_FULL_TEXT") == "1"


def zbulo_gjuhen(teksti):
    """Kthen kodin e gjuhës. hr/bs/sr bashkohen te 'sr' (langdetect i ngatërron)."""
    try:
        g = detect(teksti[:2000])
    except Exception:
        return "panjohur"
    return "sr" if g in ("hr", "bs", "sr", "mk") else g


def data_iso(entry):
    """Data e publikimit nga RSS; nëse mungon, përdor kohën e tanishme."""
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    if t:
        return datetime(*t[:6], tzinfo=timezone.utc).isoformat()
    return datetime.now(timezone.utc).isoformat()


def pastro_html(s):
    return re.sub(r"<[^>]+>", " ", s or "").strip()


def lexo_robots(statusi, rreshtat=()):
    """Rregullat sipas RFC 9309: 2xx = lexo skedarin; 4xx = s'ka rregulla (lejohet gjithçka);
    5xx ose server i paarritshëm (statusi None) = ndalohet gjithçka."""
    rp = RobotFileParser()
    if statusi is not None and 200 <= statusi < 300:
        rp.parse(rreshtat)
    elif statusi is not None and 400 <= statusi < 500:
        rp.allow_all = True
    else:
        rp.disallow_all = True
    return rp


@lru_cache(maxsize=None)
def _robots(baza):
    """robots.txt i një host-i, një herë për ekzekutim."""
    req = urllib.request.Request(f"{baza}/robots.txt", headers={"User-Agent": AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return lexo_robots(r.status, r.read().decode("utf-8", "ignore").splitlines())
    except urllib.error.HTTPError as e:
        return lexo_robots(e.code)
    except Exception:
        return lexo_robots(None)


def lejohet(url):
    """True nëse robots.txt e lejon shkarkimin e faqes."""
    u = urlsplit(url)
    return _robots(f"{u.scheme}://{u.netloc}").can_fetch(ROBOT, url)


def fragment(teksti, maks=MAKS_FRAGMENTI):
    """Paragrafët e parë deri në 'maks' karaktere (i pari pritet te fjala, nëse është më i gjatë)."""
    dalja = ""
    for p in (teksti or "").split("\n"):
        if dalja and len(dalja) + len(p) + 1 > maks:
            break
        dalja += p + "\n"
    dalja = dalja.strip()
    return dalja if len(dalja) <= maks else dalja[:maks].rsplit(" ", 1)[0]


def nxirr_tekstin(url):
    """Shkarkon faqen dhe nxjerr vetëm tekstin kryesor (pa komente)."""
    try:
        html = trafilatura.fetch_url(url)
        if html:
            return trafilatura.extract(html, include_comments=False) or ""
    except Exception:
        pass
    return ""


def gjurma(teksti):
    """SHA-256 i tekstit: ndryshon krejt edhe kur ndryshon një shkronjë."""
    return hashlib.sha256((teksti or "").encode("utf-8")).hexdigest()


def verifiko(url, hash_i_ruajtur, teksti_bruto=None):
    """Rishkarkon faqen dhe e krahason me hash-in e ruajtur kur u mblodh.
    Faqet shtojnë shpesh reklama/"më të lexuarat", ndaj hash-i ndryshon edhe kur lajmi s'ka
    ndryshuar. Nëse kemi ende tekstin bruto, tregojmë sa rreshta të lajmit mungojnë."""
    if not lejohet(url):
        return "s'u kontrollua (robots.txt e ndalon)"
    teksti = nxirr_tekstin(url)
    if not teksti:
        return "s'u arrit (fshirë ose offline)"
    if gjurma(teksti) == hash_i_ruajtur:
        return "i pandryshuar"
    if not teksti_bruto:
        return "i ndryshuar"
    rreshtat = [r for r in teksti_bruto.splitlines() if r.strip()]
    mungojne = [r for r in rreshtat if r not in teksti]
    if not mungojne:
        return "i ndryshuar vetëm rreth lajmit (teksti origjinal është i plotë)"
    return f"i ndryshuar: {len(mungojne)} nga {len(rreshtat)} rreshta të lajmit mungojnë ose ndryshuan"


def pergatit(burimi, url, titulli, data, permbledhja=""):
    """Merr tekstin dhe gjuhën; kthen dict gati për db (ose None).
    Faqja shkarkohet vetëm nëse robots.txt e lejon; përndryshe mbetet përmbledhja e RSS-së."""
    teksti = (nxirr_tekstin(url) if lejohet(url) else "") or pastro_html(permbledhja)
    if not teksti:
        return None
    # Gjuha dhe hash-i nga teksti i plotë, para se të pritet në fragment
    return dict(url=url, burimi=burimi, titulli=titulli, data=data,
                gjuha=zbulo_gjuhen(f"{titulli}\n{teksti}"),
                teksti=teksti if TEKST_I_PLOTE else fragment(teksti), hash_sha256=gjurma(teksti))


def ruaj_te_gjitha(detyrat):
    """Ekzekuton 'pergatit' paralelisht dhe ruan rezultatet. Kthen numrin e të rejave."""
    te_reja = 0
    with ThreadPoolExecutor(PUNETORE) as ex:
        for art in ex.map(lambda d: pergatit(*d), detyrat):
            if art and db.ruaj_artikull(**art):
                te_reja += 1
    return te_reja


def mblidh_rss(burimi, feed_url):
    """Mbledh artikujt e një feed-i RSS. Kthen numrin e artikujve të rinj."""
    feed = feedparser.parse(feed_url, agent=AGENT)
    detyrat = []
    for e in feed.entries:
        url = e.get("link")
        # Cache: nëse URL ekziston, mos e shkarko përsëri
        if not url or db.ekziston_url(url):
            continue
        detyrat.append((burimi, url, e.get("title", ""), data_iso(e), e.get("summary", "")))
    return ruaj_te_gjitha(detyrat)


def mblidh_gdelt(fjala="Kosovo", periudha="1d", max_artikuj=100):
    """Mbledh artikuj për Kosovën nga GDELT (gdeltdoc). Kthen numrin e të rinjve."""
    from gdeltdoc import Filters, GdeltDoc

    f = Filters(keyword=fjala, timespan=periudha, num_records=max_artikuj)
    df = None
    # GDELT lejon ~1 kërkesë në 5 sekonda; riprovo disa herë me pritje
    for prova in range(4):
        try:
            df = GdeltDoc().article_search(f)
            break
        except Exception as e:
            print(f"  GDELT gabim ({type(e).__name__}), prova {prova + 1}/4")
            time.sleep(6 * (prova + 1))
    if df is None or df.empty:
        return 0

    detyrat = []
    for _, r in df.iterrows():
        if db.ekziston_url(r["url"]):
            continue
        # seendate vjen si "20261119T101500Z"
        try:
            data = datetime.strptime(r["seendate"], "%Y%m%dT%H%M%SZ") \
                .replace(tzinfo=timezone.utc).isoformat()
        except Exception:
            data = datetime.now(timezone.utc).isoformat()
        detyrat.append((f"GDELT:{r['domain']}", r["url"], r.get("title", ""), data, ""))
    return ruaj_te_gjitha(detyrat)


def mblidh_te_gjitha():
    """Mbledh nga të gjitha burimet dhe kthen {burimi: artikuj_te_rinj}."""
    rezultati = {}
    # Artikujt e mbledhur para se të kishte hash marrin hash tani (vetëm ata me tekst bruto)
    n = db.plotreso_hash(gjurma)
    if n:
        print(f"  Hash u shtua për {n} artikuj të vjetër")
    for burimi, url in FEEDS.items():
        t0 = time.time()
        try:
            rezultati[burimi] = mblidh_rss(burimi, url)
        except Exception as e:
            print(f"  {burimi} gabim: {e}")
            rezultati[burimi] = 0
        print(f"  {burimi}: {rezultati[burimi]} të rinj ({time.time() - t0:.0f}s)")
    rezultati["GDELT"] = mblidh_gdelt()
    print(f"  GDELT: {rezultati['GDELT']} të rinj")
    return rezultati


def kontrollet():
    """Kontrolle pa rrjet: robots.txt dhe fragmenti."""
    rp = lexo_robots(200, ["User-agent: *", "Disallow: /private/",
                           "User-agent: osint-prototype", "Disallow: /lajme/sekret"])
    assert rp.can_fetch(ROBOT, "https://x.com/lajme/1")
    assert not rp.can_fetch(ROBOT, "https://x.com/lajme/sekret-2")
    assert lexo_robots(404).can_fetch(ROBOT, "https://x.com/a")       # pa robots.txt = lejohet
    assert not lexo_robots(503).can_fetch(ROBOT, "https://x.com/a")   # server i rënë = ndalohet
    assert not lexo_robots(None).can_fetch(ROBOT, "https://x.com/a")  # i paarritshëm = ndalohet
    t = "Paragrafi i parë.\nI dyti.\n" + "x " * 1000
    assert fragment(t) == "Paragrafi i parë.\nI dyti."  # paragraf i plotë, pa gjysma
    assert len(fragment("fjale " * 500)) <= MAKS_FRAGMENTI
    assert fragment("") == "" and fragment("i shkurtër") == "i shkurtër"
    print("Kontrollet e collector.py kaluan.")


if __name__ == "__main__" and "--kontrollo" in sys.argv:
    kontrollet()
elif __name__ == "__main__":
    print("Mbledhja filloi...")
    te_reja = mblidh_te_gjitha()
    print("\nArtikuj të rinj në këtë ekzekutim:")
    for b, n in te_reja.items():
        print(f"  {b:16} {n}")
    print("\nGjithsej në bazë sipas burimit:")
    for r in db.numero_sipas_burimit():
        print(f"  {r['burimi']:30} {r['n']}")
