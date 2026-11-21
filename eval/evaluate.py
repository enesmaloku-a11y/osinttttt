"""eval/evaluate.py - Mat saktësinë e sistemit mbi gold set-in (eval/gold.jsonl).

Nis me:  python eval/evaluate.py

- gold.jsonl ka artikuj SINTETIKË (të shkruar nga ekipi, jo lajme reale) në sq/sr/en,
  me përgjigjen e saktë te "pritet". Në prezantim thuaj qartë që janë sintetikë.
- Kalon të njëjtin pipeline si sistemi: processor -> extractor -> correlator -> scoring
  -> rreziku (nëse rreziku.py ekziston). Konteksti (EUvsDisinfo/EuRepoC) s'thirret, sepse varet
  nga skedarët lokalë te data/.
- Përdor një bazë SQLite të përkohshme për çdo ekzekutim dhe rregullat e besueshmërisë.
- Kërkon Ollama lokal, si processor.py.
- Mat edhe kategorinë (K2), nivelin e rrezikut dhe URGJENTE (K9), me numra bruto dhe interval
  Wilson 95%: me pak artikuj sintetikë, një përqindje e vetme do të mashtronte.
"""
import importlib.util
import json
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

DOSJA = Path(__file__).resolve().parent
sys.path.insert(0, str(DOSJA.parent))  # modulet e projektit janë një nivel më lart

import correlator  # noqa: E402
import db  # noqa: E402
import extractor  # noqa: E402
import kercenimet  # noqa: E402
import processor  # noqa: E402
import scoring  # noqa: E402

GOLD = DOSJA / "gold.jsonl"
REZULTATI = DOSJA / "rezultati.json"  # e lexon dashboard-i
# shortcut: supozim për kohën e analistit; zëvendësoje me matje reale nëse e keni
MINUTA_MANUALE = 3


def lexo_gold():
    """Lexon gold set-in dhe kontrollon që çdo rresht ka fushat e duhura."""
    with open(GOLD, encoding="utf-8") as f:
        gold = [json.loads(r) for r in f if r.strip()]
    ids = [g["id"] for g in gold]
    assert len(ids) == len(set(ids)), "id të përsëritura në gold.jsonl"
    etiketat = {}
    for g in gold:
        p = g["pritet"]
        assert g["gjuha"] in ("sq", "sr", "en"), g["id"]
        assert {"is_security_event", "in_kosovo", "type", "grupi"} <= set(p), g["id"]
        # Fushat opsionale të K9: vetëm vlera nga kercenimet.py (me "ë", fjalë për fjalë)
        k = p.get("kategoria")
        assert k is None or all(isinstance(x, str) and kercenimet.kategoria_valide(x)
                                for x in (k if isinstance(k, list) else [k])), g["id"]
        assert p.get("rreziku_niveli") in (None, *kercenimet.NIVELET), g["id"]
        assert p.get("prioriteti") in (None, *kercenimet.PRIORITETET), g["id"]
        assert p.get("aktori") in (None, *kercenimet.AKTORET), g["id"]
        # Rreziku dhe prioriteti janë të ngjarjes: të njëjtë për të gjithë artikujt e grupit
        if p["grupi"]:
            e = (p.get("rreziku_niveli"), p.get("prioriteti"))
            assert etiketat.setdefault(p["grupi"], e) == e, g["id"]
    return gold


def url_e(g):
    return f"gold://{g['id']}"


