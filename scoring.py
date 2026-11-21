"""Besueshmëria nga modeli i trajnuar ose nga rregullat fillestare.

besueshmëria = 0.40 * burimet e pavarura
             + 0.35 * besueshmëria e mediave
             + 0.25 * përputhja e detajeve
Çdo pjesë është 0..1, dhe arsyetimi ruhet që analisti ta shohë.
"""
import json
import math
import re
import unicodedata
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from vektori import EMRAT, vektori

import db

MODELI = Path("data/modeli_besueshmerise.json")
VERSIONI_MODELit = 2  # V1 i trajtonte ripostimet si raportime të pavarura.
MIN_ETIKETA, MIN_KLASA, MIN_RRITJA_AUC = 80, 20, 0.03
PERSHKRIMET = dict(zip(EMRAT, ("media të pavarura", "gjuhë", "artikuj", "besueshmëria e mediave",
    "konflikte në detaje", "vend i saktë", "datë e saktë", "aktor institucional i përmendur",
    "orë mes artikujve", "rast i ngjashëm nga EUvsDisinfo", "kopje të identifikuara")))


def modeli_kalon(metrikat):
    """Porta për regresionin logjistik që scoring mund ta lexojë nga JSON."""
    log, rreg = metrikat["logjistik"], metrikat["rregulla"]
    return (log["auc"] - rreg["auc"] + 1e-12 >= MIN_RRITJA_AUC
            and log["brier"] <= rreg["brier"])


def numer(x):
    return type(x) in (float, int) and math.isfinite(x)


def lexo_modelin(shteg):
    try:
        m = json.loads(shteg.read_text(encoding="utf-8"))
        emrat = m["veçoritë"]
        n, poz = m["n"], m["n_pozitive"]
        if (type(m["versioni"]) is not int or m["versioni"] != VERSIONI_MODELit
                or not isinstance(emrat, list) or len(set(emrat)) != len(emrat)
                or set(emrat) != set(EMRAT) - {"ka_rast_euvsdisinfo"}
                or not numer(m["intercepti"]) or type(n) is not int or type(poz) is not int
                or n < MIN_ETIKETA or min(poz, n - poz) < MIN_KLASA):
            return None
        metrikat = m["metrikat"]
        if not all(numer(v) and 0 <= v <= 1 for k in ("logjistik", "rregulla")
                   for v in (metrikat[k]["auc"], metrikat[k]["brier"])) or not modeli_kalon(metrikat):
            return None
        for k in ("mesatarja", "devijimi", "koeficientet"):
            if not isinstance(m[k], list) or len(m[k]) != len(emrat) or not all(map(numer, m[k])):
                return None
        if m["koeficientet"][emrat.index("n_kopje")] > 0:
            return None
        prec = m["metrikat"]["logjistik"]["precision_080"]
        if min(m["devijimi"]) <= 0 or (prec is not None and not (numer(prec) and 0 <= prec <= 1)):
            return None
        return m
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return None


def probabiliteti(m, vlera):
    pjeset = [float(k) * ((float(x) - a) / s) for x, a, s, k in
              zip(vlera, m["mesatarja"], m["devijimi"], m["koeficientet"], strict=True)]
    z = math.fsum([m["intercepti"], *pjeset])
    if not math.isfinite(z):
        raise ValueError("Rezultat i pafundëm")
    t = math.exp(-abs(z))
    return (1 / (1 + t) if z >= 0 else t / (1 + t)), pjeset


def vlereso_ngjarjen(e, det, modeli):
    p, arsye = vlereso(det)
    det.update(pike_rregullash=p, metoda="rregulla", arsyetimi=arsye)
    if modeli is None:
        return p
    v = vektori(e, det=det)
    emrat = modeli["veçoritë"]
    try:
        p_model, pjese = probabiliteti(modeli, [v[k] for k in emrat])
    except (ValueError, OverflowError):
        return p
    arsyet = []
    for k, vl in sorted(zip(emrat, pjese), key=lambda çift: -abs(çift[1]))[:3]:
        drejtimi = "rrit" if vl > 0 else "ul" if vl < 0 else "neutral"
        arsyet.append(f"{PERSHKRIMET[k]} ({v[k]:g}) → {drejtimi}")
    prec = modeli["metrikat"]["logjistik"]["precision_080"]
    matja = (f"{prec:.1%} e ngjarjeve me ≥80% u konfirmuan" if prec is not None
             else "asnjë ngjarje nuk arriti pragun 80%")
    arsyet.append(f"Modeli u trajnua mbi {modeli['n']} vendime. Në test, {matja}.")
    det.update(metoda="model", arsyetimi=[*arsye[:1], *arsyet])
    return p_model

