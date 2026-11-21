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
from contextlib import closing
from datetime import datetime, timezone
from functools import lru_cache
from itertools import zip_longest
from threading import Lock
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import feedparser
import db

KYCI_GJUHES = Lock()  # inicializimi i detektorit përdor gjendje të përbashkët
KYCI_HOSTEVE = {}
KOHA_HOSTEVE = {}
HOST_DELAY = 1.0
MIN_TEKST = 200

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
    "Novosti": "https://www.novosti.rs/rss/vesti/politika",
    "Danas": "https://www.danas.rs/feed/",
    # Shërbimi "Kosovo" nga slobodnaevropa.org/rssfeeds. Më 2026-11-21: 15 nga 20 hyrje kalonin
    # filtrin, kundrejt 3 nga 20 te "Srbija" (api/zototl-vomx-tpepomq).
    "RSE": "https://www.slobodnaevropa.org/api/zmtoil-vomx-tpeyomp",
    "Informer": "https://informer.rs/rss/politika/vesti",
    # RSS 2.0 i vërtetuar më 2026-11-21: 20 hyrje, të gjitha në mod.gov.rs, robots.txt e lejon.
    "MO Srbije": "https://www.mod.gov.rs/rss.php?lat",
}

BURIMET_INFO = {
    "Hibrid.info": dict(domeni="hibrid.info", gjuha="sq", lloji="media", vendi="XK"),
    "Policia e Kosovës": dict(domeni="kosovopolice.com", gjuha="sq", lloji="zyrtar", vendi="XK"),
    "RTS": dict(domeni="rts.rs", gjuha="sr", lloji="media", vendi="RS"),
    "Kosovo Online": dict(domeni="kosovo-online.com", gjuha="sr", lloji="media", vendi="RS"),  # vendi: i pa verifikuar
    "KoSSev": dict(domeni="kossev.info", gjuha="sr", lloji="media", vendi="XK"),
    "Novosti": dict(domeni="novosti.rs", gjuha="sr", lloji="media", vendi="RS"),
    "Danas": dict(domeni="danas.rs", gjuha="sr", lloji="media", vendi="RS"),
    "RSE": dict(domeni="slobodnaevropa.org", gjuha="sr", lloji="media", vendi="RS"),
    "Informer": dict(domeni="informer.rs", gjuha="sr", lloji="media", vendi="RS"),
    "MO Srbije": dict(domeni="mod.gov.rs", gjuha="sr", lloji="zyrtar", vendi="RS"),
}
AGENT = "osint-prototype/1.0"
PUNETORE = 8  # sa shkarkime paralele
# shortcut: kufi i fiksuar për kohën e përkthimit; rrite kur përpunimi të jetë më i shpejtë
MAKS_PER_FEED = 15
GDELT_PAUZA = 10
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
KOSOVA = re.compile(r"\b(kosov|kosmet|metohij|kosovsk|косов|космет|метохиј|prištin|prishtin|pristina|приштин|mitrovic|митровиц|zve[čcç]an|звечан|leposavi|лепосави|zubin\w* potok|зубин\w* поток|gazivod|газивод|ujman|jarinj|јарињ|brnjak|брњак|merdar|мердар|kfor|кфор|fsk|ksf)", re.I)
# shortcut: rrënjë shtesë me mbaresa për lakimet serbe/shqipe; propozim që kërkon miratimin e A-së (devijim nga Prompt B, Hapi 2).
KOSOVA_EKSTRA = re.compile(
    r"\b(?:"
    r"zubin\w*\s+potok\w*|зубин\w*\s+поток\w*|"  # Komuna në Kosovë, edhe kur RSS-ja përdor hapësira të shumëfishta.
    # Vija administrative vetëm me formulimin e plotë të rastit në shqip. Të miratohet nga A.
    r"grumbullim\w*\s+i\s+forc\w*\s+serb\w*\s+pran[eë]\s+vij\w*\s+administrativ\w*"
    r")\b", re.I,
)
# Formulimi shqip për forca ushtarake serbe që taksonomia s'e kap ("forcat serbe", "ushtarët serbë").
# shortcut: jeton këtu që të mos preket kercenimet.py para ngrirjes; zhvendose te taksonomia pas saj.
USHTARAK_SQ = re.compile(r"\b(?:forc|ushtar|xhandarm)\w*(?: (?:ushtarake|speciale|[eë] armatosura))?"
                         r"(?: [eë]| të)? serb", re.I)


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
        # Forma cirilike e pajisjeve e kërkuar për mbulimin shumëgjuhësh.
        fjalet.update(("ФК-3", "ХК-22", "Панцир", "МиГ-29"))
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
        return bool(KOSOVA.search(tekst) or KOSOVA_EKSTRA.search(tekst))
    kercenime = _regex_kercenimet()
    if info["lloji"] == "zyrtar" and info["vendi"] == "RS":
        militar = _regex_ushtarak_dron()
        return bool(KOSOVA.search(tekst) or KOSOVA_EKSTRA.search(tekst) or (militar and militar.search(tekst)))
    return bool(KOSOVA.search(tekst) or USHTARAK_SQ.search(tekst) or (kercenime and kercenime.search(tekst)))


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


