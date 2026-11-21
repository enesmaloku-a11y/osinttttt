"""collector.py - Mbledh artikuj nga RSS dhe GDELT dhe i ruan në SQLite pa dublikatë."""
import hashlib
import http.client
import ipaddress
import json
import re
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache
from threading import Lock
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import feedparser
import trafilatura
from langdetect import DetectorFactory, detect

import db

DetectorFactory.seed = 0  # rezultat i qëndrueshëm nga langdetect
KYCI_GJUHES = Lock()  # inicializimi i detektorit përdor gjendje të përbashkët

# Burimet RSS (URL-të u verifikuan më 2026-11-19)
FEEDS = {
    "RTK": "https://www.rtklive.com/sq/feed",
    "Koha": "https://www.koha.net/rss",
    "Kallxo": "https://kallxo.com/feed/",
    "Telegrafi": "https://telegrafi.com/feed/",
    "Gazeta Express": "https://www.gazetaexpress.com/feed/",
    "N1 Serbia": "https://n1info.rs/feed/",
    "Balkan Insight": "https://balkaninsight.com/feed/",
    "Hibrid.info": "https://hibrid.info/feed/",
    "Policia e Kosovës": "https://www.kosovopolice.com/feed/",
    "RTS": "https://www.rts.rs/vesti/rss.html",
}

BURIMET_INFO = {
    "Hibrid.info": dict(domeni="hibrid.info", gjuha="sq", lloji="media", vendi="XK"),
    "Policia e Kosovës": dict(domeni="kosovopolice.com", gjuha="sq", lloji="zyrtar", vendi="XK"),
    "RTS": dict(domeni="rts.rs", gjuha="sr", lloji="media", vendi="RS"),
}
AGENT = "osint-prototype/1.0"
PUNETORE = 8  # sa shkarkime paralele
MAKS_PER_FEED = 15
GDELT_PAUZA = 10
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
KOSOVA = re.compile(
    r"\b(kosov|kosmet|косов|космет|prishtin|pristina|priština|приштин|mitrovic|митровиц|"
    r"prizren|призрен|zve[čc]an|звечан|leposavi|лепосави|gjakov|ђаковиц|pej[ëa]|пећ)", re.I)
CIVILE = re.compile(
    r"\b(përmbyt|vërshim|zjarr|tërmet|emergjenc|evaku|ndërprer|ujësjell|rrym|"
    r"dezinform|njoftim i rremë|pretendim i rremë|mashtrim online|link i rremë|kibernet|"
    r"rrjedhje të dhënash|bllokim i rrug[ëe]|mbyllje e rrug[ëe]|trafik i ndërprerë|"
    r"poplav|po[žz]ar|zemljotres|evaku|nestanak struje|bez struje|bez vode|vodovod|"
    r"prekid saobra[ćc]aja|obustav[ae] saobra[ćc]aja|zatvoren put|"
    r"sajber|dezinform|la[žz]n[aoe] (vest|saop[šs]tenje)|поплав|пожар|земљотрес|еваку|"
    r"нестанак струје|без струје|без воде|водовод|прекид саобраћаја|обустав[ае] саобраћаја|"
    r"затворен пут|сајбер|дезинформ|лажн[аое] (вест|саопштење)|"
    r"flood|wildfire|earthquake|evacuat|power outage|water outage|data breach|"
    r"ransomware|disinform|false alert|service disruption)", re.I)
GRUPET = (
    ("fatkeqësi dhe emergjenca", ("flooding", "wildfire", "earthquake", "evacuation")),
    ("shërbime esenciale", ("power outage", "water outage", "service disruption", "road closures")),
    ("kibernetikë mbrojtëse dhe dezinformim", ("data breach", "ransomware", "false alert", "disinformation")),
)


def hosti(url):
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def adrese_publike(adresa):
    ip = ipaddress.ip_address(adresa)
    return ip.is_global and not ip.is_multicast and not ip.is_reserved


