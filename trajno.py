"""Trajnon dhe vlerëson probabilitetin e konfirmimit nga analisti."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

import db
from scoring import (MIN_ETIKETA, MIN_KLASA, MODELI, VERSIONI_MODELit, modeli_kalon,
                     pasuro_burimet, vlereso)
from vektori import EMRAT, vektori

# Mbetet jashtë që modeli të përdorë të njëjtat veçori në trajnim dhe zbatim.
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


def mat(y, p):
    import numpy as np
    from sklearn.metrics import brier_score_loss, roc_auc_score

    p = np.asarray(p)
    zgjedhur = p >= 0.80
    grupe = []
    indeksi = np.minimum((p * 5).astype(int), 4)
    for i in range(5):
        m = indeksi == i
        grupe.append({"nga": i / 5, "deri": (i + 1) / 5, "n": int(m.sum()),
                      "parashikuar": float(p[m].mean()) if m.any() else None,
                      "konfirmuar": float(y[m].mean()) if m.any() else None})
    return {"auc": float(roc_auc_score(y, p)), "brier": float(brier_score_loss(y, p)),
            "precision_080": float(y[zgjedhur].mean()) if zgjedhur.any() else None,
            "recall_080": float(y[zgjedhur].sum() / y.sum()), "n_080": int(zgjedhur.sum()),
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


def trajno():
    from collections import Counter

    numrat = Counter(v["statusi"] for v in db.vendimet().values())
    for status in db.STATUSET:
        print(f"{status}: {numrat[status]}")
    x, y, rregullat = te_dhenat()
    n, poz = len(y), sum(y)
    neg = n - poz
    print(f"Vendime: {n}, të konfirmuara: {poz}, të hedhura poshtë: {neg}.")
    if n < MIN_ETIKETA or min(poz, neg) < MIN_KLASA:
        print(f"Mungojnë për minimumin: gjithsej {max(0,MIN_ETIKETA-n)}, "
              f"pozitive {max(0,MIN_KLASA-poz)}, negative {max(0,MIN_KLASA-neg)}.")
        print("Nuk u trajnua. Besueshmëria mbetet te rregullat.")
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
    kalon = modeli_kalon(metrikat)
    rekomandim = (f"Regresioni logjistik e kaloi pragun kundrejt rregullave me {n} etiketa."
                  if kalon else f"Me {n} etiketa modeli logjistik s'i kaloi rregullat sipas pragut të vendimit.")
    raport = {"metrikat": metrikat, "n": n, "n_pozitive": poz, "pragu_i_rekomanduar": prag,
              "n_mbi_prag": int((log >= prag).sum()) if prag is not None else 0,
              "peshat": dict(zip(VECORITE, modeli["koeficientet"], strict=True)),
              "rekomandim": rekomandim, "modeli_aktiv": kalon,
              "kufizim": "Etiketuesit e kanë parë vlerësimin e besueshmërisë në ekran."}
    ruaj(MODELI.with_name("raporti_modelit.json"), raport)
    if kalon:
        ruaj(MODELI, modeli)
    else:
        MODELI.unlink(missing_ok=True)
    for emer, m in metrikat.items():
        print(f"{emer}: AUC {m['auc']:.3f}, Brier {m['brier']:.3f}, precision@80 {m['precision_080']}, recall@80 {m['recall_080']:.3f}")
    print(f"Pragu me precision ≥90% në vlerësim: {prag}. {raport['rekomandim']}")
    return 0


if __name__ == "__main__":
    assert "ka_rast_euvsdisinfo" not in VECORITE and set(VECORITE) < set(EMRAT)
    raise SystemExit(trajno())

