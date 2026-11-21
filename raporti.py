"""raporti.py - Raporti ditor (një faqe) për analistin: Urgjente, Raporte, trendet, boshllëqet, burimet.

Nis me:  python raporti.py              (raporti i sotëm te raportet/raporti_YYYY-MM-DD.md)
         python raporti.py 2026-11-18   (raporti për një datë)

Merr ngjarjet e 7 ditëve deri te data. Ngjarjet që analisti i hodhi poshtë s'futen.
Sistemi sugjeron; çdo vendim e merr analisti. Dosja raportet/ s'shkon në Git.
"""
import importlib
import json
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import db
import kercenimet
import patterns

DOSJA = Path(__file__).resolve().parent / "raportet"
DITET = 7
MAKS_URGJENTE, MAKS_RAPORTE, MAKS_BURIME = 10, 15, 10
RENDI = {"URGJENTE": 0, "RAPORT": 1, "MONITORIM": 2, "ARKIV": 3}
B_VEPRIM = 0.80  # si te rreziku.py: nën këtë, URGJENTE do të thotë "për verifikim, jo për veprim"


# ---------------- Ndihmës (i përdor edhe dashboard.py) ----------------
def rresht(t, maks=200):
    """Tekst në një rresht, pa ndryshime të tjera (për HTML dhe grafikë, ku escape-i bëhet veçmas)."""
    return re.sub(r"\s+", " ", str(t or "")).strip()[:maks]


def pastro(t, maks=200):
    """Tekst nga lajmet ose nga modeli për markdown: një rresht, me shenjat speciale të neutralizuara
    (escape, jo fshirje, që "0.4 < 0.8" të mbetet i lexueshëm)."""
    return re.sub(r"([\\`*_\[\]<>#|])", r"\\\1", rresht(t, maks))


def url_e_sigurt(u):
    """URL-ja vetëm nëse është http(s) e thjeshtë; përndryshe None (p.sh. javascript:, gold://)."""
    return u if isinstance(u, str) and re.fullmatch(r"https?://[^\s<>()\[\]\"']+", u) else None


def ngjarjet(vendimet=None):
    """Ngjarjet si dict, me "det", "burimet_l" dhe vendimin e analistit.
    Çelësi i vendimit: db.url_i_vendimit, që vendimi s'humbet kur hyn një artikull më i hershëm."""
    vendimet = db.vendimet() if vendimet is None else vendimet
    dalja = []
    for r in db.ngjarjet():
        e = dict(r)
        try:
            det = json.loads(e.get("detajet_json") or "{}")
            burimet = json.loads(e.get("burimet") or "[]")
        except ValueError:
            det, burimet = {}, []
        det = det if isinstance(det, dict) else {}
        burimet = [u for u in burimet if isinstance(u, str)] if isinstance(burimet, list) else []
        kyc = db.url_i_vendimit(burimet, vendimet) if burimet else None
        v = vendimet.get(kyc) or {}
        e.update(det=det, burimet_l=burimet, url_kryesor=kyc,
                 statusi=v.get("statusi") or "e pakonfirmuar", shenimi=v.get("shenimi") or "")
        dalja.append(e)
    return dalja


def prioriteti(e):
    p = e["det"].get("prioriteti")
    return p if p in RENDI else None


def rreziku(e):
    """(pikët, niveli, arsyet) nga rreziku.py; (None, None, []) kur s'është llogaritur."""
    r = e["det"].get("rreziku")
    if not isinstance(r, dict):
        return None, None, []
    p = r.get("pike") if isinstance(r.get("pike"), (int, float)) else None
    a = [x for x in r.get("arsyet") or [] if isinstance(x, str)]
    return p, r.get("niveli") if isinstance(r.get("niveli"), str) else None, a


def admiralty(e):
    a = e["det"].get("admiralty")
    return a.get("kodi") if isinstance(a, dict) and isinstance(a.get("kodi"), str) else None


def besueshmeria(e):
    b = e.get("besueshmeria")
    return b if isinstance(b, (int, float)) else None


def per_verifikim(e):
    """URGJENTE me besueshmëri të ulët dhe pa konfirmim: për verifikim, jo për veprim."""
    b = besueshmeria(e)
    return e["statusi"] != "e konfirmuar" and (b is None or b < B_VEPRIM)