def ekzekuto(gold):
    """Kalon pipeline-in në një bazë të përkohshme dhe kthen artikujt, grupet, kohën dhe detajet."""
    if not gold:
        raise ValueError("Gold set-i është bosh.")
    vjeter = db.DB_PATH
    with TemporaryDirectory(prefix="osint-eval-") as dosja:
        db.DB_PATH = str(Path(dosja) / "eval.db")
        try:
            for g in gold:
                db.ruaj_artikull(url=url_e(g), burimi=g["burimi"], titulli=g["titulli"],
                                 data=g["data"], gjuha=g["gjuha"], teksti=g["teksti"],
                                 published_at=g["data"])

            n = len(gold)
            t0 = time.perf_counter()
            _, gabime_perkthimi = processor.perpuno(n)
            _, filtruar, gabime_nxjerrje, _ = extractor.perpuno(n)
            correlator.korrelo()
            scoring.vlereso_te_gjitha(perdor_modelin=False)
            # "Sot" = data më e re e gold-it, për një dritare të riprodhueshme rreziku.
            ka_rrezik = importlib.util.find_spec("rreziku") is not None
            if ka_rrezik:
                importlib.import_module("rreziku").vlereso_te_gjitha(sot=max(g["data"][:10] for g in gold))
            sekonda = time.perf_counter() - t0

            id_e = {url_e(g): g["id"] for g in gold}
            rezultatet = {id_e[r["url"]]: json.loads(r["rezultati_json"]) for r in db.artikuj_te_nxjerre()}
            te_gjitha = db.ngjarjet()
            ngjarjet = [[id_e[u] for u in json.loads(e["burimet"])] for e in te_gjitha]
            detajet = [json.loads(e["detajet_json"] or "{}") for e in te_gjitha]
            info = {"filtruar": filtruar, "gabime": gabime_perkthimi + gabime_nxjerrje,
                    "rreziku_ekzekutuar": ka_rrezik,
                    "rajonale": [d.get("rajonale") is True for d in detajet], "detajet": detajet}
            return rezultatet, ngjarjet, sekonda, info
        finally:
            db.DB_PATH = vjeter


def pjese(a, b):
    return a / b if b else 0.0


def pjese_ose_none(a, b):
    """Si pjese(), por None kur emëruesi është 0 (s'ka çfarë të matet)."""
    return a / b if b else None


def wilson(k, n, z=1.96):
    """Intervali Wilson 95% për k suksese nga n, i rrumbullakuar në 2 shifra; None kur n = 0.
    I saktë edhe për n të vogël dhe për k = 0 ose k = n (ndryshe nga intervali normal)."""
    if not n:
        return None
    p = k / n
    qendra = (p + z * z / (2 * n)) / (1 + z * z / n)
    gjeresia = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / (1 + z * z / n)
    return round(qendra - gjeresia, 2), round(qendra + gjeresia, 2)


def kn(k, n):
    """'k/n [poshtë–lart]' për shfaqje; kurrë vetëm përqindje."""
    w = wilson(k, n)
    return f"{k}/{n} [{w[0]:.2f}–{w[1]:.2f}]" if w else f"{k}/{n}"


