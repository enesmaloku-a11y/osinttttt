"""dashboard.py - Pamja për analistin. Sistemi vetëm ndihmon; vendimi është i analistit.

Nis me:  streamlit run dashboard.py
"""
import html
import json
import sqlite3

import altair as alt
import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

import collector
import db
import ekzekuto
import patterns

st.set_page_config(page_title="OSINT Kosova", layout="wide")


@st.cache_data(ttl=60)
def lexo(sql):
    """Lexon një tabelë nga SQLite (cache 60 sekonda që faqja të jetë e shpejtë)."""
    db.lidhu().close()  # krijon tabelat nëse baza është e re
    with sqlite3.connect(db.DB_PATH) as con:
        return pd.read_sql(sql, con)


artikujt = lexo("SELECT id, url, burimi, titulli, data, gjuha, teksti, teksti_perkthyer, "
                "perpunuar, hash_sha256, mbledhur_me FROM articles")
ngjarjet = lexo("SELECT * FROM events")
vendimet = db.vendimet()

# Vendimi i analistit gjendet te cilado URL e ngjarjes, që të mos humbasë kur hyn artikull i ri
IKONAT = {"e konfirmuar": "✅", "e pakonfirmuar": "❓", "e hedhur poshtë": "❌"}
ngjarjet["url_kryesor"] = ngjarjet["burimet"].apply(
    lambda b: db.url_i_vendimit(json.loads(b), vendimet))
ngjarjet["statusi"] = ngjarjet["url_kryesor"].map(
    lambda u: vendimet.get(u, {}).get("statusi", "e pakonfirmuar"))
ngjarjet["shenimi"] = ngjarjet["url_kryesor"].map(lambda u: vendimet.get(u, {}).get("shenimi") or "")

artikujt["data"] = pd.to_datetime(artikujt["data"], utc=True, errors="coerce")
# Të gjitha domenet e GDELT bashkohen në një grup që grafiku të mbetet i lexueshëm
artikujt["grupi"] = artikujt["burimi"].where(~artikujt["burimi"].str.startswith("GDELT:"), "GDELT")

# ---------------- Filtrat ----------------
# Butoni kryesor në krye të sidebar-it, që të duket gjithmonë (edhe në ekran të vogël)
st.sidebar.header("Pipeline-i")
if st.sidebar.button("▶️ Ekzekuto tani", type="primary", key="ekz_sidebar", use_container_width=True):
    if ekzekuto.po_punon():
        st.sidebar.warning("Një ekzekutim po punon tashmë.")
    else:
        ekzekuto.nis_ne_sfond(20)
        st.sidebar.success("U nis në sfond (20 artikuj).")
st.sidebar.caption("⏳ Po punon tani…" if ekzekuto.po_punon() else
                   "Orari dhe log-u: skeda 'Ekzekutimi'.")

st.sidebar.header("Filtrat")
burimet = st.sidebar.multiselect("Burimi", sorted(artikujt["grupi"].unique()))
gjuhet = st.sidebar.multiselect("Gjuha", sorted(artikujt["gjuha"].unique()))
kerko = st.sidebar.text_input("Kërko në titull/tekst")
statuset = st.sidebar.multiselect("Vendimi i analistit (ngjarjet)", db.STATUSET)
if statuset:
    ngjarjet = ngjarjet[ngjarjet["statusi"].isin(statuset)]

f = artikujt
if burimet:
    f = f[f["grupi"].isin(burimet)]
if gjuhet:
    f = f[f["gjuha"].isin(gjuhet)]
if kerko:
    ka = f["titulli"].str.contains(kerko, case=False, na=False) | \
         f["teksti"].str.contains(kerko, case=False, na=False)
    f = f[ka]

# ---------------- Përmbledhja ----------------
st.title("OSINT Kosova: prototip")
st.caption("Sistemi vetëm sugjeron. Çdo vendim e merr analisti.")

k1, k2, k3, k4 = st.columns(4)
k1.metric("Artikuj", len(f))
k2.metric("Të përkthyer", int(f["teksti_perkthyer"].notna().sum()))
k3.metric("Të përpunuar", int(f["perpunuar"].sum()))
k4.metric("Ngjarje", len(ngjarjet))

tab_ngj, tab_art, tab_ekz = st.tabs(["Ngjarjet", "Artikujt", "Ekzekutimi"])

