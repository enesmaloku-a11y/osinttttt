"""dashboard.py - Pamja për analistin. Sistemi vetëm ndihmon; vendimi është i analistit.

Nis me:  streamlit run dashboard.py
"""
import json
import sqlite3

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

import db

st.set_page_config(page_title="OSINT Kosova", layout="wide")


@st.cache_data(ttl=60)
def lexo(sql):
    """Lexon një tabelë nga SQLite (cache 60 sekonda që faqja të jetë e shpejtë)."""
    db.lidhu().close()  # krijon tabelat nëse baza është e re
    with sqlite3.connect(db.DB_PATH) as con:
        return pd.read_sql(sql, con)


artikujt = lexo("SELECT id, url, burimi, titulli, data, gjuha, teksti, teksti_perkthyer, "
                "perpunuar FROM articles")
ngjarjet = lexo("SELECT * FROM events")

artikujt["data"] = pd.to_datetime(artikujt["data"], utc=True, errors="coerce")
# Të gjitha domenet e GDELT bashkohen në një grup që grafiku të mbetet i lexueshëm
artikujt["grupi"] = artikujt["burimi"].where(~artikujt["burimi"].str.startswith("GDELT:"), "GDELT")

# ---------------- Filtrat ----------------
st.sidebar.header("Filtrat")
burimet = st.sidebar.multiselect("Burimi", sorted(artikujt["grupi"].unique()))
gjuhet = st.sidebar.multiselect("Gjuha", sorted(artikujt["gjuha"].unique()))
kerko = st.sidebar.text_input("Kërko në titull/tekst")

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

tab_ngj, tab_art = st.tabs(["Ngjarjet", "Artikujt"])

# ---------------- Ngjarjet ----------------
with tab_ngj:
    # Ngjyra sipas besueshmërisë: jeshile >= 70%, portokalli >= 40%, e kuqe më poshtë
    def ngjyra(v):
        return "gray" if pd.isna(v) else "green" if v >= 0.7 else "orange" if v >= 0.4 else "red"

    ngjarjet["ngjyra"] = ngjarjet["besueshmeria"].apply(ngjyra)
    # Besueshmëria vjen nga scoring.py; nëse mungon shfaqet "e pavlerësuar"
    ngjarjet["besueshmeria"] = ngjarjet["besueshmeria"].apply(
        lambda v: "e pavlerësuar" if pd.isna(v) else f"{v:.0%}")
    harta = folium.Map(location=[42.6, 20.9], zoom_start=8)  # qendra e Kosovës
    for _, e in ngjarjet.dropna(subset=["lat", "lon"]).iterrows():
        folium.Marker(
            [e["lat"], e["lon"]],
            tooltip=e["titulli"],
            popup=f"{e['titulli']}<br>Besueshmëria: {e['besueshmeria']}",
            icon=folium.Icon(color=e["ngjyra"]),
        ).add_to(harta)
    st.caption("Ngjyra: jeshile ≥ 70%, portokalli ≥ 40%, e kuqe < 40%. "
               "Ngjarjet pa vend të njohur nuk dalin në hartë, por janë në listë.")
    st_folium(harta, height=450, use_container_width=True, returned_objects=[])

    if ngjarjet.empty:
        st.info("Ende s'ka ngjarje. Ato shfaqen këtu pasi të shtohen extractor.py dhe correlator.py.")
    else:
        for _, e in ngjarjet.sort_values("data", ascending=False).iterrows():
            with st.expander(f"{e['data'][:10]} · {e['titulli']} · besueshmëria {e['besueshmeria']}"):
                st.write(f"**Lloji:** {e['lloji'] or '-'}  ·  **Vendi:** {e['vendi'] or '-'}  ·  "
                         f"**Gjuha:** {e['gjuha']}")
                st.write("**Boshllëqet:** " + (", ".join(json.loads(e["boshllequet"])) or "asnjë"))
                det = json.loads(e["detajet_json"] or "{}")
                st.write(f"**Mediat:** {', '.join(det.get('mediat', []))}  ·  "
                         f"**Aktorët:** {', '.join(det.get('aktoret', [])) or '-'}")
                if det.get("arsyetimi"):
                    st.write("**Pse kjo besueshmëri:**")
                    for a in det["arsyetimi"]:
                        st.markdown(f"- {a}")
                st.write("**Burimet:**")
                for u in json.loads(e["burimet"]):
                    st.markdown(f"- [{u}]({u})")

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
        o, p = st.columns(2)
        o.text_area("Origjinali", a["teksti"] or "", height=300)
        p.text_area("Përkthimi (EN)", a["teksti_perkthyer"] or "Ende i papërkthyer", height=300)
