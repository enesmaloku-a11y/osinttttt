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
import extractor
import kercenimet
import kontrolli_dyte
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
:root { --bg: #05080a; --bg2: #0b1113; --vija: #1c2a26; --zbehte: #6f8a80; --theks: #3ddc84; }
html, body, p, label, input, textarea, .shiriti, .pllaka, .bluf, .feed, .legjenda, .klasifikimi {
    font-family: "JetBrains Mono", "IBM Plex Mono", Consolas, "Courier New", monospace; }
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display: none; }
.block-container { padding-top: 3.6rem; max-width: 1600px; }
h3 { font-size: .74rem !important; letter-spacing: .16em; text-transform: uppercase; color: var(--zbehte);
     border-bottom: 1px solid var(--vija); padding: 0 0 .3rem; margin: 1rem 0 .55rem; }
.klasifikimi { border: 1px solid var(--theks); color: var(--theks); text-align: center; font-size: .66rem;
               letter-spacing: .32em; padding: .15rem; margin-bottom: .6rem; }
.shiriti { display: flex; justify-content: space-between; align-items: center; background: var(--bg2);
           border: 1px solid var(--vija); padding: .5rem .9rem; margin-bottom: .6rem; }
.shiriti .emri { font-size: 1.05rem; font-weight: 700; letter-spacing: .22em; }
.shiriti .emri span { color: var(--theks); }
.shiriti .nen { color: var(--zbehte); font-size: .68rem; letter-spacing: .14em; text-transform: uppercase; margin-top: .15rem; }
.shiriti .gjendja { text-align: right; font-size: .7rem; color: var(--zbehte); line-height: 1.55; letter-spacing: .06em; }
.etiketa { display: inline-block; border: 1px solid var(--c); color: var(--c); padding: 0 .4rem; margin-left: .35rem;
           font-size: .66rem; letter-spacing: .12em; }
.pika { display: inline-block; width: .5rem; height: .5rem; border-radius: 50%; margin-right: .35rem;
        background: var(--c); box-shadow: 0 0 8px var(--c); }
.status { display: grid; grid-template-columns: repeat(5, 1fr); gap: .45rem; }
.pllaka { display: flex; justify-content: space-between; align-items: center; background: var(--bg2);
          border: 1px solid var(--vija); border-top: 2px solid var(--c); padding: .45rem .75rem; }
.pllaka .t { color: var(--zbehte); font-size: .66rem; letter-spacing: .14em; text-transform: uppercase; }
.pllaka .v { font-size: 1.5rem; font-weight: 700; color: var(--c); text-shadow: 0 0 10px var(--c); }
.bluf { background: var(--bg2); border: 1px solid var(--vija); border-left: 2px solid var(--theks);
        padding: .55rem .8rem; margin-top: .45rem; font-size: .8rem; line-height: 1.5; }
.bluf .t { color: var(--theks); font-size: .64rem; letter-spacing: .16em; text-transform: uppercase; margin-bottom: .2rem; }
.seksion { color: var(--theks); font-size: .64rem; letter-spacing: .16em; text-transform: uppercase; margin: .8rem 0 .3rem; }
.feed { max-height: 520px; overflow-y: auto; background: var(--bg2); border: 1px solid var(--vija); }
.lajm { display: grid; grid-template-columns: 6.5rem 1fr auto; gap: .6rem; align-items: start;
        padding: .45rem .7rem; border-bottom: 1px solid var(--vija); }
