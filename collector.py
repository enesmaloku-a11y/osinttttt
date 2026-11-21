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
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import feedparser
import db

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
    "Kosovo Online": "https://www.kosovo-online.com/rss.xml",
    "KoSSev": "https://kossev.info/feed/",
    "Novosti": "https://novosti.rs/rss/vesti",
    "Danas": "https://www.danas.rs/feed/",
    # Informer nuk u gjet në /rss, /rss.xml, /feed, /feed/, /rss/all, /rss/vesti.
    # RSE /api/ është feed rajonal me artikuj BiH/Kroaci, jo shërbimi serb i kërkuar.
    # MO Srbije: nuk u gjet RSS në faqen zyrtare ose shtigjet e zakonshme.
}

BURIMET_INFO = {
    "Hibrid.info": dict(domeni="hibrid.info", gjuha="sq", lloji="media", vendi="XK"),
    "Policia e Kosovës": dict(domeni="kosovopolice.com", gjuha="sq", lloji="zyrtar", vendi="XK"),
    "RTS": dict(domeni="rts.rs", gjuha="sr", lloji="media", vendi="RS"),
    "Kosovo Online": dict(domeni="kosovo-online.com", gjuha="sr", lloji="media", vendi="RS"),  # vendi: i pa verifikuar
    "KoSSev": dict(domeni="kossev.info", gjuha="sr", lloji="media", vendi="XK"),
    "Novosti": dict(domeni="novosti.rs", gjuha="sr", lloji="media", vendi="RS"),
    "Danas": dict(domeni="danas.rs", gjuha="sr", lloji="media", vendi="RS"),
}
AGENT = "osint-prototype/1.0"
PUNETORE = 8  # sa shkarkime paralele
# shortcut: kufi i fiksuar për kohën e përkthimit; rrite kur përpunimi të jetë më i shpejtë
MAKS_PER_FEED = 15
GDELT_PAUZA = 10
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
KOSOVA = re.compile(r"\b(kosov|kosmet|metohij|kosovsk|косов|космет|метохиј|priština|prishtin|pristina|приштин|mitrovic|митровиц|zvečan|звечан|leposavi|лепосави|zubin potok|зубин поток|jarinj|јарињ|brnjak|брњак|merdar|мердар|kfor|кфор|fsk|ksf)", re.I)


@lru_cache(maxsize=1)
def _regex_kercenimet():
    try:
        import kercenimet
        return kercenimet.fjale_kyce_regex()
    except Exception:
        return None


@lru_cache(maxsize=1)
def _regex_ushtarak_dron():
    try:
        import kercenimet
        fjalet = {f for k in ("ushtarak_serbia", "dron_hapesire_ajrore")
                  for ls in kercenimet.KATEGORITE[k]["fjale_kyce"].values() for f in ls}
        return re.compile(r"\b(?:" + "|".join(map(re.escape, sorted(fjalet, key=len, reverse=True))) + ")", re.I)
    except Exception:
        return None


def ka_lidhje(burimi, titulli, permbledhja=""):
    info = BURIMET_INFO.get(burimi)
    if info is None:
        return True
    tekst = f"{titulli or ''} {pastro_html(permbledhja or '')}".strip()
    if not tekst:
        return False
    if info["vendi"] == "RS" and info["lloji"] == "media":
        return bool(KOSOVA.search(tekst))
    kercenime = _regex_kercenimet()
    if info["lloji"] == "zyrtar" and info["vendi"] == "RS":
        militar = _regex_ushtarak_dron()
        return bool(KOSOVA.search(tekst) or (militar and militar.search(tekst)))
    return bool(KOSOVA.search(tekst) or (kercenime and kercenime.search(tekst)))


def hosti(url):
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def normalizo_lidhjen_rss(url, domeni):
    """Përmirëson vetëm HTTP të feed-it në HTTPS, kur hosti është i njëjtë."""
    try:
        u = urlsplit(url)
        if u.scheme == "http" and hosti(url) == domeni:
            return u._replace(scheme="https").geturl()
    except (TypeError, ValueError):
        pass
    return url


def url_normalizuar(url):
    """Heq vetëm parametrat e gjurmimit dhe fragmentin për krahasimin e URL-ve."""
    try:
        u = urlsplit(url)
        q = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() != "fbclid"]
        return urlunsplit((u.scheme.lower(), u.netloc.lower(), u.path.rstrip("/"), urlencode(q), ""))
    except (TypeError, ValueError):
        return ""


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


def _shkarko(url, domeni, maks, kontrolli=None, me_content_type=False):
    def pergjigje(status, trupi, content_type=None):
        return (status, trupi, content_type) if me_content_type else (status, trupi)
    for _ in range(4):
        if not lejohet(url, domeni) or (kontrolli and not kontrolli(url)):
            return pergjigje(None, None)
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
                    return pergjigje(r.status, None, r.getheader("Content-Type"))
                trupi = r.read(maks + 1)
                return pergjigje(r.status, trupi if len(trupi) <= maks else None,
                                 r.getheader("Content-Type"))
        except (OSError, ValueError, http.client.HTTPException):
            return pergjigje(None, None)
        finally:
            lidhja.close()
    return pergjigje(None, None)


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
    try:
        import correlator
        domenet = set(correlator.DOMENET)
    except Exception:
        domenet = set(hosti(feed) for feed in FEEDS.values())
    domenet.update(info["domeni"] for info in BURIMET_INFO.values())
    return next((d for d in sorted(domenet, key=len, reverse=True) if lejohet(url, d)), None)


