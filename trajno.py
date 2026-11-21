"""Trajnon dhe vlerëson probabilitetin e konfirmimit nga analisti."""
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

import db
from scoring import (MIN_ETIKETA, MIN_KLASA, MODELI, VERSIONI_MODELit, modeli_kalon,
                     pasuro_burimet, vlereso)
from vektori import EMRAT, vektori

# shortcut: konteksti EUvsDisinfo mbetet jashtë që skema e trajnimit dhe e zbatimit të jetë e njëjtë.
VECORITE = [k for k in EMRAT if k != "ka_rast_euvsdisinfo"]


def te_dhenat():
    vendimet = db.vendimet()
    rreshtat = sorted(db.ngjarjet(), key=lambda e: e["id"], reverse=True)
    pare, x, y, rregullat = set(), [], [], []
    for e in rreshtat:
        urls = json.loads(e["burimet"] or "[]")
        if not urls or any(u.startswith("gold://") for u in urls):
            continue
        celesi = db.url_i_vendimit(urls, vendimet)
        statusi = vendimet.get(celesi, {}).get("statusi")
        if celesi in pare or statusi not in ("e konfirmuar", "e hedhur poshtë"):
            continue
        pare.add(celesi)
        det = json.loads(e["detajet_json"] or "{}")
        pasuro_burimet(e, det)
        veçorite = vektori(e, det=det)
        x.append([veçorite[k] for k in VECORITE])
        y.append(int(statusi == "e konfirmuar"))
        rregullat.append(vlereso(det)[0])
    return x, y, rregullat


def trajno_logjistiken(x, y):
    from sklearn.linear_model import LogisticRegression
    import numpy as np
    from sklearn.model_selection import StratifiedKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    def pershtat(te_dhenat, etiketat):
        baze = make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced"))
        baze.fit(te_dhenat, etiketat)
        shkalla, reg = baze.steps[0][1], baze.steps[1][1]
        peshat, intercepti = reg.coef_[0].copy(), float(reg.intercept_[0])
        i = VECORITE.index("n_kopje")
        # Një kopje shtesë nuk krijon provë. Ruaj vlerën te 0 kopje kur pesha hiqet.
        if peshat[i] > 0:
            intercepti -= peshat[i] * shkalla.mean_[i] / shkalla.scale_[i]
            peshat[i] = 0
        return shkalla, peshat, intercepti

    brenda = StratifiedKFold(4, shuffle=True, random_state=41)
    # Çdo pikë për kalibrimin vjen nga një model që s'e ka parë atë etiketë.
    piket = np.empty(len(y))
    for mesim, prove in brenda.split(x, y):
        shkalla, peshat, intercepti = pershtat(x[mesim], y[mesim])
        piket[prove] = shkalla.transform(x[prove]) @ peshat + intercepti
    kal = LogisticRegression().fit(piket.reshape(-1, 1), y)
    shkalla, peshat, intercepti = pershtat(x, y)
    faktor = max(0.0, kal.coef_[0, 0])
    baze_kalibruar = (float(kal.intercept_[0]) if faktor else
                      float(np.log(y.mean() / (1 - y.mean()))))
    return {"mesatarja": shkalla.mean_.tolist(), "devijimi": shkalla.scale_.tolist(),
            "koeficientet": (peshat * faktor).tolist(),
            "intercepti": float(intercepti * faktor + baze_kalibruar)}


def intervali_wilson95(sakte, n):
    """Interval besimi për precision. Pa parashikime mbi prag nuk ka interval."""
    if not n:
        return None
    z = 1.959963984540054
    p = sakte / n
    emertuesi = 1 + z**2 / n
    qendra = (p + z**2 / (2 * n)) / emertuesi
    gjysma = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / emertuesi
    return {"poshte": qendra - gjysma if sakte else 0.0,
            "lart": qendra + gjysma if sakte < n else 1.0}


def mat(y, p):
    import numpy as np
    from sklearn.metrics import brier_score_loss, roc_auc_score

    y, p = np.asarray(y), np.asarray(p)
    zgjedhur = p >= 0.80
    n_080, sakte = int(zgjedhur.sum()), int(y[zgjedhur].sum())
    grupe = []
    indeksi = np.minimum((p * 5).astype(int), 4)
    for i in range(5):
        m = indeksi == i
        grupe.append({"nga": i / 5, "deri": (i + 1) / 5, "n": int(m.sum()),
                      "parashikuar": float(p[m].mean()) if m.any() else None,
                      "konfirmuar": float(y[m].mean()) if m.any() else None})
    return {"auc": float(roc_auc_score(y, p)), "brier": float(brier_score_loss(y, p)),
            "precision_080": sakte / n_080 if n_080 else None,
            "precision_080_wilson_95": intervali_wilson95(sakte, n_080),
            "recall_080": float(sakte / y.sum()), "n_080": n_080,
            "kalibrimi": grupe}


