"""rreziku.py - Rrezikshmëria (0-100), prioriteti dhe kodi NATO/Admiralty për çdo ngjarje.

Me rregulla të qarta, pa model:
- rreziku    = sa e rëndë do ishte ngjarja për FSK-në/sigurinë NËSE është e vërtetë (jo probabilitet);
- besueshmëria (scoring.py) = sa gjasa ka që të jetë e vërtetë;
- prioriteti = matrica rrezik x besueshmëri; admiralty = burimi A-F + informacioni 1-6 (AJP-2.1).
Besueshmëria s'ndryshohet kurrë këtu.
"""
import importlib
import json
import os
import re
import tempfile
from datetime import date, datetime

import db
import kercenimet
import scoring
from correlator import DOMENET, gjej_vendin

PIKE_PER_BAZE = 8  # x rrezikshmeria_baze (1..5) -> 8..40
# shortcut: baza nga "type" i vjetër kur kategoria mungon/është "tjeter"; hiqe kur K3 të jetë stabil
LLOJI_RB = {"explosion_weapons": 4, "cyber": 4, "infrastructure_disruption": 4, "border_incident": 3,
            "police_military_operation": 3, "interethnic": 3, "protest_unrest": 3,
            "disinformation": 3, "violence": 2, "murder": 2}
SHENJESTRA = {"fsk": 15, "infrastrukture_kritike": 12, "kfor_nato": 12, "institucione": 8,
              "komunitete": 6, "ekonomi": 4, "shoqeri": 3}
LIDHJE_FSK = 10  # FSK e përfshirë/prekur, por jo shenjestër e drejtpërdrejtë
AKTORI = {"shteti_serb": 10, "grupe_te_armatosura": 10, "rusia": 8, "grupe_ekstremiste": 7,
          "kina": 5, "krim_i_organizuar": 5, "media_propagandistike": 3}
# Emrat kanonikë të correlator.gjej_vendin: veriu, pikat kufitare/vija administrative dhe komunat
# serbe ngjitur me Kosovën. shortcut: "mitrovic" përfshin edhe jugun; ndaje kur correlator t'i dallojë
ZONA = {"mitrovic", "zvecan", "leposavi", "zubin potok", "veri", "jarinj", "bernjak", "banjsk",
        "podujev", "raska", "kursumlija", "medvedja", "bujanovac", "presevo"}
# Përmbledhja (titulli) është në anglisht; emrat e vendeve edhe në sq/sr
OBJEKTE = re.compile(r"\b(dam|reservoir|substation|power plant|power line|pipeline|water supply|"
                     r"canal|barracks|military base|airport|border crossing)\b|gazivod|ujman|"
                     r"bondsteel|trepca|trepç|ibar-lepenac|iber-lepenac|ibër-lepenc", re.I)
PRAGU_LARTE, PRAGU_MESEM = 55, 35
# Kërcënim i drejtpërdrejtë për sulm (p.sh. postimi "we will attack today in kosova"): modeli e përmbledh
# si "threatened to carry out an attack", por shpesh pa kategori. Përmbledhja (titulli) është në anglisht.
KERCENIM = re.compile(r"\b(?:threat\w*\s+(?:to\s+)?(?:carry\s+out\s+)?(?:an?\s+)?(?:\w+\s+)?attacks?\b"
                      r"|(?:plan\w*|vow\w*|announc\w*|call\w*\s+for)\s+(?:an?\s+)?(?:\w+\s+)?attacks?\b"
                      r"|(?:will|going\s+to)\s+attack\b)", re.I)
# Demantimet dhe lajmet e rreme për kërcënime s'janë vetë kërcënime
JO_KERCENIM = re.compile(r"\b(?:no|false\w*|fake|den(?:y|ies|ied)|hoax|rumou?r\w*)\b", re.I)
KERCENIM_PIKE = 10
# Shenjestrat që e lidhin një ngjarje rajonale drejtpërdrejt me Kosovën
RAJONALE_ME_LIDHJE = {"fsk", "kfor_nato", "institucione", "infrastrukture_kritike"}
B_LARTE, B_ULET = 0.80, 0.50  # 80% = "highly likely" (PHIA); nën 50% = më pak se gjasa të barabarta
# niveli -> prioriteti për besueshmërinë (e lartë, e mesme, e ulët)
MATRICA = {"i lartë": ("URGJENTE", "URGJENTE", "URGJENTE"),
           "i mesëm": ("RAPORT", "RAPORT", "MONITORIM"),
           "i ulët": ("MONITORIM", "ARKIV", "ARKIV")}
