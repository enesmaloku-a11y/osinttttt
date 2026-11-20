"""eval/evaluate.py - Mat saktësinë e sistemit mbi gold set-in (eval/gold.jsonl).

Nis me:  python eval/evaluate.py

- gold.jsonl ka artikuj SINTETIKË (të shkruar nga ekipi, jo lajme reale) në sq/sr/en,
  me përgjigjen e saktë te "pritet". Në prezantim thuaj qartë që janë sintetikë.
- Kalon të njëjtin pipeline si sistemi: processor -> extractor -> correlator -> scoring.
- Përdor bazë të veçantë eval/eval.db (rikrijohet çdo herë); osint.db nuk preket.
- Kërkon Ollama lokal, si processor.py.
"""
import json
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

DOSJA = Path(__file__).resolve().parent
sys.path.insert(0, str(DOSJA.parent))  # modulet e projektit janë një nivel më lart

import correlator  # noqa: E402
import db  # noqa: E402
import extractor  # noqa: E402
import processor  # noqa: E402
import scoring  # noqa: E402

GOLD = DOSJA / "gold.jsonl"
DB_EVAL = DOSJA / "eval.db"
REZULTATI = DOSJA / "rezultati.json"  # e lexon dashboard-i
# shortcut: supozim për kohën e analistit; zëvendësoje me matje reale nëse e keni
MINUTA_MANUALE = 3


def lexo_gold():
    """Lexon gold set-in dhe kontrollon që çdo rresht ka fushat e duhura."""
    with open(GOLD, encoding="utf-8") as f:
        gold = [json.loads(r) for r in f if r.strip()]
    ids = [g["id"] for g in gold]
    assert len(ids) == len(set(ids)), "id të përsëritura në gold.jsonl"
    for g in gold:
        assert g["gjuha"] in ("sq", "sr", "en"), g["id"]
        assert {"is_security_event", "in_kosovo", "type", "grupi"} <= set(g["pritet"]), g["id"]
    return gold


def url_e(g):
    return f"gold://{g['id']}"


def ekzekuto(gold):
    """Fut gold set-in në eval.db dhe kalon pipeline-in.
    Kthen ({id: JSON i extractor}, [[id, ...] për çdo ngjarje], sekonda, info).
    info["rajonale"]: për çdo ngjarje, flamuri "rajonale" që vendosi correlator.py."""
    if DB_EVAL.exists():
        DB_EVAL.unlink()
    db.DB_PATH = str(DB_EVAL)
    for g in gold:
        db.ruaj_artikull(url=url_e(g), burimi=g["burimi"], titulli=g["titulli"],
                         data=g["data"], gjuha=g["gjuha"], teksti=g["teksti"])

    n = len(gold)
    t0 = time.time()
    _, gabime_perkthimi = processor.perpuno(n)
    _, filtruar, gabime_nxjerrje, _ = extractor.perpuno(n)
    correlator.korrelo()
    scoring.vlereso_te_gjitha()
    sekonda = time.time() - t0

    id_e = {url_e(g): g["id"] for g in gold}
    rezultatet = {id_e[r["url"]]: json.loads(r["rezultati_json"]) for r in db.artikuj_te_nxjerre()}
    te_gjitha = db.ngjarjet()
    ngjarjet = [[id_e[u] for u in json.loads(e["burimet"])] for e in te_gjitha]
    info = {"filtruar": filtruar, "gabime": gabime_perkthimi + gabime_nxjerrje,
            "rajonale": [json.loads(e["detajet_json"] or "{}").get("rajonale") is True
                         for e in te_gjitha]}
    return rezultatet, ngjarjet, sekonda, info


def pjese(a, b):
    return a / b if b else 0.0