def kategoria(e):
    k = e["det"].get("kategoria")
    return kercenimet.emri(k) if isinstance(k, str) and kercenimet.kategoria_valide(k) else (e.get("lloji") or "-")


def renditja(e):
    """Për renditje: prioriteti, pastaj rreziku më i lartë, pastaj më e reja."""
    p, _, _ = rreziku(e)
    return RENDI.get(prioriteti(e), 4), -(p if p is not None else -1), str(e.get("data") or "")[::-1]


def brenda(e, nga, deri):
    try:
        d = datetime.strptime(str(e.get("data"))[:10], "%Y-%m-%d").date()
    except ValueError:
        return False
    return nga <= d <= deri


# ---------------- Raporti ----------------
def rreshti(e, nr):
    """Blloku markdown i një ngjarjeje."""
    p, niveli, arsyet = rreziku(e)
    b = besueshmeria(e)
    kodi = admiralty(e)
    koka = [str(e.get("data") or "")[:10], pastro(e.get("vendi"), 60) or "vendi i panjohur",
            pastro(kategoria(e), 60),
            f"rreziku {p}/100 ({niveli})" if p is not None else "rreziku i pallogaritur",
            f"besueshmëria {b:.0%}" if b is not None else "besueshmëria e pavlerësuar"]
    if kodi:
        koka.append(f"Admiralty {kodi}")
    koka.append(f"vendimi: {e['statusi']}")
    rr = [f"**{nr}. {pastro(e.get('titulli'))}**", f"- {' · '.join(koka)}"]
    if prioriteti(e) == "URGJENTE" and per_verifikim(e):
        rr.append("- ⚠️ **Për verifikim, jo për veprim:** besueshmëria është e ulët ose e pavlerësuar.")
    if e["det"].get("rajonale") is True:
        rr.append("- Ngjarje rajonale (jashtë Kosovës).")
    pse = [pastro(a, 120) for a in arsyet if not a.startswith("rreziku ")][:3]
    if pse:
        rr.append("- Pse: " + "; ".join(pse))
    try:
        bosh = [pastro(x, 80) for x in json.loads(e.get("boshllequet") or "[]")]
    except ValueError:
        bosh = []
    if bosh:
        rr.append("- Boshllëqet: " + ", ".join(bosh))
    if e["shenimi"]:
        rr.append(f"- Shënimi i analistit: {pastro(e['shenimi'], 150)}")
    urls = [u for u in map(url_e_sigurt, e["burimet_l"]) if u][:3]
    if urls:
        rr.append("- Burimet: " + ", ".join(f"<{u}>" for u in urls)
                  + (f" (+{len(e['burimet_l']) - len(urls)})" if len(e["burimet_l"]) > len(urls) else ""))
    return "\n".join(rr)


def burimet_e_dezinformimit():
    try:
        b = importlib.import_module("kontekst_dezinformim").burimet_e_dezinformimit()
    except Exception:  # moduli ose CSV-ja mungon: raporti s'bie
        return []
    return b if isinstance(b, list) else []


