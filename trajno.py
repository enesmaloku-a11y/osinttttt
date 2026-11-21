"""Trajnon dhe vlerëson probabilitetin e konfirmimit nga analisti."""
import json
import os
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

import db
from scoring import MODELI, vlereso
from vektori import EMRAT, vektori

# Konteksti shtohet pas vlerësimit, ndaj kjo veçori mungon gjatë parashikimit.
VECORITE = [k for k in EMRAT if k != "ka_rast_euvsdisinfo"]


def te_dhenat():
    with closing(db.lidhu()) as lidhja:
        rreshtat = lidhja.execute("""
            SELECT e.*, v.statusi, v.url_kryesor FROM events e JOIN vendimet v
            ON v.url_kryesor = json_extract(e.burimet, '$[0]')
            WHERE v.statusi IN ('e konfirmuar', 'e hedhur poshtë') ORDER BY e.id DESC
        """).fetchall()
    pare, x, y, rregullat = set(), [], [], []
    for e in rreshtat:
        if e["url_kryesor"] in pare:
            continue
        pare.add(e["url_kryesor"])
        veçorite = vektori(e)
        x.append([veçorite[k] for k in VECORITE])
        y.append(int(e["statusi"] == "e konfirmuar"))
        rregullat.append(vlereso(json.loads(e["detajet_json"] or "{}"))[0])
    return x, y, rregullat


def trajno_logjistiken(x, y):
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    baze = make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced"))
    brenda = StratifiedKFold(4, shuffle=True, random_state=41)
    # Çdo pikë për kalibrimin vjen nga një model që s'e ka parë atë etiketë.
    piket = cross_val_predict(baze, x, y, cv=brenda, method="decision_function")
    kal = LogisticRegression().fit(piket.reshape(-1, 1), y)
    baze.fit(x, y)
    shkalla, reg = baze.steps[0][1], baze.steps[1][1]
    faktor = kal.coef_[0, 0]
    return {"mesatarja": shkalla.mean_.tolist(), "devijimi": shkalla.scale_.tolist(),
            "koeficientet": (reg.coef_[0] * faktor).tolist(),
            "intercepti": float(reg.intercept_[0] * faktor + kal.intercept_[0])}


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
    x, y, rregullat = te_dhenat()
    n, poz = len(y), sum(y)
    neg = n - poz
    print(f"Vendime: {n}, të konfirmuara: {poz}, të hedhura poshtë: {neg}.")
    if n < 80 or min(poz, neg) < 20:
        print(f"Mungojnë për minimumin: gjithsej {max(0,80-n)}, pozitive {max(0,20-poz)}, negative {max(0,20-neg)}.")
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
    modeli = dict(versioni=1, trajnuar_me=datetime.now(timezone.utc).isoformat(),
                  n=n, n_pozitive=poz, metrikat=metrikat, **trajno_logjistiken(x, y))
    modeli["veçoritë"] = VECORITE
    raport = {"metrikat": metrikat, "n": n, "n_pozitive": poz, "pragu_i_rekomanduar": prag,
              "n_mbi_prag": int((log >= prag).sum()) if prag is not None else 0,
              "peshat": dict(zip(VECORITE, modeli["koeficientet"], strict=True)),
              "rekomandim": "Shqyrtoni pemët." if metrikat["peme"]["auc"] >= metrikat["logjistik"]["auc"] + .05
              else "Mbani regresionin logjistik."}
    ruaj(MODELI.with_name("raporti_modelit.json"), raport)
    ruaj(MODELI, modeli)
    for emer, m in metrikat.items():
        print(f"{emer}: AUC {m['auc']:.3f}, Brier {m['brier']:.3f}, precision@80 {m['precision_080']}, recall@80 {m['recall_080']:.3f}")
    print(f"Pragu me precision ≥90% në vlerësim: {prag}. {raport['rekomandim']}")
    return 0


if __name__ == "__main__":
    assert "ka_rast_euvsdisinfo" not in VECORITE and set(VECORITE) < set(EMRAT)
    raise SystemExit(trajno())