def mat(gold, rezultatet, ngjarjet, rajonale=None, detajet=None, *, rreziku_ekzekutuar=None):
    """Krahason parashikimet me gold set-in dhe kthen metrikat.
    rezultatet: {id: JSON i extractor.py}; ngjarjet: [[id, ...], ...] nga correlator.py;
    rajonale: [bool, ...] flamuri "rajonale" i çdo ngjarjeje (None = s'kontrollohet);
    detajet: [dict, ...] detajet_json e çdo ngjarjeje (None = rreziku/aktori s'maten)."""
    tp = fp = fn = tn = lloji_ok = kosova_ok = 0
    gjuhet = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    mungojne, alarme, lloji_gabim = [], [], []
    for g in gold:
        p, r = g["pritet"], rezultatet.get(g["id"], {})  # pa rezultat = s'u gjet
        gjet = correlator.merret(r)
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
            te_pritura[grupi[g["id"]]].add(g["id"])
            if not g["pritet"]["in_kosovo"]:
                rajonale_pritura.add(grupi[g["id"]])
    parashikuara = [set(n) for n in ngjarjet]
    sakta = {k for k, ids in te_pritura.items() if ids in parashikuara}
    shumegjuhesh = {k for k, ids in te_pritura.items() if len({gjuha[i] for i in ids}) > 1}
    bashkime_gabim = sum(1 for n in parashikuara if len({grupi[i] for i in n}) > 1)
    # Rajonale e saktë = grupi i bashkuar saktë DHE correlator e shënoi "rajonale: True"
    flamuri = {frozenset(n): f for n, f in zip(parashikuara, rajonale or [])}
    rajonale_sakta = {k for k in rajonale_pritura & sakta
                      if rajonale is None or flamuri.get(frozenset(te_pritura[k])) is True}

    # K9: kategoria sipas artikullit (lista = disa kategori të pranuara)
    kategoria_ok, kategoria_gabim = 0, []
    me_kategori = [g for g in gold if g["pritet"].get("kategoria") is not None]
    for g in me_kategori:
        k = g["pritet"]["kategoria"]
        pranuara = k if isinstance(k, list) else [k]
        rezultati = rezultatet.get(g["id"], {})
        mori = rezultati.get("kategoria") if correlator.merret(rezultati) else None
        if mori in pranuara:
            kategoria_ok += 1
        else:
            kategoria_gabim.append(f"{g['id']}: {mori} (pritej {'/'.join(pranuara)})")

    # Një parashikim i përket grupit që ka shumicën e artikujve. Nga ndarjet e të njëjtit
    # grup merret ajo me më shumë artikuj të grupit dhe më pak artikuj të tjerë.
    etiketa = {grupi[g["id"]]: g["pritet"] for g in gold if g["pritet"]["is_security_event"]}
    ka_detaje = detajet is not None
    ka_rrezik = ka_detaje and any(isinstance(d, dict) and "rreziku" in d for d in detajet)
    if rreziku_ekzekutuar is not None:
        ka_rrezik = rreziku_ekzekutuar
    nivelet = kercenimet.NIVELET

    perputhjet = {}
    for n, d in zip(parashikuara, detajet or []):
        numri = Counter(grupi[i] for i in n)
        if not numri or not isinstance(d, dict):
            continue
        k, artikuj = numri.most_common(1)[0]
        cilesia = (artikuj, artikuj - len(n))
        if k in etiketa and 2 * artikuj > len(n):
            if k not in perputhjet or cilesia > perputhjet[k][0]:
                perputhjet[k] = (cilesia, d)

    rreziku_ok = rreziku_n = prioriteti_ok = prioriteti_n = aktori_ok = aktori_n = 0
    urgjente_grupe = urgjente_kapura = gabime_2_nivele = 0
    konfuzioni = {n: {m: 0 for m in nivelet} for n in nivelet}  # pritet -> parashikuar
    for grupi_i, p in etiketa.items():
        d = perputhjet.get(grupi_i, (None, {}))[1]
        niveli = (d.get("rreziku") or {}).get("niveli")
        pritet_niveli = p.get("rreziku_niveli")
        if pritet_niveli:
            rreziku_n += 1
            rreziku_ok += niveli == pritet_niveli
            if niveli in nivelet:
                konfuzioni[pritet_niveli][niveli] += 1
                gabime_2_nivele += {niveli, pritet_niveli} == {nivelet[0], nivelet[2]}
        if p.get("prioriteti"):
            prioriteti_n += 1
            prioriteti_ok += d.get("prioriteti") == p["prioriteti"]
        if p.get("prioriteti") == "URGJENTE":
            urgjente_grupe += 1
            urgjente_kapura += d.get("prioriteti") == "URGJENTE"
        if p.get("aktori"):
            aktori_n += 1
            aktori_ok += d.get("aktori") == p["aktori"]
    # Çdo grup i pritur jep më së shumti një alarm të saktë. Ndarjet shtesë mbeten në emërues.
    urgjente_parashikuara = sum(isinstance(d, dict) and d.get("prioriteti") == "URGJENTE"
                                for d in (detajet or []))

    def vetem_me_rrezik(v):
        return v if ka_rrezik else None

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
        # K9 (None = s'u mat: pa detaje ose pa rreziku.py, ose emëruesi 0)
        "kategoria_ok": kategoria_ok, "kategoria_gjithsej": len(me_kategori),
        "kategoria_gabim": kategoria_gabim,
        "rreziku_ok": vetem_me_rrezik(rreziku_ok), "rreziku_gjithsej": vetem_me_rrezik(rreziku_n),
        "prioriteti_ok": vetem_me_rrezik(prioriteti_ok), "prioriteti_gjithsej": vetem_me_rrezik(prioriteti_n),
        "urgjente_precision": vetem_me_rrezik(pjese_ose_none(urgjente_kapura, urgjente_parashikuara)),
        "urgjente_recall": vetem_me_rrezik(pjese_ose_none(urgjente_kapura, urgjente_grupe)),
        "urgjente_sakta": vetem_me_rrezik(urgjente_kapura),
        "urgjente_parashikuara": vetem_me_rrezik(urgjente_parashikuara),
        "urgjente_kapura": vetem_me_rrezik(urgjente_kapura), "urgjente_grupe": vetem_me_rrezik(urgjente_grupe),
        "aktori_ok": aktori_ok if ka_detaje else None, "aktori_gjithsej": aktori_n if ka_detaje else None,
        "rreziku_konfuzioni": vetem_me_rrezik(konfuzioni),
        "gabime_2_nivele": vetem_me_rrezik(gabime_2_nivele),
        "intervalet": {
            "precision": wilson(tp, tp + fp), "recall": wilson(tp, tp + fn),
            "kategoria": wilson(kategoria_ok, len(me_kategori)),
            "rreziku": vetem_me_rrezik(wilson(rreziku_ok, rreziku_n)),
            "prioriteti": vetem_me_rrezik(wilson(prioriteti_ok, prioriteti_n)),
            "urgjente_precision": vetem_me_rrezik(wilson(urgjente_kapura, urgjente_parashikuara)),
            "urgjente_recall": vetem_me_rrezik(wilson(urgjente_kapura, urgjente_grupe)),
        },
    }


