"""dashboard.py - Pamja për analistin. Sistemi vetëm ndihmon; vendimi është i analistit.

Nis me:  streamlit run dashboard.py
Skedat: Përmbledhja (rrezik x besueshmëri, Serbia, zonat), Urgjente dhe Raporte (sipas prioritetit
të rreziku.py), Ngjarjet (harta, kronologjia), Kërcënimet (taksonomia), Burimet, Vlerësimi,
Artikujt, Ekzekutimi.
"""
import hashlib
import hmac
import html
import json
import os
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import altair as alt
import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

import collector
import correlator
import db
import ekzekuto
import kercenimet
import patterns
import raporti
import rreziku
import scoring

DOSJA = Path(__file__).resolve().parent
REZULTATI = DOSJA / "eval" / "rezultati.json"          # nga eval/evaluate.py
RAPORTI_MODELIT = DOSJA / "data" / "raporti_modelit.json"  # nga trajno.py

st.set_page_config(page_title="OSINT Kosova", layout="wide", initial_sidebar_state="collapsed")
# Vetëm stil (pa të dhëna brenda), ndaj unsafe_allow_html këtu s'hap rrugë për HTML nga lajmet
st.markdown("""<style>
:root { --bg2: #111c30; --vija: #22304d; --zbehte: #8796ad; --theks: #d9a23b; }
html, body, [class*="css"] { font-family: "Segoe UI", "Inter", system-ui, sans-serif; }
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display: none; }
.block-container { padding-top: 4rem; max-width: 1500px; }
h3 { font-size: .8rem !important; letter-spacing: .14em; text-transform: uppercase; color: var(--zbehte);
     border-left: 3px solid var(--theks); padding: .05rem 0 .05rem .55rem; margin: 1.1rem 0 .6rem; }
.klasifikimi { background: var(--theks); color: #0a1222; text-align: center; font-size: .7rem; font-weight: 700;
               letter-spacing: .3em; padding: .18rem; border-radius: 2px; margin-bottom: .8rem; }
.shiriti { display: flex; justify-content: space-between; align-items: center; background: var(--bg2);
           border: 1px solid var(--vija); border-radius: 6px; padding: .7rem 1.1rem; margin-bottom: .8rem; }
.shiriti .emri { font-size: 1.35rem; font-weight: 700; letter-spacing: .18em; }
.shiriti .emri span { color: var(--theks); }
.shiriti .nen { color: var(--zbehte); font-size: .78rem; letter-spacing: .04em; margin-top: .1rem; }
.shiriti .gjendja { text-align: right; font-size: .78rem; color: var(--zbehte); line-height: 1.5; }
.pika { display: inline-block; width: .55rem; height: .55rem; border-radius: 50%; margin-right: .35rem;
        background: var(--c); box-shadow: 0 0 6px var(--c); }
.status { display: grid; gap: .55rem; }
.pllaka { display: flex; justify-content: space-between; align-items: center; background: var(--bg2);
          border: 1px solid var(--vija); border-left: 4px solid var(--c); border-radius: 6px; padding: .55rem .9rem; }
.pllaka .t { color: var(--zbehte); font-size: .72rem; letter-spacing: .12em; text-transform: uppercase; }
.pllaka .v { font-size: 1.75rem; font-weight: 700; color: var(--c); }
.bluf { background: var(--bg2); border: 1px solid var(--vija); border-radius: 6px; padding: .7rem .9rem;
        margin-top: .55rem; font-size: .9rem; line-height: 1.45; }
.bluf .t { color: var(--theks); font-size: .7rem; letter-spacing: .14em; text-transform: uppercase;
           margin-bottom: .25rem; font-weight: 600; }
.seksion { color: var(--theks); font-size: .7rem; letter-spacing: .14em; text-transform: uppercase;
           font-weight: 600; margin: .9rem 0 .35rem; }
[role="tablist"] { gap: .35rem; border-bottom: 1px solid var(--vija); }
[role="tab"] { background: var(--bg2); border: 1px solid var(--vija) !important; border-bottom: none !important;
                     border-radius: 6px 6px 0 0; padding: .35rem .9rem !important; }
[role="tab"][aria-selected="true"] { background: var(--theks); }
[role="tab"][aria-selected="true"] p { color: #0a1222 !important; font-weight: 700; }
[role="tab"] p { font-size: .78rem; letter-spacing: .08em; text-transform: uppercase; }
[data-testid="stExpander"] details { background: var(--bg2); border: 1px solid var(--vija); border-radius: 6px; }
[data-testid="stMetricValue"] { color: var(--theks); }
</style>""", unsafe_allow_html=True)
FJALEKALIMI = os.environ.get("OSINT_FJALEKALIMI")
if FJALEKALIMI and not st.session_state.get("hyri"):
    dhene = st.text_input("Fjalëkalimi", type="password")
    if not hmac.compare_digest(dhene.encode(), FJALEKALIMI.encode()):
        if dhene:
            st.error("Fjalëkalim i gabuar.")
        st.stop()
    st.session_state["hyri"] = True
    st.rerun()

# Koka dhe paneli i komandës zënë vendin lart; mbushen më poshtë, pasi të llogariten numrat
VENDI_KOKES = st.container()
KOMANDA = st.expander("Komanda: mbledhja dhe filtrat", expanded=False)

# OSINT_CLOUD=0 lejon pipeline-in në Linux kur ka Ollama (p.sh. Railway).
# Në cloud pipeline-i nuk niset nga ndërfaqja. Një OSINT_DB i konfiguruar lexohet siç
# është; pa të, cloud-i përgatit një demo të izoluar për procesin.
CLOUD = os.environ.get("OSINT_CLOUD", "1" if os.name != "nt" else "0") == "1"
BAZA_E_KONFIGURUAR = os.environ.get("OSINT_DB")
DEMO_CLOUD = CLOUD and not BAZA_E_KONFIGURUAR


@st.cache_resource
def pergatit_demon():
    """Mban gjallë dosjen provuese për sa kohë Streamlit e përdor bazën."""
    import demo
    dosja = tempfile.TemporaryDirectory(prefix="osint-demo-")
    demo.gjenero(Path(dosja.name) / "demo.db")
    return dosja


if DEMO_CLOUD:
    db.DB_PATH = str(Path(pergatit_demon().name) / "demo.db")
    st.info("Demo me të dhëna **sintetike** nga `eval/gold.jsonl`. Vendimet në këtë pamje janë vetëm për lexim.")
elif BAZA_E_KONFIGURUAR:
    db.DB_PATH = BAZA_E_KONFIGURUAR


@st.cache_data(ttl=60)
def lexo(shtegu, sql):
    """Lexon një tabelë nga SQLite (cache 60 sekonda që faqja të jetë e shpejtë)."""
    with closing(sqlite3.connect(shtegu)) as con:
        return pd.read_sql(sql, con)


