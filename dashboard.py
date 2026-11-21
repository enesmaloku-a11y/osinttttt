"""dashboard.py - Pamja për analistin. Sistemi vetëm ndihmon; vendimi është i analistit.

Nis me:  streamlit run dashboard.py
Skedat: Urgjente dhe Raporte (sipas prioritetit të rreziku.py), Ngjarjet (harta, kronologjia),
Kërcënimet (taksonomia), Burimet, Vlerësimi, Artikujt, Ekzekutimi.
"""
import json
import sqlite3
from collections import Counter
from pathlib import Path

import altair as alt
import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

import collector
import db
import ekzekuto
import kercenimet
import patterns
import raporti
import scoring

DOSJA = Path(__file__).resolve().parent
REZULTATI = DOSJA / "eval" / "rezultati.json"          # nga eval/evaluate.py
RAPORTI_MODELIT = DOSJA / "data" / "raporti_modelit.json"  # nga trajno.py

st.set_page_config(page_title="OSINT Kosova", layout="wide")


@st.cache_data(ttl=60)
def lexo(sql):
    """Lexon një tabelë nga SQLite (cache 60 sekonda që faqja të jetë e shpejtë)."""
    db.lidhu().close()  # krijon tabelat nëse baza është e re
    with sqlite3.connect(db.DB_PATH) as con:
        return pd.read_sql(sql, con)


