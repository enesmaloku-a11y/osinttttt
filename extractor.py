"""extractor.py - Nxjerr nga çdo artikull ngjarjen e sigurisë si JSON (me Ollama lokal).

- Filtër me fjalë kyçe para modelit: artikujt pa asnjë fjalë sigurie s'i dërgojmë fare.
- Cache: rezultati ruhet te articles.rezultati_json dhe artikulli s'përpunohet më.
- Mos ruaj të dhëna personale: modeli udhëzohet të mos japë emra personash,
  dhe ne ruajmë vetëm fushat e listës FUSHAT.
- Klasifikimi sipas taksonomisë së kercenimet.py (K2): kategoria, aktori, shenjestrat,
  lidhje_me_fsk dhe relevante; vlerat jashtë listave zëvendësohen me rregulla.
"""
import json
import re
import sys
import time
from contextlib import closing
from datetime import datetime, timedelta

import db
import kercenimet
from processor import pyet_ollama

# Rrënjë fjalësh sigurie në shqip, serbisht (latin + cirilik) dhe anglisht
FJALE_KYCE = re.compile(
    r"polic|arrest|vra[ns]|vrasj|sulm|shpërth|armë|armat|plagos|granat|kontraband|drog|"
    r"terror|protest|kufi|incident|ushtri|fsk|kfor|eulex|trazir|dhun|"
    r"uhapš|ubi[jos]|ubistv|napad|eksploz|oružj|ranjen|granic|vojsk|bezbed|nered|"
    r"полиц|ухапш|убиј|убист|напад|експлоз|оружј|рањен|границ|војск|безбед|"
    r"police|kill|attack|explos|weapon|injur|border|troops|smuggl|riot|clash|shoot|"
    # Kibernetikë, infrastrukturë dhe dezinformim (sq, sr latin + cirilik, en)
    r"kibernet|haker|hack|ddos|sajber|cyber|ransomware|malware|data breach|"
    r"sabot|rrym|nënstacion|ujësjellës|struj|trafostanic|dalekovod|vodovod|infrastrukt|"
    r"outage|blackout|power cut|substation|infrastruct|"
    r"dezinform|disinform|rrem[eë]|lažn|fake news|false (?:claim|report)|"
    r"сајбер|хакер|саботаж|струј|трафостаниц|далековод|водовод|инфраструкт|дезинформ|лажн",
    re.I,
)
# Fjalët kyçe të taksonomisë (dron, spiunazh, struktura paralele ...); bashkohen me OR me
# FJALE_KYCE, sepse kercenimet.py s'ka fjalët e përgjithshme të krimit ("polic", "vras", "arrest")
FJALE_KERCENIMESH = kercenimet.fjale_kyce_regex()

LLOJET = ["violence", "murder", "arrest", "explosion_weapons", "border_incident",
          "protest_unrest", "interethnic", "police_military_operation", "cyber",
          "infrastructure_disruption", "disinformation", "court_case", "other"]

# Aktorët ruhen vetëm nëse duken si institucion/grup, kurrë si emër personi
INSTITUCION = re.compile(
    r"polic|court|gjykat|sud|prokuror|prosecut|tužil|ministr|govern|qeveri|vlad|"
    r"kfor|eulex|nato|fsk|ksf|army|ushtri|vojsk|forc|agenc|agjenci|agencij|"
    r"party|parti|partij|council|kuvend|skupštin|assembl|unit|njësi|service|shërbim|"
    r"customs|dogan|carin|authorit|autoritet|organi|union|bashkim|eu\b|un\b|osce|osbe",
    re.I,
)
# Fjalë që lejohen në vargje me shkronja të mëdha (vende, institucione)
LEJUARA = re.compile(
    r"^(kosov|serb|srb|alban|shqip|north|south|veri|jug|republic|republik|basic|themelor|"
    r"special|police|polic|court|gjykat|forc|secur|sigur|army|ministr|govern|nation|"
    r"european|union|prishtin|pristin|mitrovic|prizren|pej|gjakov|ferizaj|gjilan|"
    r"novi|beograd|belgrad|tirana|skopje|macedon|maqedon|montenegr|bosni|croat|europ|"
    r"косов|срб|србиј|војск|полициј|север|митровиц|приштин|београд|влад|министар|кфор|еулекс)",
    re.I,
)
# Dy ose më shumë fjalë me shkronjë të madhe, latin ose cirilik ("Милан Петровић")
EMRA = re.compile(r"\b[A-ZÇËŠŽĆČĐ][a-zçëšžćčđ]+(?:\s+[A-ZÇËŠŽĆČĐ][a-zçëšžćčđ]+)+"
                  r"|\b[А-ЯЂЈЉЊЋЏ][а-яђјљњћџ]+(?:\s+[А-ЯЂЈЉЊЋЏ][а-яђјљњћџ]+)+")


