"""correlator.py - Bashkon artikujt që flasin për të njëjtën ngjarje dhe gjen boshllëqet.

Rregullat (pa model):
- Dy artikuj = e njëjta ngjarje nëse kanë të njëjtin lloj, datat bien brenda 1 dite,
  dhe përmbledhjet e tyre ngjajnë. Dy vende të njohura duhet të përputhen.
- Burimet e pavarura numërohen sipas mediumit: "GDELT:telegrafi.com" = "Telegrafi".
- Besueshmëria NUK llogaritet këtu (do e bëjë scoring.py); këtu vetëm boshllëqet.
- K3: çdo ngjarje merr kategorinë, aktorin, shenjestrat dhe lidhjen me FSK-në nga artikujt e
  saj; artikujt e shënuar "relevante": false nuk bëhen ngjarje.
"""
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime

import db
import kercenimet

# Koordinata të përafërta të komunave/vendeve (emri pa diakritikë -> lat, lon).
# Shqip dhe serbisht, që të njihen të dyja format.
VENDET = {
    ("prishtin", "pristin", "pristina"): (42.663, 21.165),
    ("mitrovic", "mitrovica"): (42.891, 20.866),
    ("peje", "peja", "pec", "peć"): (42.659, 20.288),
    ("prizren",): (42.213, 20.739),
    ("gjakov", "djakovic", "dakovic"): (42.381, 20.431),
    ("ferizaj", "urosevac"): (42.370, 21.155),
    ("gjilan", "gnjilan"): (42.464, 21.469),
    ("vushtrri", "vucitrn"): (42.823, 20.968),
    ("podujev",): (42.911, 21.193),
    ("zvecan",): (42.908, 20.840),
    ("leposavi",): (43.104, 20.803),
    ("zubin potok",): (42.914, 20.689),
    ("gracanic",): (42.600, 21.193),
    ("shterpc", "strpc"): (42.240, 21.025),
    ("fushe kosov", "kosovo polje"): (42.636, 21.093),
    ("lipjan", "lipljan"): (42.522, 21.125),
    ("obiliq", "obilic"): (42.687, 21.077),
    ("drenas", "glogovac"): (42.627, 20.893),
    ("skenderaj", "srbica"): (42.747, 20.789),
    ("malishev", "malisev"): (42.483, 20.746),
    ("rahovec", "orahovac"): (42.399, 20.654),
    ("suharek", "suva reka"): (42.359, 20.825),
    ("kacanik",): (42.232, 21.258),
    ("decan", "decani"): (42.540, 20.288),
    ("istog",): (42.781, 20.488),
    ("klin", "kline", "klina", "klines", "klinen", "klini"): (42.621, 20.578),
    ("dragash", "dragas"): (42.062, 20.653),
    ("kamenic",): (42.578, 21.580),
    ("viti", "vitina"): (42.322, 21.358),
    ("novoberd", "novo brdo"): (42.616, 21.433),
    ("shtime", "stimlje"): (42.433, 21.040),
    ("hani i elezit", "elez han"): (42.150, 21.297),
    ("junik",): (42.476, 20.278),
    ("jarinj", "jarinje"): (43.133, 20.805),
    ("banjsk",): (42.997, 20.775),
    ("bernjak", "brnjak"): (42.870, 20.580),
    # Rajonet në FUND: kontrollohen vetëm nëse s'u gjet komunë ("Mitrovicë e Veriut" -> mitrovic)
    ("veri", "north kosov", "northern kosov", "sever kosov", "severn"): (42.95, 20.75),
}
RAJONET = {"veri"}  # emrat kanonikë që janë rajon, jo komunë