RENDI_BURIMIT = "BCDFE"  # më i miri i pari; "A" s'jepet kurrë automatikisht (shih docs)
SOCIALE = ("Telegram:", "YouTube:", "Reddit:", "X:")  # apify_burimi.py shton Reddit dhe X
RASTE_PER_E = 3  # raste të dokumentuara dezinformimi -> "histori informacioni të pavlefshëm"
DOMENI = {v: k for k, v in DOMENET.items()}  # "Koha" -> "koha.net"


def dita(s):
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def maks(vlerat):
    v = [x for x in vlerat or [] if type(x) is int and 0 <= x <= 100000]
    return max(v) if v else 0


def kategoria(det):
    k = det.get("kategoria")
    return k if isinstance(k, str) and kercenimet.kategoria_valide(k) else "tjeter"


def baza(kat):
    rb = kercenimet.KATEGORITE.get(kat, {}).get("rrezikshmeria_baze")
    return rb if type(rb) is int and 1 <= rb <= 5 else 1


def besueshmeria_valide(b):
    """Baza e vjetër mund të mos ketë ende një besueshmëri të vlefshme."""
    return b if type(b) in (int, float) and 0 <= b <= 1 else None


def brezi_besueshmerise(b, statusi):
    if statusi == "e konfirmuar" or (b is not None and b >= B_LARTE):
        return 0
    return 1 if b is not None and b >= B_ULET else 2


def prioriteti_sipas(niveli, brezi, statusi):
    if statusi == "e hedhur poshtë":
        return "ARKIV"
    if isinstance(niveli, str) and niveli in MATRICA:
        return MATRICA[niveli][brezi]
    return None


def statusi_i(e, vendimet):
    """Vendimi i analistit te cilado URL e ngjarjes (db.url_i_vendimit), që të mos humbasë kur
    korrelimi sjell një artikull më të hershëm në vend të burimet[0]."""
    vendimet = vendimet or {}
    try:
        return vendimet.get(db.url_i_vendimit(json.loads(e["burimet"] or "[]"), vendimet), {}).get("statusi")
    except (ValueError, IndexError, TypeError, KeyError):
        return None


def shkronja(m, dez):
    """Besueshmëria e burimit A-F për një medium."""
    raste = dez.get(DOMENI.get(m, m).lower(), 0)
    if raste >= RASTE_PER_E:
        return "E"
    v = scoring.MEDIAT.get(m)
    s = "F" if v is None else "B" if v >= 0.80 else "C" if v >= 0.60 else "D"
    if (m.startswith(SOCIALE) or raste) and s in "BC":
        s = "D"
    return "D" if raste and s == "F" else s


def informacioni_admiralty(det, statusi):
    if statusi == "e hedhur poshtë":
        return 5
    if statusi == "e konfirmuar":
        return 1
    mediat = [m for m in det.get("mediat") or [] if isinstance(m, str)]
    soc = sum(m.startswith(SOCIALE) for m in mediat)
    n = det.get("burime_te_pavarura")
    if type(n) is not int or n < 0:  # det i vjetër, para se scoring.py t'i grupojë ripostimet
        n = len(mediat) - soc + min(1, soc)  # kanalet sociale (shpesh ripostime) = një burim
    k = len(scoring.pike_detajesh(det, n)[1])
    rast = any(isinstance(c, dict) and c.get("lloji") == "rast_i_ngjashem" for c in det.get("konteksti") or [])
    if n >= 2:
        gjuhet = det.get("gjuhet_e_pavarura", det.get("gjuhet")) or []
        return (1 if len(gjuhet) >= 2 or n >= 3 else 2) if k == 0 else 3 if k == 1 else 4
    return 3 if n == 1 and rast else 6


def admiralty(det, statusi, dez):
    mediat = [m for m in det.get("mediat") or [] if isinstance(m, str)]
    # Pas scoring.py: vetëm origjinat janë burime; një kopje s'konfirmon dhe s'e ngre shkronjën e burimit.
    origjinat = [m for m in det.get("mediat_e_pavarura") or [] if isinstance(m, str)] or mediat
    burimi = min((shkronja(m, dez) for m in origjinat), key=RENDI_BURIMIT.index, default="F")
    info = informacioni_admiralty(det, statusi)
    return {"burimi": burimi, "informacioni": info, "kodi": f"{burimi}{info}"}


