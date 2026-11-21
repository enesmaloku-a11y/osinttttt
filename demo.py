"""demo.py - Mbush një bazë demo me artikujt SINTETIKË të eval/gold.jsonl, pa Ollama dhe pa rrjet.

Nis me:  python demo.py
         OSINT_DB=demo.db streamlit run dashboard.py      (PowerShell: $env:OSINT_DB="demo.db")

Kujdes: rezultati i "modelit" këtu merret nga përgjigjet e sakta të gold set-it (lloji, grupi),
jo nga modeli. Përmbledhja = titulli i artikullit anglisht të grupit (ose titulli i vet), që
correlator.py t'i bashkojë si do t'i bashkonte pas përkthimit. Shërben vetëm për të treguar
dashboard-in; numrat e saktësisë jepen nga eval/evaluate.py, jo nga kjo.
"""
import json
import os
import sys
from contextlib import closing
from pathlib import Path

import db

GOLD = Path(__file__).resolve().parent / "eval" / "gold.jsonl"
# Aktori kur gold-i s'e jep: vetëm për kategoritë ku s'ka dyshim se kush qëndron pas
AKTORI_NGA_KATEGORIA = {"ushtarak_serbia": "shteti_serb", "struktura_paralele": "shteti_serb",
                        "diplomatik_ligjor": "shteti_serb"}


def rezultati(g, perm, vendi):
    """JSON në formën e extractor.py, i ndërtuar nga etiketat e gold set-it."""
    p = g["pritet"]
    kat = p.get("kategoria") or "tjeter"
    kat = kat[0] if isinstance(kat, list) else kat
    return {"is_security_event": p["is_security_event"], "in_kosovo": p["in_kosovo"],
            "type": (p["type"] or ["other"])[0], "summary": perm, "event_date": g["data"], "place": vendi,
            "place_precision": ("region" if vendi == "veri" else "municipality") if vendi else None,
            "date_precision": "exact", "actors": [], "killed": None, "injured": None,
            "arrested": None, "demo": True,
            # K2: gold-i jep disa kategori të pranueshme si listë; merret e para
            "kategoria": kat,
            "aktori": p.get("aktori") or AKTORI_NGA_KATEGORIA.get(kat, "i_panjohur"), "shenjestrat": p.get("shenjestrat") or [],
            "lidhje_me_fsk": p.get("lidhje_me_fsk") is True}  # shortcut: place = emri kanonik ("mitrovic"), jo teksti i artikullit


def shenjo_aktoret_e_nxjerre(gold):
    """Aktori i nxjerrë nga kategoria s'është as etiketë as përgjigje e modelit: shënohet te ngjarja
    (correlator.py s'e bart këtë fushë nga artikujt, ndaj shkruhet pas korrelimit)."""
    me_aktor = {f"gold://{g['id']}" for g in gold if g["pritet"].get("aktori")}
    for e in db.ngjarjet():
        det = json.loads(e["detajet_json"] or "{}")
        if det.get("aktori", "i_panjohur") != "i_panjohur" and not me_aktor & set(json.loads(e["burimet"])):
            det["aktori_burimi"] = "nga_kategoria"
            db.ruaj_besueshmerine(e["id"], e["besueshmeria"], det)


def mbush(gold):
    import correlator
    import extractor
    import rreziku
    import scoring
    # Përmbledhja dhe vendi i përbashkët për çdo grup ngjarjeje
    perm, vendi = {}, {}
    for g in gold:
        k = g["pritet"]["grupi"] or g["id"]
        if g["gjuha"] == "en" or k not in perm:
            perm[k] = extractor.fshi_emrat(g["titulli"])
        if not vendi.get(k):
            vendi[k] = correlator.gjej_vendin(f"{g['titulli']} {g['teksti']}")[0]
    for g in gold:
        k = g["pritet"]["grupi"] or g["id"]
        url = f"gold://{g['id']}"
        db.ruaj_artikull(url=url, burimi=g["burimi"], titulli=g["titulli"], data=g["data"],
                         gjuha=g["gjuha"], teksti=g["teksti"])
        with closing(db.lidhu()) as con:
            aid = con.execute("SELECT id FROM articles WHERE url = ?", (url,)).fetchone()[0]
        db.sheno_perpunuar(aid, rezultati(g, perm[k], vendi[k]))
    n = correlator.korrelo()
    scoring.vlereso_te_gjitha()
    shenjo_aktoret_e_nxjerre(gold)
    # "Sot" = dita e fundit e gold set-it, që pikët e freskisë (dhe Urgjente) të mos ndryshojnë me kalendarin
    rreziku.vlereso_te_gjitha(sot=max(g["data"] for g in gold))
    return n


if __name__ == "__main__":
    if "OSINT_DB" not in os.environ:
        db.DB_PATH = "demo.db"
    if Path(db.DB_PATH).name == "osint.db":
        sys.exit("demo.py s'e prek osint.db (të dhënat reale). Përdor OSINT_DB=demo.db.")
    Path(db.DB_PATH).unlink(missing_ok=True)
    gold = [json.loads(r) for r in open(GOLD, encoding="utf-8") if r.strip()]
    n = mbush(gold)
    ngj = db.ngjarjet()
    # Kontroll: të paktën një ngjarje u bashkua nga disa gjuhë, dhe asnjë pa burim
    assert n and all(json.loads(e["burimet"]) for e in ngj)
    assert any(len(json.loads(e["detajet_json"])["gjuhet"]) > 1 for e in ngj), "s'u bashkua asgjë"
    prioritetet = {json.loads(e["detajet_json"]).get("prioriteti") for e in ngj}
    assert {"URGJENTE", "RAPORT"} <= prioritetet, prioritetet
    print(f"{db.DB_PATH}: {len(gold)} artikuj sintetikë, {n} ngjarje.\n"
          f"Hap:  OSINT_DB={db.DB_PATH} streamlit run dashboard.py")