def permbajtja(te_gjitha, deri, fillimi_mbledhjes=None):
    """Teksti markdown i raportit për dritaren 7-ditore deri te 'deri' (date)."""
    nga = deri - timedelta(days=DITET - 1)
    dritarja = [e for e in te_gjitha if brenda(e, nga, deri)]
    hedhur = [e for e in dritarja if e["statusi"] == "e hedhur poshtë"]
    aktive = sorted((e for e in dritarja if e["statusi"] != "e hedhur poshtë"), key=renditja)
    urgjente = [e for e in aktive if prioriteti(e) == "URGJENTE"]
    raporte = [e for e in aktive if prioriteti(e) in ("RAPORT", "MONITORIM")]
    pa_rrezik = [e for e in aktive if prioriteti(e) is None]

    md = [f"# Raporti ditor OSINT: {deri:%d.%m.%Y}",
          f"_Ngjarjet e {DITET} ditëve {nga:%d.%m}–{deri:%d.%m.%Y}. Burime publike; rreziku me rregulla, "
          f"besueshmëria nga provat. Sistemi sugjeron, analisti vendos._", "", "## BLUF"]
    verif = sum(per_verifikim(e) for e in urgjente)
    md.append(f"- **{len(urgjente)} urgjente** ({verif} prej tyre për verifikim), "
              f"**{sum(prioriteti(e) == 'RAPORT' for e in raporte)} raporte**, "
              f"{sum(prioriteti(e) == 'MONITORIM' for e in raporte)} në monitorim.")
    if urgjente:
        e = urgjente[0]
        md.append(f"- Më e rëndësishmja: **{pastro(e.get('titulli'))}** ({pastro(kategoria(e), 60)}, "
                  f"{pastro(e.get('vendi'), 60) or 'vendi i panjohur'}).")
    else:
        md.append("- S'ka ngjarje urgjente në këtë periudhë.")
    if hedhur:
        md.append(f"- {len(hedhur)} ngjarje i hodhi poshtë analisti; s'përfshihen.")
    if pa_rrezik:
        md.append(f"- {len(pa_rrezik)} ngjarje pa vlerësim rreziku (rreziku.py s'ka kaluar për to).")

    md += ["", "## Urgjente"]
    md += [rreshti(e, i) + "\n" for i, e in enumerate(urgjente[:MAKS_URGJENTE], 1)] or ["S'ka.", ""]
    if len(urgjente) > MAKS_URGJENTE:
        md.append(f"_+{len(urgjente) - MAKS_URGJENTE} të tjera në dashboard._\n")

    md += ["## Raporte"]
    md += [rreshti(e, i) + "\n" for i, e in enumerate(raporte[:MAKS_RAPORTE], 1)] or ["S'ka.", ""]
    if len(raporte) > MAKS_RAPORTE:
        md.append(f"_+{len(raporte) - MAKS_RAPORTE} të tjera në dashboard._\n")

    md += ["## Trendet"]
    para = [e for e in te_gjitha if e["statusi"] != "e hedhur poshtë"
            and brenda(e, nga - timedelta(days=DITET), nga - timedelta(days=1))]
    tani, me_pare = Counter(map(kategoria, aktive)), Counter(map(kategoria, para))
    for k, n in tani.most_common(6):
        md.append(f"- {pastro(k, 60)}: {n} ngjarje (7 ditët para: {me_pare.get(k, 0)})")
    if not tani:
        md.append("- S'ka ngjarje në këtë periudhë.")
    alarmet = patterns.rritjet(aktive, sot=deri.isoformat(), fillimi_mbledhjes=fillimi_mbledhjes)
    md += [f"- ⚠️ {patterns.pershkrim(a)}" for a in alarmet]
    if fillimi_mbledhjes and not patterns.histori_e_mjaftueshme(fillimi_mbledhjes, deri.isoformat()):
        md.append("- Alarmet për rritje aktivizohen pas 5 javë mbledhjeje.")

    md += ["", "## Boshllëqet e informacionit"]
    bosh = []
    for e in urgjente + raporte:
        try:
            b = [pastro(x, 80) for x in json.loads(e.get("boshllequet") or "[]")]
        except ValueError:
            b = []
        if prioriteti(e) == "URGJENTE" and per_verifikim(e):
            b.insert(0, "duhet konfirmim nga burim zyrtar ose i pavarur")
        if b:
            bosh.append(f"- {pastro(e.get('titulli'), 90)}: {', '.join(b)}")
    md += bosh[:12] or ["- S'ka boshllëqe të shënuara."]

    md += ["", "## Burimet"]
    mediat = Counter(m for e in aktive for m in e["det"].get("mediat") or [] if isinstance(m, str))
    for m, n in mediat.most_common(MAKS_BURIME):
        u = sum(m in (e["det"].get("mediat") or []) for e in urgjente)
        md.append(f"- {pastro(m, 60)}: {n} ngjarje" + (f" ({u} urgjente)" if u else ""))
    if not mediat:
        md.append("- S'ka burime në këtë periudhë.")
    dez = burimet_e_dezinformimit()
    if dez:
        md.append("\n**Burime me raste të dokumentuara dezinformimi (EUvsDisinfo):** "
                  + ", ".join(f"{pastro(b.get('emri'), 60)} ({b.get('raste')})" for b in dez[:5]))
    else:
        md.append("\n_Lista e EUvsDisinfo mungon: vendos data/euvsdisinfo.csv (shih kontekst_dezinformim.py)._")

    md += ["", f"_Gjeneruar më {datetime.now():%d.%m.%Y %H:%M}. Sugjerim automatik, jo vlerësim "
           "përfundimtar: çdo vendim e merr analisti._", ""]
    return "\n".join(md)