def shfaq(m, sekonda, n, info):
    manuale = n * MINUTA_MANUALE
    print(f"\n=== Rezultati mbi gold set-in ({n} artikuj sintetikë) ===")
    print(f"Zbulimi i ngjarjeve:    precision {kn(m['tp'], m['tp'] + m['fp'])}"
          f" · recall {kn(m['tp'], m['tp'] + m['fn'])}")
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
    print(f"Kategoria e saktë:      {kn(m['kategoria_ok'], m['kategoria_gjithsej'])}  (sipas artikullit)")
    if m["rreziku_ok"] is None:
        print("Rreziku/URGJENTE:       e pamatur në këtë ekzekutim")
    else:
        print(f"Niveli i rrezikut:      {kn(m['rreziku_ok'], m['rreziku_gjithsej'])}  (sipas grupit)"
              f" · gabime i lartë<->i ulët: {m['gabime_2_nivele']}")
        print(f"Prioriteti i saktë:     {kn(m['prioriteti_ok'], m['prioriteti_gjithsej'])}")
        print(f"URGJENTE:               precision {kn(m['urgjente_sakta'], m['urgjente_parashikuara'])}"
              f" · recall {kn(m['urgjente_kapura'], m['urgjente_grupe'])}")
        for pritej, rreshti in m["rreziku_konfuzioni"].items():
            print(f"  pritej {pritej:8} -> " + ", ".join(f"{k}: {v}" for k, v in rreshti.items()))
    if m["aktori_ok"] is not None and m["aktori_gjithsej"]:
        print(f"Aktori (K3):            {kn(m['aktori_ok'], m['aktori_gjithsej'])}")
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
    if m["kategoria_gabim"]:
        print("Kategoria gabim: " + "; ".join(m["kategoria_gabim"]))