PESHAT = {"burimet": 0.40, "mediat": 0.35, "detajet": 0.25}

# Besueshmëria e mediave (0..1). Vlerë fillestare: duhet ta caktojë/rishikojë analisti.
MEDIAT = {
    "Balkan Insight": 0.9, "Kallxo": 0.85, "RTK": 0.8, "Koha": 0.8, "N1 Serbia": 0.8,
    "Telegrafi": 0.6, "Gazeta Express": 0.6,
    # Politikë korrigjimi dhe redaksi: https://hibrid.info/rreth-nesh/ dhe anëtarësi: https://members.efcsn.com/organization/action-for-democratic-society-ads-hibrid-info
    "Hibrid.info": 0.8,
    # Burim zyrtar i palës për veprimet e veta: https://www.kosovopolice.com/
    "Policia e Kosovës": 0.7,
    # Bazë e rubrikës. Pikët për korrigjime dhe anëtarësi mbeten të paverifikuara.
    "RTS": 0.6,
    # Pikë fillestare për burime të reja; vlerë fillestare, jo e matur.
    "Kosovo Online": 0.6, "KoSSev": 0.6, "Novosti": 0.6, "Danas": 0.6, "RSE": 0.6,
    "Informer": 0.6,
    # Burim zyrtar i palës serbe: i dobishëm për veprimet e veta, jo për pretendimet për Kosovën.
    "MO Srbije": 0.6,
}
E_PANJOHUR = 0.4  # çdo domen tjetër nga GDELT
E_PLATFORME = 0.3
SOCIALE = ("Telegram:", "YouTube:")
# Pesë fjalë ruajnë radhën dhe ulin përputhjet nga emrat ose temat e përbashkëta.
PRAG_TEKST, PRAG_PERKTHIM, PRAG_CITIM = 0.60, 0.50, 0.30
CITIM = r"sipas|prenosi|javlja|prema pisanju|according to|citing|reported by"
EMRAT_E_CITIMIT = {"Koha": ("kohes", "kohe", "koha ditore"),
                  "N1 Serbia": ("n1",), "Policia e Kosovës": ("kosovo police",)}


def _normalizo(teksti):
    dekompozuar = unicodedata.normalize("NFKD", (teksti or "").casefold())
    return " ".join(re.findall(r"[^\W_]+", "".join(c for c in dekompozuar
                    if not unicodedata.combining(c))))


def _shingle(teksti):
    fjalet = teksti.split()
    return set(zip(fjalet, fjalet[1:], fjalet[2:], fjalet[3:], fjalet[4:]))


def _containment(a, b):
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


def _data(dita):
    try:
        dt = datetime.fromisoformat(dita)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return datetime.max.replace(tzinfo=timezone.utc)


def _po_citon(teksti, mediumi):
    emrat = {_normalizo(mediumi), *EMRAT_E_CITIMIT.get(mediumi, ())} - {""}
    if not emrat:
        return False
    emri = "|".join(re.escape(e) for e in sorted(emrat))
    return bool(re.search(rf"\b(?:(?:{CITIM})(?: portalit| portala| portal)? (?:{emri})"
                          rf"|(?:{emri}) (?:prenosi|javlja))\b", teksti))


def _arsye_kopjeje(a, b):
    tekst = _containment(a["origjinal"], b["origjinal"])
    if tekst >= PRAG_TEKST:
        return f"tekst {tekst:.2f}"
    perkthim = _containment(a["anglisht"], b["anglisht"])
    if a["gjuha"] and b["gjuha"] and a["gjuha"] != b["gjuha"] and perkthim >= PRAG_PERKTHIM:
        return f"përkthim {perkthim:.2f}"
    if a["koha"] < b["koha"] and max(tekst, perkthim) >= PRAG_CITIM and _po_citon(b["tekst"], a["mediumi"]):
        return f"citim i {a['mediumi']}"
    return None