def lejohet(url, domeni=None):
    if not isinstance(url, str) or not url or any(c.isspace() or c == "\\" for c in url):
        return False
    try:
        u = urlsplit(url)
        host = u.hostname
        if u.scheme != "https" or not host or u.username is not None or u.port not in (None, 443):
            return False
        try:
            publik = adrese_publike(host)
        except ValueError:
            publik = bool(re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", host))
        return publik and (domeni is None or host == domeni or host.endswith("." + domeni))
    except (ValueError, UnicodeError):
        return False


class LidhjePublike(http.client.HTTPSConnection):
    def connect(self):
        adresat = socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM)
        if not adresat or any(not adrese_publike(a[4][0]) for a in adresat):
            raise OSError("Domeni nuk zgjidhet vetëm në adresa publike")
        for familja, lloji, protokolli, _, adresa in adresat:
            with socket.socket(familja, lloji, protokolli) as raw:
                raw.settimeout(self.timeout)
                try:
                    raw.connect(adresa)
                except OSError:
                    continue
                # Lidhja përdor adresën e validuar, TLS kontrollon emrin origjinal.
                self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
                return
        raise OSError("Lidhja dështoi")


def _shkarko(url, domeni, maks, kontrolli=None):
    for _ in range(4):
        if not lejohet(url, domeni) or (kontrolli and not kontrolli(url)):
            return None, None
        u = urlsplit(url)
        lidhja = LidhjePublike(u.hostname, 443, timeout=20)
        try:
            shtegu = u.path or "/"
            if u.query:
                shtegu += "?" + u.query
            lidhja.request("GET", shtegu, headers={"User-Agent": AGENT, "Accept-Encoding": "identity"})
            with lidhja.getresponse() as r:
                if r.status in (301, 302, 303, 307, 308):
                    url = urljoin(url, r.getheader("Location") or "")
                    continue
                if r.status != 200:
                    return r.status, None
                trupi = r.read(maks + 1)
                return r.status, trupi if len(trupi) <= maks else None
        except (OSError, ValueError, http.client.HTTPException):
            return None, None
        finally:
            lidhja.close()
    return None, None


@lru_cache(maxsize=64)
def _robots(host):
    url = f"https://{host}/robots.txt"
    status, trupi = _shkarko(url, hosti(url), 512_000)
    if trupi is None and status not in (404, 410):
        return None
    r = RobotFileParser(url)
    r.parse((trupi or b"").decode("utf-8", "replace").splitlines())
    r.modified()
    return r


def _lejohet_nga_robots(url):
    r = _robots(urlsplit(url).hostname)
    return r is not None and r.can_fetch(AGENT, url)


def shkarko(url, domeni=None, maks=3_000_000):
    if not lejohet(url, domeni):
        return None
    return _shkarko(url, domeni or hosti(url), maks, _lejohet_nga_robots)[1]


def domeni_i_lejuar(url):
    if not lejohet(url):
        return None
    domenet = {hosti(feed) for feed in FEEDS.values()}
    return next((d for d in sorted(domenet, key=len, reverse=True) if lejohet(url, d)), None)


def ka_lidhje(burimi, teksti):
    info = BURIMET_INFO.get(burimi)
    return info is None or bool(CIVILE.search(teksti) and
                                (info["vendi"] == "XK" or KOSOVA.search(teksti)))


def zbulo_gjuhen(teksti):
    """Kthen kodin e gjuhës. hr/bs/sr bashkohen te 'sr' (langdetect i ngatërron)."""
    if re.search("[јљњћђџ]", teksti, re.I):
        return "sr"
    try:
        with KYCI_GJUHES:
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


