"""Kontekst historik nga eksporti manual Excel i https://eurepoc.eu/table-view/.
Kushtet https://eurepoc.eu/legal-notice/ lejojnë shkarkime personale, shkencore
ose jokomerciale. Për përdorim komercial verifikoni lejen veçmas.
Vendos eksportin te data/eurepoc.xlsx ose cakto EUREPOC_XLSX. Rezultatet
pasqyrojnë vetëm eksportin. Titujt përshkrues ndërtohen pa emra personash.
"""
import json
import os
import re
import sqlite3
import time
import xml.etree.ElementTree as ET
from contextlib import closing
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZipFile

import db
from correlator import fjalet

DOSJA = Path(__file__).resolve().parent / "data"
VENDET = {"Kosovo", "Serbia", "Albania", "North Macedonia", "Montenegro",
          "Bosnia and Herzegovina"}
# Pjesa minimale e fjalëve dalluese të ngjarjes dhe distanca maksimale në ditë.
PRAGU = 0.08
DITET = 45
LLOJET = {"cyber", "infrastructure_disruption"}
# Vetëm terma të kontrolluar dalin nga teksti i lirë në cache.
TERMA = set("""cyber attack attacks municipal municipality websites website offline
government governmental services public ministry ministries denial service ddos
disruption disrupted telecommunications telecom network networks electricity power
energy transport banking banks financial health hospital ransomware data theft leak
breach phishing espionage parliament administration systems servers infrastructure
agency agencies police media portals portal unavailable hijacking misuse defacement
communications water postal distributed malware access outages outages email""".split())


def lexo_rreshtat(skedar):
    """Lexon formatin inlineStr të TableView, duke respektuar qelizat bosh."""
    with ZipFile(skedar) as arkiv, arkiv.open("xl/worksheets/sheet1.xml") as xml:
        kolona = {}
        for _, nyja in ET.iterparse(xml):
            if not nyja.tag.endswith("}row"):
                continue
            fusha = {re.sub(r"[0-9]", "", c.attrib["r"]): "".join(c.itertext())
                     for c in nyja if not c.findall("{*}f")}
            nyja.clear()
            if not kolona:
                if not {"ID", "start_date", "receiver_country", "name", "incident_type"} <= set(fusha.values()):
                    raise ValueError("kolonat nuk përputhen me eksportin TableView")
                kolona = fusha
            else:
                yield {kolona[k]: v for k, v in fusha.items() if k in kolona}


def normalizo(r):
    try:
        vende = sorted(VENDET.intersection(v.strip() for v in r["receiver_country"].split(";")))
        ident = r["ID"]
        dita = date.fromisoformat(r["start_date"]).isoformat()
        emer, persh, lloj = r["name"], r.get("description", ""), r["incident_type"]
        if not vende or not re.fullmatch(r"[0-9]{1,12}", ident):
            return None
        if not (0 < len(emer) <= 2000 and len(persh) <= 64000 and 0 < len(lloj) <= 500):
            return None
        url = r.get("incident_url") or None
        if url:
            u = urlsplit(url)
            if (len(url) > 2048 or u.scheme != "https" or u.hostname not in {"eurepoc.eu", "www.eurepoc.eu"}
                    or u.username or u.password or u.port not in (None, 443)):
                return None
        def terma(s):
            return " ".join(sorted(TERMA.intersection(re.findall(r"[a-z]+", s.lower()))))
        tipi = terma(lloj)
        titull = f"EuRepoC #{ident} · {', '.join(vende)} · {terma(emer) or tipi or 'incident'}"[:200]
        return ident, titull, terma(persh), dita, ";".join(vende), tipi, url
    except (KeyError, ValueError, TypeError, AttributeError):
        return None


def perditeso():
    """Import atomik. Cache-i është i vlefshëm për shtatë ditë."""
    try:
        DOSJA.mkdir(exist_ok=True)
        skedar = Path(os.environ.get("EUREPOC_XLSX", DOSJA / "eurepoc.xlsx"))
        baza = DOSJA / "eurepoc.db"
        with closing(sqlite3.connect(baza)) as c, c:
            c.execute("CREATE TABLE IF NOT EXISTS gjendja (koha REAL, eksport TEXT)")
            gj = c.execute("SELECT koha, eksport FROM gjendja").fetchone()
            shenja = str((str(skedar.resolve()), skedar.stat().st_mtime_ns, skedar.stat().st_size)) if skedar.is_file() else None
            if gj and time.time() - gj[0] < 7 * 86400:
                return True
            if not shenja:
                raise ValueError("mungon eksporti data/eurepoc.xlsx ose EUREPOC_XLSX")
            c.execute("BEGIN IMMEDIATE")
            c.execute("CREATE TABLE IF NOT EXISTS incidente (id TEXT PRIMARY KEY, titull, persh, data, vende, lloj, url)")
            c.execute("DELETE FROM incidente")
            numri = 0
            for r in lexo_rreshtat(skedar):
                incident = normalizo(r)
                if incident:
                    c.execute("INSERT OR REPLACE INTO incidente VALUES (?,?,?,?,?,?,?)", incident)
                    numri += 1
            if not numri:
                raise ValueError("eksporti nuk përmban rreshta rajonalë të vlefshëm")
            c.execute("DELETE FROM gjendja")
            c.execute("INSERT INTO gjendja VALUES (?,?)", (time.time(), shenja))
        return True
    except Exception as gabim:
        print(f"EuRepoC: rifreskimi dështoi ({gabim}).")
        return False