def _grupet_burimeve(urlt):
    if not urlt:
        return [], []
    from correlator import mediumi
    with closing(db.lidhu()) as con:
        rreshtat = con.execute("""
            SELECT url, burimi, data, gjuha, COALESCE(NULLIF(TRIM(raw_text), ''), teksti) AS bruto,
                   teksti_perkthyer, titulli
            FROM articles WHERE url IN (SELECT value FROM json_each(?))
        """, (json.dumps(list(urlt)),)).fetchall()

    artikujt = []
    for r in rreshtat:
        a = dict(r)
        a["koha"] = _data(a["data"])
        a["mediumi"] = mediumi(a["burimi"])
        a["tekst"] = _normalizo(a["bruto"])
        a["origjinal"] = _shingle(a["tekst"])
        a["anglisht"] = _shingle(_normalizo(a["teksti_perkthyer"] or (a["bruto"] if a["gjuha"] == "en" else "")))
        artikujt.append(a)
    artikujt.sort(key=lambda a: (a["koha"], a["url"]))

    prindi = list(range(len(artikujt)))
    lidhjet = [{} for _ in artikujt]

    def rrenja(i):
        while i != prindi[i]:
            prindi[i] = prindi[prindi[i]]
            i = prindi[i]
        return i

    for i, a in enumerate(artikujt):
        for j in range(i + 1, len(artikujt)):
            arsye = _arsye_kopjeje(a, artikujt[j])
            if arsye:
                x, y = rrenja(i), rrenja(j)
                prindi[max(x, y)] = min(x, y)  # Indeksi më i vogël ka datën më të hershme.
                lidhjet[i][j] = lidhjet[j][i] = arsye

    hapi_drejt_origjines = {}
    for i in range(len(artikujt)):
        if rrenja(i) != i:
            continue
        hapi_drejt_origjines[i] = i
        nyjet = [i]
        for nyje in nyjet:
            for fqinj in lidhjet[nyje]:
                if fqinj not in hapi_drejt_origjines:
                    hapi_drejt_origjines[fqinj] = nyje
                    nyjet.append(fqinj)

    origjinat, kopjet, pare = [], [], set()
    for i, a in enumerate(artikujt):
        r = rrenja(i)
        if r == i:
            kanal = "sociale" if a["mediumi"].startswith(SOCIALE) else a["mediumi"]
            if kanal not in pare:
                pare.add(kanal)
                origjinat.append(a)
            continue
        arsye = lidhjet[i].get(r)
        if arsye is None:
            fqinj = hapi_drejt_origjines[i]
            arsye = f"{lidhjet[i][fqinj]} përmes {artikujt[fqinj]['mediumi']}"
        kopjet.append({"url": a["url"], "kopje_e": artikujt[r]["url"], "arsyeja": arsye})
    return origjinat, kopjet


def burimet_e_pavarura(urlt):
    """Kthen numrin e origjinave të pavarura dhe listën e ripostimeve."""
    origjinat, kopjet = _grupet_burimeve(urlt)
    return len(origjinat), kopjet


def pasuro_burimet(e, det):
    urls = json.loads(e["burimet"] or "[]")
    origjinat, kopjet = _grupet_burimeve(urls)
    if origjinat:
        mediat = [a["mediumi"] for a in origjinat]
        gjuhet = sorted({a["gjuha"] for a in origjinat if a["gjuha"]})
        urls = [a["url"] for a in origjinat]
    else:
        # Ngjarjet e vjetra pa artikuj në DB ruajnë pikëzimin e mëparshëm.
        mediat, gjuhet = det.get("mediat") or [], det.get("gjuhet") or []
    det.update(burime_te_pavarura=len(mediat), kopjet=kopjet,
               mediat_e_pavarura=mediat, gjuhet_e_pavarura=gjuhet, urlt_e_pavarura=urls)