def zbulo_gjuhen(teksti):
    """Kthen kodin e gjuhës. hr/bs/sr bashkohen te 'sr' (langdetect i ngatërron)."""
    if re.search("[јљњћђџ]", teksti, re.I):
        return "sr"
    try:
        from langdetect import DetectorFactory, detect
        DetectorFactory.seed = 0
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
        if not domeni:
            return ""
        html = shkarko(url, domeni)
        if html:
            import trafilatura
            teksti = trafilatura.extract(html, include_comments=False) or ""
            if len(teksti) >= 200:
                return teksti
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
        url = normalizo_lidhjen_rss(url, domeni) if url else None
        # Cache: nëse URL ekziston, mos e shkarko përsëri
        titulli, permbledhja = e.get("title", ""), e.get("summary", "")
        if not (isinstance(titulli, str) and isinstance(permbledhja, str)):
            filtruar += 1
            continue
        titulli, permbledhja = titulli[:500], permbledhja[:5000]
        if not ka_lidhje(burimi, f"{titulli} {pastro_html(permbledhja)}"):
            filtruar += 1
            continue
        if not lejohet(url, domeni):
            jashte += 1
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


GDELT_GRUPET = (
    ("ushtarak_serbia", '(Serbia OR Srbija OR "Vojska Srbije" OR "Војска Србије") (military OR army OR drone OR espionage OR Pancir OR FK-3 OR HQ-22 OR MiG-29 OR "China Serbia" OR "Russia Serbia")'),
    ("grupe_te_armatosura-ekstremizem_terrorizem", '(Kosovo OR Kosmet OR Kosova OR Metohija) (armed OR weapons OR terrorism OR extremist OR militant OR вооружен OR тероризам)'),
    ("kibernetik-infrastrukture_kritike", '(Kosovo OR Kosmet OR Kosova OR Metohija) (cyber OR ransomware OR DDoS OR hackers OR Gazivode OR "Ibar-Lepenac" OR KEK OR KOSTT)'),
    ("dezinformim-spiunazh_ndikim", '(Kosovo OR Kosmet OR Kosova OR Metohija) (disinformation OR propaganda OR "fake news" OR "лажне вести" OR bots)'),
    ("trazira_bllokada-struktura_paralele-kufi_kontrabande", '(Kosovo OR Kosmet OR Kosova OR Metohija) (Jarinje OR Brnjak OR Merdar OR "Zubin Potok" OR Zvečan OR Leposavić OR barricades OR "Srpska lista")'),
    ("diplomatik_ligjor-ekonomik_energjetik", '(Kosovo OR Kosmet OR Kosova OR Metohija) (recognition OR Brussels OR Ohrid OR ZSO OR sanctions OR gas OR electricity OR dinar)'),
)


def kerkesat_gdelt(ora):
    """Gjashtë kërkime sipas taksonomisë; grupi ushtarak nuk kërkon Kosovë."""
    return tuple((emri, query + " -domain:naslovi.net") for emri, query in GDELT_GRUPET)


def detyrat_gdelt(artikujt, urls_rss=None):
    detyra = []
    pare = {url_normalizuar(u) for u in (urls_rss or [])}
    for r in artikujt:
        if not isinstance(r, dict):
            continue
        url, titulli = r.get("url"), r.get("title")
        if not lejohet(url) or not isinstance(titulli, str) or not 0 < len(titulli.strip()) <= 500:
            continue
        domeni = hosti(url)
        normal = url_normalizuar(url)
        if (lejohet(url, "naslovi.net") or normal in pare or db.ekziston_url(url)
                or not (KOSOVA.search(titulli) or
                        (_regex_kercenimet() and _regex_kercenimet().search(titulli)))):
            continue
        try:
            data = datetime.strptime(r.get("seendate"), "%Y%m%dT%H%M%SZ") \
                .replace(tzinfo=timezone.utc).isoformat()
        except (TypeError, ValueError):
            continue
        # Kjo është koha kur GDELT e pa artikullin.
        detyra.append((f"GDELT:{domeni}", url, titulli, data))
        pare.add(normal)
    return detyra