def ruaj_rezultatin(m, sekonda, n):
    """Publikon raportin vetëm pasi JSON-i i plotë është shkruar."""
    rezultati = {"koha": datetime.now().isoformat(timespec="seconds"), "modeli": processor.MODELI,
                 "artikuj": n, "sekonda": round(sekonda, 1), "minuta_manuale": MINUTA_MANUALE,
                 "skorimi": "rregulla", "perputhja_ngjarjeve": "nje-me-nje", "metrikat": m}
    with NamedTemporaryFile("w", dir=REZULTATI.parent, encoding="utf-8", delete=False) as f:
        emer = Path(f.name)
        try:
            json.dump(rezultati, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.close()
            os.replace(emer, REZULTATI)
        finally:
            f.close()
            emer.unlink(missing_ok=True)


def kontrollo():
    """Kontroll i vogël i metrikave me parashikime të shpikura (pa model)."""
    from io import BytesIO
    from unittest.mock import patch

    with patch.object(processor, "MODELI", "probe:latest"):
        for katalogu, gati in ((b'{"models": [{"name": "probe"}]}', True),
                              (b'{"models": [{"model": "other:latest"}]}', False),
                              (b'{"other": null}', False), (b"jo JSON", False)):
            with patch.object(processor.urllib.request, "urlopen", return_value=BytesIO(katalogu)):
                assert processor.ollama_gati() == gati, katalogu
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
    # Një artikull i palidhur me Kosovën nuk hyn në ngjarje, edhe kur modeli e njeh si incident.
    m = mat(gold, {**rez, "a3": {**rez["a3"], "relevante": False}}, [["a1", "a2"]])
    assert (m["tp"], m["fp"], m["fn"]) == (2, 0, 1), m

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

    # K9: kategoria, rreziku dhe URGJENTE me detaje të shpikura
    def art(id_, grupi, **etiketa):
        return {"id": id_, "gjuha": "sq", "pritet": {"is_security_event": grupi is not None,
                                                    "in_kosovo": True, "type": [], "grupi": grupi,
                                                    **etiketa}}
    gold_k = [art("k1", "U1", kategoria="ushtarak_serbia", rreziku_niveli="i lartë", prioriteti="URGJENTE"),
              art("k2", "U2", kategoria=["dron_hapesire_ajrore", "tjeter"], rreziku_niveli="i lartë",
                  prioriteti="URGJENTE"),
              art("k3", "R1", kategoria="kibernetik", rreziku_niveli="i mesëm", prioriteti="RAPORT",
                  aktori="rusia"),
              art("k4", None),  # jo-sigurie
              art("k6", "U3", kategoria="kibernetik", rreziku_niveli="i lartë", prioriteti="URGJENTE")]
    rez_k = {"k1": {"is_security_event": True, "kategoria": "ushtarak_serbia"},
             "k2": {"is_security_event": True, "kategoria": "tjeter"},
             "k3": {"is_security_event": True, "kategoria": "dezinformim"},
             "k4": {"is_security_event": True, "kategoria": "tjeter"}}  # k6 s'u nxorr fare

    def d(niveli, prioriteti, **shtese):
        return {"rreziku": {"niveli": niveli}, "prioriteti": prioriteti, **shtese}
    ngj_k = [["k1"], ["k2"], ["k3"], ["k4"]]
    det_k = [d("i lartë", "URGJENTE"), d("i ulët", "ARKIV"), d("i mesëm", "RAPORT", aktori="rusia"),
             d("i lartë", "URGJENTE")]
    m = mat(gold_k, rez_k, ngj_k, detajet=det_k)
    assert (m["kategoria_ok"], m["kategoria_gjithsej"]) == (2, 4), m  # lista pranohet; k3, k6 gabim
    assert (m["rreziku_ok"], m["rreziku_gjithsej"], m["gabime_2_nivele"]) == (2, 4, 1), m  # U3 pa ngjarje
    assert m["urgjente_recall"] == 1 / 3 and m["urgjente_precision"] == 0.5, m  # k4 = alarm i rremë
    assert (m["aktori_ok"], m["aktori_gjithsej"], m["prioriteti_ok"]) == (1, 1, 2), m
    assert m["rreziku_konfuzioni"]["i lartë"] == {"i lartë": 1, "i mesëm": 0, "i ulët": 1}, m
    assert m["intervalet"]["urgjente_precision"] == wilson(1, 2), m
    # Pa detaje (ose pa rreziku.py): çelësat ekzistojnë, me vlerë None
    m = mat(gold_k, rez_k, ngj_k)
    assert all(m[k] is None for k in ("rreziku_ok", "rreziku_gjithsej", "urgjente_precision",
                                      "urgjente_recall", "aktori_ok", "gabime_2_nivele")), m
    assert m["kategoria_ok"] == 2  # kategoria s'varet nga rreziku.py
    m = mat(gold_k, rez_k, ngj_k, detajet=[{"rajonale": False}] * 4)  # detaje, por pa rreziku.py
    assert m["rreziku_ok"] is None and m["aktori_gjithsej"] == 1, m
    # Asnjë URGJENTE e parashikuar -> precision None (jo 0, jo exception), recall 0
    m = mat(gold_k, rez_k, ngj_k, detajet=[d("i mesëm", "RAPORT")] * 4)
    assert m["urgjente_precision"] is None and m["urgjente_recall"] == 0.0, m
    # Dy pjesë të një urgjence japin vetëm një parashikim të saktë.
    ndarje = gold_k + [art("k5", "U1", kategoria="ushtarak_serbia", rreziku_niveli="i lartë",
                          prioriteti="URGJENTE")]
    m = mat(ndarje, rez_k, [["k1"], ["k5"]], detajet=[d("i lartë", "URGJENTE")] * 2)
    assert (m["urgjente_sakta"], m["urgjente_kapura"], m["urgjente_precision"]) == (1, 1, 0.5), m
    # Një bashkim pa shumicë nuk mund të mbulojë dy urgjenca të pavarura.
    m = mat(gold_k, rez_k, [["k1", "k2"]], detajet=[d("i lartë", "URGJENTE")])
    assert (m["urgjente_sakta"], m["urgjente_kapura"], m["urgjente_precision"]) == (0, 0, 0), m
    m = mat(gold_k, {}, [], detajet=[], rreziku_ekzekutuar=True)
    assert (m["rreziku_ok"], m["rreziku_gjithsej"], m["urgjente_recall"]) == (0, 4, 0.0), m
    # E27: jashtë Kosovës, por ngjarje sigurie -> numërohet te rajonale
    e27 = art("k7", "E27", kategoria="ushtarak_serbia", rreziku_niveli="i mesëm", prioriteti="RAPORT")
    e27["pritet"]["in_kosovo"] = False
    m = mat(gold_k + [e27], {**rez_k, "k7": {"is_security_event": True, "in_kosovo": False}},
            ngj_k + [["k7"]], [False] * 4 + [True], det_k + [d("i mesëm", "RAPORT", rajonale=True)])
    assert (m["rajonale_gjithsej"], m["rajonale_sakta"], m["rreziku_gjithsej"]) == (1, 1, 5), m
    # Intervali Wilson 95% (me 2 shifra), edhe për n të vogël
    assert wilson(4, 5) == (0.38, 0.96) and wilson(9, 10) == (0.6, 0.98), (wilson(4, 5), wilson(9, 10))
    assert wilson(5, 5) == (0.57, 1.0) and wilson(0, 0) is None and kn(0, 0) == "0/0"
    assert kn(4, 5) == "4/5 [0.38–0.96]"


if __name__ == "__main__":
    kontrollo()
    gold = lexo_gold()
    gabimi = processor.gabimi_ollama()
    if gabimi:
        sys.exit(gabimi)
    print(f"Gold set: {len(gold)} artikuj. Pipeline-i po kalon (mund të zgjasë disa minuta)...")
    rezultatet, ngjarjet, sekonda, info = ekzekuto(gold)
    if info["gabime"] or len(rezultatet) != len(gold):
        sys.exit(f"Vlerësimi s'u plotësua ({len(rezultatet)}/{len(gold)} artikuj, "
                 f"{info['gabime']} gabime). Raporti i mëparshëm u ruajt.")
    metrikat = mat(gold, rezultatet, ngjarjet, info["rajonale"], info["detajet"],
                  rreziku_ekzekutuar=info["rreziku_ekzekutuar"])
    shfaq(metrikat, sekonda, len(gold), info)
    ruaj_rezultatin(metrikat, sekonda, len(gold))
    print(f"\nU ruajt {REZULTATI}")