def pike_burimesh(mediat, gjuhet, *, n_burime=None):
    """1 medium = 0.33, 2 = 0.67, 3+ = 1.0. Bonus nëse raportojnë media në gjuhë të ndryshme."""
    n = len(mediat) if n_burime is None else n_burime
    p = min(n, 3) / 3
    if len(gjuhet) > 1 and (n_burime is None or n > 1):
        p = min(1.0, p + 0.15)
    return p


def besueshmeria_e_mediumit(emri) -> float:
    if emri.startswith(SOCIALE):
        return E_PLATFORME
    return MEDIAT.get(emri, E_PANJOHUR)


def pike_mediash(mediat):
    """Mesatarja e besueshmërisë së mediave që raportojnë."""
    return sum(besueshmeria_e_mediumit(m) for m in mediat) / len(mediat)


def pike_detajesh(det, n_burime):
    """1.0 kur detajet përputhen; -0.3 për çdo numër kontradiktor.
    Me një burim të vetëm s'ka çfarë të krahasohet -> 0.5."""
    if n_burime < 2:
        return 0.5, []
    konflikte = [k for k in ("killed", "injured", "arrested")
                 if len({v for v in det.get(k, []) if v is not None}) > 1]
    return max(0.0, 1.0 - 0.3 * len(konflikte)), konflikte


def vlereso(det):
    """Kthen (besueshmëria 0..1, lista e arsyeve) për detajet e një ngjarjeje."""
    mediat = det.get("mediat") or []
    if not mediat:
        return 0.0, ["s'ka burime"]
    n = det.get("burime_te_pavarura", len(mediat))
    gjuhet = det.get("gjuhet_e_pavarura", det.get("gjuhet")) or []
    mediat_baze = det.get("mediat_e_pavarura", mediat) or mediat
    b = pike_burimesh(mediat, gjuhet, n_burime=n if "burime_te_pavarura" in det else None)
    m = pike_mediash(mediat_baze)
    d, konflikte = pike_detajesh(det, n)
    pike = round(PESHAT["burimet"] * b + PESHAT["mediat"] * m + PESHAT["detajet"] * d, 2)
    arsyet = [
        f"burime të pavarura: {len(mediat)} ({', '.join(mediat)}), gjuhë: {len(gjuhet)} -> {b:.2f}",
        f"besueshmëria e mediave -> {m:.2f}",
        ("detajet: s'mund të krahasohen (një burim)" if len(mediat) < 2 else
         f"detajet: {'kontradikta te ' + ', '.join(konflikte) if konflikte else 'përputhen'}")
        + f" -> {d:.2f}",
    ]
    if "burime_te_pavarura" in det:
        kopjet = det.get("kopjet") or []
        shpjegime = [f"{urlsplit(k['url']).hostname or k['url']} → "
                     f"{urlsplit(k['kopje_e']).hostname or k['kopje_e']} ({k['arsyeja']})" for k in kopjet]
        shtese = f" ({len(kopjet)} kopje: {', '.join(shpjegime)})" if kopjet else ""
        arsyet[0] = f"burime të pavarura: {n} nga {len(mediat)} media{shtese} → {b:.2f}"
    return pike, arsyet


def vlereso_te_gjitha():
    """Llogarit besueshmërinë për çdo ngjarje në bazë. Kthen numrin e ngjarjeve."""
    ngjarjet = db.ngjarjet()
    modeli = lexo_modelin(MODELI)
    for e in ngjarjet:
        det = json.loads(e["detajet_json"] or "{}")
        pasuro_burimet(e, det)
        pike = vlereso_ngjarjen(e, det, modeli)
        db.ruaj_besueshmerine(e["id"], pike, det)
    return len(ngjarjet)