# Qytetet kryesore të vendeve fqinje (shqip, serbisht, anglisht; pa diakritikë).
# Përputhen vetëm si fjalë e plotë, që "nis" të mos gjendet brenda "danish".
# Edhe rasa lokative serbe ("u Preševu"), përveç atyre që janë fjalë të zakonshme
# ("nisu", "plavu", "tirani").
RAJONI = {
    ("beograd", "belgrade", "beogradi", "beogradit", "beogradu"): (44.787, 20.457),
    ("novi pazar", "novi pazari", "novi pazarit", "novom pazaru"): (43.137, 20.512),
    ("raska", "rashke", "rashka", "raski"): (43.286, 20.616),
    ("kursumlija", "kurshumli", "kurshumlija", "kurshumlia", "kursumliji"): (43.141, 21.271),
    ("presevo", "presheve", "presheva", "preshevo", "presheves", "presevu"): (42.309, 21.649),
    ("bujanovac", "bujanoc", "bujanocit", "bujanovci", "bujanovcu"): (42.461, 21.767),
    ("medvedja", "medvegje", "medvegja", "medvegjes", "medvedji"): (42.843, 21.585),
    ("tutin", "tutinu"): (42.990, 20.337),
    ("nis", "nish", "nishi", "nishit"): (43.320, 21.896),
    ("tirane", "tirana", "tiranes"): (41.327, 19.819),
    ("kukes", "kukesi", "kukesit"): (42.077, 20.421),
    ("shkoder", "shkodra", "shkodres", "skadar"): (42.068, 19.512),
    ("shkup", "shkupi", "shkupit", "skopje", "skoplje", "skoplju"): (41.998, 21.425),
    ("kumanovo", "kumanove", "kumanova", "kumanovu"): (42.132, 21.714),
    ("tetove", "tetovo", "tetova", "tetoves", "tetovu"): (42.010, 20.971),
    ("podgorica", "podgorice", "podgorices", "podgorici"): (42.441, 19.263),
    ("rozaje", "rozhaje", "rozhaja"): (42.840, 20.167),
    ("plav", "plave", "plaves"): (42.597, 19.945),
}

# Serbishtja cirilike -> latinisht (pa diakritikë, si pjesa tjetër: ж -> z, ч -> c)
CIRILIK = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ђ": "dj", "е": "e", "ж": "z",
    "з": "z", "и": "i", "ј": "j", "к": "k", "л": "l", "љ": "lj", "м": "m", "н": "n",
    "њ": "nj", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "ћ": "c", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "c", "џ": "dz", "ш": "s",
})

# Domeni i GDELT -> emri i mediumit, që të mos numërohet dy herë. Emri duhet të jetë IDENTIK me
# çelësin te collector.FEEDS, ndryshe i njëjti medium numërohet dy herë dhe fryn besueshmërinë.
DOMENET = {
    "rtklive.com": "RTK", "koha.net": "Koha", "kallxo.com": "Kallxo",
    "telegrafi.com": "Telegrafi", "gazetaexpress.com": "Gazeta Express",
    "n1info.rs": "N1 Serbia", "balkaninsight.com": "Balkan Insight",
    # K6: burimet e reja (e njëjta listë si te collector.py i B-së)
    "kosovo-online.com": "Kosovo Online", "kossev.info": "KoSSev",
    "rts.rs": "RTS", "novosti.rs": "Novosti",
    "informer.rs": "Informer", "danas.rs": "Danas",
    "slobodnaevropa.org": "RSE", "hibrid.info": "Hibrid.info",
    "kosovopolice.com": "Policia e Kosovës", "mod.gov.rs": "MO Srbije",
    # opsionale (të verifikuara nga kërkimi; s'bëjnë dëm edhe nëse B s'i shton te FEEDS)
    "b92.net": "B92", "blic.rs": "Blic", "kurir.rs": "Kurir", "evropaelire.org": "Evropa e Lirë",
    "prishtinainsight.com": "Prishtina Insight", "reporteri.net": "Reporteri",
    "president-ksgov.net": "Presidenca e Kosovës", "srbija.gov.rs": "Vlada Srbije",
    "istinomer.rs": "Istinomer",
}

# shortcut: kategoria për JSON-et e vjetër (para K2) nga "type"; për këto 5 lloje zëvendëson
# LLOJI_RB të rreziku.py. Hiqe kur të gjithë artikujt të jenë rinxjerrë me taksoninë.
LLOJI_NE_KATEGORI = {"cyber": "kibernetik", "disinformation": "dezinformim",
                     "infrastructure_disruption": "infrastrukture_kritike",
                     "border_incident": "kufi_kontrabande", "protest_unrest": "trazira_bllokada"}


def pa_diakritike(s):
    s = s.lower().translate(CIRILIK) if isinstance(s, str) else ""  # "Звечан" -> "zvecan"
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).replace("đ", "dj")