def fshi_emrat(teksti):
    """Zëvendëson vargjet si "Emër Mbiemër" me [person], përveç vendeve/institucioneve."""
    def zevendeso(m):
        # Mbaj fjalët e lejuara ("Kosovo Police"), maskoj pjesën tjetër ("Triumf Riza")
        dalja = []
        for f in m.group().split():
            if LEJUARA.match(f):
                dalja.append(f)
            elif not dalja or dalja[-1] != "[person]":
                dalja.append("[person]")
        return " ".join(dalja)
    return EMRA.sub(zevendeso, teksti or "")
FUSHAT = ["is_security_event", "in_kosovo", "type", "summary", "event_date", "place",
          "place_precision", "date_precision", "actors", "killed", "injured", "arrested",
          "kategoria", "aktori", "shenjestrat", "lidhje_me_fsk", "relevante"]
SAKTESIA_VENDIT = ["village", "municipality", "region"]
SAKTESIA_DATES = ["exact", "approximate"]

# Përshkrim i shkurtër anglisht i çdo kategorie të kercenimet.py, sepse prompt-i është anglisht
KATEGORI_EN = {
    "ushtarak_serbia": "Serbian military activity: troops, exercises, readiness, weapons from China or Russia",
    "grupe_te_armatosura": "armed or paramilitary groups: armed attacks, weapons or explosives caches",
    "dron_hapesire_ajrore": "drones or airspace violations over FSK sites, critical infrastructure or the border",
    "kibernetik": "cyber attacks: DDoS, hacking, ransomware, data leaks",
    "infrastrukture_kritike": "sabotage or physical attack on water, power, transport or telecom",
    "dezinformim": "disinformation and false or manipulative claims about Kosovo, FSK, KFOR or the EU",
    "trazira_bllokada": "riots, barricades, road or border blockades, violent protests",
    "kufi_kontrabande": "border incidents, smuggling and trafficking of weapons, drugs or goods",
    "struktura_paralele": "Serbian-run parallel institutions in Kosovo: post offices, banks, municipal offices",
    "diplomatik_ligjor": "diplomatic or legal pressure: recognitions, memberships, UN, arrest warrants",
    "ekonomik_energjetik": "economic or energy coercion: grid interconnection, trade bans, strategic investment",
    "spiunazh_ndikim": "espionage, foreign intelligence or influence, surveillance technology",
    "ekstremizem_terrorizem": "violent extremism and terrorism, foreign fighters",
    "tjeter": "any other security event, e.g. ordinary crime or an accident",
}
KATEGORITE_PROMPT = "\n".join(f"- {k}: {v}" for k, v in KATEGORI_EN.items())

PROMPT = """You extract one security event in or about Kosovo from a news article.
Answer with JSON only, exactly these keys:
{{"is_security_event": true or false,
 "in_kosovo": true or false (did the event happen in Kosovo?),
 "type": one of {llojet},
 "summary": "one short English sentence, WITHOUT names of private persons",
 "event_date": "YYYY-MM-DD" or null,
 "place": "town or municipality in Kosovo, or a town in a neighbouring country if the event happened there" or null,
 "place_precision": "village", "municipality" or "region" (e.g. "north Kosovo") or null,
 "date_precision": "exact" (a specific day, e.g. "yesterday") or "approximate"
                   (e.g. "last week", "recently") or null,
 "actors": ["institutions or groups only, never names of individuals"],
 "killed": number or null, "injured": number or null, "arrested": number or null,
 "kategoria": one category id from the list below,
 "aktori": one of {aktoret},
 "shenjestrat": a list with zero or more of {shenjestrat},
 "lidhje_me_fsk": true or false,
 "relevante": true or false}}
Category ids:
{kategorite}
A security event is: violence, murder, arrest, attack, explosion, weapons find,
border incident, protest or unrest, interethnic incident, police or military
operation, cyber attack (DDoS, hacking, data leak, ransomware), terrorism,
sabotage or suspicious disruption of power, water, telecom or transport
("infrastructure_disruption"), and false or misleading claims about security
incidents spreading publicly, even when officials deny them ("disinformation").
Diplomatic or legal pressure, economic or energy coercion, parallel structures, espionage
and disinformation against Kosovo ARE security events. Ordinary politics and economy without
such a threat are NOT.
Planned maintenance, ordinary technical faults, sport, culture and statements without an
incident are NOT security events.
relevante: false when the article is not about a threat to Kosovo's security, the FSK/KSF,
KFOR or Kosovo institutions (e.g. sport, culture, charity, ordinary business).
Serbian military build-up, exercises near Kosovo, or acquisition of weapons, drones or
surveillance systems from China or Russia ARE relevant (relevante=true, in_kosovo=false,
kategoria=ushtarak_serbia or spiunazh_ndikim), even if Kosovo is not mentioned.
lidhje_me_fsk: true only if the Kosovo Security Force (FSK/KSF) is involved or targeted.
aktori: the actor the article reports as having carried out the act. If the article only
reports an accusation by one party that the other denies, still set the accused actor but
the summary must say 'alleged'.
An explosion is "explosion_weapons" even if it cuts power or water.
A court verdict or trial about an older crime is type "court_case", and its
event_date is the date of the verdict.

Article published: {data}
Title: {titulli}
Text:
{teksti}"""