def _kontrollo_ripostimet(dosja):
    sq = ("Komuna publikoi njoftimin për ndërprerjen e shërbimit në zonën qendrore të qytetit. "
          "Ekipet teknike kontrolluan rrjetin gjatë mëngjesit të së premtes. "
          "Ndërprerja u raportua nga operatori rreth orës tetë. Tekniku në detyrë njoftoi "
          "se shërbimi u kthye pas kontrollit. Raporti i plotë pritet të publikohet mbrëmjen e sotme.")
    en = ("The municipality published a notice about the service interruption in the central area of the city. "
          "Technical teams checked the network on Friday morning. The operator reported the interruption "
          "around eight in the morning. The technician on duty said service returned after the inspection. "
          "The complete report is expected to be published this evening.")

    def artikull(emer, medium, gjuha, tekst, ora, perkthim=None):
        url = f"https://{emer}.example.test/lajm"
        dita = f"2026-11-21T{ora:02d}:00:00+00:00"
        db.ruaj_artikull(url, medium, f"Titull {emer}", dita, gjuha, tekst)
        if perkthim:
            with closing(db.lidhu()) as con:
                aid = con.execute("SELECT id FROM articles WHERE url=?", (url,)).fetchone()[0]
            db.ruaj_perkthimin(aid, tekst, perkthim)
        return url

    global MODELI
    db_para, modeli_para = db.DB_PATH, MODELI
    db.DB_PATH, MODELI = str(Path(dosja) / "ripostimet.db"), Path(dosja) / "model-i-pamundur.json"
    try:
        a = artikull("koha", "Koha", "sq", sq, 10, en)
        b = artikull("telegrafi", "Telegrafi", "sq", sq + " Sipas Kohës, njoftimi publikohet sot.", 11, en)
        c = artikull("n1", "N1 Serbia", "sr",
                     "Prema pisanju portala Koha, opština je objavila saopštenje o prekidu usluge.", 12,
                     en + " According to Koha, the inspection is complete.")
        ids = []
        for urls, mediat, gjuhet in (
            ([a], ["Koha"], ["sq"]), ([a, b], ["Koha", "Telegrafi"], ["sq"]),
            ([c, b, a], ["Koha", "Telegrafi", "N1 Serbia"], ["sq", "sr"]),
        ):
            ids.append(db.ruaj_ngjarje("Provë", "2026-11-21", "sq", urls, [],
                                       detajet={"mediat": mediat, "gjuhet": gjuhet}))
        assert vlereso_te_gjitha() == 3
        rows = {e["id"]: e for e in db.ngjarjet()}
        nje, dy, tre = (rows[i]["besueshmeria"] for i in ids)
        assert abs(nje - tre) < .05 and nje == dy, (nje, dy, tre)
        det = json.loads(rows[ids[-1]]["detajet_json"])
        assert det["burime_te_pavarura"] == 1 and len(det["kopjet"]) == 2
        assert {k["kopje_e"] for k in det["kopjet"]} == {a}
        assert [k["arsyeja"].split()[0] for k in det["kopjet"]] == ["tekst", "përkthim"]
        v = vektori(rows[ids[-1]])
        assert v["n_mediat"] == v["n_gjuhet"] == v["n_artikuj"] == 1 and v["n_kopje"] == 2
        assert vlereso({"mediat": ["Koha", "Telegrafi", "N1 Serbia"], "gjuhet": ["sq", "sr"]})[0] == .91

        p = artikull("kallxo", "Kallxo", "sq",
                     "Disa banorë treguan se kishin dëgjuar zhurmë pranë kryqëzimit. Gazetari pa një ekip "
                     "në vend dhe kërkoi dokumentet nga zyrtarët komunalë.", 13)
        assert burimet_e_pavarura([a, p]) == (2, [])
        pa_citim = artikull("sr", "RTS", "sr", "Radovi su završeni posle tehničkog pregleda.", 14, en)
        assert burimet_e_pavarura([a, pa_citim])[1][0]["arsyeja"].startswith("përkthim")
        cite = artikull("rse", "RSE", "sq",
                        "Sipas Kohës. Komuna publikoi njoftimin për ndërprerjen e shërbimit në zonën qendrore të qytetit. "
                        "Ekipet teknike kontrolluan rrjetin gjatë mëngjesit të së premtes. "
                        "Zyrtarët paralajmërojnë se masat aktuale mbeten në fuqi deri ditën e ardhshme "
                        "dhe ekspertët kërkojnë durim ndërkohë që përgatisin një plan rezervë për të gjithë qytetarët. "
                        "Familjet në zona të tjera vijuan punën pa ndonjë pengesë.", 14)
        assert burimet_e_pavarura([a, cite])[1][0]["arsyeja"] == "citim i Koha"
        sh1 = artikull("h1", "RTK", "sq", "Policia e Kosovës arrestoi dy persona në Pejë.", 15)
        sh2 = artikull("h2", "KoSSev", "sq", "Policia e Kosovës arrestoi një person në Prishtinë.", 16)
        bosh = artikull("bosh", "Danas", "sr", "", 17)
        assert burimet_e_pavarura([sh1, sh2, bosh]) == (3, [])
        t = artikull("telegram", "Telegram:provë", "sq", "Një raport ende pa verifikim.", 18)
        y = artikull("youtube", "YouTube:provë", "sq", "Video me datë të panjohur.", 19)
        assert burimet_e_pavarura([a, t, y]) == (2, [])
        assert _shingle(_normalizo("Është një tekst, për të provuar!")) == _shingle("eshte nje tekst per te provuar")
        print(f"Ripostimet: Koha {nje:.0%}, + ripostimi {dy:.0%}, + përkthimi {tre:.0%}. "
              f"n_mediat={v['n_mediat']:g}, n_kopje={v['n_kopje']:g}.")
    finally:
        db.DB_PATH, MODELI = db_para, modeli_para