def lexo_json(shtegu):
    try:
        return json.loads(Path(shtegu).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


siguro = raporti.siguro  # escape për popup-et e folium-it; testohet te raporti.py


def perqind(v):
    return f"{v:.0%}" if isinstance(v, (int, float)) else "–"


db.lidhu().close()
artikujt = lexo(db.DB_PATH, "SELECT id, url, burimi, titulli, data, published_at, gjuha, teksti, "
                "teksti_perkthyer, raw_text, lloji_tekstit, hash_sha256, mbledhur_me FROM articles")
# Vendimet lexohen pa cache, që një vendim i ruajtur të shfaqet menjëherë
te_gjitha = raporti.ngjarjet()

# Etiketa me ngjyra të qeta (Markdown i Streamlit-it), pa emoji: ngjyra mbart vetëm prioritetin
ETIKETA = {"URGJENTE": ":red-badge[URGJENTE]", "RAPORT": ":orange-badge[RAPORT]",
           "MONITORIM": ":blue-badge[MONITORIM]", "ARKIV": ":gray-badge[ARKIV]", None: ":gray-badge[PA RREZIK]"}
VENDIMI = {"e konfirmuar": " · :green[Konfirmuar]", "e pakonfirmuar": "", "e hedhur poshtë": " · :gray[Hedhur poshtë]"}
SAKTESIA = {"village": "fshat", "municipality": "komunë", "region": "vetëm rajon",
            "exact": "e saktë", "approximate": "e përafërt", None: "e panjohur"}
# Ngjyrat e prioritetit në grafikë (të njëjtat si në hartë). Matrica s'ka "i pallogaritur":
# ngjarjet pa rrezik të llogaritur s'vizatohen aty.
NGJYRAT = ["#d95f59", "#bd9250", "#7790a6", "#7790a6", "#7790a6"]  # vetëm urgjenca dallohet fort
NGJYRA_HEX = dict(zip(kercenimet.PRIORITETET, NGJYRAT))  # rrathët e hartës, si te grafikët
NGJYRAT_PRIORITETIT = alt.Scale(domain=kercenimet.PRIORITETET + ["i pallogaritur"], range=NGJYRAT)
NGJYRAT_MATRICES = alt.Scale(domain=kercenimet.PRIORITETET, range=NGJYRAT[:4])
# Zonat e tabelës te "Përmbledhja", sipas emrave kanonikë të correlator.gjej_vendin (VENDET).
# shortcut: "mitrovic" përfshin edhe Mitrovicën e Jugut (correlator.py s'i dallon); "veri" = veriu
# pa komunë të njohur. Hani i Elezit është pika kufitare me Maqedoninë e Veriut.
ZONAT = {"Veriu": {"mitrovic", "zvecan", "leposavi", "zubin potok", "veri"},
         "Kufiri / pikat kufitare": {"jarinj", "bernjak", "banjsk", "hani i elezit"},
         "Prishtina": {"prishtin"}}
KOSOVA = {emrat[0] for emrat in correlator.VENDET}  # vendet e Kosovës; ato te RAJONI janë jashtë saj
KOSOVA_TJETER, RAJONALE, PA_VEND = "Kosova tjetër", "Rajonale (jashtë Kosovës)", "Pa vend"
# Pamjet e hartës: ([jugperëndim, verilindje], zoom-i që i nxë kufijtë në hartën 450 px të lartë).
# Evropa është edhe kufiri ku mund të lëvizet harta. fit_bounds s'përdoret: st_folium e ndërton
# hartën kur korniza ka ende gjerësi 0, prandaj fitBounds del gjithmonë në zoom-in minimal (4).
PAMJET = {"Kosova": ([[41.85, 20.00], [43.27, 21.80]], 8), "Rajoni": ([[40.80, 18.40], [44.90, 23.10]], 6),
          "Ballkani": ([[39.00, 13.00], [47.00, 30.00]], 5), "Evropa": ([[34.00, -11.00], [71.00, 40.00]], 4)}
# Lajmet s'kanë GPS: koordinatat janë qendra e komunës ose e rajonit, prandaj vizatohet një rreth
# sa pasiguria (metra). "village" (fshat ose vend i saktë) vizatohet si pikë.
RREZET = {"region": 15000, "municipality": 5000}

def shfaq_publikimin(vlera):
    """Ruan ditën kur nuk dihet ora; orën e verifikuar e shfaq në zonën e Kosovës."""
    if not isinstance(vlera, str):
        return None
    koha = pd.to_datetime(vlera, utc=True, errors="coerce")
    if pd.isna(koha):
        return None
    if len(vlera) == 10:
        return koha.strftime("%Y-%m-%d")
    return koha.tz_convert("Europe/Belgrade").strftime("%Y-%m-%d %H:%M")


artikujt["publikimi"] = artikujt["published_at"].map(shfaq_publikimin)
PUBLIKIMI_E_URL = {u: p for u, p in zip(artikujt["url"], artikujt["publikimi"]) if isinstance(p, str)}


def publikimi_i_pare(e):
    """Publikimi më i hershëm i njohur nga burimet; data e ngjarjes paraqitet veç."""
    return min((PUBLIKIMI_E_URL[u] for u in e["burimet_l"] if u in PUBLIKIMI_E_URL), default="–")


def dita_e_ngjarjes(e):
    return str(e.get("data") or "–")[:10]


artikujt["data"] = pd.to_datetime(artikujt["data"], format="mixed", utc=True, errors="coerce")
# Të gjitha domenet e GDELT bashkohen në një grup që grafiku të mbetet i lexueshëm
artikujt["grupi"] = artikujt["burimi"].where(~artikujt["burimi"].str.startswith("GDELT:"), "GDELT")

# ---------------- Komanda: mbledhja dhe filtrat (lart, në vend të sidebar-it) ----------------
ngrire = raporti.ngrire() or CLOUD  # gjatë etiketimit ose në cloud ndërfaqja s'nis pipeline-in
k_mbl, k_ngj, k_art = KOMANDA.columns([1, 2, 2])
with k_mbl:
    seksion_kmd = '<div class="seksion">{}</div>'
    st.markdown(seksion_kmd.format("Mbledhja"), unsafe_allow_html=True)
    if DEMO_CLOUD:
        st.info("Demo në cloud: mbledhja punon vetëm në laptopin me Ollama.")
    elif CLOUD:
        st.info("Në këtë instalim, mbledhja menaxhohet nga serveri.")
    elif ngrire:
        st.warning("Etiketim në vazhdim: mbledhja është e ngrirë.")
    if st.button("Mblidh lajmet tani", type="primary", key="ekz_sidebar", width="stretch",
                 disabled=ngrire, help="Mbledh nga mediat RSS dhe GDELT, pastaj përkthen dhe analizon "
                                       "deri në 20 artikuj me modelin lokal (rreth 20–25 minuta)."):
        if ekzekuto.po_punon():
            st.warning("Një mbledhje po punon tashmë.")
        else:
            ekzekuto.nis_ne_sfond(20)
            st.success("Mbledhja u nis në sfond. Ecuria: skeda 'Ekzekutimi'.")
    # Rifreskimi lexon sërish bazën (pa cache), që ngjarjet e reja të duken pa pritur 60 sekonda
    if st.button("Rifresko pamjen", key="rifresko_sidebar", width="stretch"):
        st.cache_data.clear()
        st.rerun()
with k_ngj:
    st.markdown(seksion_kmd.format("Filtrat e ngjarjeve"), unsafe_allow_html=True)
    zona = st.radio("Zona", ["Të gjitha", "Kosovë", "Rajonale"], horizontal=True)
    a, b_ = st.columns(2)
    prioritetet = a.multiselect("Prioriteti", kercenimet.PRIORITETET)
    nivelet = b_.multiselect("Niveli i rrezikut", kercenimet.NIVELET)
    kategorite = a.multiselect("Kategoria", list(kercenimet.KATEGORITE), format_func=kercenimet.emri)
    statuset = b_.multiselect("Vendimi i analistit", db.STATUSET)
with k_art:
    st.markdown(seksion_kmd.format("Filtrat e artikujve"), unsafe_allow_html=True)
    burimet = st.multiselect("Burimi", sorted(artikujt["grupi"].unique()))
    gjuhet = st.multiselect("Gjuha", sorted(artikujt["gjuha"].unique()))
    kerko = st.text_input("Kërko në titull/tekst")

def kalon_filtrat(e):
    rajonale = e["det"].get("rajonale") is True
    if (zona == "Kosovë" and rajonale) or (zona == "Rajonale" and not rajonale):
        return False
    if prioritetet and raporti.prioriteti(e) not in prioritetet:
        return False
    if kategorite and e["det"].get("kategoria") not in kategorite:
        return False
    if nivelet and raporti.rreziku(e)[1] not in nivelet:
        return False
    return not statuset or e["statusi"] in statuset


ngj = sorted(filter(kalon_filtrat, te_gjitha), key=raporti.renditja)
aktive = [e for e in ngj if e["statusi"] != "e hedhur poshtë"]
urgjente = [e for e in aktive if raporti.prioriteti(e) == "URGJENTE"]
raporte = [e for e in aktive if raporti.prioriteti(e) in ("RAPORT", "MONITORIM")]
pa_rrezik = not any(raporti.prioriteti(e) for e in te_gjitha)

f = artikujt
if burimet:
    f = f[f["grupi"].isin(burimet)]
if gjuhet:
    f = f[f["gjuha"].isin(gjuhet)]
if kerko:
    ka = (f["titulli"].str.contains(kerko, case=False, na=False, regex=False)
          | f["teksti"].str.contains(kerko, case=False, na=False, regex=False))
    f = f[ka]


def seksion(titulli):
    """Etiketë e vogël seksioni (konstante e kodit, jo e dhënë nga lajmet)."""
    st.markdown(f'<div class="seksion">{html.escape(titulli)}</div>', unsafe_allow_html=True)


def tabela(rreshtat):
    """Tabelë e thjeshtë çelës-vlerë në Markdown; vlerat kalojnë nga raporti.pastro."""
    return "| | |\n|---|---|\n" + "\n".join(f"| {k} | {v} |" for k, v in rreshtat)


# ---------------- Kartela e një ngjarjeje ----------------
def kartela(e, skeda):
    """Expander me gjithë arsyetimin dhe vendimin e analistit. 'skeda' i bën çelësat unikë."""
    det, p = e["det"], raporti.prioriteti(e)
    pike, niveli, arsyet = raporti.rreziku(e)
    b = raporti.besueshmeria(e)
    kodi = raporti.admiralty(e)
    # Ripostimet s'numërohen: burimet e pavarura vijnë nga scoring.py (origjinat), jo nga numri i URL-ve
    n_pav = det.get("burime_te_pavarura")
    n_pav = n_pav if type(n_pav) is int and n_pav >= 0 else len(det.get("mediat") or [])
    burime = " · :orange[1 burim i vetëm]" if n_pav == 1 else f" · {n_pav} origjina" if n_pav > 1 else ""
    koka = (f"{ETIKETA.get(p, ETIKETA[None])} {raporti.pastro(e['titulli'], 120)}"
            f" · Ngjarja: {dita_e_ngjarjes(e)}{burime}{VENDIMI[e['statusi']]}")
    with st.expander(koka):
        r1, r2, r3 = st.columns(3)
        r1.metric("Rreziku", f"{pike}/100" if pike is not None else "–", help="Sa e rëndë nëse është e vërtetë")
        r1.caption(f"Niveli: {niveli or '–'} · Prioriteti: {p or 'i pallogaritur'}")
        r2.metric("Besueshmëria", perqind(b), help="Gjasat që të jetë e vërtetë, nga provat")
        r2.caption(f"Admiralty: {kodi or '–'} · Burime: {len(e['burimet_l'])}, të pavarura: {n_pav}")
        r3.metric("Vendimi", e["statusi"].capitalize())
        r3.caption("Sistemi sugjeron, analisti vendos.")
        if p == "URGJENTE" and raporti.per_verifikim(e):
            st.warning("Për verifikim, jo për veprim: besueshmëria është nën 80% dhe s'ka konfirmim.")
        sociale = sorted({m.split(":")[0] for m in det.get("mediat") or []
                          if isinstance(m, str) and m.startswith(scoring.SOCIALE)})
        if sociale:
            st.info(f"Sinjal nga rrjetet sociale ({', '.join(sociale)}): për shqyrtim, jo konfirmim. Lidhjet "
                    "origjinale janë te Burimet; statusi vjen vetëm nga vendimi i analistit.")
        # Lista e 21 kategorive (rreziku.py): kryesorja + shtesat, ndikimi dhe urgjenca
        v21 = det.get("v21") if isinstance(det.get("v21"), dict) else {}
        if v21:
            emrat = [f"{n}. {kercenimet.KATEGORITE_21[n]['emri']}" for n in v21.get("kategorite") or []
                     if n in kercenimet.KATEGORITE_21]
            ndikimi = raporti.pastro(v21.get("ndikimi"), 20) or "–"
            st.write(f"**Kategoritë (lista e 21):** {emrat[0] + ' (kryesore)' if emrat else '–'}"
                     + (f" + {', '.join(emrat[1:])}" if len(emrat) > 1 else "")
                     + f"  ·  **Ndikimi:** {ndikimi}  ·  **Urgjenca:** {raporti.pastro(v21.get('urgjenca'), 20) or '–'}")
            st.caption(f"Ndikimi {ndikimi}: {kercenimet.NDIKIMET.get(v21.get('ndikimi'), '')} "
                       f"({raporti.pastro(v21.get('pse'), 120)}). Nivele paraprake, për validim nga përgjegjësi.")
            if v21.get("verifikim_urgjent") is True and e["statusi"] == "e pakonfirmuar":
                st.error("Verifikim urgjent: ndikim potencialisht i rëndë me prova të kufizuara.")
        shenj = ", ".join(kercenimet.SHENJESTRAT.get(s, s) for s in det.get("shenjestrat") or []) or "–"
        aktori = det.get("aktori")
        try:
            bosh = json.loads(e.get("boshllequet") or "[]")
        except ValueError:
            bosh = []
        majtas, djathtas = st.columns(2)
        with majtas:
            seksion("Çfarë ndodhi")
            st.markdown(tabela([
                ("Kategoria", raporti.pastro(raporti.kategoria(e), 80)),
                ("Aktori (sipas modelit)", kercenimet.AKTORET.get(aktori, "–") if aktori else "–"),
                ("Shenjestrat", shenj),
                ("Vendi", f"{raporti.pastro(e.get('vendi'), 60) or '–'} "
                          f"({SAKTESIA.get(det.get('saktesia_vendit'), 'e panjohur')})"),
                ("Data e ngjarjes", f"{dita_e_ngjarjes(e)} ({SAKTESIA.get(det.get('saktesia_dates'), 'e panjohur')})"),
                ("Publikimi i parë i njohur", publikimi_i_pare(e)),
                ("Zona · lidhje me FSK", f"{'rajonale' if det.get('rajonale') else 'Kosovë'} · "
                                         f"{'po' if det.get('lidhje_me_fsk') else 'jo'}"),
                ("Lloji · gjuha", f"{raporti.pastro(e.get('lloji'), 40) or '–'} · {raporti.pastro(e.get('gjuha'), 5)}"),
            ]))
        with djathtas:
            seksion("Burimet")
            for u in e["burimet_l"]:
                st.markdown(f"- [{raporti.pastro(u, 90)}]({u})" if raporti.url_e_sigurt(u)
                            else f"- `{raporti.pastro(u, 120)}`")
            st.caption("Mediat: " + (", ".join(map(raporti.pastro, det.get("mediat") or [])) or "–"))
            seksion("Boshllëqet e informacionit")
            st.markdown("\n".join(f"- {raporti.pastro(x)}" for x in bosh) if bosh else "Asnjë i shënuar.")
        majtas, djathtas = st.columns(2)
        with majtas:
            seksion("Pse ky rrezik")
            st.markdown("\n".join(f"- {raporti.pastro(a, 200)}" for a in arsyet) if arsyet else "–")
        with djathtas:
            seksion("Pse kjo besueshmëri")
            st.markdown("\n".join(f"- {raporti.pastro(a, 200)}" for a in det.get("arsyetimi") or []) or "–")
        konteksti = [c for c in det.get("konteksti") or [] if isinstance(c, dict)]
        if konteksti:
            seksion("Konteksti i jashtëm")
            for c in konteksti:
                u = raporti.url_e_sigurt(c.get("url"))
                titulli = raporti.pastro(c.get("titulli"), 150)
                pjeset = [f"{raporti.pastro(c.get('burimi'), 30)}: " + (f"[{titulli}]({u})" if u else titulli)]
                if c.get("data"):
                    pjeset.append(raporti.pastro(c["data"], 10))
                if isinstance(c.get("ngjashmeria"), (int, float)):
                    pjeset.append(f"ngjashmëria {c['ngjashmeria']:.0%}")
                if c.get("arsyeja"):
                    pjeset.append(raporti.pastro(c["arsyeja"], 150))
                st.markdown(("- Rast i ngjashëm: " if c.get("lloji") == "rast_i_ngjashem" else "- Trend: ")
                            + " · ".join(pjeset))
            st.caption("Ngjashmëri automatike, jo provë. Verifikoje te burimi.")
        # Vendimi i analistit: sistemi vetëm sugjeron, njeriu vendos
        seksion("Vendimi i analistit")
        k = e["url_kryesor"]
        if DEMO_CLOUD or not k:
            st.caption(e["shenimi"] or ("Demo për lexim." if DEMO_CLOUD else "Ngjarja nuk ka URL burimi për vendimin."))
            return
        # Një vendim i ruajtur rifreskon formularët e së njëjtës ngjarje në të gjitha skedat.
        gjurma = hashlib.sha256(f"{e['statusi']}\0{e['shenimi']}".encode()).hexdigest()[:16]
        celesi = f"{skeda}_{e['id']}_{k}_{gjurma}"
        statusi = st.segmented_control("Statusi", db.STATUSET, default=e["statusi"], key=f"st_{celesi}",
                                       label_visibility="collapsed") or e["statusi"]
        shenimi = st.text_input("Shënim", e["shenimi"], key=f"sh_{celesi}",
                                placeholder="p.sh. e konfirmoi Policia në Facebook")
        if st.button("Ruaj vendimin", key=f"rv_{celesi}", type="primary"):
            db.ruaj_vendimin(k, statusi, shenimi)
            st.session_state.pop(f"raporti_{db.DB_PATH}", None)
            st.rerun()


# ---------------- Skeda "Përmbledhja": grafikë të thjeshtë nga baza ----------------
def data_e(e):
    try:
        return datetime.strptime(str(e.get("data"))[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def ngjarjet_e_fundit(ngjarjet, sa=10):
    """Ngjarjet më të reja sipas datës (brenda ditës sipas prioritetit), me burimin e artikullit të parë."""
    burimi_i_url = dict(zip(artikujt["url"], artikujt["burimi"]))
    rreshtat = []
    for e in sorted(ngjarjet, key=lambda e: str(data_e(e) or ""), reverse=True)[:sa]:
        p, b = raporti.prioriteti(e), e["burimet_l"]
        burimi = burimi_i_url.get(b[0]) if b else None
        if not burimi and b and (u := raporti.url_e_sigurt(b[0])):
            burimi = urlparse(u).hostname
        rreshtat.append({"Prioriteti": p or "i pallogaritur",
                         "Data e ngjarjes": dita_e_ngjarjes(e), "Publikimi": publikimi_i_pare(e),
                         "Ngjarja": raporti.rresht(e["titulli"], 110),
                         "Burimi": (burimi or "–") + (f" (+{len(b) - 1})" if len(b) > 1 else "")})
    return pd.DataFrame(rreshtat)


def grafiku_matrices(ngjarjet):
    """Matrica rrezik x besueshmëri. Kthen (grafiku ose None, sa ngjarje s'kanë rrezik ose besueshmëri)."""
    pikat, pa_vlera = [], 0
    for e in ngjarjet:
        pike, b, p = raporti.rreziku(e)[0], raporti.besueshmeria(e), raporti.prioriteti(e)
        if pike is None or b is None or p is None:
            pa_vlera += 1
            continue
        pikat.append({"titulli": raporti.rresht(e["titulli"], 120), "data": dita_e_ngjarjes(e),
                      "publikimi": publikimi_i_pare(e),
                      "prioriteti": p, "rreziku": pike,
                      "besueshmeria": b, "kategoria": raporti.rresht(raporti.kategoria(e), 80),
                      "burime": len(e["burimet_l"])})
    if not pikat:
        return None, pa_vlera
    # Të njëjtat fusha dhe tituj në çdo shtresë, që boshtet të mos marrin tituj të përzier
    x = alt.X("besueshmeria:Q", title="Besueshmëria (gjasat që ngjarja të jetë e vërtetë)",
              scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format=".0%"))
    y = alt.Y("rreziku:Q", title="Rreziku nëse është e vërtetë (0–100)", scale=alt.Scale(domain=[0, 100]))
    vija = {"strokeDash": [4, 4], "color": "gray", "opacity": 0.8}
    vijat = (alt.Chart(pd.DataFrame({"rreziku": [rreziku.PRAGU_LARTE, rreziku.PRAGU_MESEM]}))
             .mark_rule(**vija).encode(y=y)
             + alt.Chart(pd.DataFrame({"besueshmeria": [rreziku.B_LARTE]})).mark_rule(**vija).encode(x=x))

    def etiketa(teksti, b, r, rreshtimi):
        return alt.Chart(pd.DataFrame({"besueshmeria": [b], "rreziku": [r], "t": [teksti]})).mark_text(
            align=rreshtimi, baseline="middle", color="gray", fontSize=12).encode(x=x, y=y, text="t:N")
    etiketat = (etiketa("URGJENTE për veprim", 0.99, 97, "right")
                + etiketa("URGJENTE për verifikim", 0.01, 97, "left")
                + etiketa("Raporte", 0.01, (rreziku.PRAGU_LARTE + rreziku.PRAGU_MESEM) / 2, "left")
                + etiketa("Monitorim", 0.01, rreziku.PRAGU_MESEM / 2, "left"))
    pika = alt.Chart(pd.DataFrame(pikat)).mark_circle(opacity=0.85).encode(
        x=x, y=y, color=alt.Color("prioriteti:N", title="Prioriteti", scale=NGJYRAT_MATRICES),
        size=alt.Size("burime:Q", title="Burime", scale=alt.Scale(range=[60, 400], zero=False),
                      legend=alt.Legend(format="d", tickMinStep=1)),
        tooltip=[alt.Tooltip("titulli:N", title="Ngjarja"), alt.Tooltip("data:N", title="Data e ngjarjes"),
                 alt.Tooltip("publikimi:N", title="Publikimi i parë i njohur"),
                 alt.Tooltip("prioriteti:N", title="Prioriteti"), alt.Tooltip("rreziku:Q", title="Rreziku"),
                 alt.Tooltip("besueshmeria:Q", title="Besueshmëria", format=".0%"),
                 alt.Tooltip("kategoria:N", title="Kategoria")])
    return (alt.layer(vijat, etiketat, pika).properties(height=420)
            .configure_view(strokeWidth=0).configure_axis(gridOpacity=0.25)), pa_vlera


def paneli_serbia(aktive, te_gjitha):
    """Ngjarjet me aktor shtetin serb: 7 ditët deri te data më e re në bazë (jo sot, që demo-ja të
    punojë), kundrejt 7 ditëve para tyre."""
    deri = max(filter(None, map(data_e, te_gjitha)), default=None)
    if deri is None:
        st.info("S'ka ende ngjarje.")
        return
    nga = deri - timedelta(days=6)
    serbe = [e for e in aktive if e["det"].get("aktori") == "shteti_serb"]
    tani = [e for e in serbe if raporti.brenda(e, nga, deri)]
    para = [e for e in serbe if raporti.brenda(e, nga - timedelta(days=7), nga - timedelta(days=1))]

    def numrat(lista):
        pike = [p for e in lista if (p := raporti.rreziku(e)[0]) is not None]
        urg = [e for e in lista if raporti.prioriteti(e) == "URGJENTE"]
        return {"Ngjarje": len(lista), "URGJENTE": len(urg),
                "Prej tyre për verifikim": sum(map(raporti.per_verifikim, urg)),
                "Rreziku mesatar": round(sum(pike) / len(pike)) if pike else None}
    t, p = numrat(tani), numrat(para)
    for kolona, (emri, v) in zip(st.columns(2) + st.columns(2), t.items()):  # 2x2: lexohet edhe në kolonë të ngushtë
        delta = v - p[emri] if v is not None and p[emri] is not None else None
        vlera = "–" if v is None else f"{v}/100" if emri == "Rreziku mesatar" else v
        kolona.metric(emri, vlera, delta=delta, delta_color="inverse", help="Ndryshimi kundrejt 7 ditëve para")
    kat = Counter(k for e in tani if isinstance(k := e["det"].get("kategoria"), str) and kercenimet.kategoria_valide(k))
    st.write("**Kategoritë më të shpeshta:** "
             + (", ".join(f"{kercenimet.emri(k)} ({n})" for k, n in kat.most_common(3)) or "s'ka ngjarje në këtë periudhë"))
    st.caption(f"Ngjarjet me aktor shtetin serb, {nga:%d.%m}–{deri:%d.%m.%Y} (deri te ngjarja më e re në bazë), "
               "krahasuar me 7 ditët para. Aktori vjen nga modeli; verifikoje.")


def zona_e(e):
    """Zona e tabelës: rajonale (jashtë Kosovës) së pari, pastaj sipas vendit të njohur."""
    v = correlator.gjej_vendin(e.get("vendi") or "")[0]
    if e["det"].get("rajonale") is True or (v and v not in KOSOVA):
        return RAJONALE
    if v is None:
        return PA_VEND
    return next((z for z, vendet in ZONAT.items() if v in vendet), KOSOVA_TJETER)


def tabela_zonave(ngjarjet):
    """Për çdo zonë: ngjarje, urgjente, raporte (RAPORT + MONITORIM) dhe kategoria më e shpeshtë."""
    zonat = {z: {"Zona": z, "Ngjarje": 0, "Urgjente": 0, "Raporte": 0, "kat": Counter()}
             for z in [*ZONAT, KOSOVA_TJETER, RAJONALE, PA_VEND]}
    for e in ngjarjet:
        z, p = zonat[zona_e(e)], raporti.prioriteti(e)
        z["Ngjarje"] += 1
        z["Urgjente"] += p == "URGJENTE"
        z["Raporte"] += p in ("RAPORT", "MONITORIM")
        z["kat"][raporti.kategoria(e)] += 1
    return pd.DataFrame([{**{k: v for k, v in z.items() if k != "kat"},
                          "Kategoria më e shpeshtë": z["kat"].most_common(1)[0][0] if z["kat"] else "–"}
                         for z in zonat.values()])


def harta_e(ngjarjet):
    """Harta e ngjarjeve me vend të njohur: rreth sa pasiguria e vendit, pikë vetëm për vend të saktë."""
    (lat_jug, lon_per), (lat_veri, lon_lin) = PAMJET["Evropa"][0]
    harta = folium.Map(location=[42.56, 20.90], zoom_start=8, min_zoom=4, max_bounds=True,
                       min_lat=lat_jug, max_lat=lat_veri, min_lon=lon_per, max_lon=lon_lin)
    for e in ngjarjet:
        if e.get("lat") is None or e.get("lon") is None:
            continue
        p, det = raporti.prioriteti(e), e["det"]
        pike = raporti.rreziku(e)[0]
        sv = det.get("saktesia_vendit")
        popup = (f"{siguro(raporti.rresht(e['titulli']))}<br>Data e ngjarjes: {siguro(dita_e_ngjarjes(e))}<br>"
                 f"Publikimi: {siguro(publikimi_i_pare(e))}<br>Prioriteti: {siguro(p or '–')} · "
                 f"Rreziku: {siguro(pike if pike is not None else '–')}<br>Besueshmëria: "
                 f"{siguro(perqind(raporti.besueshmeria(e)))} · Vendi: {siguro(SAKTESIA.get(sv, 'e panjohur'))}"
                 f"<br>Vendimi: {siguro(e['statusi'])}")
        tooltip = siguro(f"{dita_e_ngjarjes(e)} · {raporti.rresht(e['titulli'], 100)}")
        ngjyra = NGJYRA_HEX.get(p, NGJYRAT[4])
        # Pa saktësi të dhënë, koordinatat vijnë nga lista e komunave: trajtohen si komunë
        rreze = RREZET.get(sv or "municipality")
        if rreze:
            # Vend i përafërt: rreth sa pasiguria, që të mos duket më i saktë se ç'është
            folium.Circle([e["lat"], e["lon"]], radius=rreze, color=ngjyra, weight=1.5, fill=True,
                          fill_opacity=0.15, tooltip=tooltip, popup=popup).add_to(harta)
        if not rreze or det.get("rajonale"):
            # Pikë e plotë = vend i saktë; unazë = ngjarje rajonale (jashtë Kosovës)
            folium.CircleMarker([e["lat"], e["lon"]], radius=7, color=ngjyra, weight=2, fill=True,
                                fill_opacity=0.25 if det.get("rajonale") else 0.9,
                                tooltip=tooltip, popup=popup).add_to(harta)
    return harta


# ---------------- Përmbledhja ----------------
# Çdo e dhënë nga baza kalon nga html.escape para se të hyjë në HTML
mbledhja_e_fundit = pd.to_datetime(artikujt["mbledhur_me"], format="mixed", utc=True, errors="coerce").max()
perditesuar = (mbledhja_e_fundit.tz_convert("Europe/Belgrade").strftime("%d.%m.%Y, %H:%M")
               if pd.notna(mbledhja_e_fundit) else "ende pa mbledhje")
punon = ekzekuto.po_punon()
gjendja = (("DEMO", NGJYRAT[3]) if DEMO_CLOUD
           else ("MBLEDHJA PO PUNON", NGJYRAT[1]) if punon
           else ("E NGRIRË", NGJYRAT[3]) if raporti.ngrire()
           else ("GATI", "#3ecf8e"))
VENDI_KOKES.markdown(f"""<div class="klasifikimi">E PAKLASIFIKUAR · VETËM BURIME TË HAPURA (OSINT)</div>
<div class="shiriti"><div><div class="emri">OSINT <span>KOSOVA</span></div>
<div class="nen">Qendra e situatës · kërcënimet hibride ndaj FSK-së dhe sigurisë së Kosovës</div></div>
<div class="gjendja"><span class="pika" style="--c:{gjendja[1]}"></span>{gjendja[0]}<br>
Artikulli i fundit u mblodh: {perditesuar}<br>Ora lokale e Kosovës · analisti vendos</div></div>""", unsafe_allow_html=True)

per_verif = sum(map(raporti.per_verifikim, urgjente))
pllakat = [("Urgjente", len(urgjente), NGJYRAT[0]), ("Prej tyre: për verifikim", per_verif, NGJYRAT[1]),
           ("Për raport", sum(raporti.prioriteti(e) == "RAPORT" for e in aktive), NGJYRAT[2]),
           ("Në monitorim", sum(raporti.prioriteti(e) == "MONITORIM" for e in aktive), NGJYRAT[3]),
           ("Artikuj të mbledhur", len(f), NGJYRAT[4])]
# BLUF: një fjali për atë që ka më shumë rëndësi tani
if urgjente:
    e0 = urgjente[0]
    bluf = (f"{raporti.rresht(e0['titulli'], 160)} ({raporti.rresht(raporti.kategoria(e0), 60)}, "
            f"{raporti.rresht(e0.get('vendi'), 40) or 'vendi i panjohur'}; rreziku {raporti.rreziku(e0)[0]}, "
            f"besueshmëria {perqind(raporti.besueshmeria(e0))})")
else:
    bluf = "S'ka ngjarje urgjente me këto filtra."


def kolona_e_statusit():
    """Pllakat vertikale dhe BLUF-i: niveli 1 dhe 2 i vetëdijes për situatën."""
    st.markdown('<div class="status">' + "".join(
        f'<div class="pllaka" style="--c:{c}"><div class="t">{t}</div><div class="v">{int(v)}</div></div>'
        for t, v, c in pllakat) + "</div>", unsafe_allow_html=True)
    st.markdown(f'<div class="bluf"><div class="t">Më e rëndësishmja tani</div>{html.escape(bluf)}</div>',
                unsafe_allow_html=True)


(tab_per, tab_urg, tab_rap, tab_ngj, tab_ker, tab_bur, tab_vle,
 tab_art, tab_ekz) = st.tabs(["Përmbledhja", "Urgjente", "Raporte", "Ngjarjet", "Kërcënimet", "Burimet",
                              "Vlerësimi", "Artikujt", "Ekzekutimi"])

# ---------------- Përmbledhja ----------------
with tab_per:
    statusi_k, harta_k = st.columns([1, 3])
    with statusi_k:
        st.subheader("Gjendja")
        kolona_e_statusit()
        st.caption("‘Për verifikim’ është pjesë e ngjarjeve urgjente. Numrat e kartelave nuk mblidhen bashkë.")
    with harta_k:
        st.subheader("Harta e situatës")
        (jug, per), (veri, lin) = PAMJET["Kosova"][0]
        st_folium(harta_e(aktive), height=520, width="stretch", returned_objects=[], key="harta_per",
                  center=[(jug + veri) / 2, (per + lin) / 2], zoom=PAMJET["Kosova"][1])
    st.subheader("Ngjarjet më të reja")
    if aktive:
        st.dataframe(ngjarjet_e_fundit(aktive).style.map(
                         lambda v: f"color: {NGJYRA_HEX.get(v, NGJYRAT[4])}; font-weight: 700",
                         subset=["Prioriteti"]), hide_index=True, width="stretch")
    else:
        st.info("S'ka ende ngjarje.")
    majtas, djathtas = st.columns([3, 2])
    with majtas:
        st.subheader("Rreziku × besueshmëria")
        grafiku, pa_vlera = grafiku_matrices(aktive)
    if grafiku is None:
        majtas.info("S'ka ende ngjarje." if not aktive else
                    "Asnjë ngjarje s'ka ende rrezik dhe besueshmëri të llogaritur (shih skedën Urgjente).")
    else:
        majtas.altair_chart(grafiku, width="stretch")
        majtas.caption(f"Çdo pikë është një ngjarje ({len(aktive) - pa_vlera} në grafik"
                   + (f"; {pa_vlera} pa rrezik ose pa besueshmëri s'janë në të" if pa_vlera else "") + "). "
                   f"Vija vertikale = besueshmëria {rreziku.B_LARTE:.0%}: djathtas URGJENTE për veprim, majtas "
                   f"për verifikim. Vijat horizontale = pragjet e rrezikut {rreziku.PRAGU_LARTE} (i lartë) dhe "
                   f"{rreziku.PRAGU_MESEM} (i mesëm). Ngjyra = prioriteti i llogaritur nga rreziku.py: me "
                   "besueshmëri nën 50% rreziku i mesëm bie te MONITORIM, rreziku i ulët me besueshmëri nën 80% "
                   "te ARKIV, dhe një ngjarje e konfirmuar nga analisti është për veprim edhe majtas vijës. "
                   "Madhësia = numri i burimeve.")
    with djathtas:
        st.subheader("Serbia: aktor shtetëror")
        paneli_serbia(aktive, te_gjitha)
    st.subheader("Ku: ngjarjet sipas zonës")
    if aktive:
        st.dataframe(tabela_zonave(aktive), hide_index=True, width="stretch")
        st.caption("Zona vjen nga vendi i njohur i ngjarjes (correlator.py). Veriu: Mitrovicë, Zveçan, "
                   "Leposaviq, Zubin Potok, 'veriu'. Kufiri: Jarinjë, Bërnjak, Banjskë, Hani i Elezit. "
                   "Raporte = RAPORT + MONITORIM, si te skeda Raporte.")
    else:
        st.info("S'ka ende ngjarje.")

# ---------------- Urgjente ----------------
with tab_urg:
    if pa_rrezik:
        st.info("Rreziku s'është llogaritur ende. Ekzekuto pipeline-in (hapi 7) ose `python rreziku.py`.")
    st.caption("Rrezik i lartë për FSK-në ose sigurinë e Kosovës, renditur sipas rrezikut. "
               "'Për verifikim' = besueshmëria nën 80% dhe pa konfirmim të analistit.")
    for e in urgjente:
        kartela(e, "urg")
    if not urgjente and not pa_rrezik:
        st.success("S'ka ngjarje urgjente me këto filtra.")

    st.subheader("Raporti ditor")
    raporti_kyc = f"raporti_{db.DB_PATH}"
    if st.button("Gjenero raportin ditor", icon=":material/description:"):
        deri = date.today()
        if len(artikujt) and artikujt["url"].str.startswith("gold://").all():
            deri = max(filter(None, map(data_e, te_gjitha)), default=deri)
        st.session_state[raporti_kyc] = (
            f"raporti_{deri.isoformat()}.md", raporti.permbajtja(te_gjitha, deri, db.fillimi_i_mbledhjes())
        )
    if raporti_kyc in st.session_state:
        emri, teksti = st.session_state[raporti_kyc]
        st.download_button("Shkarko raportin", teksti, icon=":material/download:", file_name=emri, mime="text/markdown")
        with st.expander("Shiko raportin", expanded=True):
            st.markdown(teksti)

# ---------------- Raporte ----------------
with tab_rap:
    st.caption("RAPORT: rrezik i mesëm për t'u raportuar. MONITORIM: për t'u ndjekur. "
               "Ngjarjet ARKIV dhe ato të hedhura poshtë janë vetëm te 'Ngjarjet'.")
    for emri_p in ("RAPORT", "MONITORIM"):
        grupi = [e for e in raporte if raporti.prioriteti(e) == emri_p]
        st.subheader(f"{emri_p.capitalize()} ({len(grupi)})")
        for e in grupi:
            kartela(e, f"rap_{emri_p}")
        if not grupi:
            st.caption("S'ka.")

# ---------------- Ngjarjet ----------------
with tab_ngj:
    # Alarmet nga patterns.py (rritje e pazakontë e ngjarjeve në një komunë)
    fillimi = db.fillimi_i_mbledhjes()
    alarmet = patterns.rritjet(aktive, fillimi_mbledhjes=fillimi)
    for a in alarmet:
        st.warning(patterns.pershkrim(a), icon=":material/warning:")
    if fillimi and ngj and not patterns.histori_e_mjaftueshme(fillimi, max(str(e["data"]) for e in ngj)):
        st.caption(f"Alarmet për rritje aktivizohen pas 5 javë mbledhjeje "
                   f"(mbledhja filloi më {str(fillimi)[:10]}).")
    elif not alarmet:
        st.caption("S'ka rritje të pazakonta (rregulli: ≥ 3 ngjarje në 7 ditë dhe ≥ 2x mesatarja javore).")

    pamja = st.radio("Pamja e hartës", list(PAMJET), horizontal=True, key="pamja_harte")
    harta = harta_e(ngj)
    st.caption("Ngjyra: e kuqe URGJENTE, portokalli RAPORT, blu MONITORIM, gri ARKIV. Lajmet s'kanë GPS, "
               "prandaj vendi tregohet me saktësinë që dihet: rreth ~15 km = vetëm rajoni, rreth ~5 km = "
               "komuna (qendra e saj), pikë = fshat ose vend i saktë. Unaza = ngjarje rajonale (jashtë "
               "Kosovës). Ngjarjet pa vend të njohur nuk dalin në hartë, por janë në listë. Harta kërkon "
               "internet (pa të nuk shfaqet; kronologjia dhe lista punojnë).")
    # Qendra dhe zoom-i i jepen st_folium-it: kalimi mes pamjeve s'e ringarkon hartën
    (jug, per), (veri, lin) = PAMJET[pamja][0]
    st_folium(harta, height=450, width="stretch", returned_objects=[], key="harta_ngj",
              center=[(jug + veri) / 2, (per + lin) / 2], zoom=PAMJET[pamja][1])

    if not ngj:
        st.info("Ende s'ka ngjarje (ose filtrat i fshehin të gjitha).")
    else:
        # Kronologjia: një pikë për çdo ngjarje, sipas datës dhe kategorisë
        st.subheader("Kronologjia")
        k = pd.DataFrame([{
            "dita": dita_e_ngjarjes(e), "publikimi": publikimi_i_pare(e), "kategoria": raporti.rresht(raporti.kategoria(e), 80),
            "prioriteti": raporti.prioriteti(e) or "i pallogaritur",
            "titulli": raporti.rresht(e["titulli"], 120), "burime": len(e["burimet_l"]),
            "besueshmeria": perqind(raporti.besueshmeria(e)),
            "rreziku": raporti.rreziku(e)[0] if raporti.rreziku(e)[0] is not None else -1,
        } for e in ngj])
        k["dita"] = pd.to_datetime(k["dita"], errors="coerce")
        k = k.dropna(subset=["dita"])
        grafiku = alt.Chart(k).mark_circle(opacity=0.8).encode(
            # ngjarjet kanë vetëm datë (pa orë), ndaj boshti tregon ditë
            x=alt.X("dita:T", title="Data", axis=alt.Axis(format="%d %b", tickCount="day"),
                    scale=alt.Scale(padding=30)),
            y=alt.Y("kategoria:N", title="Kategoria", axis=alt.Axis(labelLimit=250)),
            size=alt.Size("burime:Q", title="Burime", scale=alt.Scale(range=[80, 500], zero=False),
                          legend=alt.Legend(format="d", tickMinStep=1)),
            color=alt.Color("prioriteti:N", title="Prioriteti", scale=NGJYRAT_PRIORITETIT),
            tooltip=[alt.Tooltip("dita:T", title="Data e ngjarjes"),
                     alt.Tooltip("publikimi:N", title="Publikimi i parë i njohur"), alt.Tooltip("titulli:N", title="Ngjarja"),
                     alt.Tooltip("prioriteti:N", title="Prioriteti"), alt.Tooltip("rreziku:Q", title="Rreziku"),
                     alt.Tooltip("besueshmeria:N", title="Besueshmëria"), alt.Tooltip("burime:Q", title="Burime")],
        )
        st.altair_chart(grafiku, width="stretch")
        st.caption("Çdo pikë është një ngjarje. Madhësia tregon numrin e burimeve.")

        st.subheader(f"Të gjitha ngjarjet ({len(ngj)})")
        for e in ngj:
            kartela(e, "ngj")

# ---------------- Kërcënimet (taksonomia) ----------------
with tab_ker:
    st.caption("Taksonomia e kërcënimeve hibride për FSK-në dhe sigurinë e Kosovës (kercenimet.py). "
               "Rrezikshmëria bazë 1–5 është pika e nisjes së rreziku.py.")
    numri = Counter(k for e in aktive if isinstance(k := e["det"].get("kategoria"), str))
    st.dataframe(pd.DataFrame([{
        "Kategoria": c["emri"], "Rrezikshmëria bazë": c["rrezikshmeria_baze"],
        "Ngjarje tani": numri.get(i, 0), "Përshkrimi": c["pershkrimi"]}
        for i, c in kercenimet.KATEGORITE.items()]), hide_index=True, width="stretch")
    for i, c in kercenimet.KATEGORITE.items():
        if i == "tjeter":
            continue
        with st.expander(f"{c['emri']} · rrezikshmëria bazë {c['rrezikshmeria_baze']}/5 · {numri.get(i, 0)} ngjarje"):
            st.write(c["pershkrimi"])
            st.write("**Treguesit:** " + "; ".join(c["treguesit"]))
            st.write("**Aktorët tipikë:** " + ", ".join(kercenimet.AKTORET.get(a, a) for a in c["aktoret_tipike"]))
            st.write("**Shenjestrat tipike:** "
                     + ", ".join(kercenimet.SHENJESTRAT.get(s, s) for s in c["shenjestrat_tipike"]))
            st.write("**Ku mblidhet:** " + "; ".join(map(str, c["burimet_e_mbledhjes"])))
            for s in c["shembuj"]:
                u = raporti.url_e_sigurt(s.get("url"))
                st.markdown(f"- {raporti.pastro(s.get('pershkrimi'), 200)}" + (f" ([burimi]({u}))" if u else ""))

# ---------------- Burimet ----------------
with tab_bur:
    st.subheader("Burimet tona")
    st.caption("Sa ngjarje sjell çdo medium dhe çfarë vendosi analisti për to. Vetëm media, institucione "
               "dhe platforma: asnjë llogari individuale.")
    rreshtat = {}
    for e in ngj:
        for m in e["det"].get("mediat") or []:
            r = rreshtat.setdefault(m, {"Burimi": m, "Ngjarje": 0, "Urgjente": 0, "Të konfirmuara": 0,
                                        "Të hedhura poshtë": 0})
            r["Ngjarje"] += 1
            r["Urgjente"] += raporti.prioriteti(e) == "URGJENTE"
            r["Të konfirmuara"] += e["statusi"] == "e konfirmuar"
            r["Të hedhura poshtë"] += e["statusi"] == "e hedhur poshtë"
    besueshmeria_e = getattr(scoring, "besueshmeria_e_mediumit", lambda m: scoring.MEDIAT.get(m, scoring.E_PANJOHUR))
    for r in rreshtat.values():
        r["Besueshmëria e mediumit"] = besueshmeria_e(r["Burimi"])
    if rreshtat:
        st.dataframe(pd.DataFrame(sorted(rreshtat.values(), key=lambda r: -r["Ngjarje"])),
                     hide_index=True, width="stretch",
                     column_config={"Besueshmëria e mediumit": st.column_config.NumberColumn(format="%.2f")})
    else:
        st.caption("S'ka ende ngjarje.")

    st.subheader("Burime me dezinformim të dokumentuar (EUvsDisinfo)")
    dez = raporti.burimet_e_dezinformimit()
    if dez:
        st.caption("Sipas rasteve të EUvsDisinfo për Kosovën dhe rajonin. Kanalet në rrjete sociale grupohen "
                   "sipas platformës, pa emra llogarish.")
        st.dataframe(pd.DataFrame(dez), hide_index=True, width="stretch",
                     column_config={"url_shembull": st.column_config.LinkColumn("Rasti i fundit")})
    else:
        st.info("Lista mungon: vendos eksportin CSV te data/euvsdisinfo.csv (shih kontekst_dezinformim.py).")

# ---------------- Vlerësimi ----------------
with tab_vle:
    r = lexo_json(REZULTATI)
    st.subheader("Saktësia e sistemit (gold set)")
    if not isinstance(r, dict) or not isinstance(r.get("metrikat"), dict):
        st.info("S'ka ende rezultat. Ekzekuto: `python eval/evaluate.py`")
    else:
        m = r["metrikat"]

        def raport_n(a, b):
            return f"{a}/{b}" if isinstance(a, int) and isinstance(b, int) and b else "–"
        st.caption(f"Mbi {r.get('artikuj', '?')} artikuj SINTETIKË (eval/gold.jsonl), modeli {r.get('modeli', '?')}, "
                   f"{str(r.get('koha', ''))[:16]}. Me lajme reale pritet të jenë më të ulëta.")
        a1, a2, a3, a4 = st.columns(4)
        a1.metric("Precision (zbulimi)", perqind(m.get("precision")))
        a2.metric("Recall (zbulimi)", perqind(m.get("recall")))
        a3.metric("Alarme të rreme", raport_n(m.get("fp"), m.get("negative")))
        sek, n, man = r.get("sekonda"), r.get("artikuj"), r.get("minuta_manuale")
        if isinstance(sek, (int, float)) and isinstance(n, int) and n:
            a4.metric("Koha për artikull", f"{sek / n:.1f} s",
                      help=f"Kundrejt ~{man} min për artikull manualisht (supozim)." if man else None)
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("Kategoria e saktë", raport_n(m.get("kategoria_ok"), m.get("kategoria_gjithsej")))
        b2.metric("Niveli i rrezikut", raport_n(m.get("rreziku_ok"), m.get("rreziku_gjithsej")))
        b3.metric("URGJENTE precision / recall",
                  f"{perqind(m.get('urgjente_precision'))} / {perqind(m.get('urgjente_recall'))}")
        b4.metric("Ngjarje të bashkuara saktë", raport_n(m.get("ngjarje_sakta"), m.get("ngjarje_gjithsej")),
                  help=f"Shumëgjuhëshe {raport_n(m.get('shumegjuhesh_sakta'), m.get('shumegjuhesh_gjithsej'))}, "
                       f"rajonale {raport_n(m.get('rajonale_sakta'), m.get('rajonale_gjithsej'))}")
        if isinstance(m.get("gjuhet"), dict) and m["gjuhet"]:
            st.dataframe(pd.DataFrame([{"Gjuha": g, "Precision": perqind(v.get("precision")),
                                        "Recall": perqind(v.get("recall"))}
                                       for g, v in m["gjuhet"].items() if isinstance(v, dict)]),
                         hide_index=True)

    st.subheader("Modeli i besueshmërisë")
    rm = lexo_json(RAPORTI_MODELIT)
    if isinstance(rm, dict) and isinstance(rm.get("metrikat"), dict):
        st.caption(f"Trajnuar mbi {rm.get('n', '?')} vendime të analistit ({rm.get('n_pozitive', '?')} të "
                   f"konfirmuara). Vendimet e reja hyjnë vetëm kur modeli ritrajnohet me "
                   f"`python trajno.py`. {rm.get('rekomandim', '')}")
        st.dataframe(pd.DataFrame([{"Modeli": k, **{x: y for x, y in v.items() if isinstance(y, (int, float))}}
                                   for k, v in rm["metrikat"].items() if isinstance(v, dict)]),
                     hide_index=True)
    else:
        st.info("Modeli është gati të mësojë nga analistët, por s'është trajnuar ende (`python trajno.py` "
                "pas etiketimit). Deri atëherë besueshmëria vjen nga rregullat e qarta te scoring.py.")

# ---------------- Artikujt ----------------
with tab_art:
    m, d = st.columns(2)
    m.subheader("Sipas burimit")
    if f.empty:
        m.caption("S'ka artikuj me këta filtra.")
    else:
        m.bar_chart(f["grupi"].value_counts())
    d.subheader("Sipas ditës së publikimit")
    datat_e_publikimit = f["publikimi"].dropna()
    if datat_e_publikimit.empty:
        d.caption("S'ka datë të njohur publikimi për këta artikuj.")
    else:
        d.bar_chart(datat_e_publikimit.str[:10].value_counts().sort_index())

    st.subheader("Lista")
    lista_artikujve = f.sort_values("data", ascending=False)[["publikimi", "burimi", "gjuha", "titulli", "url"]].copy()
    lista_artikujve["publikimi"] = lista_artikujve["publikimi"].fillna("–")
    lista_artikujve["url"] = lista_artikujve["url"].map(raporti.url_e_sigurt)
    st.dataframe(
        lista_artikujve,
        column_config={"url": st.column_config.LinkColumn("URL"),
                       "publikimi": st.column_config.TextColumn("Publikuar (ora e Kosovës)")},
        hide_index=True, width="stretch", height=400,
    )

    # Leximi i një artikulli: origjinali dhe përkthimi krah për krah
    zgjedhje = f.sort_values("data", ascending=False).head(200).set_index("id")
    if not zgjedhje.empty:
        id_zgjedhur = st.selectbox(
            "Lexo artikullin", zgjedhje.index,
            format_func=lambda i: zgjedhje.at[i, "titulli"] or str(i))
        a = zgjedhje.loc[id_zgjedhur]
        url = raporti.url_e_sigurt(a["url"])
        publikimi = a["publikimi"] if isinstance(a["publikimi"], str) else "e panjohur"
        st.markdown(f"**Publikuar:** {publikimi}"
                    + (f"  ·  [Hap burimin]({url})" if url else ""))
        # Gjurma e tekstit kur u mblodh: provon nëse portali e ndryshoi/fshiu lajmin më vonë
        if isinstance(a["hash_sha256"], str):  # pandas e jep NaN kur mungon
            h, b = st.columns([3, 1])
            h.caption(f"Hash SHA-256: `{a['hash_sha256'][:12]}…` · mbledhur më {a['mbledhur_me']} UTC")
            if a["lloji_tekstit"] != "plote" or not url:
                b.caption("Krahasimi kërkon tekst të plotë nga faqja e burimit.")
            elif b.button("Verifiko tani", key=f"vf_{id_zgjedhur}"):
                with st.spinner("Po shkarkohet faqja..."):
                    bruto = a["raw_text"] if isinstance(a["raw_text"], str) else None
                    b.write(collector.verifiko(url, a["hash_sha256"], bruto, lloji_tekstit=a["lloji_tekstit"]))
        else:
            st.caption("Pa hash: artikulli u përpunua para se të shtohej hash-i.")
        o, p = st.columns(2)
        o.text_area("Origjinali", a["teksti"] if isinstance(a["teksti"], str) else "", height=300, disabled=True)
        p.text_area("Përkthimi (EN)", a["teksti_perkthyer"] if isinstance(a["teksti_perkthyer"], str)
                    else "Ende i papërkthyer", height=300, disabled=True)

# ---------------- Ekzekutimi i pipeline-it ----------------
with tab_ekz:
    st.subheader("Ekzekuto tani")
    n = st.number_input("Sa artikuj të përkthehen dhe analizohen në një ekzekutim", 5, 500, 20, step=5,
                        help="Më shumë artikuj = më shumë kohë (rreth 1 minutë për artikull me modelin aktual).")
    # Bllokimi te ekzekuto.py s'lejon dy ekzekutime njëkohësisht.
    if ekzekuto.po_punon():
        st.info(icon=":material/hourglass_top:", body="Pipeline-i po punon tani. Shiko log-un më poshtë; kur të mbarojë, kliko 'Rifresko të dhënat'.")
    if st.button("Ekzekuto tani", type="primary", disabled=ngrire, icon=":material/play_arrow:"):
        if ekzekuto.po_punon():
            st.warning("Një ekzekutim po punon tashmë. Prit sa të mbarojë, pastaj provo sërish.")
        else:
            ekzekuto.nis_ne_sfond(n)
            st.success("U nis në sfond. Mund ta mbyllësh këtë faqe; puna vazhdon.")

    st.subheader("Automatikisht")
    opsionet = {"Jo (vetëm me dorë)": 0, "Çdo 1 orë": 1, "Çdo 2 orë": 2, "Çdo 3 orë": 3,
                "Çdo 6 orë": 6, "Çdo 12 orë": 12, "Çdo 24 orë": 24}
    if not ekzekuto.WINDOWS:
        st.info("Orari menaxhohet nga serveri. Ky kontroll përdor Windows Task Scheduler.")
    aktuale = ekzekuto.orari_aktual() if ekzekuto.WINDOWS else None
    vlera = aktuale["ore"] if aktuale else 0
    zgjedhja = st.selectbox("Sa shpesh të ekzekutohet vetë", list(opsionet),
                            index=list(opsionet.values()).index(vlera) if vlera in opsionet.values() else 0,
                            disabled=ngrire or not ekzekuto.WINDOWS)
    if aktuale:
        st.caption(f"Aktiv: çdo {aktuale['ore']} orë, {aktuale['n']} artikuj. Punon edhe kur dashboard-i "
                   "është i mbyllur, por kompjuteri duhet të jetë ndezur dhe Ollama duke punuar.")
    if st.button("Ruaj orarin", disabled=ngrire or not ekzekuto.WINDOWS):
        ore = opsionet[zgjedhja]
        ok, mesazhi = ekzekuto.vendos_orarin(ore, n) if ore else ekzekuto.hiq_orarin()
        (st.success if ok else st.error)(("Orari u ruajt." if ore else "Orari automatik u hoq.")
                                         if ok else f"Gabim nga Task Scheduler: {mesazhi}")
        if ok:
            st.rerun()

    # Rrjetet sociale: postimet hyjnë si artikuj; "Ekzekuto tani" pastaj i analizon si lajmet
    st.subheader("Rrjetet sociale (Apify)")
    import apify_burimi
    st.caption("Statusi i lejes: " + " · ".join(f"{p}: {s}" for p, s in apify_burimi.STATUSI.items())
               + ". Aktivizohet me APIFY_LEJET te variablat e serverit.")
    s1, s2, s3 = st.columns([1, 1, 2])
    platforma = s1.selectbox("Platforma", list(apify_burimi.PLATFORMAT), key="apify_platforma")
    menyra = s2.radio("Nga", ["Dataset", "Run", "Nisje e re (me pagesë)"], key="apify_menyra")
    id_apify = s3.text_input("Dataset ID ose Run ID", key="apify_id", disabled=menyra.startswith("Nisje"))
    if st.button("Merr postimet", disabled=ngrire, key="apify_merr"):
        try:
            with st.spinner("Po merren postimet nga Apify..."):
                if menyra == "Dataset":
                    rez = apify_burimi.importo(platforma, dataset=id_apify.strip())
                elif menyra == "Run":
                    rez = apify_burimi.importo(platforma, run=id_apify.strip())
                else:
                    rez = apify_burimi.nis(platforma, 20)
            st.success(f"{platforma}: {rez}. Tani shtyp 'Ekzekuto tani' që modeli t'i analizojë.")
            st.cache_data.clear()
        except apify_burimi.GabimApify as e:
            st.error(f"{platforma}: {e}")

    st.subheader("Log-u i fundit")
    st.code(ekzekuto.log_fundit(25), language=None)
    if st.button("Rifresko të dhënat", icon=":material/refresh:"):
        st.cache_data.clear()
        st.rerun()