# ---------------- Ngjarjet ----------------
with tab_ngj:
    # Alarmet nga patterns.py (rritje e pazakontë e ngjarjeve në një komunë)
    fillimi = db.fillimi_i_mbledhjes()
    alarmet = patterns.rritjet(ngjarjet.to_dict("records"), fillimi_mbledhjes=fillimi)
    for a in alarmet:
        st.warning("⚠️ " + patterns.pershkrim(a))
    if fillimi and not ngjarjet.empty and not patterns.histori_e_mjaftueshme(
            fillimi, ngjarjet["data"].max()):
        st.caption(f"Alarmet për rritje aktivizohen pas 5 javë mbledhjeje "
                   f"(mbledhja filloi më {str(fillimi)[:10]}).")
    elif not alarmet:
        st.caption("S'ka rritje të pazakonta (rregulli: ≥ 3 ngjarje në 7 ditë dhe ≥ 2x mesatarja javore).")

    # Ngjyra sipas besueshmërisë: jeshile >= 70%, portokalli >= 40%, e kuqe më poshtë
    def ngjyra(v):
        return "gray" if pd.isna(v) else "green" if v >= 0.7 else "orange" if v >= 0.4 else "red"

    ngjarjet["ngjyra"] = ngjarjet["besueshmeria"].apply(ngjyra)
    # Besueshmëria vjen nga scoring.py; nëse mungon shfaqet "e pavlerësuar"
    ngjarjet["besueshmeria"] = ngjarjet["besueshmeria"].apply(
        lambda v: "e pavlerësuar" if pd.isna(v) else f"{v:.0%}")
    harta = folium.Map(location=[42.6, 20.9], zoom_start=8)  # qendra e Kosovës
    SAKTESIA = {"village": "fshat", "municipality": "komunë", "region": "vetëm rajon",
                "exact": "e saktë", "approximate": "e përafërt", None: "e panjohur"}
    ngjarjet["det"] = ngjarjet["detajet_json"].apply(lambda d: json.loads(d or "{}"))
    for _, e in ngjarjet.dropna(subset=["lat", "lon"]).iterrows():
        sv = e["det"].get("saktesia_vendit")
        # Titulli vjen nga lajmi/modeli. Folium e fut në një template literal JS (`...`),
        # ndaj përveç HTML-së neutralizohen edhe \\, ` dhe $ (${...}, \u{...})
        titulli = html.escape(e["titulli"]).replace("\\", "&#92;").replace("`", "&#96;").replace("$", "&#36;")
        popup = (f"{titulli}<br>Besueshmëria: {e['besueshmeria']}<br>"
                 f"Vendi: {SAKTESIA[sv]} · Vendimi: {e['statusi']}")
        if sv == "region":
            # Vend i përafërt: rreth i madh në vend të pikës, që të mos duket më i saktë se ç'është
            folium.Circle([e["lat"], e["lon"]], radius=15000, color=e["ngjyra"], fill=True,
                          fill_opacity=0.15, tooltip=titulli, popup=popup).add_to(harta)
        else:
            folium.Marker([e["lat"], e["lon"]], tooltip=titulli, popup=popup,
                          icon=folium.Icon(color=e["ngjyra"])).add_to(harta)
    st.caption("Ngjyra: jeshile ≥ 70%, portokalli ≥ 40%, e kuqe < 40%. Rrethi = vendi dihet vetëm "
               "në nivel rajoni. Ngjarjet pa vend të njohur nuk dalin në hartë, por janë në listë.")
    st_folium(harta, height=450, use_container_width=True, returned_objects=[])

    if ngjarjet.empty:
        st.info("Ende s'ka ngjarje. Ato shfaqen këtu pasi të shtohen extractor.py dhe correlator.py.")
    else:
        # Kronologjia: një pikë për çdo ngjarje, sipas datës dhe llojit
        st.subheader("Kronologjia")
        nivelet = {"green": "≥ 70%", "orange": "40–70%", "red": "< 40%", "gray": "e pavlerësuar"}
        k = ngjarjet.assign(
            dita=pd.to_datetime(ngjarjet["data"], errors="coerce"),
            lloji=ngjarjet["lloji"].fillna("other"),
            burime=ngjarjet["burimet"].apply(lambda b: len(json.loads(b))),
            niveli=ngjarjet["ngjyra"].map(nivelet),
        ).dropna(subset=["dita"])
        grafiku = alt.Chart(k).mark_circle(opacity=0.8).encode(
            # ngjarjet kanë vetëm datë (pa orë), ndaj boshti tregon ditë
            x=alt.X("dita:T", title="Data", axis=alt.Axis(format="%d %b", tickCount="day"),
                    scale=alt.Scale(padding=30)),
            y=alt.Y("lloji:N", title="Lloji", axis=alt.Axis(labelLimit=250)),
            size=alt.Size("burime:Q", title="Burime", scale=alt.Scale(range=[80, 500], zero=False),
                          legend=alt.Legend(format="d", tickMinStep=1)),
            color=alt.Color("niveli:N", title="Besueshmëria",
                            scale=alt.Scale(domain=list(nivelet.values()),
                                            range=list(nivelet.keys()))),
            tooltip=[alt.Tooltip("dita:T", title="Data"), alt.Tooltip("titulli:N", title="Ngjarja"),
                     alt.Tooltip("besueshmeria:N", title="Besueshmëria"),
                     alt.Tooltip("burime:Q", title="Burime")],
        )
        st.altair_chart(grafiku, use_container_width=True)
        st.caption("Çdo pikë është një ngjarje. Madhësia tregon numrin e burimeve.")

        for _, e in ngjarjet.sort_values("data", ascending=False).iterrows():
            with st.expander(f"{IKONAT[e['statusi']]} {e['data'][:10]} · {e['titulli']} · "
                             f"besueshmëria {e['besueshmeria']}"):
                det = e["det"]
                st.write(f"**Lloji:** {e['lloji'] or '-'}  ·  **Vendi:** {e['vendi'] or '-'} "
                         f"({SAKTESIA[det.get('saktesia_vendit')]})  ·  "
                         f"**Data:** {SAKTESIA[det.get('saktesia_dates')]}  ·  **Gjuha:** {e['gjuha']}")
                st.write("**Boshllëqet:** " + (", ".join(json.loads(e["boshllequet"])) or "asnjë"))
                st.write(f"**Mediat:** {', '.join(det.get('mediat', []))}  ·  "
                         f"**Aktorët:** {', '.join(det.get('aktoret', [])) or '-'}")
                if det.get("arsyetimi"):
                    st.write("**Pse kjo besueshmëri:**")
                    for a in det["arsyetimi"]:
                        st.markdown(f"- {a}")
                # Raste të ngjashme nga burime të jashtme (kontekst_*.py): sugjerim, jo provë
                if det.get("konteksti"):
                    st.write("**Konteksti (raste të ngjashme):**")
                for x in det.get("konteksti") or []:
                    emri = f"[{x['titulli']}]({x['url']})" if x.get("url") else x["titulli"]
                    st.markdown(f"- {x['burimi']}: {emri} ({x.get('arsyeja') or ''})")
                st.write("**Burimet:**")
                for u in json.loads(e["burimet"]):
                    st.markdown(f"- [{u}]({u})")

                # Vendimi i analistit: sistemi vetëm sugjeron, njeriu vendos
                st.write("**Vendimi i analistit:**")
                k = e["url_kryesor"]
                statusi = st.radio("Statusi", db.STATUSET, index=db.STATUSET.index(e["statusi"]),
                                   key=f"st_{k}", horizontal=True, label_visibility="collapsed")
                shenimi = st.text_input("Shënim", e["shenimi"], key=f"sh_{k}",
                                        placeholder="p.sh. e konfirmoi Policia në Facebook")
                if st.button("Ruaj vendimin", key=f"rv_{k}"):
                    db.ruaj_vendimin(k, statusi, shenimi)
                    st.cache_data.clear()
                    st.rerun()