def ruaj(shteg, permbajtja):
    shteg.parent.mkdir(exist_ok=True)
    with NamedTemporaryFile("w", dir=shteg.parent, encoding="utf-8", delete=False) as f:
        emer = Path(f.name)
        try:
            json.dump(permbajtja, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.close()
            os.replace(emer, shteg)
        finally:
            f.close()
            emer.unlink(missing_ok=True)


def raporti_modelit(modeli, prag, n_mbi_prag, n_pakonfirmuara, ver_korrelatori):
    n, poz, metrikat = modeli["n"], modeli["n_pozitive"], modeli["metrikat"]
    kalon = modeli_kalon(metrikat)
    rekomandim = (f"Mbani regresionin logjistik. Kaloi pragun kundrejt rregullave me {n} etiketa."
                  if kalon else f"Mbani rregullat. Me {n} etiketa logjistiku nuk e kaloi pragun e vendimit.")
    return {
        "metrikat": metrikat, "n": n, "n_pozitive": poz, "n_negative": n - poz,
        "n_pakonfirmuara": n_pakonfirmuara, "pragu_i_rekomanduar": prag, "n_mbi_prag": n_mbi_prag,
        "peshat": dict(zip(modeli["veçoritë"], modeli["koeficientet"], strict=True)),
        "rekomandim": rekomandim, "modeli_aktiv": kalon, "versioni_korrelatorit": ver_korrelatori,
        "kufizimet": [
            "Etiketat vijnë nga analistët. Shikimi i pikës në ekran mund të ketë ndikuar vendimet.",
            "Vlerësimi mbulon vetëm ngjarjet e etiketuara. Mbulimi i burimeve të reja duhet kontrolluar veçmas.",
            "Veçoria EUvsDisinfo është përjashtuar nga trajnimi dhe parashikimi.",
            f"Versioni i korrelatorit që prodhoi ngjarjet: {ver_korrelatori}.",
            "Pragu ≥90% u zgjodh mbi parashikimet jashtë ndarjeve të trajnimit. Kërkon verifikim të pavarur.",
        ],
    }


def ploteson_minimumin(n, poz):
    return n >= MIN_ETIKETA and min(poz, n - poz) >= MIN_KLASA


def trajno():
    from collections import Counter

    numrat = Counter(v["statusi"] for v in db.vendimet().values())
    for status in db.STATUSET:
        print(f"{status}: {numrat[status]}")
    x, y, rregullat = te_dhenat()
    n, poz = len(y), sum(y)
    neg = n - poz
    print(f"Vendime: {n}, të konfirmuara: {poz}, të hedhura poshtë: {neg}.")
    if not ploteson_minimumin(n, poz):
        print(f"Mungojnë për minimumin: gjithsej {max(0,MIN_ETIKETA-n)}, "
              f"pozitive {max(0,MIN_KLASA-poz)}, negative {max(0,MIN_KLASA-neg)}.")
        print("Nuk u trajnua. Nuk u prodhua model ose raport i ri.")
        if MODELI.is_file():
            print("Modeli ekzistues mbeti siç ishte. Rishikojeni para përdorimit me këtë bazë.")
        return 1

    import numpy as np
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.model_selection import StratifiedKFold
    from scoring import probabiliteti

    x, y = np.array(x), np.array(y)
    log, peme = np.zeros(n), np.zeros(n)
    for mesim, prove in StratifiedKFold(5, shuffle=True, random_state=42).split(x, y):
        parametrat = trajno_logjistiken(x[mesim], y[mesim])
        log[prove] = [probabiliteti(parametrat, r)[0] for r in x[prove]]
        krahasim = HistGradientBoostingClassifier(random_state=42).fit(x[mesim], y[mesim])
        peme[prove] = krahasim.predict_proba(x[prove])[:, 1]
    metrikat = {emer: mat(y, p) for emer, p in
                (("logjistik", log), ("peme", peme), ("rregulla", rregullat))}
    prag = next((float(t) for t in np.unique(log) if y[log >= t].mean() >= .90), None)
    modeli = dict(versioni=VERSIONI_MODELit, trajnuar_me=datetime.now(timezone.utc).isoformat(),
                  n=n, n_pozitive=poz, metrikat=metrikat, **trajno_logjistiken(x, y))
    modeli["veçoritë"] = VECORITE
    n_mbi_prag = int((log >= prag).sum()) if prag is not None else 0
    ver_korrelatori = os.environ.get("OSINT_VERSION_KORRELATORIT", "").strip() or "i padokumentuar"
    raport = raporti_modelit(modeli, prag, n_mbi_prag, numrat["e pakonfirmuar"], ver_korrelatori)
    ruaj(MODELI.with_name("raporti_modelit.json"), raport)
    if raport["modeli_aktiv"]:
        ruaj(MODELI, modeli)
    else:
        MODELI.unlink(missing_ok=True)
    for emer, m in metrikat.items():
        print(f"{emer}: AUC {m['auc']:.3f}, Brier {m['brier']:.3f}, precision@80 {m['precision_080']}, "
              f"n_080 {m['n_080']}, Wilson 95% {m['precision_080_wilson_95']}, recall@80 {m['recall_080']:.3f}")
    print(f"Pragu me precision >=90% në vlerësim: {prag}. {raport['rekomandim']}")
    return 0


def kontrollo():
    import contextlib
    import io
    from tempfile import TemporaryDirectory
    from unittest.mock import patch

    assert "ka_rast_euvsdisinfo" not in VECORITE and set(VECORITE) < set(EMRAT)
    assert ploteson_minimumin(80, 20) and ploteson_minimumin(80, 60)
    assert not ploteson_minimumin(79, 40)
    assert not ploteson_minimumin(80, 19) and not ploteson_minimumin(80, 61)
    assert intervali_wilson95(0, 0) is None
    assert intervali_wilson95(0, 10)["poshte"] == 0 and intervali_wilson95(10, 10)["lart"] == 1
    intervali = intervali_wilson95(8, 10)
    assert math.isclose(intervali["poshte"], .49016, abs_tol=1e-5)
    assert math.isclose(intervali["lart"], .94332, abs_tol=1e-5)
    matja = mat([1, 0, 1, 0], [.9, .8, .7, .1])
    assert matja["precision_080"] == matja["recall_080"] == .5 and matja["n_080"] == 2
    assert len(matja["kalibrimi"]) == 5 and sum(g["n"] for g in matja["kalibrimi"]) == 4
    bosh = mat([1, 0], [.7, .2])
    assert bosh["precision_080"] is None and bosh["precision_080_wilson_95"] is None
    assert bosh["n_080"] == bosh["recall_080"] == 0
    model = {"n": 80, "n_pozitive": 30, "veçoritë": ["n_mediat"], "koeficientet": [0],
             "metrikat": {"logjistik": dict(matja, auc=.83, brier=.15), "peme": matja,
                          "rregulla": dict(matja, auc=.80, brier=.15)}}
    raport = raporti_modelit(model, .9, 5, 2, "prove")
    assert raport["n_negative"] == 50 and raport["n_pakonfirmuara"] == 2 and raport["n_mbi_prag"] == 5
    assert raport["modeli_aktiv"] and raport["rekomandim"].startswith("Mbani regresionin logjistik")
    assert len(raport["kufizimet"]) >= 4 and raport["versioni_korrelatorit"] == "prove"
    model["metrikat"]["logjistik"]["brier"] = .16
    assert not raporti_modelit(model, None, 0, 0, "prove")["modeli_aktiv"]
    with TemporaryDirectory() as dosja:
        shteg = Path(dosja) / "model.json"
        for etiketa in ([], [1] * 40 + [0] * 39, [1] * 19 + [0] * 61, [1] * 61 + [0] * 19):
            with (patch(__name__ + ".MODELI", shteg),
                  patch(__name__ + ".te_dhenat", return_value=([], etiketa, [])),
                  patch.object(db, "vendimet", return_value={}), contextlib.redirect_stdout(io.StringIO())):
                assert trajno() == 1 and not list(Path(dosja).iterdir())
    print("Kontrollet e metrikave, Wilson dhe portës së modelit kaluan.")


if __name__ == "__main__":
    assert "ka_rast_euvsdisinfo" not in VECORITE and set(VECORITE) < set(EMRAT)
    if "--kontrollo" in sys.argv:
        kontrollo()
    else:
        raise SystemExit(trajno())