def ka_fjale_sigurie(a):
    teksti = f"{a['titulli']} {a['teksti'] or ''}"
    return bool(FJALE_KYCE.search(teksti) or FJALE_KERCENIMESH.search(teksti))


def numer(v):
    """Kthen int ose None (modeli ndonjëherë jep "3" ose "disa")."""
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def valido(r, data_publikimit):
    """Mban vetëm fushat e lejuara dhe i kontrollon me rregulla."""
    r = {k: r.get(k) for k in FUSHAT}
    r["is_security_event"] = r["is_security_event"] is True
    r["in_kosovo"] = r["in_kosovo"] is True
    if r["type"] not in LLOJET:
        r["type"] = "other"
    # Rregull: dezinformimi për siguri është vetë ngjarje sigurie, edhe kur policia e mohon.
    # Modeli shpesh e njeh llojin, por thotë "s'ka ngjarje" sepse sulmi s'ndodhi.
    if r["type"] == "disinformation":
        r["is_security_event"] = True
    # K2: vetëm ID-të e kercenimet.py; çdo gjë tjetër bie te vlera e paracaktuar
    k, a, sh = r["kategoria"], r["aktori"], r["shenjestrat"]
    r["kategoria"] = k if isinstance(k, str) and kercenimet.kategoria_valide(k) else "tjeter"
    r["aktori"] = a if isinstance(a, str) and a in kercenimet.AKTORET else "i_panjohur"
    # Pa dyfishime dhe në radhën e SHENJESTRAT
    r["shenjestrat"] = [x for x in kercenimet.SHENJESTRAT if isinstance(sh, list) and x in sh]
    r["lidhje_me_fsk"] = r["lidhje_me_fsk"] is True
    r["relevante"] = r["relevante"] is not False  # modeli që e harron fushën s'i hedh të gjitha
    # Rregull si ai i dezinformimit: kërcënim hibrid i lidhur me Kosovën = ngjarje sigurie
    if r["kategoria"] != "tjeter" and r["relevante"]:
        r["is_security_event"] = True
    for k in ("killed", "injured", "arrested"):
        r[k] = numer(r[k])
    # Mbrojtja e të dhënave personale me rregulla, jo me besim te modeli
    r["actors"] = [str(x) for x in (r["actors"] or []) if x and INSTITUCION.search(str(x))][:5]
    r["summary"] = fshi_emrat(str(r["summary"] or ""))[:300]
    # Data e ngjarjes pranohet vetëm nëse bie 0-7 ditë para publikimit
    pub = data_publikimit[:10]
    try:
        d = datetime.strptime(str(r["event_date"]), "%Y-%m-%d")
        p = datetime.strptime(pub, "%Y-%m-%d")
        if not (p - timedelta(days=7) <= d <= p):
            raise ValueError
    except ValueError:
        r["event_date"] = None
    # Saktësia: vetëm vlerat e njohura; pa vend/datë s'ka saktësi
    if r["place_precision"] not in SAKTESIA_VENDIT or not r["place"]:
        r["place_precision"] = None
    if r["date_precision"] not in SAKTESIA_DATES or not r["event_date"]:
        r["date_precision"] = None
    return r