def lexo_json(shtegu):
    try:
        return json.loads(Path(shtegu).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


siguro = raporti.siguro  # escape për popup-et e folium-it; testohet te raporti.py


def perqind(v):
    return f"{v:.0%}" if isinstance(v, (int, float)) else "–"


artikujt = lexo("SELECT id, url, burimi, titulli, data, gjuha, teksti, teksti_perkthyer, "
                "perpunuar, hash_sha256, mbledhur_me FROM articles")
db.lidhu().close()
# Vendimet lexohen pa cache, që një vendim i ruajtur të shfaqet menjëherë
te_gjitha = raporti.ngjarjet()

IKONAT = {"e konfirmuar": "✅", "e pakonfirmuar": "❓", "e hedhur poshtë": "❌"}
SHENJA = {"URGJENTE": "🔴", "RAPORT": "🟠", "MONITORIM": "🔵", "ARKIV": "⚪", None: "▫️"}
NGJYRA_HARTE = {"URGJENTE": "red", "RAPORT": "orange", "MONITORIM": "blue", "ARKIV": "gray", None: "lightgray"}
SAKTESIA = {"village": "fshat", "municipality": "komunë", "region": "vetëm rajon",
            "exact": "e saktë", "approximate": "e përafërt", None: "e panjohur"}

artikujt["data"] = pd.to_datetime(artikujt["data"], utc=True, errors="coerce")
# Të gjitha domenet e GDELT bashkohen në një grup që grafiku të mbetet i lexueshëm
artikujt["grupi"] = artikujt["burimi"].where(~artikujt["burimi"].str.startswith("GDELT:"), "GDELT")

# ---------------- Sidebar ----------------
# Butoni kryesor në krye të sidebar-it, që të duket gjithmonë (edhe në ekran të vogël)
st.sidebar.header("Pipeline-i")
# Gjatë etiketimit (pipeline.ngrire ose OSINT_NGRIRE=1) asgjë s'nis pipeline-in nga dashboard-i
ngrire = raporti.ngrire()
if ngrire:
    st.sidebar.warning("Etiketim në vazhdim: pipeline-i është i ngrirë. Ekzekutimi dhe orari janë çaktivizuar.")
if st.sidebar.button("▶️ Ekzekuto tani", type="primary", key="ekz_sidebar", use_container_width=True,
                     disabled=ngrire):
    if ekzekuto.po_punon():
        st.sidebar.warning("Një ekzekutim po punon tashmë.")
    else:
        ekzekuto.nis_ne_sfond(20)
        st.sidebar.success("U nis në sfond (20 artikuj).")
st.sidebar.caption("⏳ Po punon tani…" if ekzekuto.po_punon() else
                   "Orari dhe log-u: skeda 'Ekzekutimi'.")

st.sidebar.header("Filtrat e ngjarjeve")
zona = st.sidebar.radio("Zona", ["Të gjitha", "Kosovë", "Rajonale"], horizontal=True)
prioritetet = st.sidebar.multiselect("Prioriteti", kercenimet.PRIORITETET)
kategorite = st.sidebar.multiselect("Kategoria", list(kercenimet.KATEGORITE), format_func=kercenimet.emri)
nivelet = st.sidebar.multiselect("Niveli i rrezikut", kercenimet.NIVELET)
statuset = st.sidebar.multiselect("Vendimi i analistit", db.STATUSET)

st.sidebar.header("Filtrat e artikujve")
burimet = st.sidebar.multiselect("Burimi", sorted(artikujt["grupi"].unique()))
gjuhet = st.sidebar.multiselect("Gjuha", sorted(artikujt["gjuha"].unique()))
kerko = st.sidebar.text_input("Kërko në titull/tekst")


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
    ka = f["titulli"].str.contains(kerko, case=False, na=False) | \
         f["teksti"].str.contains(kerko, case=False, na=False)
    f = f[ka]


# ---------------- Kartela e një ngjarjeje ----------------
def kartela(e, skeda):
    """Expander me gjithë arsyetimin dhe vendimin e analistit. 'skeda' i bën çelësat unikë."""
    det, p = e["det"], raporti.prioriteti(e)
    pike, niveli, arsyet = raporti.rreziku(e)
    b = raporti.besueshmeria(e)
    koka = (f"{IKONAT[e['statusi']]} {SHENJA[p]} {str(e['data'])[:10]} · {raporti.pastro(e['titulli'], 120)}"
            f" · rreziku {pike if pike is not None else '–'} · besueshmëria {perqind(b)}")
    with st.expander(koka):
        kodi = raporti.admiralty(e)
        st.write(f"**Prioriteti:** {p or 'i pallogaritur'}  ·  **Rreziku:** "
                 f"{f'{pike}/100 ({niveli})' if pike is not None else '–'}  ·  **Besueshmëria:** {perqind(b)}"
                 + (f"  ·  **Admiralty:** {kodi}" if kodi else ""))
        if p == "URGJENTE" and raporti.per_verifikim(e):
            st.warning("Për verifikim, jo për veprim: besueshmëria është nën 80% dhe s'ka konfirmim.")
        shenj = ", ".join(kercenimet.SHENJESTRAT.get(s, s) for s in det.get("shenjestrat") or []) or "-"
        aktori = det.get("aktori")
        st.write(f"**Kategoria:** {raporti.pastro(raporti.kategoria(e), 80)}  ·  "
                 f"**Aktori (sipas modelit):** {kercenimet.AKTORET.get(aktori, '-') if aktori else '-'}  ·  "
                 f"**Shenjestrat:** {shenj}  ·  **Lidhje me FSK:** {'po' if det.get('lidhje_me_fsk') else 'jo'}"
                 f"  ·  **Zona:** {'rajonale' if det.get('rajonale') else 'Kosovë'}")
        st.write(f"**Lloji:** {e.get('lloji') or '-'}  ·  **Vendi:** {raporti.pastro(e.get('vendi'), 60) or '-'} "
                 f"({SAKTESIA.get(det.get('saktesia_vendit'), 'e panjohur')})  ·  "
                 f"**Data:** {SAKTESIA.get(det.get('saktesia_dates'), 'e panjohur')}  ·  **Gjuha:** {e.get('gjuha')}")
        try:
            bosh = json.loads(e.get("boshllequet") or "[]")
        except ValueError:
            bosh = []
        st.write("**Boshllëqet:** " + (", ".join(map(raporti.pastro, bosh)) or "asnjë"))
        st.write(f"**Mediat:** {', '.join(map(raporti.pastro, det.get('mediat') or [])) or '-'}  ·  "
                 f"**Aktorët në lajme:** {', '.join(map(raporti.pastro, det.get('aktoret') or [])) or '-'}")
        if arsyet:
            st.write("**Pse ky rrezik:**")
            for a in arsyet:
                st.markdown(f"- {raporti.pastro(a, 200)}")
        if det.get("arsyetimi"):
            st.write("**Pse kjo besueshmëri:**")
            for a in det["arsyetimi"]:
                st.markdown(f"- {raporti.pastro(a, 200)}")
        konteksti = [c for c in det.get("konteksti") or [] if isinstance(c, dict)]
        if konteksti:
            st.write("**Konteksti i jashtëm:**")
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
                st.markdown(("- 🔗 " if c.get("lloji") == "rast_i_ngjashem" else "- 📈 ") + " · ".join(pjeset))
            st.caption("Ngjashmëri automatike, jo provë. Verifikoje te burimi.")
        st.write("**Burimet:**")
        for u in e["burimet_l"]:
            st.markdown(f"- [{u}]({u})" if raporti.url_e_sigurt(u) else f"- `{raporti.pastro(u, 120)}`")

        # Vendimi i analistit: sistemi vetëm sugjeron, njeriu vendos
        st.write("**Vendimi i analistit:**")
        k = e["url_kryesor"]
        statusi = st.radio("Statusi", db.STATUSET, index=db.STATUSET.index(e["statusi"]),
                           key=f"st_{skeda}_{k}", horizontal=True, label_visibility="collapsed")
        shenimi = st.text_input("Shënim", e["shenimi"], key=f"sh_{skeda}_{k}",
                                placeholder="p.sh. e konfirmoi Policia në Facebook")
        if st.button("Ruaj vendimin", key=f"rv_{skeda}_{k}"):
            db.ruaj_vendimin(k, statusi, shenimi)
            st.cache_data.clear()
            st.rerun()


# ---------------- Përmbledhja ----------------
st.title("OSINT Kosova: kërcënimet hibride")
st.caption("Sistemi vetëm sugjeron. Çdo vendim e merr analisti.")

k1, k2, k3, k4 = st.columns(4)
k1.metric("Urgjente", len(urgjente))
k2.metric("Raporte", len(raporte))
k3.metric("Ngjarje", len(ngj))
k4.metric("Artikuj", len(f))

(tab_urg, tab_rap, tab_ngj, tab_ker, tab_bur, tab_vle,
 tab_art, tab_ekz) = st.tabs(["Urgjente", "Raporte", "Ngjarjet", "Kërcënimet", "Burimet",
                              "Vlerësimi", "Artikujt", "Ekzekutimi"])

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
    if st.button("📝 Gjenero raportin ditor"):
        st.session_state["raporti"] = str(raporti.gjenero())
    if st.session_state.get("raporti") and Path(st.session_state["raporti"]).exists():
        shtegu = Path(st.session_state["raporti"])
        teksti = shtegu.read_text(encoding="utf-8")
        st.download_button("⬇️ Shkarko raportin", teksti, file_name=shtegu.name, mime="text/markdown")
        with st.expander("Shiko raportin", expanded=True):
            st.markdown(teksti)

# ---------------- Raporte ----------------
with tab_rap:
    st.caption("RAPORT: rrezik i mesëm për t'u raportuar. MONITORIM: për t'u ndjekur. "
               "Ngjarjet ARKIV dhe ato të hedhura poshtë janë vetëm te 'Ngjarjet'.")
    for emri_p in ("RAPORT", "MONITORIM"):
        grupi = [e for e in raporte if raporti.prioriteti(e) == emri_p]
        st.subheader(f"{SHENJA[emri_p]} {emri_p} ({len(grupi)})")
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
        st.warning("⚠️ " + patterns.pershkrim(a))
    if fillimi and ngj and not patterns.histori_e_mjaftueshme(fillimi, max(str(e["data"]) for e in ngj)):
        st.caption(f"Alarmet për rritje aktivizohen pas 5 javë mbledhjeje "
                   f"(mbledhja filloi më {str(fillimi)[:10]}).")
    elif not alarmet:
        st.caption("S'ka rritje të pazakonta (rregulli: ≥ 3 ngjarje në 7 ditë dhe ≥ 2x mesatarja javore).")

    harta = folium.Map(location=[42.8, 20.9], zoom_start=7)  # Kosova dhe vendet fqinje
    for e in ngj:
        if e.get("lat") is None or e.get("lon") is None:
            continue
        p, det = raporti.prioriteti(e), e["det"]
        pike = raporti.rreziku(e)[0]
        sv = det.get("saktesia_vendit")
        popup = (f"{siguro(raporti.rresht(e['titulli']))}<br>Prioriteti: {siguro(p or '–')} · "
                 f"Rreziku: {siguro(pike if pike is not None else '–')}<br>Besueshmëria: "
                 f"{siguro(perqind(raporti.besueshmeria(e)))} · Vendi: {siguro(SAKTESIA.get(sv, 'e panjohur'))}"
                 f"<br>Vendimi: {siguro(e['statusi'])}")
        tooltip = siguro(raporti.rresht(e["titulli"], 100))
        ngjyra = NGJYRA_HARTE.get(p, "lightgray")
        if sv == "region":
            # Vend i përafërt: rreth i madh në vend të pikës, që të mos duket më i saktë se ç'është
            folium.Circle([e["lat"], e["lon"]], radius=15000, color=ngjyra, fill=True,
                          fill_opacity=0.15, tooltip=tooltip, popup=popup).add_to(harta)
        else:
            ikona = folium.Icon(color=ngjyra, icon="globe" if det.get("rajonale") else "info-sign")
            folium.Marker([e["lat"], e["lon"]], tooltip=tooltip, popup=popup, icon=ikona).add_to(harta)
    st.caption("Ngjyra: e kuqe URGJENTE, portokalli RAPORT, blu MONITORIM, gri ARKIV. Globi = ngjarje "
               "rajonale (jashtë Kosovës). Rrethi = vendi dihet vetëm në nivel rajoni. Ngjarjet pa vend të "
               "njohur nuk dalin në hartë, por janë në listë.")
    st_folium(harta, height=450, use_container_width=True, returned_objects=[])

    if not ngj:
        st.info("Ende s'ka ngjarje (ose filtrat i fshehin të gjitha).")
    else:
        # Kronologjia: një pikë për çdo ngjarje, sipas datës dhe kategorisë
        st.subheader("Kronologjia")
        k = pd.DataFrame([{
            "dita": str(e["data"])[:10], "kategoria": raporti.rresht(raporti.kategoria(e), 80),
            "prioriteti": raporti.prioriteti(e) or "i pallogaritur",
            "titulli": raporti.rresht(e["titulli"], 120), "burime": len(e["burimet_l"]),
            "besueshmeria": perqind(raporti.besueshmeria(e)),
            "rreziku": raporti.rreziku(e)[0] if raporti.rreziku(e)[0] is not None else -1,
        } for e in ngj])
        k["dita"] = pd.to_datetime(k["dita"], errors="coerce")
        k = k.dropna(subset=["dita"])
        domena = kercenimet.PRIORITETET + ["i pallogaritur"]
        grafiku = alt.Chart(k).mark_circle(opacity=0.8).encode(
            # ngjarjet kanë vetëm datë (pa orë), ndaj boshti tregon ditë
            x=alt.X("dita:T", title="Data", axis=alt.Axis(format="%d %b", tickCount="day"),
                    scale=alt.Scale(padding=30)),
            y=alt.Y("kategoria:N", title="Kategoria", axis=alt.Axis(labelLimit=250)),
            size=alt.Size("burime:Q", title="Burime", scale=alt.Scale(range=[80, 500], zero=False),
                          legend=alt.Legend(format="d", tickMinStep=1)),
            color=alt.Color("prioriteti:N", title="Prioriteti",
                            scale=alt.Scale(domain=domena, range=["red", "orange", "#3b82f6", "gray", "#cbd5e1"])),
            tooltip=[alt.Tooltip("dita:T", title="Data"), alt.Tooltip("titulli:N", title="Ngjarja"),
                     alt.Tooltip("prioriteti:N", title="Prioriteti"), alt.Tooltip("rreziku:Q", title="Rreziku"),
                     alt.Tooltip("besueshmeria:N", title="Besueshmëria"), alt.Tooltip("burime:Q", title="Burime")],
        )
        st.altair_chart(grafiku, use_container_width=True)
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
        for i, c in kercenimet.KATEGORITE.items()]), hide_index=True, use_container_width=True)
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
                     hide_index=True, use_container_width=True,
                     column_config={"Besueshmëria e mediumit": st.column_config.NumberColumn(format="%.2f")})
    else:
        st.caption("S'ka ende ngjarje.")

    st.subheader("Burime me dezinformim të dokumentuar (EUvsDisinfo)")
    dez = raporti.burimet_e_dezinformimit()
    if dez:
        st.caption("Sipas rasteve të EUvsDisinfo për Kosovën dhe rajonin. Kanalet në rrjete sociale grupohen "
                   "sipas platformës, pa emra llogarish.")
        st.dataframe(pd.DataFrame(dez), hide_index=True, use_container_width=True,
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
                   f"konfirmuara). Mëson nga çdo vendim i ri. {rm.get('rekomandim', '')}")
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
    if st.button("▶️ Ekzekuto tani", type="primary", disabled=ngrire):
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
    if st.button("Ruaj orarin", disabled=ngrire):
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