def _shkarko(url, domeni, maks, kontrolli=None, me_content_type=False, *,
             ridrejtimet=3, me_trupin_e_gabimit=False):
    def pergjigje(status, trupi, content_type=None):
        return (status, trupi, content_type) if me_content_type else (status, trupi)
    for _ in range(ridrejtimet + 1):
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
                    if not ridrejtimet:
                        return pergjigje(r.status, None, r.getheader("Content-Type"))
                    url = urljoin(url, r.getheader("Location") or "")
                    continue
                if r.status == 429 or (r.status != 200 and not me_trupin_e_gabimit):
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


def shkarko(url, domeni=None, maks=3_000_000, me_content_type=False):
    if not lejohet(url, domeni):
        return (None, None, None) if me_content_type else None
    status, body, content_type = _shkarko(url, domeni or hosti(url), maks,
                                         _lejohet_nga_robots, me_content_type=True)
    return (status, body, content_type) if me_content_type else body


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
        kyci = KYCI_HOSTEVE.setdefault(domeni, Lock())
        with kyci:
            prit = HOST_DELAY - (time.monotonic() - KOHA_HOSTEVE.get(domeni, 0))
            if prit > 0:
                time.sleep(prit)
            KOHA_HOSTEVE[domeni] = time.monotonic()
        html = shkarko(url, domeni)
        if html:
            import trafilatura
            teksti = trafilatura.extract(html, include_comments=False) or ""
            if len(teksti) >= MIN_TEKST:
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
    # Përmbledhja e RSS përdoret kur teksti i plotë mungon.
    teksti_plote = nxirr_tekstin(url)
    permbledhje_rss = pastro_html(permbledhja)
    teksti = teksti_plote or permbledhje_rss or titulli
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
                hash_sha256=gjurma(teksti),
                _teksti_lloji=("plote" if teksti_plote else
                               "permbledhje" if permbledhje_rss else "deshtoi"))


def ruaj_te_gjitha(detyrat, me_statistika=False):
    """Ekzekuton 'pergatit' paralelisht dhe ruan rezultatet. Kthen numrin e të rejave."""
    te_reja = 0
    tekstet = {"plote": 0, "permbledhje": 0, "deshtoi": 0}
    with ThreadPoolExecutor(PUNETORE) as ex:
        for art in ex.map(lambda d: pergatit(*d), detyrat):
            if art:
                lloji = art.pop("_teksti_lloji", "deshtoi")
                tekstet[lloji] += 1
                if db.ruaj_artikull(**art):
                    te_reja += 1
            else:
                tekstet["deshtoi"] += 1
    return (te_reja, tekstet) if me_statistika else te_reja


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
    te_reja, tekstet = ruaj_te_gjitha(detyrat, me_statistika=True)
    print(f"  {burimi}: {te_reja} të rinj, {filtruar} të filtruar, {jashte} jashtë domenit, "
          f"{teprica} mbi kufirin, {tekstet['plote']} tekst i plotë, "
          f"{tekstet['permbledhje']} përmbledhje, {tekstet['deshtoi']} dështuar")
    return te_reja