def gjenero(data=None, dosja=None):
    """Shkruan raportet/raporti_YYYY-MM-DD.md dhe kthen shtegun. data: "YYYY-MM-DD" ose None (sot)."""
    deri = datetime.strptime(str(data)[:10], "%Y-%m-%d").date() if data else date.today()
    dosja = Path(dosja) if dosja else DOSJA
    dosja.mkdir(parents=True, exist_ok=True)
    shtegu = dosja / f"raporti_{deri.isoformat()}.md"
    shtegu.write_text(permbajtja(ngjarjet(), deri, db.fillimi_i_mbledhjes()), encoding="utf-8")
    return shtegu


if __name__ == "__main__":
    import tempfile
    # Kontrolle me bazë të përkohshme (osint.db s'preket)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        origjinali, db.DB_PATH = db.DB_PATH, str(Path(tmp, "test.db"))

        def ngj(titulli, data, p, pike, b, url, **det):
            return db.ruaj_ngjarje(
                titulli=titulli, data=data, gjuha="sq", burimet=[url, "javascript:alert(1)"],
                boshllequet=["vetëm një burim"], vendi="Zvečan", besueshmeria=b,
                detajet={"prioriteti": p, "rreziku": {"pike": pike, "niveli": "i lartë",
                                                      "arsyet": ["aktori: shteti_serb → +10"]},
                         "admiralty": {"kodi": "B2"}, "kategoria": "ushtarak_serbia",
                         "mediat": ["Koha"], **det})
        ngj("Trupa pranë vijës | rreshti\nri", "2026-11-18", "URGJENTE", 80, 0.9, "https://a.example/1")
        ngj("Thashethem për sulm", "2026-11-17", "URGJENTE", 70, 0.4, "https://a.example/2")
        ngj("Protestë e vogël", "2026-11-16", "RAPORT", 40, 0.7, "https://a.example/3")
        ngj("Lajm i hedhur poshtë", "2026-11-18", "URGJENTE", 90, 0.9, "https://a.example/4")
        ngj("Ngjarje e vjetër", "2026-10-01", "URGJENTE", 95, 0.9, "https://a.example/5")
        db.ruaj_ngjarje(titulli="Pa rrezik", data="2026-11-18", gjuha="sq",
                        burimet=["https://a.example/6"], boshllequet=[])
        db.ruaj_vendimin("https://a.example/4", "e hedhur poshtë")
        db.ruaj_vendimin("https://a.example/1", "e konfirmuar", "e konfirmoi Policia")
        r = permbajtja(ngjarjet(), date(2026, 11, 18))
        assert "**2 urgjente** (1 prej tyre për verifikim)" in r, r
        assert r.index("Trupa pranë vijës") < r.index("Thashethem për sulm") < r.index("Protestë e vogël")
        assert "Lajm i hedhur poshtë" not in r and "Ngjarje e vjetër" not in r
        assert "1 ngjarje i hodhi poshtë analisti" in r and "1 ngjarje pa vlerësim rreziku" in r
        assert "javascript:" not in r and "Trupa pranë vijës \\| rreshti ri" in r
        assert pastro("0.4 < 0.8 [x](y)") == "0.4 \\< 0.8 \\[x\\](y)" and rresht("a\n  b") == "a b"
        assert "Për verifikim, jo për veprim" in r and "e konfirmoi Policia" in r and "Admiralty B2" in r
        shtegu = gjenero("2026-11-18", tmp)
        assert shtegu.name == "raporti_2026-11-18.md"
        assert shtegu.read_text(encoding="utf-8").startswith("# Raporti ditor OSINT: 18.11.2026")
        db.DB_PATH = origjinali
    print("Kontrollet kaluan.")
    print(f"Raporti: {gjenero(sys.argv[1] if len(sys.argv) > 1 else None)}")