def gjej_vendin(vendi):
    """Kthen (emri_kanonik, lat, lon) ose (None, None, None) nëse vendi s'njihet.
    Radha: komunat e Kosovës, qytetet fqinje, pastaj rajoni "veri" i Kosovës."""
    v = pa_diakritike(vendi)
    for emrat, (lat, lon) in VENDET.items():
        if emrat[0] in RAJONET:
            continue
        # Klina duhet të dalë si fjalë e plotë; "klinika" nuk e identifikon komunën.
        perputhet = any(re.search(rf"\b{re.escape(e)}\b", v) for e in emrat) if emrat[0] == "klin" else any(
            e in v for e in emrat)
        if perputhet:
            return emrat[0], lat, lon
    for emrat, (lat, lon) in RAJONI.items():
        if any(re.search(rf"\b{re.escape(e)}\b", v) for e in emrat):
            return emrat[0], lat, lon
    # Rajoni vetëm kur përmendet Kosova: "Maqedonia e Veriut" s'është veriu i Kosovës
    for emrat, (lat, lon) in VENDET.items():
        if emrat[0] in RAJONET and "kosov" in v and any(e in v for e in emrat):
            return emrat[0], lat, lon
    return None, None, None


def mediumi(burimi):
    """Emri i mediumit; njeh edhe nëndomenet ("GDELT:sr.n1info.rs" = "N1 Serbia")."""
    if burimi.startswith("GDELT:"):
        d = burimi[6:].lower().removeprefix("www.")
        return next((m for dom, m in DOMENET.items() if d == dom or d.endswith("." + dom)), d)
    return burimi


def merret(j):
    """A bëhet artikulli pjesë e një ngjarjeje? Ngjarje sigurie (edhe rajonale), jo e palidhur."""
    return isinstance(j, dict) and j.get("is_security_event") is True and j.get("relevante", True) is not False


def kategoria_e(j):
    """Kategoria e artikullit nga K2; për JSON-et e vjetër pa të, nga "type"."""
    k = j.get("kategoria")
    if isinstance(k, str) and kercenimet.kategoria_valide(k):
        return k
    lloji = j.get("type")
    return LLOJI_NE_KATEGORI.get(lloji, "tjeter") if isinstance(lloji, str) else "tjeter"


def agrego(grup):
    """K3: kategoria dhe aktori më të shpeshtë (pa "tjeter"/"i_panjohur"; barazimi sipas radhës
    te kercenimet.py), bashkimi i shenjestrave dhe lidhja me FSK-në."""
    kat = Counter(a["kategoria"] for a in grup if a["kategoria"] != "tjeter")
    akt = Counter(a.get("aktori") for a in grup
                  if a.get("aktori") in kercenimet.AKTORET and a.get("aktori") != "i_panjohur")
    rk, ra = list(kercenimet.KATEGORITE), list(kercenimet.AKTORET)
    shenjestrat = {s for a in grup for s in a.get("shenjestrat") or []}
    return {
        "kategoria": min(kat, key=lambda k: (-kat[k], rk.index(k))) if kat else "tjeter",
        "aktori": min(akt, key=lambda x: (-akt[x], ra.index(x))) if akt else "i_panjohur",
        "shenjestrat": [s for s in kercenimet.SHENJESTRAT if s in shenjestrat],
        "lidhje_me_fsk": any(a.get("lidhje_me_fsk") is True for a in grup),
    }


def rendit_burimet(urls, vendimet):
    """URL-ja me vendim analisti del e para, që vendimi të mbetet te burimet[0] edhe kur rigrupimi
    sjell një artikull më të hershëm. Sort i qëndrueshëm: të tjerat mbeten sipas datës."""
    return sorted(urls, key=lambda u: u not in vendimet)


# Fjalë që dalin pothuajse në çdo përmbledhje; s'tregojnë që dy ngjarje janë e njëjta
TE_PERGJITHSHME = {"kosovo", "kosova", "police", "court", "person", "individuals", "officer",
                   "were", "was", "with", "from", "that", "this", "their", "have", "been",
                   "after", "about", "into", "over", "they", "which"}


def fjalet(s):
    return {w for w in re.findall(r"[a-z]{4,}", pa_diakritike(s))} - TE_PERGJITHSHME


def ngjashmeri(a, b):
    """Jaccard i fjalëve të përmbledhjeve (0..1)."""
    fa, fb = fjalet(a), fjalet(b)
    return len(fa & fb) / len(fa | fb) if fa and fb else 0.0