def nxirr_tekstin(url, domeni=None):
    """Shkarkon faqen dhe nxjerr vetëm tekstin kryesor (pa komente)."""
    try:
        domeni = domeni or domeni_i_lejuar(url)
        if not domeni or domeni in {info["domeni"] for info in BURIMET_INFO.values()}:
            return ""
        html = shkarko(url, domeni)
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
    if domeni_i_lejuar(url) in {info["domeni"] for info in BURIMET_INFO.values()}:
        return "krahasimi i faqes nuk zbatohet për përmbajtjen nga RSS"
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
    # Për burimet e reja përdoret teksti i botuar në RSS, me URL-në e origjinalit.
    teksti = nxirr_tekstin(url) or pastro_html(permbledhja) or titulli
    if not teksti:
        return None
    # Hash-i merret mbi tekstin bruto, para se processor.py ta pastrojë/presë
    gjuha = zbulo_gjuhen(f"{titulli}\n{teksti}")
    gjuha_e_burimit = BURIMET_INFO.get(burimi, {}).get("gjuha")
    if gjuha == "panjohur" and gjuha_e_burimit:
        gjuha = gjuha_e_burimit
    if gjuha in ("bg", "ru", "uk") and gjuha_e_burimit == "sr":
        gjuha = "sr"
    return dict(url=url, burimi=burimi, titulli=titulli, data=data,
                gjuha=gjuha, teksti=teksti,
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
    domeni = hosti(feed_url)
    trupi = shkarko(feed_url, domeni)
    if trupi is None:
        print(f"  {burimi}: RSS i paarritshëm ose i kufizuar nga robots.txt")
        return 0
    feed = feedparser.parse(trupi)
    if not feed.version:
        print(f"  {burimi}: përgjigjja nuk ishte RSS ose Atom")
        return 0
    detyrat, filtruar, jashte = [], 0, 0
    for e in feed.entries:
        linku = e.get("link")
        url = urljoin(feed_url, linku) if isinstance(linku, str) and linku else None
        # Cache: nëse URL ekziston, mos e shkarko përsëri
        if not lejohet(url, domeni):
            jashte += 1
            continue
        titulli, permbledhja = e.get("title", ""), e.get("summary", "")
        if not (isinstance(titulli, str) and isinstance(permbledhja, str)):
            filtruar += 1
            continue
        titulli, permbledhja = titulli[:500], permbledhja[:5000]
        if not ka_lidhje(burimi, f"{titulli} {pastro_html(permbledhja)}"):
            filtruar += 1
            continue
        if not db.ekziston_url(url):
            detyrat.append((burimi, url, titulli, data_iso(e), permbledhja))
    teprica = 0
    if burimi in BURIMET_INFO:
        detyrat.sort(key=lambda d: d[3], reverse=True)
        teprica = max(0, len(detyrat) - MAKS_PER_FEED)
        detyrat = detyrat[:MAKS_PER_FEED]
    te_reja = ruaj_te_gjitha(detyrat)
    print(f"  {burimi}: {te_reja} të rinj, {filtruar} të filtruar, {jashte} jashtë domenit, {teprica} mbi kufirin")
    return te_reja


def kerkesat_gdelt(ora):
    """Një kërkim në mediat serbe dhe një grup temash me rrotullim."""
    emri, terma = GRUPET[ora % len(GRUPET)]
    tema = "(" + " OR ".join(f'"{t}"' if " " in t else t for t in terma) + ")"
    zona = "(Kosovo OR Kosmet)"
    return (("media serbe", f"{zona} {tema} sourcecountry:serbia -domain:naslovi.net"),
            (emri, f"{zona} {tema} -domain:naslovi.net"))


def detyrat_gdelt(artikujt):
    detyra = []
    for r in artikujt:
        if not isinstance(r, dict):
            continue
        url, titulli = r.get("url"), r.get("title")
        if not lejohet(url) or not isinstance(titulli, str) or not 0 < len(titulli.strip()) <= 500:
            continue
        domeni = hosti(url)
        if lejohet(url, "naslovi.net") or db.ekziston_url(url):
            continue
        try:
            data = datetime.strptime(r.get("seendate"), "%Y%m%dT%H%M%SZ") \
                .replace(tzinfo=timezone.utc).isoformat()
        except (TypeError, ValueError):
            continue
        # Kjo është koha kur GDELT e pa artikullin.
        detyra.append((f"GDELT:{domeni}", url, titulli, data))
    return detyra


def mblidh_gdelt(ora=None):
    te_reja = 0
    for i, (emri, query) in enumerate(kerkesat_gdelt(datetime.now().hour if ora is None else ora)):
        if i:
            time.sleep(GDELT_PAUZA)
        params = urlencode(dict(query=query, mode="artlist", format="json",
                                timespan="1d", maxrecords=50, sort="datedesc"))
        url = f"{GDELT}?{params}"
        status, trupi = _shkarko(url, "api.gdeltproject.org", 1_000_000, _lejohet_nga_robots)
        if status == 429 or (trupi and b"please limit requests" in trupi.lower()):
            print("  GDELT: kufiri i ritmit")
            break
        if trupi is None:
            print(f"  GDELT: kërkesa «{emri}» nuk u arrit" + (f" (HTTP {status})" if status else ""))
            break
        try:
            pergjigjja = json.loads(trupi)
            artikujt = pergjigjja.get("articles", []) if isinstance(pergjigjja, dict) else None
            if not isinstance(artikujt, list):
                raise ValueError("Format i papritur")
        except (ValueError, UnicodeError):
            print(f"  GDELT: përgjigje e pavlefshme për «{emri}»")
            break
        shtuar = ruaj_te_gjitha(detyrat_gdelt(artikujt[:50]))
        te_reja += shtuar
        print(f"  GDELT «{emri}»: {len(artikujt)} rezultate, {shtuar} të rinj")
    return te_reja


def mblidh_te_gjitha():
    """Mbledh nga të gjitha burimet dhe kthen {burimi: artikuj_te_rinj}."""
    rezultati = {}
    _robots.cache_clear()
    # Artikujt e mbledhur para se të kishte hash marrin hash tani (vetëm ata me tekst bruto)
    n = db.plotreso_hash(gjurma)
    if n:
        print(f"  Hash u shtua për {n} artikuj të vjetër")
    for burimi, url in FEEDS.items():
        t0 = time.time()
        try:
            rezultati[burimi] = mblidh_rss(burimi, url)
        except Exception as e:
            print(f"  {burimi}: gabim ({type(e).__name__})")
            rezultati[burimi] = 0
        print(f"  {burimi}: {rezultati[burimi]} të rinj ({time.time() - t0:.0f}s)")
    try:
        rezultati["GDELT"] = mblidh_gdelt()
    except Exception as e:
        print(f"  GDELT: gabim ({type(e).__name__})")
        rezultati["GDELT"] = 0
    print(f"  GDELT: {rezultati['GDELT']} të rinj")
    return rezultati


def kontrollo():
    import scoring

    assert set(BURIMET_INFO) <= set(FEEDS) and set(BURIMET_INFO) <= set(scoring.MEDIAT)
    assert all(hosti(FEEDS[b]) == f["domeni"] for b, f in BURIMET_INFO.items())
    assert lejohet("https://www.rts.rs/a", "rts.rs")
    for url in ("https://rts.rs.example/a", "https://fakrts.rs/", "http://rts.rs/",
                "https://u@rts.rs/", "file:///c:/x", "https://rts.rs:8443/"):
        assert not lejohet(url, "rts.rs"), url
    for url in ("https://127.0.0.1/", "https://10.0.0.1/", "https://localhost/", "https://[::1]/"):
        assert not lejohet(url), url
    assert domeni_i_lejuar("https://www.rts.rs/a") == "rts.rs"
    assert domeni_i_lejuar("https://panjohur.example/a") is None
    assert zbulo_gjuhen("У Приштини је пријављен нестанак струје") == "sr"
    assert ka_lidhje("RTS", "У Приштини је пријављен нестанак струје")
    assert not ka_lidhje("RTS", "Пожар у Београду") and not ka_lidhje("RTS", "Kosovo: koncert")
    assert ka_lidhje("Hibrid.info", "Njoftim i rremë për ujin")
    assert len({kerkesat_gdelt(i)[1][1] for i in range(3)}) == 3
    print("Kontrollet e mbledhjes kaluan.")


if __name__ == "__main__" and "--kontrollo" in sys.argv:
    kontrollo()
elif __name__ == "__main__":
    print("Mbledhja filloi...")
    te_reja = mblidh_te_gjitha()
    print("\nArtikuj të rinj në këtë ekzekutim:")
    for b, n in te_reja.items():
        print(f"  {b:16} {n}")
    print("\nGjithsej në bazë sipas burimit:")
    for r in db.numero_sipas_burimit():
        print(f"  {r['burimi']:30} {r['n']}")
