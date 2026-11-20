"""collector.py - Mbledh artikuj nga RSS dhe GDELT dhe i ruan në SQLite pa dublikatë."""
import hashlib
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

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
PUNETORE = 8  # sa shkarkime paralele


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
    """Merr tekstin e plotë dhe gjuhën; kthen dict gati për db (ose None)."""
    teksti = nxirr_tekstin(url) or pastro_html(permbledhja)
    if not teksti:
        return None
    # Hash-i merret mbi tekstin bruto, para se processor.py ta pastrojë/presë
    return dict(url=url, burimi=burimi, titulli=titulli, data=data,
                gjuha=zbulo_gjuhen(f"{titulli}\n{teksti}"), teksti=teksti,
                hash_sha256=gjurma(teksti))


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


if __name__ == "__main__":
    print("Mbledhja filloi...")
    te_reja = mblidh_te_gjitha()
    print("\nArtikuj të rinj në këtë ekzekutim:")
    for b, n in te_reja.items():
        print(f"  {b:16} {n}")
    print("\nGjithsej në bazë sipas burimit:")
    for r in db.numero_sipas_burimit():
        print(f"  {r['burimi']:30} {r['n']}")