if __name__ == "__main__":
    # Kontrolle të vogla: më shumë burime/gjuhë => më e besueshme; kontradiktat ulin
    nje, _ = vlereso({"mediat": ["Telegrafi"], "gjuhet": ["sq"]})
    tre, _ = vlereso({"mediat": ["Koha", "N1 Serbia", "Balkan Insight"], "gjuhet": ["sq", "sr", "en"],
                      "killed": [1, 1, 1]})
    kontra, _ = vlereso({"mediat": ["Koha", "N1 Serbia"], "gjuhet": ["sq", "sr"], "killed": [1, 3]})
    pajtim, _ = vlereso({"mediat": ["Koha", "N1 Serbia"], "gjuhet": ["sq", "sr"], "killed": [1, 1]})
    assert nje < pajtim < tre and kontra < pajtim, (nje, kontra, pajtim, tre)
    assert besueshmeria_e_mediumit("Telegram:x") == besueshmeria_e_mediumit("YouTube:y") == 0.3 < E_PANJOHUR
    assert besueshmeria_e_mediumit("RTS") == MEDIAT["RTS"]
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as dosja:
        _kontrollo_ripostimet(dosja)
        shteg = Path(dosja) / "model.json"
        det = {"mediat": ["Telegrafi"], "gjuhet": ["sq"]}
        e = {"detajet_json": json.dumps(det)}
        assert vlereso_ngjarjen(e, det, lexo_modelin(shteg)) == nje
        emrat = [k for k in EMRAT if k != "ka_rast_euvsdisinfo"]
        model = {"versioni": VERSIONI_MODELit, "n": 100, "n_pozitive": 50, "veçoritë": emrat,
                 "mesatarja": [0] * len(emrat), "devijimi": [1] * len(emrat),
                 "koeficientet": [math.log(3) if k == "n_mediat" else 0 for k in emrat], "intercepti": 0,
                 "metrikat": {"logjistik": {"precision_080": None, "auc": .83, "brier": .12},
                              "rregulla": {"auc": .80, "brier": .12}}}
        shteg.write_text(json.dumps(model), encoding="utf-8")
        assert math.isclose(vlereso_ngjarjen(e, det, lexo_modelin(shteg)), .75)
        model["metrikat"]["logjistik"]["brier"] = .13
        shteg.write_text(json.dumps(model), encoding="utf-8")
        assert lexo_modelin(shteg) is None
        shteg.write_text("{", encoding="utf-8")
        assert vlereso_ngjarjen(e, det, lexo_modelin(shteg)) == nje and det["metoda"] == "rregulla"
    print(f"Shembuj: 1 burim {nje}, 2 burime me kontradiktë {kontra}, 2 në pajtim {pajtim}, 3 burime {tre}")