def dita(s):
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def perputhen(grup, art):
    """A i përket artikulli këtij grupi? Krahasohet me artikullin e parë të grupit."""
    g = grup[0]
    if g["rajonale"] != art["rajonale"]:  # ngjarje jashtë Kosovës s'bashkohet me një brenda
        return False
    dita_grupit, dita_artikullit = dita(g["dita"]), dita(art["dita"])
    if (g["type"] != art["type"] or not dita_grupit or not dita_artikullit
            or abs((dita_grupit - dita_artikullit).days) > 1):
        return False
    # I njëjti vend nuk mjafton (në Prishtinë ndodhin shumë gjëra në një ditë),
    # duhet edhe pak ngjashmëri në përmbledhje
    sim = ngjashmeri(g["summary"], art["summary"])
    if g["vendi"] and art["vendi"]:
        return g["vendi"] == art["vendi"] and sim >= 0.15
    return sim >= 0.35


RENDI_VENDIT = {"village": 3, "municipality": 2, "region": 1}


def saktesia_vendit(grup):
    """Saktësia më e mirë në grup. Rregull: nëse vendi u gjet si rajon, s'mund të jetë më mirë."""
    if grup[0]["vendi"] in RAJONET:
        return "region"
    vlerat = [p for a in grup if isinstance(p := a.get("place_precision"), str) and p in RENDI_VENDIT]
    if not vlerat and grup[0]["vendi"]:
        return "municipality"  # vendi u njoh nga lista e komunave
    return max(vlerat, key=RENDI_VENDIT.get) if vlerat else None


def saktesia_dates(grup):
    """'exact' nëse të paktën një burim jep ditën e saktë."""
    vlerat = {a.get("date_precision") for a in grup}
    return "exact" if "exact" in vlerat else "approximate" if "approximate" in vlerat else None


def boshllequet(grup):
    """Lista e boshllëqeve për analistin (rregulla të qarta)."""
    b = []
    mediat = {a["mediumi"] for a in grup}
    if len(mediat) == 1:
        b.append("vetëm një burim")
    if len({a["gjuha"] for a in grup}) == 1:
        b.append("vetëm një gjuhë")
    if not grup[0]["vendi"]:
        b.append("vendi i panjohur ose jashtë listës")
    if all(a["data_nga_publikimi"] for a in grup):
        b.append("data e ngjarjes nga data e publikimit")
    if saktesia_vendit(grup) == "region":
        b.append("vendi vetëm në nivel rajoni")
    if saktesia_dates(grup) == "approximate":
        b.append("data e përafërt")
    datat_e_raportuara = {a["dita"] for a in grup if not a["data_nga_publikimi"]}
    if len(datat_e_raportuara) > 1:
        b.append("datat e raportuara ndryshojnë: " + ", ".join(sorted(datat_e_raportuara)))
    for k, emri in (("killed", "të vdekurve"), ("injured", "të plagosurve"), ("arrested", "të arrestuarve")):
        vlerat = {a[k] for a in grup if a[k] is not None}
        if len(vlerat) > 1:
            b.append(f"numri i {emri} ndryshon: {sorted(vlerat)}")
    return b