.lajm:hover { background: #0f191b; }
.lajm .koha { color: var(--zbehte); font-size: .66rem; letter-spacing: .04em; }
.lajm .tit { font-size: .74rem; line-height: 1.4; }
.lajm .bur { color: var(--zbehte); font-size: .64rem; margin-top: .1rem; }
.lajm .st { color: var(--c); font-size: .64rem; font-weight: 700; letter-spacing: .1em; text-align: right; white-space: nowrap; }
.legjenda { display: flex; gap: 1.1rem; background: var(--bg2); border: 1px solid var(--vija); border-top: none;
            padding: .3rem .7rem; font-size: .64rem; letter-spacing: .12em; color: var(--zbehte); }
[role="tablist"] { gap: .25rem; border-bottom: 1px solid var(--vija); }
[role="tab"] { background: var(--bg2); border: 1px solid var(--vija) !important; border-bottom: none !important;
               border-radius: 0; padding: .28rem .8rem !important; }
[role="tab"][aria-selected="true"] { background: var(--theks); }
[role="tab"][aria-selected="true"] p { color: #05080a !important; font-weight: 700; }
[role="tab"] p { font-size: .7rem; letter-spacing: .12em; text-transform: uppercase; }
[data-testid="stExpander"] details { background: var(--bg2); border: 1px solid var(--vija); border-radius: 0; }
[data-testid="stMetricValue"] { color: var(--theks); }
button[kind="primary"] { background: var(--theks) !important; color: #05080a !important; border-radius: 0 !important; }
button { border-radius: 0 !important; }
</style>""", unsafe_allow_html=True)
FJALEKALIMI = os.environ.get("OSINT_FJALEKALIMI")
if FJALEKALIMI and not st.session_state.get("hyri"):
    dhene = st.text_input("Password", type="password")
    if not hmac.compare_digest(dhene.encode(), FJALEKALIMI.encode()):
        if dhene:
            st.error("Wrong password.")
        st.stop()
    st.session_state["hyri"] = True
    st.rerun()

# Koka dhe paneli i komandës zënë vendin lart; mbushen më poshtë, pasi të llogariten numrat
VENDI_KOKES = st.container()
KOMANDA = st.expander("Command: collection and filters", expanded=False)

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
    st.info("Demo with **synthetic** data from `eval/gold.jsonl`. Decisions in this view are read-only.")
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
ETIKETA = {"URGJENTE": ":red-badge[URGENT]", "RAPORT": ":orange-badge[REPORT]",
           "MONITORIM": ":blue-badge[MONITOR]", "ARKIV": ":gray-badge[ARCHIVE]", None: ":gray-badge[NOT SCORED]"}
VENDIMI = {"e konfirmuar": " · :green[Confirmed]", "e pakonfirmuar": "", "e hedhur poshtë": " · :gray[Dismissed]"}
SAKTESIA = {"village": "village", "municipality": "municipality", "region": "region only",
            "exact": "exact", "approximate": "approximate", None: "unknown"}
# Ndërfaqja në anglisht: vlerat e brendshme mbeten në shqip (rreziku.py, db.py); përkthehen vetëm në shfaqje
PRIO_EN = {"URGJENTE": "URGENT", "RAPORT": "REPORT", "MONITORIM": "MONITOR", "ARKIV": "ARCHIVE", None: "NOT SCORED"}
NIVEL_EN = {"i lartë": "high", "i mesëm": "medium", "i ulët": "low", None: "–"}
STATUS_EN = {"e pakonfirmuar": "unconfirmed", "e konfirmuar": "confirmed", "e hedhur poshtë": "dismissed"}
NDIKIM_EN = {"kritik": "critical", "i lartë": "high", "mesatar": "medium", "i ulët": "low", "i papërcaktuar": "undetermined"}
URGJENCA_EN = {"në zhvillim": "developing", "afatgjatë": "long-term", "e papërcaktuar": "undetermined"}
KAT_EN = {"ushtarak_serbia": "Serbian military activity", "grupe_te_armatosura": "Armed and paramilitary groups",
          "dron_hapesire_ajrore": "Drones and airspace violations", "kibernetik": "Cyber attacks",
          "infrastrukture_kritike": "Critical infrastructure sabotage", "dezinformim": "Disinformation",
          "trazira_bllokada": "Riots and blockades", "kufi_kontrabande": "Border incidents and smuggling",
          "struktura_paralele": "Parallel structures", "diplomatik_ligjor": "Diplomatic and legal pressure",
          "ekonomik_energjetik": "Economic and energy coercion", "spiunazh_ndikim": "Espionage and foreign influence",
          "ekstremizem_terrorizem": "Extremism and terrorism", "tjeter": "Other"}
AKTOR_EN = {"shteti_serb": "Serbian state", "grupe_te_armatosura": "Armed groups", "krim_i_organizuar": "Organized crime",
            "rusia": "Russia", "kina": "China", "grupe_ekstremiste": "Extremist groups",
            "media_propagandistike": "Propaganda media", "i_panjohur": "Unknown"}
SHENJ_EN = {"fsk": "Kosovo Security Force (KSF)", "infrastrukture_kritike": "Critical infrastructure",
            "institucione": "Kosovo institutions", "kfor_nato": "KFOR / NATO", "komunitete": "Communities",
            "shoqeri": "Society and public opinion", "ekonomi": "Economy"}
KAT21_EN = {1: "Armed violence and armed groups", 2: "Sabotage of critical infrastructure", 3: "Riots and violent protests",
            4: "Military escalation and regional tension", 5: "Cyber attacks", 6: "Organized crime and trafficking",
            7: "Terrorism and violent extremism", 8: "Disinformation and information manipulation",
            9: "Impersonation of institutions and fake alerts", 10: "Threats to civilians and communities",
            11: "Disruption of communications and emergency services", 12: "Disruption of supply and transport",
            13: "Natural disasters and industrial accidents", 14: "Health crisis",
            15: "Energy weaknesses and critical dependencies", 16: "Obstruction of institutional functioning",
            17: "Corruption and institutional integrity", 18: "Weakened international cooperation",
            19: "Obstacles to security integration and cooperation", 20: "Loss of human capacity",
            21: "Foreign influence and strategic dependencies"}


def kat_en(e):
    """Emri anglisht i kategorisë së ngjarjes (vetëm për shfaqje)."""
    k = e["det"].get("kategoria")
    return KAT_EN.get(k, KAT_EN["tjeter"]) if isinstance(k, str) else KAT_EN["tjeter"]

# Ngjyrat e prioritetit në grafikë (të njëjtat si në hartë). Matrica s'ka "i pallogaritur":
# ngjarjet pa rrezik të llogaritur s'vizatohen aty.
NGJYRAT = ["#ff4d4d", "#f5a524", "#3ddc84", "#5b6b66", "#2a3632"]  # urgjente, raport, monitorim, arkiv, pa
NGJYRA_HEX = dict(zip(kercenimet.PRIORITETET, NGJYRAT))  # rrathët e hartës, si te grafikët
NGJYRA_EN = {PRIO_EN[k]: v for k, v in NGJYRA_HEX.items()}  # tabelat shfaqin prioritetin në anglisht
NGJYRAT_PRIORITETIT = alt.Scale(domain=[PRIO_EN[k] for k in kercenimet.PRIORITETET] + ["NOT SCORED"], range=NGJYRAT)
NGJYRAT_MATRICES = alt.Scale(domain=[PRIO_EN[k] for k in kercenimet.PRIORITETET], range=NGJYRAT[:4])
# Zonat e tabelës te "Përmbledhja", sipas emrave kanonikë të correlator.gjej_vendin (VENDET).
# shortcut: "mitrovic" përfshin edhe Mitrovicën e Jugut (correlator.py s'i dallon); "veri" = veriu
# pa komunë të njohur. Hani i Elezit është pika kufitare me Maqedoninë e Veriut.
ZONAT = {"North": {"mitrovic", "zvecan", "leposavi", "zubin potok", "veri"},
         "Border / crossings": {"jarinj", "bernjak", "banjsk", "hani i elezit"},
         "Pristina": {"prishtin"}}
KOSOVA = {emrat[0] for emrat in correlator.VENDET}  # vendet e Kosovës; ato te RAJONI janë jashtë saj
KOSOVA_TJETER, RAJONALE, PA_VEND = "Rest of Kosovo", "Regional (outside Kosovo)", "No location"
# Pamjet e hartës: ([jugperëndim, verilindje], zoom-i që i nxë kufijtë në hartën 450 px të lartë).
# Evropa është edhe kufiri ku mund të lëvizet harta. fit_bounds s'përdoret: st_folium e ndërton
# hartën kur korniza ka ende gjerësi 0, prandaj fitBounds del gjithmonë në zoom-in minimal (4).
PAMJET = {"Kosovo": ([[41.85, 20.00], [43.27, 21.80]], 8), "Region": ([[40.80, 18.40], [44.90, 23.10]], 6),
          "Balkans": ([[39.00, 13.00], [47.00, 30.00]], 5), "Europe": ([[34.00, -11.00], [71.00, 40.00]], 4)}
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
    st.markdown(seksion_kmd.format("Collection"), unsafe_allow_html=True)
    if DEMO_CLOUD:
        st.info("Cloud demo: collection runs only on the laptop with Ollama.")
    elif CLOUD:
        st.info("In this deployment, collection is managed by the server.")
    elif ngrire:
        st.warning("Labelling in progress: collection is frozen.")
    if st.button("Collect news now", type="primary", key="ekz_sidebar", width="stretch",
                 disabled=ngrire, help="Collects from RSS media and GDELT, then translates and analyses "
                                       "up to 20 articles with the model."):
        if ekzekuto.po_punon():
            st.warning("A collection is already running.")
        else:
            ekzekuto.nis_ne_sfond(20)
            st.success("Collection started in the background. Progress: the 'Run' tab.")
    # Rifreskimi lexon sërish bazën (pa cache), që ngjarjet e reja të duken pa pritur 60 sekonda
    if st.button("Refresh view", key="rifresko_sidebar", width="stretch"):
        st.cache_data.clear()
        st.rerun()
with k_ngj:
    st.markdown(seksion_kmd.format("Event filters"), unsafe_allow_html=True)
    zona = st.radio("Area", ["All", "Kosovo", "Regional"], horizontal=True)
    a, b_ = st.columns(2)
    prioritetet = a.multiselect("Priority", kercenimet.PRIORITETET, format_func=PRIO_EN.get)
    nivelet = b_.multiselect("Risk level", kercenimet.NIVELET, format_func=NIVEL_EN.get)
    kategorite = a.multiselect("Category", list(kercenimet.KATEGORITE), format_func=lambda k: KAT_EN.get(k, k))
    statuset = b_.multiselect("Analyst decision", db.STATUSET, format_func=STATUS_EN.get)
with k_art:
    st.markdown(seksion_kmd.format("Article filters"), unsafe_allow_html=True)
    burimet = st.multiselect("Source", sorted(artikujt["grupi"].unique()))
    gjuhet = st.multiselect("Language", sorted(artikujt["gjuha"].unique()))
    kerko = st.text_input("Search title/text")

def kalon_filtrat(e):
    rajonale = e["det"].get("rajonale") is True
    if (zona == "Kosovo" and rajonale) or (zona == "Regional" and not rajonale):
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
    burime = " · :orange[single source]" if n_pav == 1 else f" · {n_pav} origins" if n_pav > 1 else ""
    koka = (f"{ETIKETA.get(p, ETIKETA[None])} {dita_e_ngjarjes(e)} · {raporti.pastro(e['titulli'], 120)}"
            f" · risk {pike if pike is not None else '–'} · credibility {perqind(b)}"
            + (f" · {kodi}" if kodi else "") + f"{burime}{VENDIMI[e['statusi']]}")
    with st.expander(koka):
        r1, r2, r3 = st.columns(3)
        r1.metric("Risk", f"{pike}/100" if pike is not None else "–", help="How severe if true")
        r1.caption(f"Level: {NIVEL_EN.get(niveli, niveli or '–')} · Priority: {PRIO_EN.get(p, p)}")
        r2.metric("Credibility", perqind(b), help="Likelihood it is true, from the evidence")
        r2.caption(f"Admiralty: {kodi or '–'} · Sources: {len(e['burimet_l'])}, independent: {n_pav}")
        r3.metric("Decision", STATUS_EN.get(e["statusi"], e["statusi"]).capitalize())
        r3.caption("The system suggests, the analyst decides.")
        kontroll = kontrolli_dyte.lexo(e["burimet_l"])
        seksion("Initial assessment")
        st.write(f"{PRIO_EN.get(p, p or 'Pending')} · risk {pike if pike is not None else '–'}/100 · credibility {perqind(b)}")
        seksion("Second AI check")
        if kontroll:
            status = kontroll["status"]
            st.write("Needs verification" if status == "nuk_pajtohet" else
                     "Agrees" if status == "pajtohet" else "Insufficient evidence")
            st.write(raporti.pastro(kontroll["reason"], 300))
            if kontroll["gaps"]:
                st.caption("Missing evidence: " + "; ".join(raporti.pastro(x, 120) for x in kontroll["gaps"]))
        else:
            st.caption("No second check yet. The analyst's decision remains independent.")
        if p == "URGJENTE" and raporti.per_verifikim(e):
            st.warning("For verification, not for action: credibility is below 80% and not confirmed.")
        sociale = sorted({m.split(":")[0] for m in det.get("mediat") or []
                          if isinstance(m, str) and m.startswith(scoring.SOCIALE)})
        if sociale:
            st.info(f"Social media signal ({', '.join(sociale)}): for review, not confirmation. Original "
                    "links are under Sources; the status comes only from the analyst's decision.")
        # Lista e 21 kategorive (rreziku.py): kryesorja + shtesat, ndikimi dhe urgjenca
        v21 = det.get("v21") if isinstance(det.get("v21"), dict) else {}
        if v21:
            emrat = [f"{n}. {KAT21_EN.get(n, kercenimet.KATEGORITE_21[n]['emri'])}" for n in v21.get("kategorite") or []
                     if n in kercenimet.KATEGORITE_21]
            ndikimi = NDIKIM_EN.get(v21.get("ndikimi"), raporti.pastro(v21.get("ndikimi"), 20) or "–")
            st.write(f"**Categories (list of 21):** {emrat[0] + ' (main)' if emrat else '–'}"
                     + (f" + {', '.join(emrat[1:])}" if len(emrat) > 1 else "")
                     + f"  ·  **Impact:** {ndikimi}  ·  **Urgency:** "
                     + URGJENCA_EN.get(v21.get("urgjenca"), raporti.pastro(v21.get("urgjenca"), 20) or "–"))
            st.caption(f"Impact {ndikimi} ({raporti.pastro(v21.get('pse'), 120)}). "
                       "Preliminary levels, to be validated by the responsible officer.")
            if v21.get("verifikim_urgjent") is True and e["statusi"] == "e pakonfirmuar":
                st.error("Urgent verification: potentially severe impact with limited evidence.")
        shenj = ", ".join(SHENJ_EN.get(s, s) for s in det.get("shenjestrat") or []) or "–"
        aktori = det.get("aktori")
        try:
            bosh = json.loads(e.get("boshllequet") or "[]")
        except ValueError:
            bosh = []
        majtas, djathtas = st.columns(2)
        with majtas:
            seksion("What happened")
            st.markdown(tabela([
                ("Category", kat_en(e)),
                ("Actor (per model)", AKTOR_EN.get(aktori, "–") if aktori else "–"),
                ("Targets", shenj),
                ("Location", f"{raporti.pastro(e.get('vendi'), 60) or '–'} "
                             f"({SAKTESIA.get(det.get('saktesia_vendit'), 'unknown')})"),
                ("Event date", f"{dita_e_ngjarjes(e)} ({SAKTESIA.get(det.get('saktesia_dates'), 'unknown')})"),
                ("First known publication", publikimi_i_pare(e)),
                ("Area · KSF link", f"{'regional' if det.get('rajonale') else 'Kosovo'} · "
                                    f"{'yes' if det.get('lidhje_me_fsk') else 'no'}"),
                ("Type · language", f"{raporti.pastro(e.get('lloji'), 40) or '–'} · {raporti.pastro(e.get('gjuha'), 5)}"),
            ]))
        with djathtas:
            seksion("Sources")
            for u in e["burimet_l"]:
                st.markdown(f"- [{raporti.pastro(u, 90)}]({u})" if raporti.url_e_sigurt(u)
                            else f"- `{raporti.pastro(u, 120)}`")
            st.caption("Media: " + (", ".join(map(raporti.pastro, det.get("mediat") or [])) or "–"))
            seksion("Information gaps")
            st.markdown("\n".join(f"- {raporti.pastro(x)}" for x in bosh) if bosh else "None recorded.")
        majtas, djathtas = st.columns(2)
        with majtas:
            seksion("Why this risk")
            st.markdown("\n".join(f"- {raporti.pastro(a, 200)}" for a in arsyet) if arsyet else "–")
        with djathtas:
            seksion("Why this credibility")
            st.markdown("\n".join(f"- {raporti.pastro(a, 200)}" for a in det.get("arsyetimi") or []) or "–")
        konteksti = [c for c in det.get("konteksti") or [] if isinstance(c, dict)]
        if konteksti:
            seksion("External context")
            for c in konteksti:
                u = raporti.url_e_sigurt(c.get("url"))
                titulli = raporti.pastro(c.get("titulli"), 150)
                pjeset = [f"{raporti.pastro(c.get('burimi'), 30)}: " + (f"[{titulli}]({u})" if u else titulli)]
                if c.get("data"):
                    pjeset.append(raporti.pastro(c["data"], 10))
                if isinstance(c.get("ngjashmeria"), (int, float)):
                    pjeset.append(f"similarity {c['ngjashmeria']:.0%}")
                if c.get("arsyeja"):
                    pjeset.append(raporti.pastro(c["arsyeja"], 150))
                st.markdown(("- Similar case: " if c.get("lloji") == "rast_i_ngjashem" else "- Trend: ")
                            + " · ".join(pjeset))
            st.caption("Automatic similarity, not proof. Verify at the source.")
        # Vendimi i analistit: sistemi vetëm sugjeron, njeriu vendos
        seksion("Analyst decision")
        k = e["url_kryesor"]
        if DEMO_CLOUD or not k:
            st.caption(e["shenimi"] or ("Read-only demo." if DEMO_CLOUD else "The event has no source URL for a decision."))
            return
        # Një vendim i ruajtur rifreskon formularët e së njëjtës ngjarje në të gjitha skedat.
        gjurma = hashlib.sha256(f"{e['statusi']}\0{e['shenimi']}".encode()).hexdigest()[:16]
        celesi = f"{skeda}_{e['id']}_{k}_{gjurma}"
        statusi = st.segmented_control("Status", db.STATUSET, default=e["statusi"], key=f"st_{celesi}",
                                       format_func=STATUS_EN.get, label_visibility="collapsed") or e["statusi"]
        shenimi = st.text_input("Note", e["shenimi"], key=f"sh_{celesi}",
                                placeholder="e.g. confirmed by Kosovo Police on Facebook")
        if st.button("Save decision", key=f"rv_{celesi}", type="primary"):
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
        rreshtat.append({"Priority": PRIO_EN.get(p, p),
                         "Event date": dita_e_ngjarjes(e), "Published": publikimi_i_pare(e),
                         "Event": raporti.rresht(e["titulli"], 110),
                         "Source": (burimi or "–") + (f" (+{len(b) - 1})" if len(b) > 1 else "")})
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
                      "prioriteti": PRIO_EN.get(p, p), "rreziku": pike,
                      "besueshmeria": b, "kategoria": kat_en(e),
                      "burime": len(e["burimet_l"])})
    if not pikat:
        return None, pa_vlera
    # Të njëjtat fusha dhe tituj në çdo shtresë, që boshtet të mos marrin tituj të përzier
    x = alt.X("besueshmeria:Q", title="Credibility (likelihood the event is true)",
              scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format=".0%"))
    y = alt.Y("rreziku:Q", title="Risk if true (0–100)", scale=alt.Scale(domain=[0, 100]))
    vija = {"strokeDash": [4, 4], "color": "gray", "opacity": 0.8}
    vijat = (alt.Chart(pd.DataFrame({"rreziku": [rreziku.PRAGU_LARTE, rreziku.PRAGU_MESEM]}))
             .mark_rule(**vija).encode(y=y)
             + alt.Chart(pd.DataFrame({"besueshmeria": [rreziku.B_LARTE]})).mark_rule(**vija).encode(x=x))

    def etiketa(teksti, b, r, rreshtimi):
        return alt.Chart(pd.DataFrame({"besueshmeria": [b], "rreziku": [r], "t": [teksti]})).mark_text(
            align=rreshtimi, baseline="middle", color="gray", fontSize=12).encode(x=x, y=y, text="t:N")
    etiketat = (etiketa("URGENT for action", 0.99, 97, "right")
                + etiketa("URGENT for verification", 0.01, 97, "left")
                + etiketa("Reports", 0.01, (rreziku.PRAGU_LARTE + rreziku.PRAGU_MESEM) / 2, "left")
                + etiketa("Monitor", 0.01, rreziku.PRAGU_MESEM / 2, "left"))
    pika = alt.Chart(pd.DataFrame(pikat)).mark_circle(opacity=0.85).encode(
        x=x, y=y, color=alt.Color("prioriteti:N", title="Priority", scale=NGJYRAT_MATRICES),
        size=alt.Size("burime:Q", title="Sources", scale=alt.Scale(range=[60, 400], zero=False),
                      legend=alt.Legend(format="d", tickMinStep=1)),
        tooltip=[alt.Tooltip("titulli:N", title="Event"), alt.Tooltip("data:N", title="Event date"),
                 alt.Tooltip("publikimi:N", title="First known publication"),
                 alt.Tooltip("prioriteti:N", title="Priority"), alt.Tooltip("rreziku:Q", title="Risk"),
                 alt.Tooltip("besueshmeria:Q", title="Credibility", format=".0%"),
                 alt.Tooltip("kategoria:N", title="Category")])
    return (alt.layer(vijat, etiketat, pika).properties(height=420)
            .configure_view(strokeWidth=0).configure_axis(gridOpacity=0.25)), pa_vlera


def paneli_serbia(aktive, te_gjitha):
    """Ngjarjet me aktor shtetin serb: 7 ditët deri te data më e re në bazë (jo sot, që demo-ja të
    punojë), kundrejt 7 ditëve para tyre."""
    deri = max(filter(None, map(data_e, te_gjitha)), default=None)
    if deri is None:
        st.info("No events yet.")
        return
    nga = deri - timedelta(days=6)
    serbe = [e for e in aktive if e["det"].get("aktori") == "shteti_serb"]
    tani = [e for e in serbe if raporti.brenda(e, nga, deri)]
    para = [e for e in serbe if raporti.brenda(e, nga - timedelta(days=7), nga - timedelta(days=1))]

    def numrat(lista):
        pike = [p for e in lista if (p := raporti.rreziku(e)[0]) is not None]
        urg = [e for e in lista if raporti.prioriteti(e) == "URGJENTE"]
        return {"Events": len(lista), "URGENT": len(urg),
                "Of which for verification": sum(map(raporti.per_verifikim, urg)),
                "Average risk": round(sum(pike) / len(pike)) if pike else None}
    t, p = numrat(tani), numrat(para)
    for kolona, (emri, v) in zip(st.columns(2) + st.columns(2), t.items()):  # 2x2: lexohet edhe në kolonë të ngushtë
        delta = v - p[emri] if v is not None and p[emri] is not None else None
        vlera = "–" if v is None else f"{v}/100" if emri == "Average risk" else v
        kolona.metric(emri, vlera, delta=delta, delta_color="inverse", help="Change versus the previous 7 days")
    kat = Counter(k for e in tani if isinstance(k := e["det"].get("kategoria"), str) and kercenimet.kategoria_valide(k))
    st.write("**Most frequent categories:** "
             + (", ".join(f"{KAT_EN.get(k, k)} ({n})" for k, n in kat.most_common(3)) or "no events in this period"))
    st.caption(f"Events with the Serbian state as actor, {nga:%d.%m}–{deri:%d.%m.%Y} (up to the newest event in the "
               "database), compared with the previous 7 days. The actor comes from the model; verify it.")


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
    zonat = {z: {"Area": z, "Events": 0, "Urgent": 0, "Reports": 0, "kat": Counter()}
             for z in [*ZONAT, KOSOVA_TJETER, RAJONALE, PA_VEND]}
    for e in ngjarjet:
        z, p = zonat[zona_e(e)], raporti.prioriteti(e)
        z["Events"] += 1
        z["Urgent"] += p == "URGJENTE"
        z["Reports"] += p in ("RAPORT", "MONITORIM")
        z["kat"][kat_en(e)] += 1
    return pd.DataFrame([{**{k: v for k, v in z.items() if k != "kat"},
                          "Most frequent category": z["kat"].most_common(1)[0][0] if z["kat"] else "–"}
                         for z in zonat.values()])


def harta_e(ngjarjet):
    """Harta e ngjarjeve me vend të njohur: rreth sa pasiguria e vendit, pikë vetëm për vend të saktë."""
    (lat_jug, lon_per), (lat_veri, lon_lin) = PAMJET["Europe"][0]
    harta = folium.Map(location=[42.56, 20.90], zoom_start=8, min_zoom=4, max_bounds=True,
                       min_lat=lat_jug, max_lat=lat_veri, min_lon=lon_per, max_lon=lon_lin)
    harta.get_root().header.add_child(folium.Element(
        "<style>.leaflet-tile-pane{filter:invert(1) hue-rotate(180deg) brightness(.8) contrast(.95) "
        "saturate(.35)}.leaflet-container{background:#05080a}</style>"))
    for e in ngjarjet:
        if e.get("lat") is None or e.get("lon") is None:
            continue
        p, det = raporti.prioriteti(e), e["det"]
        pike = raporti.rreziku(e)[0]
        sv = det.get("saktesia_vendit")
        popup = (f"{siguro(raporti.rresht(e['titulli']))}<br>Event date: {siguro(dita_e_ngjarjes(e))}<br>"
                 f"Published: {siguro(publikimi_i_pare(e))}<br>Priority: {siguro(PRIO_EN.get(p, p))} · "
                 f"Risk: {siguro(pike if pike is not None else '–')}<br>Credibility: "
                 f"{siguro(perqind(raporti.besueshmeria(e)))} · Location: {siguro(SAKTESIA.get(sv, 'unknown'))}"
                 f"<br>Decision: {siguro(STATUS_EN.get(e['statusi'], e['statusi']))}")
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
perditesuar = mbledhja_e_fundit.strftime("%Y-%m-%d %H:%M UTC") if pd.notna(mbledhja_e_fundit) else "–"
punon = ekzekuto.po_punon()
gjendja = (("DEMO", NGJYRAT[3]) if DEMO_CLOUD
           else ("COLLECTION RUNNING", NGJYRAT[1]) if punon
           else ("FROZEN", NGJYRAT[3]) if raporti.ngrire()
           else ("READY", "#3ecf8e"))
VENDI_KOKES.markdown(f"""<div class="klasifikimi">UNCLASSIFIED · OPEN SOURCES ONLY (OSINT)</div>
<div class="shiriti"><div><div class="emri">OSINT <span>KOSOVO</span><span class="etiketa" style="--c:#3ddc84">
<span class="pika" style="--c:#3ddc84"></span>LIVE</span></div>
<div class="nen">Situation monitor · hybrid threats to the KSF and Kosovo's security</div></div>
<div class="gjendja">{pd.Timestamp.now(tz="UTC").strftime("%a, %d %b %Y %H:%M UTC").upper()}<br>
<span class="pika" style="--c:{gjendja[1]}"></span>{gjendja[0]} · last collection {perditesuar}<br>
The system suggests · the analyst decides</div></div>""", unsafe_allow_html=True)

per_verif = sum(map(raporti.per_verifikim, urgjente))
pllakat = [("Urgent", len(urgjente), NGJYRAT[0]), ("For verification", per_verif, NGJYRAT[1]),
           ("Reports", sum(raporti.prioriteti(e) == "RAPORT" for e in aktive), NGJYRAT[1]),
           ("Monitoring", sum(raporti.prioriteti(e) == "MONITORIM" for e in aktive), NGJYRAT[2]),
           ("Articles", len(f), NGJYRAT[3])]
# BLUF: një fjali për atë që ka më shumë rëndësi tani
if urgjente:
    e0 = urgjente[0]
    bluf = (f"{raporti.rresht(e0['titulli'], 160)} ({kat_en(e0)}, "
            f"{raporti.rresht(e0.get('vendi'), 40) or 'unknown location'}; risk {raporti.rreziku(e0)[0]}, "
            f"credibility {perqind(raporti.besueshmeria(e0))})")
else:
    bluf = "No urgent events with these filters."


def kolona_e_statusit():
    """Pllakat vertikale dhe BLUF-i: niveli 1 dhe 2 i vetëdijes për situatën."""
    st.markdown('<div class="status">' + "".join(
        f'<div class="pllaka" style="--c:{c}"><div class="t">{t}</div><div class="v">{int(v)}</div></div>'
        for t, v, c in pllakat) + "</div>", unsafe_allow_html=True)
    st.markdown(f'<div class="bluf"><div class="t">Most important now</div>{html.escape(bluf)}</div>',
                unsafe_allow_html=True)


def lista_live(ngjarjet, sa=15):
    """Lista live si Liveuamap: më të rejat sipas publikimit, me ngjyrën e prioritetit, orën dhe burimin.
    Çdo e dhënë nga baza kalon nga html.escape."""
    burimi_i_url = dict(zip(artikujt["url"], artikujt["burimi"]))
    rreshtat = []
    for e in sorted(ngjarjet, key=lambda e: (publikimi_i_pare(e), dita_e_ngjarjes(e)), reverse=True)[:sa]:
        p, b = raporti.prioriteti(e), e["burimet_l"]
        burimi = (burimi_i_url.get(b[0]) or urlparse(str(b[0])).hostname or "–") if b else "–"
        koha = publikimi_i_pare(e) if publikimi_i_pare(e) != "–" else dita_e_ngjarjes(e)
        rreshtat.append(
            f'<div class="lajm" style="--c:{NGJYRA_HEX.get(p, NGJYRAT[4])}"><div class="koha">{html.escape(koha)}</div>'
            f'<div><div class="tit">{html.escape(raporti.rresht(e["titulli"], 140))}</div>'
            f'<div class="bur">{html.escape(burimi)} · {html.escape(kat_en(e))}</div></div>'
            f'<div class="st">{html.escape(PRIO_EN.get(p, str(p)))}</div></div>')
    st.markdown('<div class="feed">' + ("".join(rreshtat) or '<div class="bur">No events yet.</div>')
                + "</div>", unsafe_allow_html=True)


(tab_per, tab_urg, tab_rap, tab_ngj, tab_ker, tab_bur, tab_vle,
 tab_art, tab_ekz) = st.tabs(["Overview", "Urgent", "Reports", "Events", "Threats", "Sources",
                              "Evaluation", "Articles", "Run"])

# ---------------- Përmbledhja ----------------
with tab_per:
    kolona_e_statusit()
    harta_k, lista_k = st.columns([3, 2])
    with harta_k:
        st.subheader("Situation map")
        (jug, per), (veri, lin) = PAMJET["Kosovo"][0]
        st_folium(harta_e(aktive), height=520, width="stretch", returned_objects=[], key="harta_per",
                  center=[(jug + veri) / 2, (per + lin) / 2], zoom=PAMJET["Kosovo"][1])
        st.markdown('<div class="legjenda">' + "".join(
            f'<span><span class="pika" style="--c:{c}"></span>{t}</span>'
            for t, c in zip(("URGENT", "REPORT", "MONITOR", "ARCHIVE"), NGJYRAT)) + "</div>", unsafe_allow_html=True)
    with lista_k:
        st.subheader("Live feed")
        lista_live(aktive)
    st.subheader("Latest events")
    if aktive:
        st.dataframe(ngjarjet_e_fundit(aktive).style.map(
                         lambda v: f"color: {NGJYRA_EN.get(v, NGJYRAT[4])}; font-weight: 700",
                         subset=["Priority"]), hide_index=True, width="stretch")
    else:
        st.info("No events yet.")
    majtas, djathtas = st.columns([3, 2])
    with majtas:
        st.subheader("Risk × credibility")
        grafiku, pa_vlera = grafiku_matrices(aktive)
    if grafiku is None:
        majtas.info("No events yet." if not aktive else
                    "No event has a computed risk and credibility yet (see the Urgent tab).")
    else:
        majtas.altair_chart(grafiku, width="stretch")
        majtas.caption(f"Each dot is one event ({len(aktive) - pa_vlera} on the chart"
                   + (f"; {pa_vlera} without risk or credibility are not shown" if pa_vlera else "") + "). "
                   f"Vertical line = credibility {rreziku.B_LARTE:.0%}: right URGENT for action, left for "
                   f"verification. Horizontal lines = risk thresholds {rreziku.PRAGU_LARTE} (high) and "
                   f"{rreziku.PRAGU_MESEM} (medium). Colour = priority computed by rreziku.py: with credibility "
                   "below 50% a medium risk drops to MONITOR, a low risk with credibility below 80% to ARCHIVE, "
                   "and an event confirmed by the analyst is for action even left of the line. "
                   "Size = number of sources.")
    with djathtas:
        st.subheader("Serbia: state actor")
        paneli_serbia(aktive, te_gjitha)
    st.subheader("Where: events by area")
    if aktive:
        st.dataframe(tabela_zonave(aktive), hide_index=True, width="stretch")
        st.caption("The area comes from the known event location (correlator.py). North: Mitrovica, Zvečan, "
                   "Leposavić, Zubin Potok, 'north'. Border: Jarinje, Bërnjak, Banjska, Hani i Elezit. "
                   "Reports = REPORT + MONITOR, as in the Reports tab.")
    else:
        st.info("No events yet.")

# ---------------- Urgjente ----------------
with tab_urg:
    if pa_rrezik:
        st.info("Risk has not been computed yet. Run the pipeline (step 7) or `python rreziku.py`.")
    st.caption("High risk to the KSF or Kosovo's security, sorted by risk. "
               "'For verification' = credibility below 80% and not confirmed by the analyst.")
    for e in urgjente:
        kartela(e, "urg")
    if not urgjente and not pa_rrezik:
        st.success("No urgent events with these filters.")

    st.subheader("Daily report")
    raporti_kyc = f"raporti_{db.DB_PATH}"
    if st.button("Generate daily report", icon=":material/description:"):
        deri = date.today()
        if len(artikujt) and artikujt["url"].str.startswith("gold://").all():
            deri = max(filter(None, map(data_e, te_gjitha)), default=deri)
        st.session_state[raporti_kyc] = (
            f"raporti_{deri.isoformat()}.md", raporti.permbajtja(te_gjitha, deri, db.fillimi_i_mbledhjes())
        )
    if raporti_kyc in st.session_state:
        emri, teksti = st.session_state[raporti_kyc]
        st.download_button("Download report", teksti, icon=":material/download:", file_name=emri, mime="text/markdown")
        with st.expander("View report", expanded=True):
            st.markdown(teksti)

# ---------------- Raporte ----------------
with tab_rap:
    st.caption("REPORT: medium risk to be reported. MONITOR: to be followed. "
               "ARCHIVE events and dismissed events are only under 'Events'.")
    for emri_p in ("RAPORT", "MONITORIM"):
        grupi = [e for e in raporte if raporti.prioriteti(e) == emri_p]
        st.subheader(f"{PRIO_EN[emri_p].capitalize()} ({len(grupi)})")
        for e in grupi:
            kartela(e, f"rap_{emri_p}")
        if not grupi:
            st.caption("None.")

# ---------------- Ngjarjet ----------------
with tab_ngj:
    # Alarmet nga patterns.py (rritje e pazakontë e ngjarjeve në një komunë)
    fillimi = db.fillimi_i_mbledhjes()
    alarmet = patterns.rritjet(aktive, fillimi_mbledhjes=fillimi)
    for a in alarmet:
        st.warning(patterns.pershkrim(a), icon=":material/warning:")
    if fillimi and ngj and not patterns.histori_e_mjaftueshme(fillimi, max(str(e["data"]) for e in ngj)):
        st.caption(f"Surge alerts activate after 5 weeks of collection "
                   f"(collection started on {str(fillimi)[:10]}).")
    elif not alarmet:
        st.caption("No unusual surges (rule: ≥ 3 events in 7 days and ≥ 2x the weekly average).")

    pamja = st.radio("Map view", list(PAMJET), horizontal=True, key="pamja_harte")
    harta = harta_e(ngj)
    st.caption("Colour: red URGENT, orange REPORT, blue MONITOR, grey ARCHIVE. News has no GPS, so the "
               "location is shown with the known precision: circle ~15 km = region only, ~5 km = municipality "
               "(its centre), dot = village or exact place. Ring = regional event (outside Kosovo). Events "
               "without a known location are not on the map but are in the list. The map needs internet "
               "(without it the timeline and list still work).")
    # Qendra dhe zoom-i i jepen st_folium-it: kalimi mes pamjeve s'e ringarkon hartën
    (jug, per), (veri, lin) = PAMJET[pamja][0]
    st_folium(harta, height=450, width="stretch", returned_objects=[], key="harta_ngj",
              center=[(jug + veri) / 2, (per + lin) / 2], zoom=PAMJET[pamja][1])

    if not ngj:
        st.info("No events yet (or the filters hide them all).")
    else:
        # Kronologjia: një pikë për çdo ngjarje, sipas datës dhe kategorisë
        st.subheader("Timeline")
        k = pd.DataFrame([{
            "dita": dita_e_ngjarjes(e), "publikimi": publikimi_i_pare(e), "kategoria": kat_en(e),
            "prioriteti": PRIO_EN.get(raporti.prioriteti(e), "NOT SCORED"),
            "titulli": raporti.rresht(e["titulli"], 120), "burime": len(e["burimet_l"]),
            "besueshmeria": perqind(raporti.besueshmeria(e)),
            "rreziku": raporti.rreziku(e)[0] if raporti.rreziku(e)[0] is not None else -1,
        } for e in ngj])
        k["dita"] = pd.to_datetime(k["dita"], errors="coerce")
        k = k.dropna(subset=["dita"])
        grafiku = alt.Chart(k).mark_circle(opacity=0.8).encode(
            # ngjarjet kanë vetëm datë (pa orë), ndaj boshti tregon ditë
            x=alt.X("dita:T", title="Date", axis=alt.Axis(format="%d %b", tickCount="day"),
                    scale=alt.Scale(padding=30)),
            y=alt.Y("kategoria:N", title="Category", axis=alt.Axis(labelLimit=250)),
            size=alt.Size("burime:Q", title="Sources", scale=alt.Scale(range=[80, 500], zero=False),
                          legend=alt.Legend(format="d", tickMinStep=1)),
            color=alt.Color("prioriteti:N", title="Priority", scale=NGJYRAT_PRIORITETIT),
            tooltip=[alt.Tooltip("dita:T", title="Event date"),
                     alt.Tooltip("publikimi:N", title="First known publication"), alt.Tooltip("titulli:N", title="Event"),
                     alt.Tooltip("prioriteti:N", title="Priority"), alt.Tooltip("rreziku:Q", title="Risk"),
                     alt.Tooltip("besueshmeria:N", title="Credibility"), alt.Tooltip("burime:Q", title="Sources")],
        )
        st.altair_chart(grafiku, width="stretch")
        st.caption("Each dot is one event. Size shows the number of sources.")

        st.subheader(f"All events ({len(ngj)})")
        for e in ngj:
            kartela(e, "ngj")

# ---------------- Kërcënimet (taksonomia) ----------------
with tab_ker:
    st.caption("Taxonomy of hybrid threats to the KSF and Kosovo's security (kercenimet.py). "
               "The base severity 1–5 is the starting point of rreziku.py.")
    numri = Counter(k for e in aktive if isinstance(k := e["det"].get("kategoria"), str))
    st.dataframe(pd.DataFrame([{
        "Category": KAT_EN.get(i, c["emri"]), "Base severity": c["rrezikshmeria_baze"],
        "Events now": numri.get(i, 0), "Description": extractor.KATEGORI_EN.get(i, c["pershkrimi"])}
        for i, c in kercenimet.KATEGORITE.items()]), hide_index=True, width="stretch")
    for i, c in kercenimet.KATEGORITE.items():
        if i == "tjeter":
            continue
        with st.expander(f"{KAT_EN.get(i, c['emri'])} · base severity {c['rrezikshmeria_baze']}/5 · {numri.get(i, 0)} events"):
            st.write(extractor.KATEGORI_EN.get(i, c["pershkrimi"]))
            st.write("**Indicators (Albanian, from the taxonomy):** " + "; ".join(c["treguesit"]))
            st.write("**Typical actors:** " + ", ".join(AKTOR_EN.get(a, a) for a in c["aktoret_tipike"]))
            st.write("**Typical targets:** " + ", ".join(SHENJ_EN.get(s, s) for s in c["shenjestrat_tipike"]))
            st.write("**Collected from:** " + "; ".join(map(str, c["burimet_e_mbledhjes"])))
            for s in c["shembuj"]:
                u = raporti.url_e_sigurt(s.get("url"))
                st.markdown(f"- {raporti.pastro(s.get('pershkrimi'), 200)}" + (f" ([source]({u}))" if u else ""))

# ---------------- Burimet ----------------
with tab_bur:
    st.subheader("Our sources")
    st.caption("How many events each outlet brings and what the analyst decided. Only media, institutions "
               "and platforms: no individual accounts.")
    rreshtat = {}
    for e in ngj:
        for m in e["det"].get("mediat") or []:
            r = rreshtat.setdefault(m, {"Source": m, "Events": 0, "Urgent": 0, "Confirmed": 0,
                                        "Dismissed": 0})
            r["Events"] += 1
            r["Urgent"] += raporti.prioriteti(e) == "URGJENTE"
            r["Confirmed"] += e["statusi"] == "e konfirmuar"
            r["Dismissed"] += e["statusi"] == "e hedhur poshtë"
    besueshmeria_e = getattr(scoring, "besueshmeria_e_mediumit", lambda m: scoring.MEDIAT.get(m, scoring.E_PANJOHUR))
    for r in rreshtat.values():
        r["Outlet credibility"] = besueshmeria_e(r["Source"])
    if rreshtat:
        st.dataframe(pd.DataFrame(sorted(rreshtat.values(), key=lambda r: -r["Events"])),
                     hide_index=True, width="stretch",
                     column_config={"Outlet credibility": st.column_config.NumberColumn(format="%.2f")})
    else:
        st.caption("No events yet.")

    st.subheader("Sources with documented disinformation (EUvsDisinfo)")
    dez = raporti.burimet_e_dezinformimit()
    if dez:
        st.caption("Based on EUvsDisinfo cases on Kosovo and the region. Social media channels are grouped "
                   "by platform, without account names.")
        st.dataframe(pd.DataFrame(dez), hide_index=True, width="stretch",
                     column_config={"url_shembull": st.column_config.LinkColumn("Latest case")})
    else:
        st.info("List missing: place the CSV export at data/euvsdisinfo.csv (see kontekst_dezinformim.py).")

# ---------------- Vlerësimi ----------------
with tab_vle:
    r = lexo_json(REZULTATI)
    st.subheader("System accuracy (gold set)")
    if not isinstance(r, dict) or not isinstance(r.get("metrikat"), dict):
        st.info("No result yet. Run: `python eval/evaluate.py`")
    else:
        m = r["metrikat"]

        def raport_n(a, b):
            return f"{a}/{b}" if isinstance(a, int) and isinstance(b, int) and b else "–"
        st.caption(f"On {r.get('artikuj', '?')} SYNTHETIC articles (eval/gold.jsonl), model {r.get('modeli', '?')}, "
                   f"{str(r.get('koha', ''))[:16]}. With real news the numbers are expected to be lower.")
        a1, a2, a3, a4 = st.columns(4)
        a1.metric("Precision (detection)", perqind(m.get("precision")))
        a2.metric("Recall (detection)", perqind(m.get("recall")))
        a3.metric("False alarms", raport_n(m.get("fp"), m.get("negative")))
        sek, n, man = r.get("sekonda"), r.get("artikuj"), r.get("minuta_manuale")
        if isinstance(sek, (int, float)) and isinstance(n, int) and n:
            a4.metric("Time per article", f"{sek / n:.1f} s",
                      help=f"Versus ~{man} min per article manually (assumption, not measured)." if man else None)
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("Correct category", raport_n(m.get("kategoria_ok"), m.get("kategoria_gjithsej")))
        b2.metric("Risk level", raport_n(m.get("rreziku_ok"), m.get("rreziku_gjithsej")))
        b3.metric("URGJENTE precision / recall",
                  f"{perqind(m.get('urgjente_precision'))} / {perqind(m.get('urgjente_recall'))}")
        b4.metric("Correctly merged events", raport_n(m.get("ngjarje_sakta"), m.get("ngjarje_gjithsej")),
                  help=f"Multilingual {raport_n(m.get('shumegjuhesh_sakta'), m.get('shumegjuhesh_gjithsej'))}, "
                       f"regional {raport_n(m.get('rajonale_sakta'), m.get('rajonale_gjithsej'))}")
        if isinstance(m.get("gjuhet"), dict) and m["gjuhet"]:
            st.dataframe(pd.DataFrame([{"Language": g, "Precision": perqind(v.get("precision")),
                                        "Recall": perqind(v.get("recall"))}
                                       for g, v in m["gjuhet"].items() if isinstance(v, dict)]),
                         hide_index=True)

    st.subheader("Credibility model")
    rm = lexo_json(RAPORTI_MODELIT)
    if isinstance(rm, dict) and isinstance(rm.get("metrikat"), dict):
        st.caption(f"Trained on {rm.get('n', '?')} analyst decisions ({rm.get('n_pozitive', '?')} "
                   f"confirmed). New decisions are used only when the model is retrained with "
                   f"`python trajno.py`. {rm.get('rekomandim', '')}")
        st.dataframe(pd.DataFrame([{"Model": k, **{x: y for x, y in v.items() if isinstance(y, (int, float))}}
                                   for k, v in rm["metrikat"].items() if isinstance(v, dict)]),
                     hide_index=True)
    else:
        st.info("The model is ready to learn from analysts but is not trained yet (`python trajno.py` "
                "after labelling). Until then credibility comes from the explicit rules in scoring.py.")

# ---------------- Artikujt ----------------
with tab_art:
    m, d = st.columns(2)
    m.subheader("By source")
    if f.empty:
        m.caption("No articles with these filters.")
    else:
        m.bar_chart(f["grupi"].value_counts())
    d.subheader("By publication day")
    datat_e_publikimit = f["publikimi"].dropna()
    if datat_e_publikimit.empty:
        d.caption("No known publication date for these articles.")
    else:
        d.bar_chart(datat_e_publikimit.str[:10].value_counts().sort_index())

    st.subheader("List")
    lista_artikujve = f.sort_values("data", ascending=False)[["publikimi", "burimi", "gjuha", "titulli", "url"]].copy()
    lista_artikujve["publikimi"] = lista_artikujve["publikimi"].fillna("–")
    lista_artikujve["url"] = lista_artikujve["url"].map(raporti.url_e_sigurt)
    st.dataframe(
        lista_artikujve,
        column_config={"url": st.column_config.LinkColumn("URL"),
                       "publikimi": st.column_config.TextColumn("Published (Kosovo time)"),
                       "burimi": st.column_config.TextColumn("Source"), "gjuha": st.column_config.TextColumn("Language"),
                       "titulli": st.column_config.TextColumn("Title")},
        hide_index=True, width="stretch", height=400,
    )

    # Leximi i një artikulli: origjinali dhe përkthimi krah për krah
    zgjedhje = f.sort_values("data", ascending=False).head(200).set_index("id")
    if not zgjedhje.empty:
        id_zgjedhur = st.selectbox(
            "Read article", zgjedhje.index,
            format_func=lambda i: zgjedhje.at[i, "titulli"] or str(i))
        a = zgjedhje.loc[id_zgjedhur]
        url = raporti.url_e_sigurt(a["url"])
        publikimi = a["publikimi"] if isinstance(a["publikimi"], str) else "unknown"
        st.markdown(f"**Published:** {publikimi}"
                    + (f"  ·  [Open source]({url})" if url else ""))
        # Gjurma e tekstit kur u mblodh: provon nëse portali e ndryshoi/fshiu lajmin më vonë
        if isinstance(a["hash_sha256"], str):  # pandas e jep NaN kur mungon
            h, b = st.columns([3, 1])
            h.caption(f"Hash SHA-256: `{a['hash_sha256'][:12]}…` · collected on {a['mbledhur_me']} UTC")
            if a["lloji_tekstit"] != "plote" or not url:
                b.caption("The comparison needs the full text from the source page.")
            elif b.button("Verify now", key=f"vf_{id_zgjedhur}"):
                with st.spinner("Downloading the page..."):
                    bruto = a["raw_text"] if isinstance(a["raw_text"], str) else None
                    b.write(collector.verifiko(url, a["hash_sha256"], bruto, lloji_tekstit=a["lloji_tekstit"]))
        else:
            st.caption("No hash: the article was processed before hashing was added.")
        o, p = st.columns(2)
        o.text_area("Original", a["teksti"] if isinstance(a["teksti"], str) else "", height=300, disabled=True)
        p.text_area("Translation (EN)", a["teksti_perkthyer"] if isinstance(a["teksti_perkthyer"], str)
                    else "Not translated yet", height=300, disabled=True)

# ---------------- Ekzekutimi i pipeline-it ----------------
with tab_ekz:
    st.subheader("Run now")
    n = st.number_input("How many articles to translate and analyse in one run", 5, 500, 20, step=5,
                        help="More articles = more time.")
    # Bllokimi te ekzekuto.py s'lejon dy ekzekutime njëkohësisht.
    if ekzekuto.po_punon():
        st.info(icon=":material/hourglass_top:", body="The pipeline is running. Watch the log below; when it finishes, click 'Refresh data'.")
    if st.button("Run now", type="primary", disabled=ngrire, icon=":material/play_arrow:"):
        if ekzekuto.po_punon():
            st.warning("A run is already in progress. Wait until it finishes, then try again.")
        else:
            ekzekuto.nis_ne_sfond(n)
            st.success("Started in the background. You can close this page; the work continues.")

    st.subheader("Automatic")
    opsionet = {"No (manual only)": 0, "Every 1 hour": 1, "Every 2 hours": 2, "Every 3 hours": 3,
                "Every 6 hours": 6, "Every 12 hours": 12, "Every 24 hours": 24}
    if not ekzekuto.WINDOWS:
        st.info("The schedule is managed by the server. This control uses Windows Task Scheduler.")
    aktuale = ekzekuto.orari_aktual() if ekzekuto.WINDOWS else None
    vlera = aktuale["ore"] if aktuale else 0
    zgjedhja = st.selectbox("How often to run automatically", list(opsionet),
                            index=list(opsionet.values()).index(vlera) if vlera in opsionet.values() else 0,
                            disabled=ngrire or not ekzekuto.WINDOWS)
    if aktuale:
        st.caption(f"Active: every {aktuale['ore']} hours, {aktuale['n']} articles. Runs even when the dashboard "
                   "is closed, but the computer must be on and Ollama running.")
    if st.button("Save schedule", disabled=ngrire or not ekzekuto.WINDOWS):
        ore = opsionet[zgjedhja]
        ok, mesazhi = ekzekuto.vendos_orarin(ore, n) if ore else ekzekuto.hiq_orarin()
        (st.success if ok else st.error)(("Schedule saved." if ore else "Automatic schedule removed.")
                                         if ok else f"Task Scheduler error: {mesazhi}")
        if ok:
            st.rerun()

    # Rrjetet sociale: postimet hyjnë si artikuj; "Ekzekuto tani" pastaj i analizon si lajmet
    st.subheader("Social media (Apify)")
    import apify_burimi
    st.caption("Permission status: " + " · ".join(f"{p}: {s}" for p, s in apify_burimi.STATUSI.items())
               + ". Enabled with APIFY_LEJET in the server variables.")
    s1, s2, s3 = st.columns([1, 1, 2])
    platforma = s1.selectbox("Platform", list(apify_burimi.PLATFORMAT), key="apify_platforma")
    menyra = s2.radio("From", ["Dataset", "Run", "New run (paid)"], key="apify_menyra")
    id_apify = s3.text_input("Dataset ID or Run ID", key="apify_id", disabled=menyra.startswith("New"))
    if st.button("Fetch posts", disabled=ngrire, key="apify_merr"):
        try:
            with st.spinner("Fetching posts from Apify..."):
                if menyra == "Dataset":
                    rez = apify_burimi.importo(platforma, dataset=id_apify.strip())
                elif menyra == "Run":
                    rez = apify_burimi.importo(platforma, run=id_apify.strip())
                else:
                    rez = apify_burimi.nis(platforma, 20)
            st.success(f"{platforma}: {rez}. Now press 'Run now' so the model analyses them.")
            st.cache_data.clear()
        except apify_burimi.GabimApify as e:
            st.error(f"{platforma}: {e}")

    st.subheader("Latest log")
    st.code(ekzekuto.log_fundit(25), language=None)
    if st.button("Refresh data", icon=":material/refresh:"):
        st.cache_data.clear()
        st.rerun()