def mat(gold, rezultatet, ngjarjet, rajonale=None):
    """Krahason parashikimet me gold set-in dhe kthen metrikat.
    rezultatet: {id: JSON i extractor.py}; ngjarjet: [[id, ...], ...] nga correlator.py;
    rajonale: [bool, ...] flamuri "rajonale" i çdo ngjarjeje (None = s'kontrollohet)."""
    tp = fp = fn = tn = lloji_ok = kosova_ok = 0
    gjuhet = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    mungojne, alarme, lloji_gabim = [], [], []
    for g in gold:
        p, r = g["pritet"], rezultatet.get(g["id"], {})  # pa rezultat = s'u gjet
        gjet = r.get("is_security_event") is True
        gj = gjuhet[g["gjuha"]]
        if p["is_security_event"] and gjet:
            tp += 1
            gj["tp"] += 1
            if r.get("type") in p["type"]:
                lloji_ok += 1
            else:
                lloji_gabim.append(f"{g['id']}: {r.get('type')} (pritej {'/'.join(p['type'])})")
            kosova_ok += r.get("in_kosovo") is p["in_kosovo"]
        elif gjet:
            fp += 1
            gj["fp"] += 1
            alarme.append(g["id"])
        elif p["is_security_event"]:
            fn += 1
            gj["fn"] += 1
            mungojne.append(g["id"])
        else:
            tn += 1

    # Korrelimi: correlator.py mban të gjitha ngjarjet e sigurisë, edhe ato rajonale
    gjuha = {g["id"]: g["gjuha"] for g in gold}
    grupi = {g["id"]: g["pritet"]["grupi"] or g["id"] for g in gold}
    te_pritura, rajonale_pritura = defaultdict(set), set()
    for g in gold:
        if g["pritet"]["is_security_event"]:
            te_pritura[g["pritet"]["grupi"]].add(g["id"])
            if not g["pritet"]["in_kosovo"]:
                rajonale_pritura.add(g["pritet"]["grupi"])
    parashikuara = [set(n) for n in ngjarjet]
    sakta = {k for k, ids in te_pritura.items() if ids in parashikuara}
    shumegjuhesh = {k for k, ids in te_pritura.items() if len({gjuha[i] for i in ids}) > 1}
    bashkime_gabim = sum(1 for n in parashikuara if len({grupi[i] for i in n}) > 1)
    # Rajonale e saktë = grupi i bashkuar saktë DHE correlator e shënoi "rajonale: True"
    flamuri = {frozenset(n): f for n, f in zip(parashikuara, rajonale or [])}
    rajonale_sakta = {k for k in rajonale_pritura & sakta
                      if rajonale is None or flamuri.get(frozenset(te_pritura[k])) is True}

    return {
        "precision": pjese(tp, tp + fp), "recall": pjese(tp, tp + fn),
        "tp": tp, "fp": fp, "fn": fn, "negative": fp + tn,
        "lloji_ok": lloji_ok, "kosova_ok": kosova_ok,
        "gjuhet": {k: {"precision": pjese(v["tp"], v["tp"] + v["fp"]),
                       "recall": pjese(v["tp"], v["tp"] + v["fn"])} for k, v in sorted(gjuhet.items())},
        "ngjarje_sakta": len(sakta), "ngjarje_gjithsej": len(te_pritura),
        "shumegjuhesh_sakta": len(sakta & shumegjuhesh), "shumegjuhesh_gjithsej": len(shumegjuhesh),
        "bashkime_gabim": bashkime_gabim,
        "mungojne": mungojne, "alarme": alarme, "lloji_gabim": lloji_gabim,
        "ngjarje_gabim": sorted(set(te_pritura) - sakta),
        "rajonale_sakta": len(rajonale_sakta), "rajonale_gjithsej": len(rajonale_pritura),
        "rajonale_gabim": sorted(rajonale_pritura - rajonale_sakta),
    }


def shfaq(m, sekonda, n, info):
    manuale = n * MINUTA_MANUALE
    print(f"\n=== Rezultati mbi gold set-in ({n} artikuj sintetikë) ===")
    print(f"Zbulimi i ngjarjeve:    precision {m['precision']:.2f} · recall {m['recall']:.2f}"
          f"  (gjetur saktë {m['tp']}, munguan {m['fn']})")
    print(f"Alarme të rreme:        {m['fp']} nga {m['negative']} artikuj pa kërcënim")
    print(f"Lloji i saktë:          {m['lloji_ok']}/{m['tp']}")
    print(f"Brenda/jashtë Kosovës:  {m['kosova_ok']}/{m['tp']}")
    for k, v in m["gjuhet"].items():
        print(f"  gjuha {k}:             precision {v['precision']:.2f} · recall {v['recall']:.2f}")
    print(f"Ngjarje të bashkuara saktë: {m['ngjarje_sakta']}/{m['ngjarje_gjithsej']}"
          f"  (shumëgjuhëshe {m['shumegjuhesh_sakta']}/{m['shumegjuhesh_gjithsej']})")
    print(f"Bashkime të gabuara:    {m['bashkime_gabim']}")
    print(f"Ngjarje rajonale saktë: {m['rajonale_sakta']}/{m['rajonale_gjithsej']}"
          "  (jashtë Kosovës, me flamurin 'rajonale')")
    print(f"Koha:                   {sekonda:.0f} s ({pjese(sekonda, n):.1f} s/artikull) kundrejt "
          f"~{manuale} min manualisht (supozim {MINUTA_MANUALE} min/artikull)")
    print(f"Filtruar pa model:      {info['filtruar']} · gabime të modelit: {info['gabime']}")
    # Detajet që ekipi të dijë çfarë të rregullojë
    if m["mungojne"]:
        print(f"\nMunguan (ngjarje që sistemi s'i gjeti): {', '.join(m['mungojne'])}")
    if m["alarme"]:
        print(f"Alarme të rreme: {', '.join(m['alarme'])}")
    if m["lloji_gabim"]:
        print("Lloji gabim: " + "; ".join(m["lloji_gabim"]))
    if m["ngjarje_gabim"]:
        print(f"Ngjarje të pabashkuara saktë: {', '.join(m['ngjarje_gabim'])}")
    if m["rajonale_gabim"]:
        print(f"Rajonale gabim: {', '.join(m['rajonale_gabim'])}")