def korrelo():
    """Rindërton tabelën events nga artikujt e nxjerrë. Kthen numrin e ngjarjeve."""
    artikujt, te_pavlefshem = [], 0
    for r in db.artikuj_te_nxjerre():
        try:
            j = json.loads(r["rezultati_json"])
        except (ValueError, TypeError):
            te_pavlefshem += 1
            continue
        if not isinstance(j, dict):
            te_pavlefshem += 1
            continue
        # Mbahen të gjitha ngjarjet e sigurisë (ato jashtë Kosovës si rajonale), pa të palidhurat
        if not merret(j):
            continue
        dita_e_raportuar = dita(j.get("event_date"))
        data = dita_e_raportuar or dita(r["data"])
        if not data:
            te_pavlefshem += 1
            continue
        saktesia_e_dates = j.get("date_precision")
        vendi, lat, lon = gjej_vendin(j.get("place"))
        artikujt.append({
            **j, "url": r["url"], "gjuha": r["gjuha"], "mediumi": mediumi(r["burimi"]),
            "rajonale": not j.get("in_kosovo"), "kategoria": kategoria_e(j),
            "dita": data.isoformat(), "data_nga_publikimi": not dita_e_raportuar,
            "date_precision": saktesia_e_dates if dita_e_raportuar and saktesia_e_dates in ("exact", "approximate") else None,
            "vendi": vendi, "vendi_tekst": j.get("place") if isinstance(j.get("place"), str) else None,
            "lat": lat, "lon": lon,
            "type": j.get("type") if isinstance(j.get("type"), str) else "other",
            "summary": j.get("summary") if isinstance(j.get("summary"), str) else "",
            "aktori": j.get("aktori") if isinstance(j.get("aktori"), str) else None,
            **{k: [x for x in j[k] if isinstance(x, str)] if isinstance(j.get(k), list) else []
               for k in ("actors", "shenjestrat")},
            **{k: j[k] if type(j.get(k)) is int and j[k] >= 0 else None
               for k in ("killed", "injured", "arrested")},
        })
    if te_pavlefshem:
        print(f"Korrelimi la jashtë {te_pavlefshem} artikuj me rezultat ose datë të pavlefshme.")

    grupet = []
    for a in artikujt:  # të renditur sipas datës
        for g in grupet:
            if perputhen(g, a):
                g.append(a)
                break
        else:
            grupet.append([a])

    vendimet = db.vendimet()
    ngjarjet = []
    for g in grupet:
        p = g[0]
        burimi_i_dates = max(g, key=lambda a: (a["date_precision"] == "exact",
                                               a["date_precision"] == "approximate",
                                               not a["data_nga_publikimi"]))
        ngjarjet.append(dict(
            titulli=p["summary"] or "(pa përmbledhje)", data=burimi_i_dates["dita"], gjuha=p["gjuha"],
            burimet=rendit_burimet([a["url"] for a in g], vendimet), boshllequet=boshllequet(g),
            lloji=p["type"], vendi=p["vendi_tekst"], lat=p["lat"], lon=p["lon"],
            detajet={
                "rajonale": p["rajonale"],  # True = ngjarja ndodhi jashtë Kosovës
                "mediat": sorted({a["mediumi"] for a in g}),
                "gjuhet": sorted({a["gjuha"] for a in g}),
                "aktoret": sorted({x for a in g for x in a.get("actors") or []}),
                "saktesia_vendit": saktesia_vendit(g),
                "saktesia_dates": saktesia_dates(g),
                **{k: [a[k] for a in g] for k in ("killed", "injured", "arrested")},
                **agrego(g),  # K3: kategoria, aktori, shenjestrat, lidhje_me_fsk
            },
        ))
    db.zevendeso_ngjarjet(ngjarjet)
    return len(grupet)