def nxirr(a):
    """Kthen JSON-in e validuar për një artikull."""
    # Përkthimin e përdorim nëse ekziston; përndryshe tekstin origjinal
    teksti = (a["teksti_perkthyer"] or a["teksti"] or "")[:2500]
    pergjigja = pyet_ollama(PROMPT.format(llojet=LLOJET, data=a["data"][:10], titulli=a["titulli"],
                                          teksti=teksti, kategorite=KATEGORITE_PROMPT,
                                          aktoret=list(kercenimet.AKTORET),
                                          shenjestrat=list(kercenimet.SHENJESTRAT)), si_json=True)
    return valido(json.loads(pergjigja), a["data"])


def perpuno(limit=20):
    """Kalon artikujt e paparë. Kthen (te_nxjerre_me_model, te_filtruar, gabime, ngjarje)."""
    model = filtruar = gabime = ngjarje = 0
    for a in db.artikuj_per_nxjerrje(limit):
        if not ka_fjale_sigurie(a):
            # Rregull i thjeshtë, pa model: s'ka fjalë sigurie -> s'ka ngjarje
            db.sheno_perpunuar(a["id"], {"is_security_event": False, "arsyeja": "pa fjalë kyçe"})
            filtruar += 1
            continue
        t0 = time.time()
        try:
            r = nxirr(a)
        except Exception as e:
            gabime += 1  # s'shënohet si i përpunuar, provohet sërish herën tjetër
            print(f"  #{a['id']} gabim: {e}")
            continue
        db.sheno_perpunuar(a["id"], r)
        model += 1
        if r["is_security_event"]:
            ngjarje += 1
        print(f"  #{a['id']} [{a['gjuha']}] {'NGJARJE ' + r['type'] if r['is_security_event'] else '-'}"
              f" ({time.time() - t0:.0f}s)")
    return model, filtruar, gabime, ngjarje


def rinxirr_sigurine(dite=14):
    """Rihap për modelin artikujt e sigurisë të nxjerrë para taksonomisë (pa "kategoria") dhe të
    publikuar në 'dite' ditët e fundit. perpuno() i rinxjerr me model herën tjetër. Kthen numrin."""
    kufiri = (datetime.now() - timedelta(days=dite)).strftime("%Y-%m-%d")
    with closing(db.lidhu()) as con, con:
        n = con.execute(
            "UPDATE articles SET perpunuar = 0 WHERE perpunuar = 1 "
            "AND json_extract(rezultati_json, '$.is_security_event') = 1 "
            "AND json_extract(rezultati_json, '$.kategoria') IS NULL AND data >= ?", (kufiri,)).rowcount
    print(f"U rihapën {n} artikuj sigurie pa kategori (~{n} min me Ollama)")
    return n


def rishiko_te_filtruarat():
    """Rihap artikujt e filtruar "pa fjalë kyçe" që tani kapen nga fjalët e kercenimet.py."""
    with closing(db.lidhu()) as con, con:
        rreshtat = con.execute(
            "SELECT id, titulli, teksti FROM articles WHERE perpunuar = 1 "
            "AND json_extract(rezultati_json, '$.arsyeja') = ?", ("pa fjalë kyçe",)).fetchall()
        ids = [(r["id"],) for r in rreshtat if ka_fjale_sigurie(r)]
        con.executemany("UPDATE articles SET perpunuar = 0 WHERE id = ?", ids)
    print(f"U rihapën {len(ids)} artikuj që filtri i ri i kap (~{len(ids)} min me Ollama)")
    return len(ids)


