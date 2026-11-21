"""demo_live.py - Demo live: forum i SIMULUAR + zbulim i menjëhershëm me rregulla (pa model, pa internet).

Nis me:  streamlit run demo_live.py --server.port 8505
- Tab 1: http://localhost:8505/?pamja=forum  -> shkruaj një postim (forum demo, jo platformë reale)
- Tab 2: http://localhost:8505/              -> brenda ~2 sekondave del si kërcënim, me arsye
Kontrollet: python demo_live.py

Rruga e shpejtë, pa model: kercenimet.py jep kategorinë, rreziku.py pikët, prioritetin dhe kodin
Admiralty. Forumi është burim i panjohur me një postim -> F6, pra gjithmonë "për verifikim".
Postimet ruhen te demo_live.db (*.db s'shkon në Git), me emrat e personave të maskuar.
osint.db s'preket.
"""
import os
import re
import sqlite3
import time
from contextlib import closing
from datetime import date, datetime

import extractor
import kercenimet
import rreziku
from correlator import gjej_vendin

DB = os.environ.get("DEMO_LIVE_DB", "demo_live.db")
MEDIUMI = "Forum demo"  # s'është te scoring.MEDIAT -> shkronja F (burim i panjohur)
MAKS_POSTIMI = 1000

# Një regex për çdo kategori; më të gjatat të parat, që "jarinje" të numërohet një herë
KAT_RE = {kid: re.compile(r"\b(?:" + "|".join(map(re.escape, sorted(
    {f for l in c["fjale_kyce"].values() for f in l}, key=len, reverse=True))) + ")", re.I)
    for kid, c in kercenimet.KATEGORITE.items() if any(c["fjale_kyce"].values())}

# Aktorët dhe shenjestrat me rregulla të thjeshta (sq, sr latin + cirilik, en)
AKTORET_RE = {
    "shteti_serb": r"ushtri\w* (e |së )?serb|trupa\w* serbe|vojsk\w* srbij|војск\w* србиј|"
                   r"serbian (army|troops|forces|armed)|\bbia\b|\bвс\b",
    "grupe_te_armatosura": r"armatosur|paraushtarak|naoružan|наоружан|armed group|gunmen|paramilitar",
    "rusia": r"\brus(e|i|isë)?\b|\brussia|\bruski|\bруск|\bрусиј",
    "kina": r"\bkin(a|ez)|\bchin(a|ese)|\bkine(sk|z)|\bкинеск",
    "grupe_ekstremiste": r"ekstremist|extremist|isis|xhihad|jihad",
    "krim_i_organizuar": r"kontraband|trafikim|smuggl|traffick|šverc|шверц",
}
SHENJESTRAT_RE = {
    "fsk": r"\bfsk\b|\bksf\b|\bкбс\b|\bkbs\b|forc\w* (e |së )?sigurisë",
    "kfor_nato": r"\bkfor|\bnato|\bкфор|\bнато",
    "infrastrukture_kritike": r"gazivod|ujman|ib[eë]r|ibar|lepenc|nënstacion|substation|trafostanic|"
                              r"\bdam\b|digë|termocentral|power plant|elektran|далековод|трафостаниц",
    "institucione": r"polic|policij|полициј|ministri|qeveri|government|vlad[ae]\b",
}


def lidhu():
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS postimet (id INTEGER PRIMARY KEY, koha TEXT NOT NULL, "
                "teksti TEXT NOT NULL)")
    return con


def maskoj(t):
    """Si extractor.fshi_emrat, por emrat e vendeve që njeh correlator ("Zubin Potok") s'maskohen."""
    return extractor.EMRA.sub(lambda m: m.group() if gjej_vendin(m.group())[0] else
                              extractor.fshi_emrat(m.group()), t)


def shto_postim(teksti):
    """Ruan postimin me emrat e personave të maskuar; kthen id ose None për tekst bosh."""
    teksti = maskoj(" ".join(str(teksti or "").split()))[:MAKS_POSTIMI]
    if not teksti:
        return None
    with closing(lidhu()) as con, con:
        return con.execute("INSERT INTO postimet (koha, teksti) VALUES (?, ?)",
                           (datetime.now().isoformat(timespec="seconds"), teksti)).lastrowid


def postimet():
    with closing(lidhu()) as con:
        return con.execute("SELECT id, koha, teksti FROM postimet ORDER BY id DESC").fetchall()


def gjuha(t):
    if re.search(r"[а-яђјљњћџ]", t, re.I):
        return "sr"
    if re.search(r"[ëç]|\b(dhe|është|në|për|janë|një|dy|nga|mbi|sot|policia|ushtria)\b", t, re.I):
        return "sq"
    if re.search(r"[čćšžđ]|\b(je|su|u|na|kod|i)\b", t, re.I):
        return "sr"
    return "en"