def ndikimi_21(e, det, pike, b, statusi):
    """Lista e 21 kategorive: kategoria kryesore dhe shtesë, ndikimi, urgjenca dhe verifikimi urgjent.
    Rregulla paraprake (treguesit i miraton personi përgjegjës); ndikimi s'varet nga besueshmëria."""
    kat = kercenimet.kategorite_21(f"{e.get('titulli') or ''} {e.get('vendi') or ''}", det.get("kategoria"),
                                   det.get("aktori"), det.get("shenjestrat"))
    k, i = maks(det.get("killed")), maks(det.get("injured"))
    if i >= 10 and 14 not in kat:
        kat.append(14)  # ngjarje me shumë të lënduar = edhe krizë shëndetësore
    esenciale = len(kercenimet.SHERBIME_ESENCIALE & set(kat))
    if not kat and not k and not i:
        ndikimi, pse = "i papërcaktuar", "s'ka shenja të mjaftueshme për asnjë kategori"
    elif k >= 3 or i >= 10 or (esenciale >= 2 and pike >= PRAGU_LARTE):
        ndikimi, pse = "kritik", f"{k} të vdekur, {i} të plagosur, {esenciale} shërbime esenciale, rreziku {pike}"
    elif k >= 1 or i >= 3 or pike >= PRAGU_LARTE:
        ndikimi, pse = "i lartë", f"{k} të vdekur, {i} të plagosur, rreziku {pike}"
    elif i >= 1 or pike >= PRAGU_MESEM:
        ndikimi, pse = "mesatar", f"{i} të plagosur, rreziku {pike}"
    else:
        ndikimi, pse = "i ulët", f"rreziku {pike}, pa viktima"
    # Ndikim potencialisht i rëndë me prova të kufizuara: verifikim urgjent
    verifikim = (ndikimi in ("kritik", "i lartë") and statusi not in ("e konfirmuar", "e hedhur poshtë")
                 and (b is None or b < B_LARTE))
    return {"kategorite": kat, "ndikimi": ndikimi, "pse": pse,
            "urgjenca": ("afatgjatë" if kercenimet.KATEGORITE_21[kat[0]]["afatgjate"] else "në zhvillim")
            if kat else "e papërcaktuar", "verifikim_urgjent": verifikim}