def mblidh_gdelt(ora=None):
    te_reja = sukses = deshtime = 0
    for i, (emri, query) in enumerate(kerkesat_gdelt(datetime.now().hour if ora is None else ora)):
        if i:
            time.sleep(GDELT_PAUZA)
        params = urlencode(dict(query=query, mode="artlist", format="json",
                                timespan="1d", maxrecords=50, sort="datedesc"))
        url = f"{GDELT}?{params}"
        # API publike, robots.txt i saj jep 404; robots mbetet aktiv për faqet e artikujve.
        status, trupi, content_type = _shkarko(url, "api.gdeltproject.org", 1_000_000,
                                              me_content_type=True)
        for riprovim in range(2):
            if status != 429 and not (trupi and b"please limit requests" in trupi.lower()):
                break
            print(f"  GDELT {emri}: HTTP 429/kufizim ritmi; riprovim {riprovim + 1}/2")
            time.sleep(15 * (2 ** riprovim))
            status, trupi, content_type = _shkarko(url, "api.gdeltproject.org", 1_000_000,
                                                   me_content_type=True)
        if status == 429 or (trupi and b"please limit requests" in trupi.lower()):
            deshtime += 1
            print(f"  GDELT {emri}: dështoi pas 2 riprovimeve; HTTP {status}; Content-Type={content_type}; body={repr((trupi or b'')[:300])}")
            continue
        if trupi is None:
            deshtime += 1
            print(f"  GDELT: kërkesa «{emri}» nuk u arrit" + (f" (HTTP {status})" if status else ""))
            continue
        try:
            pergjigjja = json.loads(trupi)
            artikujt = pergjigjja.get("articles", []) if isinstance(pergjigjja, dict) else None
            if not isinstance(artikujt, list):
                raise ValueError("Format i papritur")
        except (ValueError, UnicodeError):
            deshtime += 1
            print(f"  GDELT {emri}: përgjigje jo-JSON, HTTP {status}, Content-Type={content_type}, {len(trupi)} bajtë; body={trupi[:300]!r}")
            continue
        shtuar = ruaj_te_gjitha(detyrat_gdelt(artikujt[:50]))
        te_reja += shtuar
        sukses += 1
        print(f"  GDELT «{emri}»: {len(artikujt)} rezultate, {shtuar} të rinj")
    print(f"  GDELT përmbledhje: {sukses} grupe të suksesshme, {deshtime} të dështuara, {te_reja} artikuj të rinj")
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
    import inspect

    for s in ("Kosovo", "Косово", "Космет", "Metohija", "Zubin Potok", "Jarinje", "Јариње",
              "KFOR", "FSK", "Mitrovica", "Приштина", "Leposavić"):
        assert KOSOVA.search(s), s
    for s in ("Prizren", "Gjakova", "Peja", "Pejë", "protest studenata u Beogradu",
              "blokada auto-puta kod Novog Sada"):
        assert not KOSOVA.search(s), s
    assert ka_lidhje("RTS", "Dron nadleteo branu Gazivode na Kosovu")
    assert not ka_lidhje("RTS", "Војска Србије подигла борбену готовост код Рашке")
    assert ka_lidhje("Policia e Kosovës", "Policia sekuestron armë pranë Jarinjës")
    assert ka_lidhje("Hibrid.info", "Lajm i rremë për FSK-në")
    assert ka_lidhje("RTS", "Lajm i rremë për FSK-në")
    assert ka_lidhje("RTS", "protest u Beogradu") is False
    assert ka_lidhje("RTS", "") is False and ka_lidhje("Koha", "") is True
    assert url_normalizuar("https://a.test/x/?utm_source=a&fbclid=z#f") == "https://a.test/x"
    assert normalizo_lidhjen_rss("http://www.rtklive.com/a", "rtklive.com") == "https://www.rtklive.com/a"
    assert normalizo_lidhjen_rss("http://evil.example/a", "rtklive.com").startswith("http://")
    assert lejohet("https://www.rts.rs/a", "rts.rs")
    for url in ("https://evil-rts.rs.attacker.com/a", "http://127.0.0.1/", "http://10.0.0.1/",
                "http://192.168.1.1/", "http://169.254.1.1/", "https://rts.rs@evil.com/",
                "file:///etc/passwd", "https://rts.rs:8443/"):
        assert not lejohet(url, "rts.rs"), url
    for b, i in BURIMET_INFO.items():
        assert i["gjuha"] in ("sr", "sq", "en") and i["lloji"] in ("media", "zyrtar")
        assert i["vendi"] in ("RS", "XK") and b in FEEDS
        assert b in scoring.MEDIAT
    assert all(KOSOVA.search(q) for _, q in kerkesat_gdelt(0)[1:])
    assert not any(x in " ".join(q for _, q in kerkesat_gdelt(0)).lower()
                   for x in ("flood", "fire", "outage", "poplav", "požar", "përmbytje", "zjarr"))
    q_tegjitha = re.sub(r"\bOR\b", "", " ".join(q for _, q in kerkesat_gdelt(0)), flags=re.I)
    assert not re.search(r"(?<![\w-])[a-z]{1,2}(?![\w-])", q_tegjitha, re.I)
    assert not re.search(r"kosov|kosmet|косов", kerkesat_gdelt(0)[0][1], re.I)
    assert len(inspect.signature(verifiko).parameters) == 3
    assert len(kerkesat_gdelt(0)) == 6
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
