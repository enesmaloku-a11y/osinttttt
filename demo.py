"""demo.py - Mbush një bazë demo me artikujt SINTETIKË të eval/gold.jsonl, pa Ollama dhe pa rrjet.

Nis me:  python demo.py                 (krijon demo.db në dosjen aktuale)
         python demo.py --kontrollo     (prova e mbrojtjes, në dosje të përkohshme)
         python demo.py demo2.db        (shteg tjetër)
Pastaj (PowerShell):  $env:OSINT_DB="demo.db"; python -m streamlit run dashboard.py

Mbrojtja e bazave: demo.py s'shkruan kurrë te OSINT_DB dhe s'mbishkruan asnjë skedar ekzistues.
Baza ndërtohet në një skedar të përkohshëm dhe publikohet me emrin e kërkuar vetëm pasi
kontrollet kalojnë; nëse emri ekziston (edhe nga një ekzekutim paralel), skedari ruhet dhe
komanda kërkon një shteg tjetër.

Kujdes: rezultati i "modelit" këtu merret nga përgjigjet e sakta të gold set-it (lloji, grupi),
jo nga modeli. Përmbledhja = titulli i artikullit anglisht të grupit (ose titulli i vet), që
correlator.py t'i bashkojë si do t'i bashkonte pas përkthimit. Shërben vetëm për të treguar
dashboard-in; numrat e saktësisë jepen nga eval/evaluate.py, jo nga kjo.
"""
import json
import os
import sys
import tempfile
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
                         gjuha=g["gjuha"], teksti=g["teksti"], published_at=g["data"])
        with closing(db.lidhu()) as con:
            aid = con.execute("SELECT id FROM articles WHERE url = ?", (url,)).fetchone()[0]
        db.sheno_perpunuar(aid, rezultati(g, perm[k], vendi[k]))
    n = correlator.korrelo()
    scoring.vlereso_te_gjitha(perdor_modelin=False)
    shenjo_aktoret_e_nxjerre(gold)
    # "Sot" = dita e fundit e gold set-it, që pikët e freskisë (dhe Urgjente) të mos ndryshojnë me kalendarin
    rreziku.vlereso_te_gjitha(sot=max(g["data"] for g in gold))
    return n


def gjenero(destinacioni):
    """Ndërton demon në një skedar të përkohshëm dhe e publikon te destinacioni pa mbishkruar asgjë.
    Kthen (artikuj, ngjarje, urgjente); ngre FileExistsError nëse destinacioni ekziston."""
    destinacioni = Path(destinacioni).resolve()
    if destinacioni.name.casefold() == "osint.db":
        raise ValueError("demo.py s'e prek osint.db (të dhënat reale)")
    if destinacioni.exists():
        raise FileExistsError(destinacioni)
    fd, tmp = tempfile.mkstemp(prefix=".demo-", suffix=".db", dir=destinacioni.parent)
    os.close(fd)
    vjeter, db.DB_PATH = db.DB_PATH, tmp  # OSINT_DB s'preket kurrë
    try:
        gold = [json.loads(r) for r in open(GOLD, encoding="utf-8") if r.strip()]
        n = mbush(gold)
        ngj = db.ngjarjet()
        # Kontroll: të paktën një ngjarje u bashkua nga disa gjuhë, dhe asnjë pa burim
        assert n and all(json.loads(e["burimet"]) for e in ngj)
        assert any(len(json.loads(e["detajet_json"])["gjuhet"]) > 1 for e in ngj), "s'u bashkua asgjë"
        prioritetet = [json.loads(e["detajet_json"]).get("prioriteti") for e in ngj]
        assert {"URGJENTE", "RAPORT"} <= set(prioritetet), prioritetet
        # Lidhje e fortë: atomike dhe dështon nëse emri u krijua ndërkohë (os.rename në POSIX mbishkruan)
        os.link(tmp, destinacioni)
        return len(gold), n, prioritetet.count("URGJENTE")
    finally:
        db.DB_PATH = vjeter
        Path(tmp).unlink(missing_ok=True)


def kontrollo_mbrojtjen():
    """Pa rrjet: krijimi, skedari ekzistues, dështimi gjatë gjenerimit dhe gara me një proces tjetër."""
    global mbush
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        pune = d / "pune.db"
        pune.write_bytes(b"baze pune")
        os.environ["OSINT_DB"] = str(pune)  # demo s'shkruan kurrë te OSINT_DB
        artikuj, n, urgjente = gjenero(d / "demo.db")
        assert artikuj and n and urgjente and pune.read_bytes() == b"baze pune"
        para = (d / "demo.db").read_bytes()
        for ekzistues in (d / "demo.db", pune):
            try:
                gjenero(ekzistues)
                raise AssertionError("mbishkroi " + ekzistues.name)
            except FileExistsError:
                pass
        assert (d / "demo.db").read_bytes() == para and pune.read_bytes() == b"baze pune"
        origjinali = mbush

        def deshton(gold):
            raise RuntimeError("ndërprerje")

        def gare(gold):  # një proces tjetër krijon destinacionin gjatë gjenerimit
            (d / "gara.db").write_bytes(b"tjetri")
            return origjinali(gold)

        try:
            mbush = deshton
            try:
                gjenero(d / "pjesshme.db")
                raise AssertionError("dështimi s'u raportua")
            except RuntimeError:
                pass
            assert not (d / "pjesshme.db").exists()
            mbush = gare
            try:
                gjenero(d / "gara.db")
                raise AssertionError("gara mbishkroi")
            except FileExistsError:
                pass
            assert (d / "gara.db").read_bytes() == b"tjetri"
        finally:
            mbush = origjinali
        assert not list(d.glob(".demo-*")), "mbeti skedar i përkohshëm"
    print(f"Kontrollet e demos kaluan: {artikuj} artikuj, {n} ngjarje, {urgjente} urgjente; "
          f"bazat ekzistuese s'u prekën.")


if __name__ == "__main__":
    if sys.argv[1:] == ["--kontrollo"]:
        kontrollo_mbrojtjen()
        sys.exit()
    shtegu = Path(sys.argv[1] if len(sys.argv) > 1 else "demo.db")
    try:
        artikuj, n, urgjente = gjenero(shtegu)
    except FileExistsError:
        sys.exit(f"{shtegu.resolve()} ekziston dhe s'u prek. Hape ashtu siç është, ose krijo një të re "
                 f"me shteg tjetër:  python demo.py demo2.db")
    except ValueError as e:
        sys.exit(str(e))
    print(f"{shtegu.resolve()}: {artikuj} artikuj sintetikë, {n} ngjarje, {urgjente} urgjente.\n"
          f'Hap (PowerShell):  $env:OSINT_DB="{shtegu.resolve()}"; python -m streamlit run dashboard.py')