GDELT_GRUPET = (
    ("ushtarak_serbia", "spiunazh_ndikim"),
    ("grupe_te_armatosura", "infrastrukture_kritike", "dron_hapesire_ajrore",
     "kibernetik", "trazira_bllokada"),
    ("dezinformim", "ekstremizem_terrorizem", "kufi_kontrabande",
     "struktura_paralele", "diplomatik_ligjor", "ekonomik_energjetik"),
)
GDELT_SERBIA = "(Kosovo OR Kosmet) sourcecountry:serbia -domain:naslovi.net"
GDELT_SPIRANCA = (
    "(Serbia OR Srbija) (China OR Chinese OR Russia OR Russian OR Kina OR Rusija)",
    "(Kosovo OR Kosmet)",
    "(Kosovo OR Kosmet)",
)
ZGJERIMI = {
    "disinform": "disinformation", "misinform": "misinformation",
    "paramilitar": "paramilitary", "smuggl": "smuggling",
    "extremis": "extremism", "radicali": "radicalization",
    "derecogni": "derecognition", "military build": "military buildup",
    "chinese compan": "chinese company", "russian compan": "russian company",
    "provisional authorit": "provisional authorities",
    "unmanned aerial": "unmanned aerial vehicle", "gazivod": "gazivode",
}


def termat_gdelt(kategorite, grupi):
    lista = [kategorite[id]["fjale_kyce"]["en"] for id in GDELT_GRUPET[grupi]]
    termat = {}
    for radha in zip_longest(*lista):
        for term in radha:
            if term is None:
                continue
            term = " ".join(term.lower().split())
            term = ZGJERIMI.get(term, term)
            if sum(c.isalpha() for c in term) < 4:
                continue
            if grupi == 0 and KOSOVA.search(term):
                continue
            termat.setdefault(term, None)
            if len(termat) == 10:
                return tuple(termat)
    return tuple(termat)


def kerkesat_gdelt(ora=None):
    """Një kërkim fiks dhe deri një grup tematik."""
    fillimi = (("media_serbia", GDELT_SERBIA),)
    try:
        from kercenimet import KATEGORITE
    except ImportError:
        return fillimi
    # shortcut: rrotullo grupin sipas orës që çdo ekzekutim të mbajë vetëm dy kërkesa.
    grupi = (datetime.now().hour if ora is None else ora) % len(GDELT_GRUPET)
    termat = termat_gdelt(KATEGORITE, grupi)
    if not termat:
        return fillimi
    pyetja = " OR ".join(f'"{t}"' if " " in t or "-" in t else t for t in termat)
    return (*fillimi, (f"grupi_{grupi}", f"{GDELT_SPIRANCA[grupi]} ({pyetja}) -domain:naslovi.net"))


def detyrat_gdelt(artikujt, urls_rss=None, me_statistika=False, *, urls_gdelt=None):
    detyra = []
    rss = {url_normalizuar(u) for u in (urls_rss or [])}
    pare = {url_normalizuar(u) for u in (urls_gdelt or [])}
    statistika = {"rezultate": len(artikujt), "mbajtur": 0, "dublikat_rss": 0,
                  "dublikat_db": 0, "jashte": 0, "filtruar": 0, "date_gabim": 0}
    for r in artikujt:
        if not isinstance(r, dict):
            statistika["filtruar"] += 1
            continue
        url, titulli = r.get("url"), r.get("title")
        if not lejohet(url) or not isinstance(titulli, str) or not 0 < len(titulli.strip()) <= 500:
            statistika["jashte"] += 1
            continue
        domeni = hosti(url)
        normal = url_normalizuar(url)
        if lejohet(url, "naslovi.net"):
            statistika["jashte"] += 1
            continue
        if normal in rss:
            statistika["dublikat_rss"] += 1
            continue
        if normal in pare or db.ekziston_url(url):
            statistika["dublikat_db"] += 1
            continue
        if not (KOSOVA.search(titulli) or
                (_regex_kercenimet() and _regex_kercenimet().search(titulli))):
            statistika["filtruar"] += 1
            continue
        try:
            data = datetime.strptime(r.get("seendate"), "%Y%m%dT%H%M%SZ") \
                .replace(tzinfo=timezone.utc).isoformat()
        except (TypeError, ValueError):
            statistika["date_gabim"] += 1
            continue
        # Kjo është koha kur GDELT e pa artikullin.
        detyra.append((f"GDELT:{domeni}", url, titulli, data))
        pare.add(normal)
        statistika["mbajtur"] += 1
    return (detyra, statistika) if me_statistika else detyra