def konteksti(lloji, dita, tekst, incidente):
    if lloji not in LLOJET:
        return []
    fj = fjalet(tekst)
    raste, historik = [], []
    for ident, titull, persh, data, vende, tipi, url in incidente:
        larg = (dita - date.fromisoformat(data)).days
        if lloji == "cyber" and 0 < larg <= 365 and "Kosovo" in vende.split(";"):
            historik.append((data, ident, titull, url))
        if abs(larg) > DITET or not fj:
            continue
        bashke = fj & fjalet(" ".join((titull, persh, tipi)))
        pike = len(bashke) / len(fj)
        if len(bashke) >= 2 and pike >= PRAGU:
            raste.append((pike, abs(larg), ident, dict(burimi="EuRepoC", lloji="rast_i_ngjashem",
                titulli=titull, url=url, data=data, ngjashmeria=pike,
                arsyeja=f"Fjalë të përbashkëta: {', '.join(sorted(bashke))}; {abs(larg)} ditë larg.")))
    dalja = [v[3] for v in sorted(raste, key=lambda v: (-v[0], v[1], v[2]))[:3]]
    if lloji == "cyber":
        data, _, fundit, url = max(historik, default=(None, "", "", None))
        dalja.append(dict(burimi="EuRepoC", lloji="statistike", titulli=f"Kosovë: {len(historik)} incidente në eksport gjatë 365 ditëve paraprake",
                          data=data, url=url, ngjashmeria=None, arsyeja=f"Më i fundit: {fundit}" if fundit else "Asnjë rast për këtë periudhë në eksport."))
    return dalja


def bashko(vjeter, reja):
    return [v for v in vjeter if not isinstance(v, dict) or v.get("burimi") != "EuRepoC"] + reja


def pasuro_te_gjitha() -> int:
    try:
        if not perditeso():
            return 0
        with closing(sqlite3.connect(DOSJA / "eurepoc.db")) as cache:
            incidente = cache.execute("SELECT * FROM incidente ORDER BY id").fetchall()
        numri = 0
        with closing(db.lidhu()) as lidhja:
            for e in db.ngjarjet():
                if e["lloji"] not in LLOJET:
                    continue
                det = json.loads(e["detajet_json"] or "{}")
                urls = json.loads(e["burimet"])
                artikuj = lidhja.execute("SELECT substr(teksti_perkthyer,1,2000) FROM articles WHERE url IN (SELECT value FROM json_each(?)) ORDER BY url", (json.dumps(urls),))
                tekst = " ".join([e["titulli"]] + [r[0] for r in artikuj if r[0]])
                reja = konteksti(e["lloji"], date.fromisoformat(e["data"][:10]), tekst, incidente)
                lista = bashko(det.get("konteksti", []), reja)
                if lista != det.get("konteksti", []):
                    det["konteksti"] = lista
                    db.ruaj_besueshmerine(e["id"], e["besueshmeria"], det)
                numri += bool(reja)
        return numri
    except Exception as gabim:
        print(f"EuRepoC: pasurimi u ndërpre ({gabim}).")
        return 0


def kontrollet():
    tekst = "Cyber attack knocks Kosovo municipal websites offline"
    dita = date(2026, 11, 17)
    r = dict(ID="1", name="DDoS on Kosovo government municipal websites",
             incident_type="Disruption", receiver_country="Kosovo", start_date="2026-11-16")
    incidente = [normalizo(r), normalizo(dict(r, ID="2", start_date="2026-05-17"))]
    reja = konteksti("cyber", dita, tekst, incidente)
    assert len(reja) == 2 and reja[0]["data"] == "2026-11-16"
    assert reja[1]["lloji"] == "statistike" and "2 incidente" in reja[1]["titulli"]
    assert konteksti("murder", dita, tekst, incidente) == []
    tjeter = [{"burimi": "EUvsDisinfo"}]
    assert bashko(bashko(tjeter, reja), reja) == tjeter + reja
    for ndryshim in [dict(incident_url="https://example.org"), dict(start_date="bad"),
                     dict(name="x"*2001), dict(receiver_country="Italy"), dict(incident_type=None)]:
        assert normalizo(dict(r, **ndryshim)) is None
    print("EuRepoC: kontrollet kaluan.")


if __name__ == "__main__":
    kontrollet()
    print(f"EuRepoC: {pasuro_te_gjitha()} ngjarje me kontekst.")

