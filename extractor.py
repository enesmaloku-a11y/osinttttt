"""extractor.py - Nxjerr nga çdo artikull ngjarjen e sigurisë si JSON (me Ollama lokal).

- Filtër me fjalë kyçe para modelit: artikujt pa asnjë fjalë sigurie s'i dërgojmë fare.
- Cache: rezultati ruhet te articles.rezultati_json dhe artikulli s'përpunohet më.
- Mos ruaj të dhëna personale: modeli udhëzohet të mos japë emra personash,
  dhe ne ruajmë vetëm fushat e listës FUSHAT.
"""
import json
import re
import sys
import time
from datetime import datetime, timedelta

import db
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
    r"novi|beograd|belgrad|tirana|skopje|macedon|maqedon|montenegr|bosni|croat|europ)", re.I,
)
EMRA = re.compile(r"\b[A-ZÇËŠŽĆČĐ][a-zçëšžćčđ]+(?:\s+[A-ZÇËŠŽĆČĐ][a-zçëšžćčđ]+)+")


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
          "place_precision", "date_precision", "actors", "killed", "injured", "arrested"]
SAKTESIA_VENDIT = ["village", "municipality", "region"]
SAKTESIA_DATES = ["exact", "approximate"]

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
 "killed": number or null, "injured": number or null, "arrested": number or null}}
A security event is: violence, murder, arrest, attack, explosion, weapons find,
border incident, protest or unrest, interethnic incident, police or military
operation, cyber attack (DDoS, hacking, data leak, ransomware), terrorism,
sabotage or suspicious disruption of power, water, telecom or transport
("infrastructure_disruption"), and false or misleading claims about security
incidents spreading publicly, even when officials deny them ("disinformation").
Planned maintenance, ordinary technical faults, politics, economy, sport,
culture and statements without an incident are NOT security events.
An explosion is "explosion_weapons" even if it cuts power or water.
A court verdict or trial about an older crime is type "court_case", and its
event_date is the date of the verdict.

Article published: {data}
Title: {titulli}
Text:
{teksti}"""


def ka_fjale_sigurie(a):
    return bool(FJALE_KYCE.search(f"{a['titulli']} {a['teksti'] or ''}"))


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
    pergjigja = pyet_ollama(PROMPT.format(llojet=LLOJET, data=a["data"][:10],
                                          titulli=a["titulli"], teksti=teksti), si_json=True)
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
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    model, filtruar, gabime, ngjarje = perpuno(n)
    print(f"\nModeli: {model} artikuj ({ngjarje} ngjarje sigurie). "
          f"Filtruar pa model: {filtruar}. Gabime: {gabime}.")
