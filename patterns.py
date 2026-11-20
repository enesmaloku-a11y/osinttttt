"""patterns.py - Zbulon rritje të pazakonta të ngjarjeve sipas komunës (me rregulla, pa model).

Rregulli:
- "këtë javë" = 7 ditët e fundit (deri te 'sot', përfshirë).
- "mesatarja" = ngjarjet në 28 ditët para tyre / 4 (mesatare javore), me dysheme 0.5
  që një ngjarje e vetme pas heshtjes të mos duket si "rritje pafund".
- Alarm nëse këtë javë ka >= 3 ngjarje DHE >= 2 herë mesataren.
"""
from collections import Counter
from datetime import datetime, timedelta

import db
from correlator import gjej_vendin

MIN_NGJARJE = 3
HERE_MESATARJA = 2.0
DYSHEMEJA = 0.5


def dita(s):
    return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()


def histori_e_mjaftueshme(fillimi_mbledhjes, sot):
    """Mesatarja ka kuptim vetëm nëse kemi mbledhur lajme gjatë gjithë 5 javëve."""
    return dita(fillimi_mbledhjes) <= dita(sot) - timedelta(days=6 + 28)


def rritjet(ngjarjet, sot=None, fillimi_mbledhjes=None):
    """ngjarjet: lista me fusha 'data' dhe 'vendi'. Kthen alarmet, më i forti i pari.
    fillimi_mbledhjes: kur filloi mbledhja; pa 5 javë histori s'ka alarm (mesatarja s'dihet)."""
    ngjarjet = [e for e in ngjarjet if e["data"]]
    if not ngjarjet:
        return []
    sot = dita(sot) if sot else max(dita(e["data"]) for e in ngjarjet)
    if fillimi_mbledhjes and not histori_e_mjaftueshme(fillimi_mbledhjes, sot):
        return []
    fillimi_javes = sot - timedelta(days=6)
    fillimi_bazes = fillimi_javes - timedelta(days=28)

    kete_jave, baza, emrat = Counter(), Counter(), {}
    for e in ngjarjet:
        # "Mitrovicë e Veriut" dhe "Mitrovica" = një komunë (vendi mund të mungojë / NaN nga pandas)
        teksti = e["vendi"] if isinstance(e["vendi"], str) else ""
        vendi = gjej_vendin(teksti)[0]
        if not vendi:
            continue
        emrat.setdefault(vendi, Counter())[teksti] += 1  # emri më i shpeshtë, për shfaqje
        d = dita(e["data"])
        if fillimi_javes <= d <= sot:
            kete_jave[vendi] += 1
        elif fillimi_bazes <= d < fillimi_javes:
            baza[vendi] += 1

    alarmet = []
    for vendi, n in kete_jave.items():
        mesatarja = max(baza[vendi] / 4, DYSHEMEJA)
        if n >= MIN_NGJARJE and n >= HERE_MESATARJA * mesatarja:
            alarmet.append({"vendi": vendi, "emri": emrat[vendi].most_common(1)[0][0],
                            "kete_jave": n, "mesatarja": mesatarja,
                            "raporti": round(n / mesatarja, 1)})
    return sorted(alarmet, key=lambda a: -a["raporti"])


def pershkrim(a):
    return (f"Rritje e pazakontë në {a['emri']}: {a['kete_jave']} ngjarje këtë javë, "
            f"mesatarja {a['mesatarja']:.1f} në javë ({a['raporti']}x)")


if __name__ == "__main__":
    # Kontrolle me të dhëna sintetike
    def ngj(d, v):
        return {"data": d, "vendi": v}
    # Mitrovicë: 1 në javë për 4 javë, pastaj 5 këtë javë -> alarm (5 >= 2 x 1)
    test = [ngj(f"2026-10-{d:02d}", "Mitrovica") for d in (20, 27)] + \
           [ngj(f"2026-11-{d:02d}", "Mitrovicë e Veriut") for d in (3, 10, 15, 16, 17, 18, 19)] + \
           [ngj("2026-11-19", "Prishtina")] * 2 + \
           [ngj(f"2026-11-{d:02d}", "Peja") for d in (1, 2, 4, 5, 6, 7, 8, 9, 15, 16, 17)]
    a = rritjet(test, "2026-11-19")
    assert [x["vendi"] for x in a] == ["mitrovic"], a  # Prishtina ka vetëm 2; Peja s'është rritje
    assert a[0]["kete_jave"] == 5 and a[0]["mesatarja"] == 1.0, a  # baza: 4 ngjarje / 4 javë
    # Pas heshtjes: 3 ngjarje pa asnjë më parë -> dyshemeja 0.5, raporti 6
    a = rritjet([ngj("2026-11-19", "Gjilan")] * 3)
    assert a[0]["mesatarja"] == 0.5 and a[0]["raporti"] == 6.0, a
    assert rritjet([]) == []
    # Pa 5 javë histori mbledhjeje s'ka alarm, edhe kur numrat duken si rritje
    assert rritjet([ngj("2026-11-19", "Gjilan")] * 3, fillimi_mbledhjes="2026-11-01") == []
    assert rritjet([ngj("2026-11-19", "Gjilan")] * 3, fillimi_mbledhjes="2026-10-01")

    fillimi = db.fillimi_i_mbledhjes()
    alarmet = rritjet(db.ngjarjet(), fillimi_mbledhjes=fillimi)
    print("\n".join(pershkrim(x) for x in alarmet) or
          f"S'ka rritje të pazakonta (mbledhja filloi më {str(fillimi)[:10]}).")
