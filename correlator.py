"""correlator.py - Bashkon artikujt që flasin për të njëjtën ngjarje dhe gjen boshllëqet.

Rregullat (pa model):
- Dy artikuj = e njëjta ngjarje nëse kanë të njëjtin lloj, datat bien brenda 1 dite,
  dhe kanë të njëjtin vend OSE përmbledhje shumë të ngjashme.
- Burimet e pavarura numërohen sipas mediumit: "GDELT:telegrafi.com" = "Telegrafi".
- Besueshmëria NUK llogaritet këtu (do e bëjë scoring.py); këtu vetëm boshllëqet.
"""
import json
import re
import unicodedata
from datetime import datetime

import db

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
    ("klin",): (42.621, 20.578),
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

# Domeni i GDELT -> emri i mediumit, që të mos numërohet dy herë
DOMENET = {
    "rtklive.com": "RTK", "koha.net": "Koha", "kallxo.com": "Kallxo",
    "telegrafi.com": "Telegrafi", "gazetaexpress.com": "Gazeta Express",
    "n1info.rs": "N1 Serbia", "balkaninsight.com": "Balkan Insight",
}


def pa_diakritike(s):
    s = (s or "").lower().translate(CIRILIK)  # cirilikja së pari: "Звечан" -> "zvecan"
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).replace("đ", "dj")


def gjej_vendin(vendi):
    """Kthen (emri_kanonik, lat, lon) ose (None, None, None) nëse vendi s'njihet.
    Radha: komunat e Kosovës, qytetet fqinje, pastaj rajoni "veri" i Kosovës."""
    v = pa_diakritike(vendi)
    for emrat, (lat, lon) in VENDET.items():
        if emrat[0] not in RAJONET and any(e in v for e in emrat):
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
    if burimi.startswith("GDELT:"):
        d = burimi[6:].removeprefix("www.")
        return DOMENET.get(d, d)
    return burimi


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
    return datetime.strptime(s[:10], "%Y-%m-%d")


def perputhen(grup, art):
    """A i përket artikulli këtij grupi? Duhet të përputhet me shumicën e anëtarëve (> gjysma),
    jo vetëm me njërin: A~B dhe B~C s'e bashkojnë C-në me A-në (pa zinxhir tranzitiv).
    Grupet me 1-2 artikuj kërkojnë përputhje me të gjithë."""
    return 2 * sum(perputhen_cift(g, art) for g in grup) > len(grup)


def perputhen_cift(g, art):
    """Rregullat për dy artikuj: lloji, data (±1 ditë), vendi dhe ngjashmëria e përmbledhjes."""
    if g["rajonale"] != art["rajonale"]:  # ngjarje jashtë Kosovës s'bashkohet me një brenda
        return False
    if g["type"] != art["type"] or abs((dita(g["dita"]) - dita(art["dita"])).days) > 1:
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
    vlerat = [a.get("place_precision") for a in grup if a.get("place_precision")]
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
    for k, emri in (("killed", "të vdekurve"), ("injured", "të plagosurve"), ("arrested", "të arrestuarve")):
        vlerat = {a[k] for a in grup if a[k] is not None}
        if len(vlerat) > 1:
            b.append(f"numri i {emri} ndryshon: {sorted(vlerat)}")
    return b


def korrelo():
    """Rindërton tabelën events nga artikujt e nxjerrë. Kthen numrin e ngjarjeve."""
    artikujt = []
    for r in db.artikuj_te_nxjerre():
        j = json.loads(r["rezultati_json"])
        # Mbahen të gjitha ngjarjet e sigurisë; ato jashtë Kosovës shënohen si rajonale
        if not j.get("is_security_event"):
            continue
        vendi, lat, lon = gjej_vendin(j.get("place"))
        artikujt.append({
            **j, "url": r["url"], "gjuha": r["gjuha"], "mediumi": mediumi(r["burimi"]),
            "rajonale": not j.get("in_kosovo"),
            "dita": j.get("event_date") or r["data"][:10],
            "data_nga_publikimi": not j.get("event_date"),
            "vendi": vendi, "vendi_tekst": j.get("place"), "lat": lat, "lon": lon,
        })

    grupet = []
    for a in artikujt:  # të renditur sipas datës
        for g in grupet:
            if perputhen(g, a):
                g.append(a)
                break
        else:
            grupet.append([a])

    db.fshi_ngjarjet()
    for g in grupet:
        p = g[0]
        db.ruaj_ngjarje(
            titulli=p["summary"] or "(pa përmbledhje)", data=p["dita"], gjuha=p["gjuha"],
            burimet=[a["url"] for a in g], boshllequet=boshllequet(g),
            lloji=p["type"], vendi=p["vendi_tekst"], lat=p["lat"], lon=p["lon"],
            detajet={
                "rajonale": p["rajonale"],  # True = ngjarja ndodhi jashtë Kosovës
                "mediat": sorted({a["mediumi"] for a in g}),
                "gjuhet": sorted({a["gjuha"] for a in g}),
                "aktoret": sorted({x for a in g for x in a.get("actors") or []}),
                "saktesia_vendit": saktesia_vendit(g),
                "saktesia_dates": saktesia_dates(g),
                **{k: [a[k] for a in g] for k in ("killed", "injured", "arrested")},
            },
        )
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
    # Pa zinxhir: A~B dhe B~C, por A dhe C janë ngjarje të ndryshme -> C s'hyn te grupi i A-së
    ka = {**a, "rajonale": False, "type": "protest_unrest", "vendi": None}
    A = {**ka, "summary": "farmers protest fuel prices highway"}
    B = {**ka, "summary": "farmers protest fuel prices teachers strike salaries"}
    C = {**ka, "summary": "teachers strike salaries unpaid"}
    assert perputhen([A], B) and perputhen([B], C) and not perputhen([A], C)
    assert not perputhen([A, B], C)
    # Shumica: me 3 anëtarë mjaftojnë 2 përputhje
    assert perputhen([A, B, {**A, "summary": "farmers protest fuel prices block"}], B)
    print(f"U krijuan {korrelo()} ngjarje.")
    # Ngjarjet rindërtohen nga e para, ndaj besueshmëria rillogaritet menjëherë
    import scoring
    print(f"U vlerësuan {scoring.vlereso_te_gjitha()} ngjarje.")
