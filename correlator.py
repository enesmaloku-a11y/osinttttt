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
}

# Domeni i GDELT -> emri i mediumit, që të mos numërohet dy herë
DOMENET = {
    "rtklive.com": "RTK", "koha.net": "Koha", "kallxo.com": "Kallxo",
    "telegrafi.com": "Telegrafi", "gazetaexpress.com": "Gazeta Express",
    "n1info.rs": "N1 Serbia", "balkaninsight.com": "Balkan Insight",
}


def pa_diakritike(s):
    s = unicodedata.normalize("NFKD", s or "").lower()
    return "".join(c for c in s if not unicodedata.combining(c)).replace("đ", "dj")


def gjej_vendin(vendi):
    """Kthen (emri_kanonik, lat, lon) ose (None, None, None) nëse vendi s'njihet."""
    v = pa_diakritike(vendi)
    for emrat, (lat, lon) in VENDET.items():
        if any(e in v for e in emrat):
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
    """A i përket artikulli këtij grupi? Krahasohet me artikullin e parë të grupit."""
    g = grup[0]
    if g["type"] != art["type"] or abs((dita(g["dita"]) - dita(art["dita"])).days) > 1:
        return False
    # I njëjti vend nuk mjafton (në Prishtinë ndodhin shumë gjëra në një ditë),
    # duhet edhe pak ngjashmëri në përmbledhje
    sim = ngjashmeri(g["summary"], art["summary"])
    if g["vendi"] and art["vendi"]:
        return g["vendi"] == art["vendi"] and sim >= 0.15
    return sim >= 0.35


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
        if not (j.get("is_security_event") and j.get("in_kosovo")):
            continue
        vendi, lat, lon = gjej_vendin(j.get("place"))
        artikujt.append({
            **j, "url": r["url"], "gjuha": r["gjuha"], "mediumi": mediumi(r["burimi"]),
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
                "mediat": sorted({a["mediumi"] for a in g}),
                "gjuhet": sorted({a["gjuha"] for a in g}),
                "aktoret": sorted({x for a in g for x in a.get("actors") or []}),
                **{k: [a[k] for a in g] for k in ("killed", "injured", "arrested")},
            },
        )
    return len(grupet)


if __name__ == "__main__":
    # Kontroll i vogël i rregullave
    assert gjej_vendin("Северна Митровица")[0] is None  # cirilikja s'njihet (boshllëk)
    assert gjej_vendin("Mitrovicë e Veriut")[0] == "mitrovic"
    assert gjej_vendin("Peć")[0] == "peje"
    assert mediumi("GDELT:www.telegrafi.com") == "Telegrafi"
    print(f"U krijuan {korrelo()} ngjarje.")
    # Ngjarjet rindërtohen nga e para, ndaj besueshmëria rillogaritet menjëherë
    import scoring
    print(f"U vlerësuan {scoring.vlereso_te_gjitha()} ngjarje.")