if __name__ == "__main__":
    # Kontroll i vogël i rregullave
    # Cirilikja tani njihet
    assert gjej_vendin("Северна Митровица")[0] == "mitrovic"
    assert gjej_vendin("Звечан")[0] == "zvecan"
    assert gjej_vendin("Београд") == ("beograd", 44.787, 20.457)
    assert gjej_vendin("Прешево")[0] == "presevo"
    assert gjej_vendin("код полицијске станице у Прешеву")[0] == "presevo"
    assert gjej_vendin("nisu znali")[0] is None  # "nisu" = "nuk ishin", jo Nish
    assert pa_diakritike("Ђаковица, Љубљана, Њујорк, Џеп") == "djakovica, ljubljana, njujork, dzep"
    # Çdo variant i qyteteve fqinje gjen qytetin e vet (asnjë komunë e Kosovës s'e "vjedh")
    for emrat in RAJONI:
        for e in emrat:
            assert gjej_vendin(e)[0] == emrat[0], (e, gjej_vendin(e))
    assert gjej_vendin("Preševo, Serbia")[0] == "presevo"
    assert gjej_vendin("Medveđa")[0] == "medvedja"
    assert gjej_vendin("Niš")[0] == "nis" and gjej_vendin("Nish, Serbi")[0] == "nis"
    # Emrat e shkurtër vetëm si fjalë e plotë
    assert gjej_vendin("Danish embassy")[0] is None      # "nis" brenda "danish"
    assert gjej_vendin("plavi most")[0] is None           # "plav" brenda "plavi"
    assert gjej_vendin("Tutinovo naselje")[0] is None     # "tutin" brenda "tutinovo"
    assert gjej_vendin("policia nisi hetimin")[0] is None  # "nis" brenda "nisi"
    # "Veriu" i një shteti tjetër s'është veriu i Kosovës
    assert gjej_vendin("Tetovë, Maqedonia e Veriut")[0] == "tetove"
    assert gjej_vendin("Kumanovo, Северна Македонија")[0] == "kumanovo"
    assert gjej_vendin("Maqedonia e Veriut")[0] is None
    assert gjej_vendin("veriu i Kosovës")[0] == "veri"
    assert gjej_vendin("Mitrovicë e Veriut")[0] == "mitrovic"
    assert gjej_vendin("Peć")[0] == "peje"
    assert gjej_vendin("në Klinë")[0] == "klin" and gjej_vendin("Qendra Klinike Universitare")[0] is None
    assert mediumi("GDELT:www.telegrafi.com") == "Telegrafi"
    assert gjej_vendin("North Kosovo")[0] == "veri"
    assert gjej_vendin("Mitrovicë e Veriut")[0] == "mitrovic"  # komuna fiton mbi rajonin
    assert saktesia_vendit([{"vendi": "veri", "place_precision": "village"}]) == "region"
    assert saktesia_vendit([{"vendi": "peje", "place_precision": None}]) == "municipality"
    assert saktesia_dates([{"date_precision": "approximate"}, {"date_precision": "exact"}]) == "exact"
    # Rajonale dhe në Kosovë nuk bashkohen kurrë, edhe kur gjithçka tjetër përputhet
    a = {"type": "police_military_operation", "dita": "2026-11-16", "vendi": None,
         "summary": "army drills near the administrative boundary line", "rajonale": True}
    assert perputhen([a], dict(a))
    assert not perputhen([a], {**a, "rajonale": False})
    assert not perputhen([{**a, "rajonale": False}], a)
    # DOMENET: çdo emër vetëm një herë (rreziku.py e kthen së prapthi); nëndomenet njihen
    assert len(set(DOMENET.values())) == len(DOMENET)
    assert mediumi("GDELT:sr.n1info.rs") == "N1 Serbia" and mediumi("GDELT:www.kossev.info") == "KoSSev"
    assert mediumi("GDELT:jon1info.rs") == "jon1info.rs" and mediumi("Telegram:x") == "Telegram:x"
    # K3: artikujt e palidhur s'bëhen ngjarje; relevante që mungon = e lidhur
    assert merret({"is_security_event": True}) and not merret({"is_security_event": False})
    assert not merret({"is_security_event": True, "relevante": False})
    assert not merret({"is_security_event": "false"}) and not merret(None)
    # K3: barazimi sipas radhës te kercenimet, "i_panjohur" s'numërohet, JSON i vjetër nga "type"
    assert kategoria_e({"type": "border_incident"}) == "kufi_kontrabande"
    assert kategoria_e({"type": "murder"}) == "tjeter"
    assert kategoria_e({"kategoria": "tjeter", "type": "cyber"}) == "tjeter"  # K2 e dha "tjeter"
    g = [{"kategoria": kategoria_e({"type": "cyber"}), "aktori": "i_panjohur", "shenjestrat": ["institucione"]},
         {"kategoria": "dezinformim", "aktori": "rusia", "shenjestrat": ["fsk"], "lidhje_me_fsk": True},
         {"kategoria": "tjeter"}]
    assert agrego(g) == {"kategoria": "kibernetik", "aktori": "rusia",
                         "shenjestrat": ["fsk", "institucione"], "lidhje_me_fsk": True}, agrego(g)
    assert agrego([{"kategoria": "tjeter"}]) == {"kategoria": "tjeter", "aktori": "i_panjohur",
                                                 "shenjestrat": [], "lidhje_me_fsk": False}
    # Vendimi i analistit mbetet te burimet[0] edhe kur rigrupimi sjell artikull më të hershëm
    assert rendit_burimet(["u1", "u2"], {"u2": {"statusi": "e konfirmuar"}}) == ["u2", "u1"]
    assert rendit_burimet(["u1", "u2"], {}) == ["u1", "u2"]
    print(f"U krijuan {korrelo()} ngjarje.")
    # Ngjarjet rindërtohen nga e para, ndaj besueshmëria rillogaritet menjëherë
    import scoring
    print(f"U vlerësuan {scoring.vlereso_te_gjitha()} ngjarje.")