if __name__ == "__main__":
    # Kontroll i vogël i filtrit të emrave
    assert fshi_emrat("Aleksandar Vučić pardoned Toma Stojić") == "[person] pardoned [person]"
    assert fshi_emrat("Kosovo Police arrested two in North Mitrovica") == \
        "Kosovo Police arrested two in North Mitrovica"
    assert fshi_emrat("Kosovo Police Officer Triumf Riza") == "Kosovo Police [person]"
    # Saktësia e vendit/datës: vlera të panjohura ose pa vend/datë -> None
    r = valido({"place": "North Kosovo", "place_precision": "region", "event_date": "2026-11-19",
                "date_precision": "exact"}, "2026-11-20")
    assert (r["place_precision"], r["date_precision"]) == ("region", "exact"), r
    r = valido({"place": None, "place_precision": "village", "event_date": None,
                "date_precision": "approximate"}, "2026-11-20")
    assert (r["place_precision"], r["date_precision"]) == (None, None), r
    assert valido({"place": "Peja", "place_precision": "city"}, "2026-11-20")["place_precision"] is None
    # Filtri duhet të kapë edhe kibernetikën, infrastrukturën dhe dezinformimin
    for t in ("Hakerët publikuan të dhëna", "Sever Kosova ostao bez struje", "Саботажа далековода",
              "Fake news about poisoned water", "Lajme të rreme për ujin"):
        assert ka_fjale_sigurie({"titulli": t, "teksti": ""}), t
    assert not ka_fjale_sigurie({"titulli": "Kosova fiton ndeshjen miqësore", "teksti": ""})
    assert valido({"type": "disinformation"}, "2026-11-18")["type"] == "disinformation"
    # Filtri i ri kap edhe fjalët e taksonomisë, por jo lajmet e zakonshme
    for t in ("Dron mbi Jarinjë", "Беспилотна летелица изнад Јариња", "Russian propaganda on Telegram",
              "strukturat paralele", "spiunazh"):
        assert ka_fjale_sigurie({"titulli": t, "teksti": ""}), t
    assert not ka_fjale_sigurie({"titulli": "Ekstremisht nxehtë sot në Prishtinë", "teksti": ""})
    # Emrat në cirilik maskohen; vendet dhe institucionet jo
    assert fshi_emrat("Милан Петровић је ухапшен") == "[person] је ухапшен"
    assert fshi_emrat("Војска Србије је") == "Војска Србије је"
    # K2: vlerat jashtë listave bien te paracaktimet; relevante që mungon = True
    assert set(KATEGORI_EN) == set(kercenimet.KATEGORITE)
    r = valido({"kategoria": "Dezinformim", "aktori": ["rusia"], "lidhje_me_fsk": "po",
                "shenjestrat": ["fsk", "x", "fsk", "kfor_nato"]}, "2026-11-20")
    assert (r["kategoria"], r["aktori"], r["shenjestrat"], r["lidhje_me_fsk"], r["relevante"]) == \
        ("tjeter", "i_panjohur", ["fsk", "kfor_nato"], False, True), r
    assert valido({"shenjestrat": "fsk"}, "2026-11-20")["shenjestrat"] == []
    r = valido({"kategoria": "spiunazh_ndikim", "aktori": "shteti_serb", "lidhje_me_fsk": True},
               "2026-11-20")
    assert (r["is_security_event"], r["aktori"], r["lidhje_me_fsk"]) == (True, "shteti_serb", True), r
    assert not valido({"kategoria": "ushtarak_serbia", "relevante": False}, "2026-11-20")["is_security_event"]
    # Rinxjerrja në DB të përkohshme: rihapen vetëm sigurie pa kategori brenda 14 ditëve,
    # dhe të filtruarat që filtri i ri i kap
    import tempfile
    vjeter = db.DB_PATH
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as dosja:
        db.DB_PATH = f"{dosja}/prove.db"
        try:
            sot = datetime.now()
            rastet = {"a": ("Shpërthim në Zveçan", 3, {"is_security_event": True}),
                      "b": ("Koncert në Prishtinë", 3, {"is_security_event": False}),
                      "c": ("Sulm kibernetik", 3, {"is_security_event": True, "kategoria": "kibernetik"}),
                      "d": ("Shpërthim në Leposaviq", 30, {"is_security_event": True}),
                      "e": ("Dron mbi Jarinjë", 3, {"is_security_event": False, "arsyeja": "pa fjalë kyçe"}),
                      "f": ("Festivali i filmit në Prizren", 3,
                            {"is_security_event": False, "arsyeja": "pa fjalë kyçe"})}
            for url, (titulli, dite, _) in rastet.items():
                db.ruaj_artikull(url, "Koha", titulli, (sot - timedelta(days=dite)).isoformat(), "sq", titulli)
            with closing(db.lidhu()) as con:
                ids = {r["url"]: r["id"] for r in con.execute("SELECT id, url FROM articles")}
            for url, (_, _, rez) in rastet.items():
                db.sheno_perpunuar(ids[url], rez)
            assert rinxirr_sigurine(14) == 1 and rishiko_te_filtruarat() == 1
            with closing(db.lidhu()) as con:
                hapur = {r["url"] for r in con.execute("SELECT url FROM articles WHERE perpunuar = 0")}
            assert hapur == {"a", "e"}, hapur
            assert rinxirr_sigurine(14) == 0  # thirrja e dytë s'rihap asgjë tjetër
        finally:
            db.DB_PATH = vjeter
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    model, filtruar, gabime, ngjarje = perpuno(n)
    print(f"\nModeli: {model} artikuj ({ngjarje} ngjarje sigurie). "
          f"Filtruar pa model: {filtruar}. Gabime: {gabime}.")