# Emrat e vendeve dhe objekteve tregojnë KU ndodhi, jo ÇFARË ndodhi: numërohen gjysmë pike,
# që "dron mbi Gazivodë" të jetë dron dhe "ushtria serbe te Jarinja" aktivitet ushtarak
VENDE = re.compile(r"jarinj|bërnjak|bernjak|brnjak|banjsk|gazivod|ujman|ib[eë]r|ibar|lepenc|"
                   r"јарињ|брњак|бањск|газивод|ибар|лепен", re.I)


def kategoria_e(t):
    """(kategoria, provat): kategoria me më shumë pikë nga fjalët kyçe; barazimi -> rrezikshmëria
    bazë më e lartë, pastaj radha te kercenimet.py."""
    gjetje = {kid: [m.group(0) for m in r.finditer(t)] for kid, r in KAT_RE.items()}
    pike = {k: sum(0.5 if VENDE.match(f) else 1 for f in v) for k, v in gjetje.items() if v}
    if not pike:
        return "tjeter", []
    rendi = list(kercenimet.KATEGORITE)
    kat = min(pike, key=lambda k: (-pike[k], -kercenimet.KATEGORITE[k]["rrezikshmeria_baze"], rendi.index(k)))
    return kat, gjetje[kat]


def vlereso_postimin(id_, koha, teksti):
    """Kategoria, aktori, shenjestrat dhe rreziku për një postim, vetëm me rregulla."""
    kat, provat = kategoria_e(teksti)
    aktori = next((a for a, r in AKTORET_RE.items() if re.search(r, teksti, re.I)), "i_panjohur")
    shenjestrat = [s for s, r in SHENJESTRAT_RE.items() if re.search(r, teksti, re.I)]
    det = {"kategoria": kat, "aktori": aktori, "shenjestrat": shenjestrat,
           "lidhje_me_fsk": "fsk" in shenjestrat, "mediat": [MEDIUMI], "gjuhet": [gjuha(teksti)]}
    e = {"id": id_, "data": koha[:10], "vendi": teksti, "titulli": teksti, "besueshmeria": None,
         "burimet": f'["demo://{id_}"]', "lloji": None}
    r = rreziku.vlereso(e, det, sot=koha[:10])
    siguri = kat != "tjeter" or bool(extractor.FJALE_KYCE.search(teksti))
    return {"id": id_, "koha": koha, "teksti": teksti, "kategoria": kat, "provat": provat,
            "aktori": aktori, "shenjestrat": shenjestrat, "vendi": gjej_vendin(teksti)[0],
            "gjuha": det["gjuhet"][0], "siguri": siguri, **r}


def cfare_verifikohet(v):
    """Lista e kontrolleve që analisti duhet të bëjë para se të veprojë."""
    lista = ["Konfirmim nga të paktën 2 media të pavarura (shqip, serbisht ose anglisht)",
             "Deklaratë zyrtare: KFOR, Policia e Kosovës ose Ministria e Mbrojtjes"]
    if v["vendi"]:
        lista.append(f"Vendi i ngjarjes ({v['vendi'].capitalize()}): pamje ose raport nga terreni")
    if v["kategoria"] in ("ushtarak_serbia", "dron_hapesire_ajrore"):
        lista.append("Lëvizje e konfirmuar nga KFOR/NATO ose nga burime të mbrojtjes")
    if v["kategoria"] == "infrastrukture_kritike" or "infrastrukture_kritike" in v["shenjestrat"]:
        lista.append("Konfirmim nga operatori (KEK, KOSTT, Ibër-Lepenci)")
    return lista