def mblidh_gdelt(ora=None):
    te_reja = sukses = deshtime = 0
    # RSS përpunohet para GDELT; mbaj URL-të e tij për numërimin e dublikatave.
    urls_rss, urls_gdelt = [], []
    with closing(db.lidhu()) as con:
        for url, burimi in con.execute("SELECT url, burimi FROM articles"):
            if burimi in FEEDS:
                urls_rss.append(url)
            elif burimi.startswith("GDELT:"):
                urls_gdelt.append(url)
    for i, (emri, query) in enumerate(kerkesat_gdelt(ora)):
        if i:
            time.sleep(GDELT_PAUZA)
        params = urlencode(dict(query=query, mode="artlist", format="json",
                                timespan="1d", maxrecords=50, sort="datedesc"))
        url = f"{GDELT}?{params}"
        # API publike, robots.txt i saj jep 404; robots mbetet aktiv për faqet e artikujve.
        status, trupi, content_type = _shkarko(url, "api.gdeltproject.org", 1_000_000,
                                              me_content_type=True, ridrejtimet=0,
                                              me_trupin_e_gabimit=True)
        if status == 429 or (trupi and b"please limit requests" in trupi.lower()):
            deshtime += 1
            print(f"  GDELT: kufiri i ritmit ({emri}, HTTP {status})")
            break
        if status != 200 or trupi is None:
            deshtime += 1
            print(f"  GDELT: kërkesa «{emri}» nuk u arrit" + (f" (HTTP {status})" if status else ""))
            continue
        try:
            pergjigjja = json.loads(trupi)
            artikujt = pergjigjja.get("articles") if isinstance(pergjigjja, dict) else None
            if not isinstance(artikujt, list):
                raise ValueError("Format i papritur")
        except (ValueError, UnicodeError):
            deshtime += 1
            print(f"  GDELT {emri}: përgjigje jo-JSON ose pa listën articles, HTTP {status}, "
                  f"Content-Type={content_type}, {len(trupi)} bajtë")
            continue
        detyrat, stats = detyrat_gdelt(artikujt[:50], urls_rss, me_statistika=True,
                                       urls_gdelt=urls_gdelt)
        shtuar, tekstet = ruaj_te_gjitha(detyrat, me_statistika=True)
        te_reja += shtuar
        sukses += 1
        urls_gdelt.extend(d[1] for d in detyrat)
        print(f"  GDELT «{emri}»: HTTP {status}, JSON, {len(artikujt)} rezultate; "
              f"{stats['mbajtur']} mbajtur pas filtrit; {stats['dublikat_rss']} dublikatë RSS, "
              f"{stats['dublikat_db']} dublikatë DB, {stats['filtruar']} filtruar, "
              f"{stats['jashte']} jashtë, {stats['date_gabim']} pa datë të vlefshme; {shtuar} të rinj, "
              f"{tekstet['plote']} tekst i plotë, {tekstet['permbledhje']} përmbledhje, "
              f"{tekstet['deshtoi']} dështuar")
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
    global _shkarko, nxirr_tekstin, pergatit, shkarko, ruaj_te_gjitha
    import scoring
    import inspect
    import contextlib
    import io
    from unittest.mock import patch

    import kercenimet

    for s in ("Kosovo", "Косово", "Космет", "Metohija", "Zubin Potok", "Jarinje", "Јариње", "Prištini",
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
    assert ka_lidhje("Kosovo Online", "Dron nadleteo branu Gazivode na Kosovu")
    assert ka_lidhje("Kosovo Online", "Tužilaštvo: U Prištini zaplenjeno više od 15 kilograma narkotika")
    assert not ka_lidhje("RTS", "Војска Србије подигла борбену готовост код Рашке")
    mo_tituj = ("Исporučen kineski sistem FK-3 Vojsci Srbije",
                "Isporučen kineski sistem FK-3 Vojsci Srbije",
                "Испоручен кинески систем ФК-3 Војсци Србије")
    assert all(ka_lidhje("MO Srbije", t) for t in mo_tituj)
    assert all(not ka_lidhje("RTS", t) for t in mo_tituj)
    assert ka_lidhje("Hibrid.info", "Lajm i rremë për FSK-në")
    assert ka_lidhje("KoSSev", "ransomware attack on servers")
    assert ka_lidhje("burim i vjetër", "tekst pa filtër")
    for media_rs in ("RTS", "Novosti", "Informer", "Danas", "RSE"):
        assert ka_lidhje(media_rs, "protest u Beogradu") is False, media_rs
    assert ka_lidhje("RSE", "Policia arrestoi të dyshuarit në Kosovë")
    assert ka_lidhje("Informer", "Izveštaj o Kosovu")
    assert ka_lidhje("RTS", "") is False and ka_lidhje("Koha", "") is True
    # Humbjet e auditit: lakimet e Gazivodës, Zubin Potokut, Zveçanit dhe formulimi shqip ushtarak
    for b, t in (("RTS", "Dron iznad Gazivoda"), ("Novosti", "Пад нивоа воде у Газиводама"),
                 ("Danas", "Napad na policiju u Zubinom Potoku"), ("RTS", "Барикаде код Зубиног Потока"),
                 ("RSE", "Incident u Zvecanu"), ("Hibrid.info", "Forcat serbe afër kufirit"),
                 ("Hibrid.info", "Lëvizje të forcave ushtarake serbe pranë kufirit"),
                 ("Hibrid.info", "Ushtarët serbë në gatishmëri"),
                 ("Policia e Kosovës", "Sulm ndaj personit zyrtar në Zveçan")):
        assert ka_lidhje(b, t), t
    import correlator
    for b, u in FEEDS.items():  # emri dhe domeni përputhen te FEEDS, BURIMET_INFO dhe correlator
        assert correlator.DOMENET.get(hosti(u)) == b, b
        assert b not in BURIMET_INFO or BURIMET_INFO[b]["domeni"] == hosti(u), b
    assert domeni_i_lejuar("https://www.rts.rs/a") == "rts.rs" and domeni_i_lejuar("https://evil.example/a") is None
    # Njoftimi policor jashtë veriut bie: vepër e zakonshme, pa spirancë dhe pa term taksonomie
    for b, t in (("Policia e Kosovës", "Sulm ndaj personit zyrtar në Ferizaj"), ("RTS", "veri"),
                 ("RTS", "Kiša na severu Srbije"), ("Novosti", "Cene goriva od ponedeljka niže"),
                 ("Informer", "Potok izlio u Čačku"), ("RTS", "Gazirana pića poskupljuju"),
                 ("RSE", "Zubin zid u Beogradu"), ("Hibrid.info", "Forcat e Shqipërisë në mision NATO")):
        assert not ka_lidhje(b, t), t
    # Kufiri 15 vjen pas filtrit: 40 hyrje ku 30 bien -> 10 mbeten; 20 të vlefshme -> 15 më të rejat
    parse_v, shkarko_v, ekziston_v, ruaj_v = feedparser.parse, shkarko, db.ekziston_url, ruaj_te_gjitha
    try:
        for n_mira, pritet in ((10, 10), (20, 15)):
            hyrjet = [dict(link=f"https://www.rts.rs/a{i}", title="Dron iznad Gazivoda" if i < n_mira
                           else "Protest u Beogradu", summary="", published_parsed=(2026, 11, 1 + i, 0, 0, 0))
                      for i in range(40)]
            feedparser.parse = lambda _t, h=hyrjet: type("F", (), {"version": "rss20", "entries": h})()
            shkarko = lambda *_a, **_k: b"<rss/>"
            db.ekziston_url = lambda _u: False
            marre = []
            ruaj_te_gjitha = lambda d, **_k: (marre.extend(d), (0, {"plote": 0, "permbledhje": 0, "deshtoi": 0}))[1]
            with contextlib.redirect_stdout(io.StringIO()):
                mblidh_rss("RTS", "https://www.rts.rs/vesti/rss.html")
            assert len(marre) == pritet and marre[0][1] == f"https://www.rts.rs/a{n_mira - 1}", (n_mira, len(marre))
    finally:
        feedparser.parse, shkarko, db.ekziston_url, ruaj_te_gjitha = parse_v, shkarko_v, ekziston_v, ruaj_v
    assert url_normalizuar("https://a.test/x/?utm_source=a&fbclid=z#f") == "https://a.test/x"
    assert normalizo_lidhjen_rss("http://www.rtklive.com/a", "rtklive.com") == "https://www.rtklive.com/a"
    assert normalizo_lidhjen_rss("http://evil.example/a", "rtklive.com").startswith("http://")
    assert lejohet("https://www.rts.rs/a", "rts.rs")
    for url in ("https://rts.rs.keq.com/a", "https://keqrts.rs/", "http://rts.rs/",
                "https://127.0.0.1/", "https://10.0.0.1/", "https://localhost/",
                "https://u@rts.rs/", "file:///c:/x",
                "https://evil-rts.rs.attacker.com/a", "http://127.0.0.1/", "http://10.0.0.1/",
                "http://192.168.1.1/", "http://169.254.1.1/", "https://rts.rs@evil.com/",
                "file:///etc/passwd", "https://rts.rs:8443/"):
        assert not lejohet(url, "rts.rs"), url
    assert set(BURIMET_INFO) <= set(FEEDS)
    for b, i in BURIMET_INFO.items():
        assert i["domeni"] == hosti(FEEDS[b])
        assert i["gjuha"] in ("sr", "sq", "en") and i["lloji"] in ("media", "zyrtar", "telegram", "youtube")
        assert i["vendi"] in ("RS", "XK")
        assert b in scoring.MEDIAT
    korpusi = {
        "sq": (
            ("Grumbullim i forcave serbe pranë vijës administrative",
             "Hetim për një dron mbi Gazivodë", "Barrikada në Zubin Potok",
             "Policia raporton incident pranë Jarinjës", "Sulm kibernetik ndaj institucioneve të Kosovës",
             "Pretendim i rremë për KFOR-in", "Ndërprerje e furnizimit në Mitrovicë",
             "Raport për një incident pranë Bërnjakut në Kosovë"),
            ("Rriten çmimet e karburanteve në Shqipëri", "Koncert i ri në Beograd",
             "Kuvendi i Shqipërisë miratoi projektbuxhetin", "Bllokohet qarkullimi pranë Durrësit",
             "Punime përgjatë vijës administrative në Tiranë",
             "Protestë për pagat në Shkup", "Kampionat basketbolli në Elbasan",
             "Autoritetet lokale diskutojnë vijën administrative të dy komunave"),
        ),
        "sr": (
            ("Dron nadleteo Gazivode", "Barikade na putu ka Zubinom Potoku",
             "Radovi kod Zubinog Potoka", "Incident na Jarinju", "Sajber napad na institucije Kosova",
             "Dezinformacije o KFOR-u", "Nestanak struje u Mitrovici", "Saopštenje policije u Leposaviću"),
            ("Studenti blokirali raskrsnicu u Beogradu, protest se nastavlja",
             "Protest u Novom Sadu", "Cene goriva više za tri dinara", "Koncert u Beogradu",
             "Ibarska magistrala zatvorena zbog radova", "Nova pruga Beograd–Niš",
             "Obnova puta uz administrativnu liniju između opština u Vojvodini",
             "Sezonski radovi na putu Zubinovac–Niš"),
        ),
        "sr_cyr": (
            ("Дрон надлетео Газиводе", "Барикаде код Зубиног Потока",
             "Радови на путу ка Зубином Потоку", "Инцидент на Јарињу", "Сајбер напад на институције Косова",
             "Дезинформације о КФОР-у", "Нестанак струје у Митровици", "Саопштење полиције у Лепосавићу"),
            ("Студенти блокирали раскрсницу у Београду, протест се наставља",
             "Протест у Новом Саду", "Цене горива више за три динара", "Концерт у Београду",
             "Ибарска магистрала затворена због радова", "Нова пруга Београд–Ниш",
             "Обнова пута уз административну линију између општина у Војводини",
             "Радови на путу Зубиновац–Ниш"),
        ),
    }
    media_rs = [b for b, i in BURIMET_INFO.items() if (i["vendi"], i["lloji"]) == ("RS", "media")]
    burime_xk = [b for b, i in BURIMET_INFO.items() if i["vendi"] == "XK"]
    burime_te_vjetra = set(FEEDS) - set(BURIMET_INFO)
    for gjuha, (pozitive, negative) in korpusi.items():
        assert len(pozitive) >= 8 and len(negative) >= 8
        titujt = (*pozitive, *negative)
        for burimi in media_rs:
            assert all(ka_lidhje(burimi, t) for t in pozitive), (gjuha, burimi)
            assert not any(ka_lidhje(burimi, t) for t in negative), (gjuha, burimi)
        for burimi in burime_te_vjetra:
            assert all(ka_lidhje(burimi, t) for t in titujt), (gjuha, burimi)
        me_ekstra = {b: [ka_lidhje(b, t) for t in titujt] for b in burime_xk}
        with patch(__name__ + ".KOSOVA_EKSTRA", re.compile(r"(?!)")):
            assert me_ekstra == {b: [ka_lidhje(b, t) for t in titujt] for b in burime_xk}
            para = (sum(ka_lidhje("RTS", t) for t in pozitive), sum(ka_lidhje("RTS", t) for t in negative))
        print(f"Filtri RS {gjuha}: TP {para[0]} → {len(pozitive)}; FP {para[1]} → 0")
    assert ka_lidhje("RTS", "Incident u Zubinom  Potoku")
    assert ka_lidhje("RTS", "Инцидент код Зубиног  Потока")
    assert ka_lidhje("MO Srbije", "Dron nadleteo Gazivode")
    assert GDELT_PAUZA == 10
    nxirr_vjeter, pergatit_vjeter, ruaj_vjeter = nxirr_tekstin, pergatit, db.ruaj_artikull
    try:
        nxirr_tekstin = lambda *_: "tekst i plotë " * 25
        assert pergatit("RTK", "https://example.com/a", "titull", "2026-01-01", "rss")[
            "_teksti_lloji"] == "plote"
        nxirr_tekstin = lambda *_: ""
        assert pergatit("RTK", "https://example.com/a", "titull", "2026-01-01", "përmbledhje RSS") [
            "_teksti_lloji"] == "permbledhje"
        assert pergatit("RTK", "https://example.com/a", "titull", "2026-01-01", "") [
            "_teksti_lloji"] == "deshtoi"
        llojet = iter(("plote", "permbledhje", "deshtoi"))
        pergatit = lambda *_: {"_teksti_lloji": lloji} if (lloji := next(llojet, None)) else None
        db.ruaj_artikull = lambda **_: True
        nr, numrat = ruaj_te_gjitha([(1,), (2,), (3,), (4,)], me_statistika=True)
        assert nr == 3 and numrat == {"plote": 1, "permbledhje": 1, "deshtoi": 2}
    finally:
        nxirr_tekstin, pergatit = nxirr_vjeter, pergatit_vjeter
        db.ruaj_artikull = ruaj_vjeter
    id_te_gjitha = [id for grup in GDELT_GRUPET for id in grup]
    assert len(id_te_gjitha) == len(set(id_te_gjitha)) == 13
    assert set(id_te_gjitha) == set(kercenimet.KATEGORITE) - {"tjeter"}
    assert len({kerkesat_gdelt(i)[1][1] for i in range(3)}) == 3
    assert kerkesat_gdelt(0) == kerkesat_gdelt(3)
    for grup in range(3):
        pare, tematike = kerkesat_gdelt(grup)
        assert pare == ("media_serbia", "(Kosovo OR Kosmet) sourcecountry:serbia -domain:naslovi.net")
        assert tematike[0] == f"grupi_{grup}" and tematike[1].startswith(GDELT_SPIRANCA[grup])
        assert tematike[1].endswith(" -domain:naslovi.net")
        assert bool(KOSOVA.search(tematike[1])) == (grup != 0)
        termat = termat_gdelt(kercenimet.KATEGORITE, grup)
        assert 0 < len(termat) == len(set(termat)) <= 10
        assert not set(termat) & set(ZGJERIMI)
        assert all(sum(c.isalpha() for c in t) >= 4 for t in termat)
        assert all(f'"{t}"' in tematike[1] for t in termat if " " in t or "-" in t)
    assert len(inspect.signature(verifiko).parameters) == 3
    ekziston_vjeter = db.ekziston_url
    try:
        db.ekziston_url = lambda _url: False
        detyra, stats = detyrat_gdelt([
            {"url": "https://www.rtklive.com/unique?utm_source=x", "title": "Kosovo security", "seendate": "20261121T100000Z"},
            {"url": "https://www.rtklive.com/lajm", "title": "Kosovo duplicate", "seendate": "20261121T100000Z"},
            {"url": "https://www.rtklive.com/unique", "title": "Kosovo repeat", "seendate": "20261121T100000Z"},
            {"url": "https://www.rtklive.com/old/?utm_source=gdelt", "title": "Kosovo old", "seendate": "20261121T100000Z"},
            {"url": "https://www.rtklive.com/other", "title": "Sport result", "seendate": "20261121T100000Z"},
            {"url": "https://www.rtklive.com/bad-date", "title": "Kosovo incident", "seendate": "bad"},
            {"url": "http://evil.example/item", "title": "Kosovo incident", "seendate": "20261121T100000Z"},
            {"url": "https://naslovi.net/item", "title": "Kosovo incident", "seendate": "20261121T100000Z"},
        ], ["https://www.rtklive.com/lajm"], me_statistika=True,
            urls_gdelt=["https://www.rtklive.com/old"])
        assert len(detyra) == 1 and stats == {"rezultate": 8, "mbajtur": 1, "dublikat_rss": 1,
            "dublikat_db": 2, "jashte": 2, "filtruar": 1, "date_gabim": 1}
    finally:
        db.ekziston_url = ekziston_vjeter
    with patch(__name__ + ".shkarko", side_effect=AssertionError("host jashtë listës")):
        titull = "Kosovo public notice from an unknown publisher"
        assert pergatit("GDELT:panjohur.example", "https://panjohur.example/a", titull,
                        "2026-11-21")["teksti"] == titull

    def prove_gdelt(pergjigjet, n, pritjet, mesazhi):
        dalje = io.StringIO()
        with (patch(__name__ + "._shkarko", side_effect=pergjigjet) as shkarkimi,
              patch.object(time, "sleep") as prit, contextlib.redirect_stdout(dalje)):
            assert mblidh_gdelt(0) == 0
        assert shkarkimi.call_count == n and [p.args[0] for p in prit.call_args_list] == pritjet
        assert all(c.kwargs["ridrejtimet"] == 0 for c in shkarkimi.call_args_list)
        assert mesazhi in dalje.getvalue(), dalje.getvalue()

    ok = (200, b'{"articles":[]}', "application/json")
    kufi = (429, None, "text/plain")
    prove_gdelt([ok, ok], 2, [10], "2 grupe të suksesshme")
    prove_gdelt([kufi], 1, [], "GDELT: kufiri i ritmit")
    prove_gdelt([(503, b"Please limit requests", "text/plain")], 1, [], "GDELT: kufiri i ritmit")
    prove_gdelt([ok, kufi], 2, [10], "GDELT: kufiri i ritmit")
    prove_gdelt([(302, None, "text/html"), ok], 2, [10], "HTTP 302")
    prove_gdelt([(200, b"{}", "application/json"), ok], 2, [10], "pa listën articles")
    with patch.dict(sys.modules, {"kercenimet": None}):
        assert kerkesat_gdelt(0) == (("media_serbia", GDELT_SERBIA),)
        prove_gdelt([ok], 1, [], "1 grupe të suksesshme")

    with patch(__name__ + ".LidhjePublike") as lidhja:
        pergjigjja = lidhja.return_value.getresponse.return_value.__enter__.return_value
        pergjigjja.status = 302
        status, _, _ = _shkarko(GDELT, "api.gdeltproject.org", 100, me_content_type=True,
                                 ridrejtimet=0)
        assert status == 302 and lidhja.return_value.request.call_count == 1
        pergjigjja.status = 429
        status, _, _ = _shkarko(GDELT, "api.gdeltproject.org", 100, me_content_type=True,
                                 ridrejtimet=0, me_trupin_e_gabimit=True)
        assert status == 429 and not pergjigjja.read.called
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