# ---------------- Artikujt ----------------
with tab_art:
    m, d = st.columns(2)
    m.subheader("Sipas burimit")
    m.bar_chart(f["grupi"].value_counts())
    d.subheader("Sipas ditës")
    d.bar_chart(f.dropna(subset=["data"]).groupby(f["data"].dt.date).size())

    st.subheader("Lista")
    st.dataframe(
        f.sort_values("data", ascending=False)[["data", "burimi", "gjuha", "titulli", "url"]],
        column_config={"url": st.column_config.LinkColumn("URL"),
                       "data": st.column_config.DatetimeColumn("Data", format="YYYY-MM-DD HH:mm")},
        hide_index=True, use_container_width=True, height=400,
    )

    # Leximi i një artikulli: origjinali dhe përkthimi krah për krah
    zgjedhje = f.sort_values("data", ascending=False).head(200)
    if not zgjedhje.empty:
        id_zgjedhur = st.selectbox(
            "Lexo artikullin", zgjedhje["id"],
            format_func=lambda i: zgjedhje.set_index("id").loc[i, "titulli"] or str(i))
        a = zgjedhje.set_index("id").loc[id_zgjedhur]
        st.markdown(f"[Hap burimin]({a['url']})")
        # Gjurma e tekstit kur u mblodh: provon nëse portali e ndryshoi/fshiu lajmin më vonë
        if isinstance(a["hash_sha256"], str):  # pandas e jep NaN kur mungon
            h, b = st.columns([3, 1])
            h.caption(f"Hash SHA-256: `{a['hash_sha256'][:12]}…` · mbledhur më {a['mbledhur_me']} UTC")
            if b.button("Verifiko tani", key=f"vf_{id_zgjedhur}"):
                with st.spinner("Po shkarkohet faqja..."):
                    # Teksti është ende bruto vetëm nëse processor.py s'e ka pastruar/përkthyer
                    bruto = a["teksti"] if not isinstance(a["teksti_perkthyer"], str) else None
                    b.write(collector.verifiko(a["url"], a["hash_sha256"], bruto))
        else:
            st.caption("Pa hash: artikulli u përpunua para se të shtohej hash-i.")
        o, p = st.columns(2)
        o.text_area("Origjinali", a["teksti"] or "", height=300)
        p.text_area("Përkthimi (EN)", a["teksti_perkthyer"] if isinstance(a["teksti_perkthyer"], str)
                    else "Ende i papërkthyer", height=300)  # pandas jep NaN, jo None