def vlereso(e, det, *, sot=None, te_tjerat=(), vendimet=None, dez=None):
    """Kthen {"rreziku", "prioriteti", "admiralty"} për një ngjarje (s'e ndryshon det).
    te_tjerat: [(id, kategoria, data, vendi_kanonik)] për trendin; sot: "YYYY-MM-DD" (testet/eval)."""
    e = dict(e)
    sot = dita(sot) or date.today()
    arsyet = []

    def shto(p, teksti):
        if p:
            arsyet.append(f"{teksti} → +{p}")
        return p

    kat = kategoria(det)
    titulli = e.get("titulli") if isinstance(e.get("titulli"), str) else ""
    kercenim = bool(KERCENIM.search(titulli)) and not JO_KERCENIM.search(titulli)
    if kercenim and kat == "tjeter":
        kat = "ekstremizem_terrorizem"  # kërcënimi për sulm s'mbetet "tjetër" kur modeli s'i jep kategori
    rb = baza(kat) if kat != "tjeter" else LLOJI_RB.get(e.get("lloji"), baza("tjeter"))
    burim_baze = kat if kat != "tjeter" or e.get("lloji") not in LLOJI_RB else f"lloji i vjetër {e['lloji']}"
    pike = shto(PIKE_PER_BAZE * rb, f"kategoria: {burim_baze} (rrezikshmëri bazë {rb}/5)")
    shenjestrat = list(det.get("shenjestrat") or [])
    if kercenim and re.search(r"kosov", titulli, re.I) and not shenjestrat:
        shenjestrat = ["institucione"]  # sulm i paralajmëruar "në Kosovë" pa shenjestër më të saktë
    p, s = max(((SHENJESTRA[x], x) for x in shenjestrat if x in SHENJESTRA), default=(0, None))
    if det.get("lidhje_me_fsk") is True and p < LIDHJE_FSK:
        p, s = LIDHJE_FSK, "lidhje me FSK-në"
    pike += shto(p, f"shenjestra: {s}")
    a = det.get("aktori")
    pike += shto(AKTORI.get(a, 0) if isinstance(a, str) else 0, f"aktori: {a}")
    pike += shto(KERCENIM_PIKE if kercenim else 0, "kërcënim i drejtpërdrejtë për sulm")
    k, i, ar = (maks(det.get(x)) for x in ("killed", "injured", "arrested"))
    pike += shto(min(15, 10 * (k >= 1) + 3 * (k >= 3) + 4 * (i >= 1) + 2 * (i >= 5) + 2 * (ar >= 1)),
                 f"shkalla: {k} të vdekur, {i} të plagosur, {ar} të arrestuar")
    vendi = gjej_vendin(e.get("vendi") if isinstance(e.get("vendi"), str) else "")[0]
    obj = OBJEKTE.search(f"{e.get('titulli') or ''} {e.get('vendi') or ''}")
    pike += shto(min(8, 6 * (vendi in ZONA) + 4 * bool(obj)),
                 f"vendi: {vendi or '-'}{' (zonë e ndjeshme)' if vendi in ZONA else ''}"
                 f"{', pranë objektit: ' + obj.group(0) if obj else ''}")
    d = dita(e.get("data"))
    mosha = (sot - d).days if d else None
    p = 0 if mosha is None or mosha < 0 else 7 if mosha <= 1 else 3 if mosha <= 7 else 0
    pike += shto(p, "brenda 48 orëve" if p == 7 else "brenda 7 ditëve")
    afer = [(dita(dd), v) for (id_, kt, dd, v) in te_tjerat
            if id_ != e.get("id") and kt == kat != "tjeter" and d and dita(dd)]
    n7 = sum(0 <= (d - dd).days <= 6 for dd, _ in afer)
    zonat = {v for dd, v in afer if v and abs((d - dd).days) <= 1} | ({vendi} if vendi else set())
    pike += shto(min(10, 5 * (n7 >= 2) + 5 * (len(zonat) >= 3)),
                 f"trendi: {n7} ngjarje të tjera '{kat}' në 7 ditë, {len(zonat)} zona njëkohësisht")
    pike = max(0, min(100, pike))
    # Ngjarje rajonale pa lidhje me Kosovën (p.sh. paradë në Beograd): jo më lart se "i mesëm",
    # që "Urgjente" të mos mbushet me lajme të brendshme serbe. Pikët kufizohen nën pragun e lartë.
    if (det.get("rajonale") is True and vendi not in ZONA and det.get("lidhje_me_fsk") is not True
            and not RAJONALE_ME_LIDHJE & set(det.get("shenjestrat") or [])) and pike >= PRAGU_LARTE:
        pike = PRAGU_LARTE - 1
        arsyet.append("rajonale pa lidhje të drejtpërdrejtë me Kosovën → maksimumi i mesëm")
    nv = kercenimet.NIVELET
    niveli = nv[0] if pike >= PRAGU_LARTE else nv[1] if pike >= PRAGU_MESEM else nv[2]
    arsyet.append(f"rreziku {pike}/100 → {niveli}")

    statusi = statusi_i(e, vendimet)
    b = besueshmeria_valide(e.get("besueshmeria"))
    brezi = brezi_besueshmerise(b, statusi)
    prioriteti = prioriteti_sipas(niveli, brezi, statusi)
    if prioriteti == "URGJENTE":
        arsyet.append("URGJENTE për veprim" if brezi == 0 else
                      f"URGJENTE për verifikim, jo për veprim (besueshmëria "
                      f"{'e pavlerësuar' if b is None else f'{b} < {B_LARTE}'})")
    elif statusi == "e hedhur poshtë":
        arsyet.append("ARKIV: analisti e hodhi poshtë")
    return {"rreziku": {"pike": pike, "niveli": niveli, "arsyet": arsyet},
            "prioriteti": prioriteti, "admiralty": admiralty(det, statusi, dez or {}),
            "v21": ndikimi_21(e, det, pike, b, statusi)}


def raste_dezinformimi():
    """{domeni: raste} nga EUvsDisinfo (K5); bosh kur moduli ose CSV mungon."""
    try:
        burimet = importlib.import_module("kontekst_dezinformim").burimet_e_dezinformimit()
    except (ImportError, AttributeError, OSError, ValueError, TypeError, KeyError):
        return {}
    dez = {}
    for b in burimet if isinstance(burimet, list) else []:
        d, n = (b.get("domeni"), b.get("raste")) if isinstance(b, dict) else (None, None)
        if isinstance(d, str) and type(n) is int and n > 0:
            dez[d.lower().removeprefix("www.")] = n
    return dez