def ruaj_rezultatin(m, sekonda, n):
    """Shkruan eval/rezultati.json për dashboard-in."""
    rezultati = {"koha": datetime.now().isoformat(timespec="seconds"), "modeli": processor.MODELI,
                 "artikuj": n, "sekonda": round(sekonda, 1), "minuta_manuale": MINUTA_MANUALE,
                 "metrikat": m}
    with open(REZULTATI, "w", encoding="utf-8") as f:
        json.dump(rezultati, f, ensure_ascii=False, indent=2)


def kontrollo():
    """Kontroll i vogël i metrikave me parashikime të shpikura (pa model)."""
    gold = [
        {"id": "a1", "gjuha": "sq", "pritet": {"is_security_event": True, "in_kosovo": True,
                                               "type": ["arrest"], "grupi": "E1"}},
        {"id": "a2", "gjuha": "sr", "pritet": {"is_security_event": True, "in_kosovo": True,
                                               "type": ["arrest"], "grupi": "E1"}},
        {"id": "a3", "gjuha": "sq", "pritet": {"is_security_event": False, "in_kosovo": True,
                                               "type": [], "grupi": None}},
        {"id": "a4", "gjuha": "en", "pritet": {"is_security_event": True, "in_kosovo": True,
                                               "type": ["cyber"], "grupi": "E2"}},
    ]
    rez = {"a1": {"is_security_event": True, "in_kosovo": True, "type": "arrest"},
           "a2": {"is_security_event": True, "in_kosovo": True, "type": "violence"},
           "a3": {"is_security_event": True, "in_kosovo": True, "type": "other"}}  # a4 mungon
    m = mat(gold, rez, [["a1", "a2", "a3"]])
    assert (m["tp"], m["fp"], m["fn"], m["negative"]) == (2, 1, 1, 1), m
    assert round(m["precision"], 2) == 0.67 and round(m["recall"], 2) == 0.67, m
    assert m["lloji_ok"] == 1 and m["alarme"] == ["a3"] and m["mungojne"] == ["a4"], m
    assert m["ngjarje_sakta"] == 0 and m["bashkime_gabim"] == 1, m
    assert m["shumegjuhesh_gjithsej"] == 1, m
    m = mat(gold, rez, [["a1", "a2"], ["a3"]])
    assert m["ngjarje_sakta"] == 1 and m["shumegjuhesh_sakta"] == 1 and m["bashkime_gabim"] == 0, m

    # Rasti rajonal: E3 ndodhi jashtë Kosovës dhe u raportua në dy gjuhë
    pritet_r = {"is_security_event": True, "in_kosovo": False, "type": ["explosion_weapons"], "grupi": "E3"}
    gold_r = gold + [{"id": "a5", "gjuha": "sq", "pritet": pritet_r},
                     {"id": "a6", "gjuha": "sr", "pritet": pritet_r}]
    rez_r = {**rez, **{i: {"is_security_event": True, "in_kosovo": False, "type": "explosion_weapons"}
                       for i in ("a5", "a6")}}
    m = mat(gold_r, rez_r, [["a1", "a2"], ["a3"], ["a5", "a6"]], [False, False, True])
    assert (m["rajonale_sakta"], m["rajonale_gjithsej"], m["rajonale_gabim"]) == (1, 1, []), m
    assert (m["ngjarje_sakta"], m["ngjarje_gjithsej"], m["shumegjuhesh_gjithsej"]) == (2, 3, 2), m
    assert (m["tp"], m["kosova_ok"], m["bashkime_gabim"]) == (4, 4, 0), m  # a1, a2, a5, a6
    # Grupi i saktë por pa flamurin "rajonale" -> s'numërohet si rajonale e saktë
    m = mat(gold_r, rez_r, [["a1", "a2"], ["a3"], ["a5", "a6"]], [False, False, False])
    assert (m["rajonale_sakta"], m["rajonale_gabim"], m["ngjarje_sakta"]) == (0, ["E3"], 2), m
    # Grupi i ndarë në dy -> as ngjarje e saktë, as rajonale e saktë
    m = mat(gold_r, rez_r, [["a1", "a2"], ["a3"], ["a5"], ["a6"]], [False, False, True, True])
    assert (m["rajonale_sakta"], m["ngjarje_sakta"]) == (0, 1), m
    # Pa flamuj (rajonale=None) mjafton grupi i saktë
    assert mat(gold_r, rez_r, [["a5", "a6"]])["rajonale_sakta"] == 1


if __name__ == "__main__":
    kontrollo()
    gold = lexo_gold()
    if not processor.ollama_gati():
        sys.exit("Ollama nuk po punon. Nise me 'ollama serve' dhe provo përsëri.")
    print(f"Gold set: {len(gold)} artikuj. Pipeline-i po kalon (mund të zgjasë disa minuta)...")
    rezultatet, ngjarjet, sekonda, info = ekzekuto(gold)
    metrikat = mat(gold, rezultatet, ngjarjet, info["rajonale"])
    shfaq(metrikat, sekonda, len(gold), info)
    ruaj_rezultatin(metrikat, sekonda, len(gold))
    print(f"\nU ruajt {REZULTATI}")