# ---------------- Ekzekutimi i pipeline-it ----------------
with tab_ekz:
    st.subheader("Ekzekuto tani")
    n = st.number_input("Sa artikuj të përkthehen dhe analizohen në një ekzekutim", 5, 500, 20, step=5,
                        help="Më shumë artikuj = më shumë kohë (rreth 1 minutë për artikull me modelin aktual).")
    # Butoni është gjithmonë aktiv; bllokimi te ekzekuto.py s'lejon dy ekzekutime njëkohësisht
    if ekzekuto.po_punon():
        st.info("⏳ Pipeline-i po punon tani. Shiko log-un më poshtë; kur të mbarojë, kliko 'Rifresko të dhënat'.")
    if st.button("▶️ Ekzekuto tani", type="primary"):
        if ekzekuto.po_punon():
            st.warning("Një ekzekutim po punon tashmë. Prit sa të mbarojë, pastaj provo sërish.")
        else:
            ekzekuto.nis_ne_sfond(n)
            st.success("U nis në sfond. Mund ta mbyllësh këtë faqe; puna vazhdon.")

    st.subheader("Automatikisht")
    opsionet = {"Jo (vetëm me dorë)": 0, "Çdo 1 orë": 1, "Çdo 2 orë": 2, "Çdo 3 orë": 3,
                "Çdo 6 orë": 6, "Çdo 12 orë": 12, "Çdo 24 orë": 24}
    aktuale = ekzekuto.orari_aktual()
    vlera = aktuale["ore"] if aktuale else 0
    zgjedhja = st.selectbox("Sa shpesh të ekzekutohet vetë", list(opsionet),
                            index=list(opsionet.values()).index(vlera) if vlera in opsionet.values() else 0)
    if aktuale:
        st.caption(f"Aktiv: çdo {aktuale['ore']} orë, {aktuale['n']} artikuj. Punon edhe kur dashboard-i "
                   "është i mbyllur, por kompjuteri duhet të jetë ndezur dhe Ollama duke punuar.")
    if st.button("Ruaj orarin"):
        ore = opsionet[zgjedhja]
        ok, mesazhi = ekzekuto.vendos_orarin(ore, n) if ore else ekzekuto.hiq_orarin()
        (st.success if ok else st.error)(("Orari u ruajt." if ore else "Orari automatik u hoq.")
                                         if ok else f"Gabim nga Task Scheduler: {mesazhi}")
        if ok:
            st.rerun()

    st.subheader("Log-u i fundit")
    st.code(ekzekuto.log_fundit(25), language=None)
    if st.button("🔄 Rifresko të dhënat"):
        st.cache_data.clear()
        st.rerun()