def vlereso_te_gjitha(sot=None):
    """Shton rreziku/prioriteti/admiralty te çdo ngjarje (idempotent). Kthen numrin e ngjarjeve."""
    vendimet, dez = db.vendimet(), raste_dezinformimi()
    rreshtat = []
    for e in db.ngjarjet():
        try:
            det = json.loads(e["detajet_json"] or "{}")
        except ValueError:
            det = {}
        rreshtat.append((e, det if isinstance(det, dict) else {}))
    # Ngjarjet e hedhura poshtë s'numërohen te trendi i të tjerave
    te_tjerat = [(e["id"], kategoria(det), e["data"], gjej_vendin(e["vendi"] or "")[0])
                 for e, det in rreshtat if statusi_i(e, vendimet) != "e hedhur poshtë"]
    for e, det in rreshtat:
        det.update(vlereso(e, det, sot=sot, te_tjerat=te_tjerat, vendimet=vendimet, dez=dez))
        db.ruaj_besueshmerine(e["id"], e["besueshmeria"], det)
    return len(rreshtat)


if __name__ == "__main__":
    def ng(data, vendi, titulli, b, url="u1", lloji=None, id_=1):
        return {"id": id_, "lloji": lloji, "data": data, "vendi": vendi, "titulli": titulli,
                "besueshmeria": b, "burimet": json.dumps([url])}
    SERB = {"kategoria": "ushtarak_serbia", "aktori": "shteti_serb", "shenjestrat": ["fsk", "kfor_nato"],
            "mediat": ["Balkan Insight", "Koha", "N1 Serbia"], "gjuhet": ["en", "sq", "sr"]}
    # Në formën e db.vendimet()
    VEND = {"u8": {"statusi": "e hedhur poshtë", "koha": "2026-11-21 10:00:00"},
            "u9": {"statusi": "e konfirmuar", "koha": "2026-11-21 11:00:00"}}
    DIZ = ((2, "dezinformim", "2026-11-18", None), (3, "dezinformim", "2026-11-15", None))
    BLL = ((12, "trazira_bllokada", "2026-11-21", "zvecan"), (13, "trazira_bllokada", "2026-11-20", "leposavi"))
    RASTET = [  # (ngjarja, detajet, te_tjerat, dez) -> (pike, niveli, prioriteti, kodi)
        (ng("2026-11-20", "Raška", "Serbian army units deployed near the boundary line", 0.94), SERB, (), {},
         (78, "i lartë", "URGJENTE", "B1")),
        (ng("2026-11-20", "Zvečan", "Armed group attacked a police patrol near Banjska", 0.79),
         {"kategoria": "grupe_te_armatosura", "aktori": "grupe_te_armatosura", "shenjestrat": ["institucione"],
          "mediat": ["Kallxo", "N1 Serbia"], "gjuhet": ["sq", "sr"], "killed": [1, 1], "injured": [2, 3]},
         (), {}, (85, "i lartë", "URGJENTE", "B3")),
        (ng("2026-11-21", "Jarinje", "Telegram channel claims Serbian troops crossed at Jarinje", 0.40),
         {**SERB, "shenjestrat": ["fsk"], "mediat": ["Telegram:kanali_x"], "gjuhet": ["sr"]}, (), {},
         (78, "i lartë", "URGJENTE", "F6")),
        (ng("2026-11-19", "Prishtina", "DDoS attack took down government websites", 0.80),
         {"kategoria": "kibernetik", "aktori": "i_panjohur", "shenjestrat": ["institucione"],
          "mediat": ["Koha", "RTK"], "gjuhet": ["sq"]}, (), {}, (35, "i mesëm", "RAPORT", "B2")),
        (ng("2026-11-20", None, "False claims that the KSF is preparing an attack on Serbs", 0.40),
         {"kategoria": "dezinformim", "aktori": "media_propagandistike", "shenjestrat": ["fsk"],
          "mediat": ["informer.rs"], "gjuhet": ["sr"], "konteksti": [{"lloji": "rast_i_ngjashem"}]},
         DIZ, {"informer.rs": 4}, (54, "i mesëm", "MONITORIM", "E3")),
        (ng("2026-11-11", "Podujevo", "Police arrested two people smuggling cigarettes", 0.80),
         {"kategoria": "kufi_kontrabande", "aktori": "krim_i_organizuar", "shenjestrat": ["ekonomi"],
          "mediat": ["Koha", "RTK"], "gjuhet": ["sq"], "arrested": [2, 2]}, (), {},
         (33, "i ulët", "MONITORIM", "B2")),
        (ng("2026-11-01", "Prizren", "Traffic accident on the main road", 0.40),
         {"kategoria": "tjeter", "mediat": ["example.com"], "gjuhet": ["en"]}, (), {}, (8, "i ulët", "ARKIV", "F6")),
        (ng("2026-11-20", "Raška", "Serbian army units deployed near the boundary line", 0.94, url="u8"),
         SERB, (), {}, (78, "i lartë", "ARKIV", "B5")),
        (ng("2026-11-21", "Zubin Potok", "Unidentified drone flew over the Gazivoda dam", 0.54, url="u9"),
         {"kategoria": "dron_hapesire_ajrore", "aktori": "i_panjohur", "shenjestrat": ["infrastrukture_kritike"],
          "mediat": ["RTK"], "gjuhet": ["sq"]}, (), {}, (59, "i lartë", "URGJENTE", "B1")),
        (ng("2026-11-20", "Mitrovicë e Veriut", "Explosion at an electricity substation", 0.86,
            lloji="explosion_weapons"), {"mediat": ["Koha", "N1 Serbia"], "gjuhet": ["sq", "sr"]}, (), {},
         (47, "i mesëm", "RAPORT", "B1")),
        (ng("2026-11-21", "Zubin Potok", "Roadblocks set up on main roads", 0.62, id_=11),
         {"kategoria": "trazira_bllokada", "aktori": "i_panjohur", "shenjestrat": ["institucione"],
          "mediat": ["Kallxo", "Telegram:a", "Telegram:b"], "gjuhet": ["sq", "sr"]}, BLL, {},
         (63, "i lartë", "URGJENTE", "B1")),
        # T12: paradë ushtarake në Beograd, rajonale pa lidhje me Kosovën: 57 pa kufizim -> 54, i mesëm
        (ng("2026-11-20", "Belgrade", "Serbian army holds a military parade in Belgrade", 0.90),
         {"kategoria": "ushtarak_serbia", "aktori": "shteti_serb", "shenjestrat": [], "rajonale": True,
          "mediat": ["N1 Serbia", "Balkan Insight"], "gjuhet": ["sr", "en"]}, (), {},
         (54, "i mesëm", "RAPORT", "B1")),
    ]
    for e, det, tt, dez, pritet in RASTET:
        para = json.dumps(det, sort_keys=True)
        r = vlereso(e, det, sot="2026-11-21", te_tjerat=tt, vendimet=VEND, dez=dez)
        mori = (r["rreziku"]["pike"], r["rreziku"]["niveli"], r["prioriteti"], r["admiralty"]["kodi"])
        assert mori == pritet, (e["titulli"], mori, r["rreziku"]["arsyet"])
        assert r == vlereso(e, det, sot="2026-11-21", te_tjerat=tt, vendimet=VEND, dez=dez)  # idempotent
        assert json.dumps(det, sort_keys=True) == para  # det s'ndryshon
    assert "për verifikim" in vlereso(*RASTET[2][:2], sot="2026-11-21")["rreziku"]["arsyet"][-1]
    pa_b = {**RASTET[2][0], "besueshmeria": None}  # besueshmëria mungon: tekst i lexueshëm, jo "None"
    assert vlereso(pa_b, RASTET[2][1], sot="2026-11-21")["rreziku"]["arsyet"][-1].endswith("(besueshmëria e pavlerësuar)")
    # Vendimi gjendet edhe kur një artikull më i hershëm u bë burimet[0]
    e = dict(ng("2026-11-20", "Zvečan", "Road blocked", 0.9), burimet=json.dumps(["i_ri", "u8"]))
    assert statusi_i(e, VEND) == "e hedhur poshtë" and vlereso(e, {}, vendimet=VEND)["prioriteti"] == "ARKIV"
    kritike = vlereso(dict(e, besueshmeria=0.3), {"killed": [3]}, vendimet=VEND)
    assert kritike["prioriteti"] == "ARKIV" and kritike["v21"]["verifikim_urgjent"] is False
    assert besueshmeria_valide(float("nan")) is None and besueshmeria_valide(1.1) is None
    assert statusi_i(dict(e, burimet="[]"), VEND) is None and statusi_i(e, None) is None
    # Rajonalja me shenjestër në Kosovë ose me lidhje me FSK-në s'kufizohet
    parade_e, parade = RASTET[11][:2]
    for shtese in ({"shenjestrat": ["fsk"]}, {"lidhje_me_fsk": True}):
        assert vlereso(parade_e, {**parade, **shtese}, sot="2026-11-21")["rreziku"]["niveli"] == "i lartë"
    assert vlereso(parade_e, {**parade, "rajonale": False}, sot="2026-11-21")["rreziku"]["pike"] == 57
    assert any("rajonale pa lidhje" in a for a in vlereso(parade_e, parade, sot="2026-11-21")["rreziku"]["arsyet"])
    # Ripostimet (scoring.py): 3 media, 1 origjinë -> s'është "e konfirmuar nga të tjerë"
    ripost = {"mediat": ["Koha", "Telegrafi", "N1 Serbia"], "gjuhet": ["sq", "sr"]}
    assert admiralty(ripost, None, {})["kodi"] == "B1"  # det i vjetër: sjellja e mëparshme
    ripost.update(burime_te_pavarura=1, mediat_e_pavarura=["Koha"], gjuhet_e_pavarura=["sq"])
    assert admiralty(ripost, None, {})["kodi"] == "B6", admiralty(ripost, None, {})
    # Thashethem nga Telegram që e kopjon një media e besueshme: burimi mbetet F
    tg = {"mediat": ["Telegram:kanali_x", "Koha"], "gjuhet": ["sr", "sq"], "burime_te_pavarura": 1,
          "mediat_e_pavarura": ["Telegram:kanali_x"], "gjuhet_e_pavarura": ["sr"]}
    assert admiralty(tg, None, {})["kodi"] == "F6", admiralty(tg, None, {})
    # Reddit dhe X (apify_burimi.py): sociale, shumë postime = një burim, shkronja F
    assert admiralty({"mediat": ["Reddit:r/kosovo", "X:x.com", "Reddit:r/serbia"]}, None, {})["kodi"] == "F6"
    # Dy origjina të pavarura me gjuhë të ndryshme -> 1, si më parë
    dy = {**ripost, "burime_te_pavarura": 2, "mediat_e_pavarura": ["Koha", "N1 Serbia"],
          "gjuhet_e_pavarura": ["sq", "sr"]}
    assert admiralty(dy, None, {})["kodi"] == "B1"
    # Vetitë: matrica monotone, A kurrë, pa të dhëna -> i ulët/ARKIV/F6
    rendi = ["ARKIV", "MONITORIM", "RAPORT", "URGJENTE"]
    for niv in MATRICA.values():
        assert all(rendi.index(x) >= rendi.index(y) for x, y in zip(niv, niv[1:]))
    for j in range(3):
        kolona = [rendi.index(MATRICA[n][j]) for n in ("i ulët", "i mesëm", "i lartë")]
        assert kolona == sorted(kolona)
    assert vlereso({}, {}) == {"rreziku": {"pike": 8, "niveli": "i ulët", "arsyet": [
        "kategoria: tjeter (rrezikshmëri bazë 1/5) → +8", "rreziku 8/100 → i ulët"]},
        "prioriteti": "ARKIV", "admiralty": {"burimi": "F", "informacioni": 6, "kodi": "F6"},
        "v21": {"kategorite": [], "ndikimi": "i papërcaktuar", "pse": "s'ka shenja të mjaftueshme për asnjë kategori",
                "urgjenca": "e papërcaktuar", "verifikim_urgjent": False}}
    # Lista e 21 kategorive: ndikimi dhe verifikimi urgjent
    v = [vlereso(e, det, sot="2026-11-21", te_tjerat=tt, vendimet=VEND, dez=dez)["v21"]
         for e, det, tt, dez, _ in RASTET]
    assert v[0]["kategorite"][0] == 4 and v[0]["ndikimi"] == "i lartë" and not v[0]["verifikim_urgjent"]
    assert v[1]["kategorite"][0] == 1 and v[1]["ndikimi"] == "i lartë"  # 1 i vdekur, 3 të plagosur
    assert v[2]["ndikimi"] == "i lartë" and v[2]["verifikim_urgjent"]  # Telegram 0.40 -> verifikim urgjent
    assert v[11]["ndikimi"] == "mesatar" and v[11]["urgjenca"] == "në zhvillim"  # parada: 54
    assert vlereso({}, {"killed": [3]})["v21"]["ndikimi"] == "kritik"  # viktimat mjaftojnë edhe pa kategori
    assert vlereso({}, {"kategoria": "grupe_te_armatosura", "injured": [12]})["v21"]["kategorite"] == [1, 14]
    assert vlereso({}, {"kategoria": "grupe_te_armatosura", "injured": [12]})["v21"]["ndikimi"] == "kritik"
    assert vlereso({}, {"kategoria": "struktura_paralele"})["v21"]["urgjenca"] == "afatgjatë"
    for kat in ("dezinformim", "kufi_kontrabande", "tjeter"):  # një faktor i vetëm s'mjafton për "i lartë"
        for x in ({"shenjestrat": ["fsk"]}, {"aktori": "shteti_serb"}, {"killed": [5]}):
            assert vlereso({}, {"kategoria": kat, **x})["rreziku"]["niveli"] != "i lartë"
    # Kontroll me DB të përkohshme: idempotent, besueshmëria/arsyetimi s'preken, e hedhura poshtë -> ARKIV
    vjeter = db.DB_PATH
    with tempfile.TemporaryDirectory() as dosja:
        db.DB_PATH = os.path.join(dosja, "prove.db")
        try:
            baze = {"kategoria": "trazira_bllokada", "aktori": "i_panjohur", "shenjestrat": ["institucione"],
                    "mediat": ["Kallxo"], "gjuhet": ["sq"], "arsyetimi": ["nga scoring"]}
            for vendi, url in (("Zubin Potok", "a"), ("Zvečan", "b"), ("Leposavić", "c")):
                id_ = db.ruaj_ngjarje("Roadblocks set up", "2026-11-21", "sq", [url], [],
                                      lloji="protest_unrest", vendi=vendi, detajet=baze)
                db.ruaj_besueshmerine(id_, 0.55, baze)
            db.ruaj_vendimin("c", "e hedhur poshtë")
            assert vlereso_te_gjitha(sot="2026-11-21") == 3
            para = [dict(x) for x in db.ngjarjet()]
            assert vlereso_te_gjitha(sot="2026-11-21") == 3
            pas = [dict(x) for x in db.ngjarjet()]
            assert para == pas
            dets = {x["vendi"]: json.loads(x["detajet_json"]) for x in pas}
            assert all(x["besueshmeria"] == 0.55 for x in pas)
            assert all(d["arsyetimi"] == ["nga scoring"] for d in dets.values())
            assert dets["Leposavić"]["prioriteti"] == "ARKIV" and dets["Leposavić"]["admiralty"]["informacioni"] == 5
            assert not any("3 zona" in a for a in dets["Zubin Potok"]["rreziku"]["arsyet"])
        finally:
            db.DB_PATH = vjeter
    # Kërcënim i drejtpërdrejtë: "we will attack today in kosova" -> URGJENTE për verifikim (burim social F)
    kerc = {"id": 99, "titulli": "An unidentified party threatened to carry out an attack in Kosovo.",
            "data": "2026-11-22", "besueshmeria": 0.36, "burimet": json.dumps(["https://www.reddit.com/r/x/1"])}
    r = vlereso(kerc, {"mediat": ["Reddit:r/x"], "aktori": "i_panjohur"}, sot="2026-11-22")
    assert (r["rreziku"]["niveli"], r["prioriteti"]) == ("i lartë", "URGJENTE"), r["rreziku"]
    assert any("kërcënim i drejtpërdrejtë" in a for a in r["rreziku"]["arsyet"])
    for t in ("Police deny claims of a threat to attack a school in Kosovo.",
              "Kosovo football club plans attacking style for the new season.",
              "The Serbian army is scheduled to hold a training exercise near Kosovo."):
        assert vlereso({**kerc, "titulli": t}, {"mediat": ["Reddit:r/x"]}, sot="2026-11-22")["rreziku"]["niveli"] != "i lartë", t
    print(f"Kontrollet kaluan: {len(RASTET)} raste, vetitë dhe kontrolli me DB të përkohshme.")
