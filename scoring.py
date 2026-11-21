"""Besueshmëria nga modeli i trajnuar ose nga rregullat fillestare.

besueshmëria = 0.40 * burimet e pavarura
             + 0.35 * besueshmëria e mediave
             + 0.25 * përputhja e detajeve
Çdo pjesë është 0..1, dhe arsyetimi ruhet që analisti ta shohë.
"""
import json
import math
from pathlib import Path

from vektori import EMRAT, vektori

import db

MODELI = Path("data/modeli_besueshmerise.json")
PERSHKRIMET = dict(zip(EMRAT, ("media të pavarura", "gjuhë", "artikuj", "besueshmëria e mediave",
    "konflikte në detaje", "vend i saktë", "datë e saktë", "aktor institucional i përmendur",
    "orë mes artikujve", "rast i ngjashëm nga EUvsDisinfo")))


def numer(x):
    return type(x) in (float, int) and math.isfinite(x)


def lexo_modelin(shteg):
    try:
        m = json.loads(shteg.read_text(encoding="utf-8"))
        emrat = m["veçoritë"]
        if (type(m["versioni"]) is not int or m["versioni"] != 1 or not isinstance(emrat, list)
                or not emrat or len(set(emrat)) != len(emrat) or not set(emrat) <= set(EMRAT)
                or not numer(m["intercepti"]) or type(m["n"]) is not int or m["n"] <= 0):
            return None
        for k in ("mesatarja", "devijimi", "koeficientet"):
            if not isinstance(m[k], list) or len(m[k]) != len(emrat) or not all(map(numer, m[k])):
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
    v = vektori(e)
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
    det.update(metoda="model", arsyetimi=arsyet)
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
    "Kosovo Online": 0.6, "KoSSev": 0.6, "Novosti": 0.6, "Danas": 0.6,
}
E_PANJOHUR = 0.4  # çdo domen tjetër nga GDELT
E_PLATFORME = 0.3


def pike_burimesh(mediat, gjuhet):
    """1 medium = 0.33, 2 = 0.67, 3+ = 1.0. Bonus nëse raportojnë media në gjuhë të ndryshme."""
    p = min(len(mediat), 3) / 3
    if len(gjuhet) > 1:
        p = min(1.0, p + 0.15)
    return p


def besueshmeria_e_mediumit(emri) -> float:
    if emri.startswith(("Telegram:", "YouTube:")):
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
    gjuhet = det.get("gjuhet") or []
    b = pike_burimesh(mediat, gjuhet)
    m = pike_mediash(mediat)
    d, konflikte = pike_detajesh(det, len(mediat))
    pike = round(PESHAT["burimet"] * b + PESHAT["mediat"] * m + PESHAT["detajet"] * d, 2)
    arsyet = [
        f"burime të pavarura: {len(mediat)} ({', '.join(mediat)}), gjuhë: {len(gjuhet)} -> {b:.2f}",
        f"besueshmëria e mediave -> {m:.2f}",
        ("detajet: s'mund të krahasohen (një burim)" if len(mediat) < 2 else
         f"detajet: {'kontradikta te ' + ', '.join(konflikte) if konflikte else 'përputhen'}")
        + f" -> {d:.2f}",
    ]
    return pike, arsyet


def vlereso_te_gjitha():
    """Llogarit besueshmërinë për çdo ngjarje në bazë. Kthen numrin e ngjarjeve."""
    ngjarjet = db.ngjarjet()
    modeli = lexo_modelin(MODELI)
    for e in ngjarjet:
        det = json.loads(e["detajet_json"] or "{}")
        pike = vlereso_ngjarjen(e, det, modeli)
        db.ruaj_besueshmerine(e["id"], pike, det)
    return len(ngjarjet)


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
        shteg = Path(dosja) / "model.json"
        det = {"mediat": ["Telegrafi"], "gjuhet": ["sq"]}
        e = {"detajet_json": json.dumps(det)}
        assert vlereso_ngjarjen(e, det, lexo_modelin(shteg)) == nje
        model = {"versioni": 1, "n": 100, "veçoritë": ["n_mediat"], "mesatarja": [0],
                 "devijimi": [1], "koeficientet": [math.log(3)], "intercepti": 0,
                 "metrikat": {"logjistik": {"precision_080": None}}}
        shteg.write_text(json.dumps(model), encoding="utf-8")
        assert math.isclose(vlereso_ngjarjen(e, det, lexo_modelin(shteg)), .75)
        shteg.write_text("{", encoding="utf-8")
        assert vlereso_ngjarjen(e, det, lexo_modelin(shteg)) == nje and det["metoda"] == "rregulla"
    print(f"Shembuj: 1 burim {nje}, 2 burime me kontradiktë {kontra}, 2 në pajtim {pajtim}, 3 burime {tre}")
    print(f"U vlerësuan {vlereso_te_gjitha()} ngjarje.")