def app():
    import streamlit as st

    st.set_page_config(page_title="Demo live", layout="wide")
    if st.query_params.get("pamja") == "forum":
        st.title("Forum demo")
        st.caption("Forum i SIMULUAR për demonstrim. Asgjë s'publikohet në internet.")
        with st.form("postim", clear_on_submit=True):
            teksti = st.text_area("Shkruaj një postim", height=120)
            if st.form_submit_button("Posto") and shto_postim(teksti):
                st.success("U postua.")
        for _, koha, t in postimet():
            st.markdown(f"**anonim** · {koha[11:16]}\n\n{t}")
            st.divider()
        return

    st.title("Zbulimi live: forumi demo")
    st.caption("Pa model dhe pa internet: kategoria nga kercenimet.py, rreziku nga rreziku.py. "
               "Rreziku = sa e rëndë do ishte nëse është e vërtetë; burimi i panjohur → verifiko së pari.")
    if st.button("Fshi postimet e demos"):
        with closing(lidhu()) as con, con:
            con.execute("DELETE FROM postimet")
    pare = st.session_state.setdefault("pare", {})
    shenja = {"URGJENTE": "🔴", "RAPORT": "🟠", "MONITORIM": "🔵", "ARKIV": "⚪"}
    emrat_admiralty = {"F": "burim i panjohur, besueshmëria s'mund të gjykohet",
                       6: "një burim i vetëm, vërtetësia s'mund të gjykohet ende"}

    @st.fragment(run_every=2)
    def lista():
        for i, (id_, koha, t) in enumerate(postimet()):
            pare.setdefault(id_, time.time())
            v = vlereso_postimin(id_, koha, t)
            sek = max(0.0, pare[id_] - datetime.fromisoformat(koha).timestamp())
            if not v["siguri"]:
                st.markdown(f"⚪ **Pa shenja sigurie** · {t[:120]}")
                continue
            r, a = v["rreziku"], v["admiralty"]
            koka = (f"{shenja[v['prioriteti']]} **{v['prioriteti']}** · Rreziku {r['pike']}/100 "
                    f"({r['niveli']}) · {kercenimet.emri(v['kategoria'])} · Admiralty {a['kodi']}")
            with st.expander(koka, expanded=i == 0):
                st.markdown(f"> {t}")
                st.write(f"**Zbuluar:** {sek:.0f} s pas postimit · **Gjuha:** {v['gjuha']} · "
                         f"**Vendi:** {(v['vendi'] or 'i panjohur').capitalize()} · "
                         f"**Aktori:** {kercenimet.AKTORET.get(v['aktori'])} · "
                         f"**Shenjestrat:** {', '.join(kercenimet.SHENJESTRAT[s] for s in v['shenjestrat']) or '–'}")
                st.write(f"**Fjalët që e kapën:** {', '.join(sorted(set(v['provat'])))}")
                st.markdown("**Pse ky rrezik:**\n" + "\n".join(f"- {x}" for x in r["arsyet"]))
                st.write(f"**Admiralty {a['kodi']}:** {a['burimi']} = {emrat_admiralty.get(a['burimi'], '')}; "
                         f"{a['informacioni']} = {emrat_admiralty.get(a['informacioni'], '')}")
                st.markdown("**Çfarë duhet verifikuar para veprimit:**\n" +
                            "\n".join(f"- {x}" for x in cfare_verifikohet(v)))

    lista()


def kontrollet():
    """Rastet e demos: kategoria, rreziku dhe "për verifikim" pa model dhe pa rrjet."""
    sot = date.today().isoformat() + "T21:00:00"
    jarinje = vlereso_postimin(1, sot, "URGENT: Serbian army units crossed the Jarinje crossing "
                                       "tonight, KSF positions in the north are threatened")
    assert jarinje["kategoria"] == "ushtarak_serbia", jarinje["kategoria"]  # jo trazira nga "Jarinje"
    assert (jarinje["rreziku"]["pike"], jarinje["rreziku"]["niveli"], jarinje["prioriteti"],
            jarinje["admiralty"]["kodi"]) == (78, "i lartë", "URGJENTE", "F6"), jarinje["rreziku"]
    assert "për verifikim" in jarinje["rreziku"]["arsyet"][-1]
    cir = vlereso_postimin(2, sot, "ХИТНО: Јединице Војске Србије у копненој зони код Јариња")
    assert (cir["kategoria"], cir["aktori"], cir["gjuha"]) == ("ushtarak_serbia", "shteti_serb", "sr"), cir
    dron = vlereso_postimin(3, sot, "Dron i paidentifikuar fluturoi mbi digën e Gazivodës sonte")
    assert dron["kategoria"] == "dron_hapesire_ajrore" and "infrastrukture_kritike" in dron["shenjestrat"]
    assert dron["prioriteti"] == "URGJENTE" and dron["admiralty"]["kodi"] == "F6", dron["rreziku"]
    for t in ("Kosova fiton ndeshjen miqësore", "Ekstremisht nxehtë sot në Prishtinë"):
        assert not vlereso_postimin(4, sot, t)["siguri"], t
    assert gjuha("Policija je uhapsila dvojicu") == "sr" and gjuha("Policia arrestoi dy persona") == "sq"
    # Maskimi: personat maskohen, vendet jo
    assert maskoj("Banorët në Zubin Potok dhe Filan Fisteku") == "Banorët në Zubin Potok dhe [person]"
    print("Kontrollet kaluan: 5 raste demo (en, sr-cirilik, sq, 2 pa kërcënim).")
    print(f"Jarinje: {jarinje['prioriteti']} · {jarinje['rreziku']['pike']}/100 · {jarinje['admiralty']['kodi']}")
    print(f"Dron mbi Gazivodë: {dron['prioriteti']} · {dron['rreziku']['pike']}/100 · {dron['admiralty']['kodi']}")


if __name__ == "__main__":
    from streamlit.runtime import exists
    if exists():  # i nisur me "streamlit run"
        app()
    else:
        kontrollet()
