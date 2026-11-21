"""kercenimet.py - Taksonomia e kërcënimeve hibride për FSK-në dhe sigurinë e Kosovës (v1).

Burim i vetëm i së vërtetës për kategoritë, aktorët, shenjestrat, nivelet dhe prioritetet që
përdorin extractor.py, correlator.py, rreziku.py, raporti.py dhe dashboard.py.

Korniza: "The landscape of Hybrid Threats: A conceptual model" (JRC / Hybrid CoE, 2021,
EUR 30585 EN), me 13 fusha (domains) që ruhen te FUSHAT_HIBRIDE me emrat origjinalë:
https://publications.jrc.ec.europa.eu/repository/handle/JRC123305
Për Kosovën: KCSS "Dealing with Hybrid Threats in Kosovo" (2025), raporte të BIRN/Prishtina
Insight, RFE/RL, Al Jazeera, Energy Community, EUvsDisinfo. Shembujt kanë URL të kontrolluar
(kthejnë HTTP 200) më 2026-11-20; atribuimi i kontestuar shkruhet "sipas ...".

Fjalët kyçe janë rrënjë: përputhen në fillim të fjalës (\\b), pa marrë parasysh shkronjat e
mëdha, që "isis" të mos kapë "crisis". "sr_cyr" është transliterimi i saktë i "sr" (kontrollohet
te __main__). Kategoria "tjeter" s'ka fjalë kyçe: është vetëm vlera e paracaktuar.
Privatësia: asnjë emër personi privat; shtetet dhe institucionet përmenden sipas rolit.
"""
import re

# 13 fushat e modelit JRC / Hybrid CoE (seksioni 4.1)
FUSHAT_HIBRIDE = ["Infrastructure", "Cyber", "Space", "Economy", "Military/Defence", "Culture",
                  "Social/Societal", "Public Administration", "Legal", "Intelligence",
                  "Diplomacy", "Political", "Information"]

AKTORET = {
    "shteti_serb": "Shteti serb (institucionet e Serbisë)",
    "grupe_te_armatosura": "Grupe të armatosura",
    "krim_i_organizuar": "Krimi i organizuar",
    "rusia": "Rusia (shteti dhe mediat shtetërore)",
    "kina": "Kina (shteti dhe kompanitë shtetërore)",
    "grupe_ekstremiste": "Grupe ekstremiste",
    "media_propagandistike": "Media propagandistike",
    "i_panjohur": "I panjohur",
}

SHENJESTRAT = {
    "fsk": "Forca e Sigurisë së Kosovës (FSK)",
    "infrastrukture_kritike": "Infrastruktura kritike",
    "institucione": "Institucionet e Kosovës",
    "kfor_nato": "KFOR / NATO",
    "komunitete": "Komunitetet dhe marrëdhëniet ndëretnike",
    "shoqeri": "Shoqëria dhe opinioni publik",
    "ekonomi": "Ekonomia",
}

NIVELET = ["i lartë", "i mesëm", "i ulët"]
PRIORITETET = ["URGJENTE", "RAPORT", "MONITORIM", "ARKIV"]

KATEGORITE = {
    "ushtarak_serbia": {
        "emri": "Aktivitet ushtarak i Serbisë",
        "pershkrimi": "Grumbullim trupash, gatishmëri luftarake, stërvitje dhe armatime të reja të "
                      "Ushtrisë së Serbisë pranë Kosovës, përfshirë sistemet nga Kina dhe Rusia.",
        "fusha_hibride": ["Military/Defence", "Diplomacy", "Political"],
        "treguesit": [
            "Lëvizje ose grumbullim i artilerisë, tankeve, këmbësorisë së mekanizuar pranë kufirit "
            "ose në Zonën Tokësore të Sigurisë",
            "Urdhër për ngritjen e gatishmërisë luftarake",
            "Dorëzim ose vënie në shërbim i sistemeve kineze (FK-3/HQ-22, HQ-17A, CH-92A, CH-95, "
            "CM-400AKG) ose ruse (Pancir-S1, MiG-29)",
            "Stërvitje ushtarake pranë kufirit ose me forca ruse/bjelloruse",
            "Deklarata zyrtare për kthimin e forcave serbe në Kosovë sipas Rezolutës 1244",
            "Fluturime të avionëve ose dronëve ushtarakë pranë kufirit",
        ],
        "fjale_kyce": {
            "sq": ["ushtria e serbisë", "ushtrisë së serbisë", "ushtria serbe", "ushtrisë serbe",
                   "trupat serbe", "trupave serbe", "luftarak", "artileri", "tanke",
                   "zona tokësore", "stërvitje ushtarake", "mjete të blinduara"],
            "sr": ["vojska srbije", "vojske srbije", "mig-29", "borben", "artiljerij", "tenkov",
                   "mehanizovan", "kopnena zona", "kopnenoj zoni", "vojna vežba", "vojne vežbe",
                   "pancir"],
            "sr_cyr": ["војска србије", "војске србије", "миг-29", "борбен", "артиљериј", "тенков",
                       "механизован", "копнена зона", "копненој зони", "војна вежба", "војне вежбе",
                       "панцир"],
            "en": ["serbian army", "serbian armed forces", "serbian troops", "military build",
                   "combat readiness", "ground safety zone", "artillery", "mechanized", "pantsir",
                   "fk-3", "hq-22", "cm-400"],
        },
        "aktoret_tipike": ["shteti_serb", "rusia", "kina"],
        "shenjestrat_tipike": ["fsk", "kfor_nato", "institucione"],
        # 5: kërcënim konvencional; në shtator 2023 SHBA e quajti grumbullimin "të paparë"
        "rrezikshmeria_baze": 5,
        "burimet_e_mbledhjes": [
            "Zyrtare serbe: Ministria e Mbrojtjes (mod.gov.rs), Ushtria e Serbisë (vs.rs)",
            "Media serbe: N1 Serbia, RTS, Tanjug, Novosti (latin dhe cirilik)",
            "Deklarata të KFOR/NATO, SHBA dhe BE",
            "Media mbrojtjeje dhe analiza: Defense News, RFE/RL, SIPRI Arms Transfers Database",
            "GDELT: kërkim 'Serbian army' OR 'Vojska Srbije' me Kosovo",
        ],
        "shembuj": [
            {"pershkrimi": "Shtator 2023: Shtëpia e Bardhë raporton grumbullim të paparë të "
                           "artilerisë, tankeve dhe këmbësorisë së mekanizuar serbe pranë kufirit.",
             "url": "https://www.aljazeera.com/news/2023/9/30/us-concerned-by-large-serbian-military-mobilisation-near-kosovo"},
            {"pershkrimi": "Prill 2022: Kina dërgon me avionë Y-20 sistemin e mbrojtjes ajrore FK-3 "
                           "(HQ-22) në Beograd.",
             "url": "https://www.defensenews.com/land/2022/04/11/china-delivers-anti-aircraft-missiles-to-serbia/"},
            {"pershkrimi": "Janar 2026: RFE/RL përmbledh blerjet ushtarake serbe nga Kina (CH-92, "
                           "FK-3, CH-95, HQ-17A) dhe armët me origjinë ruse (MiG-29).",
             "url": "https://www.rferl.org/a/serbia-china-military-cooperation-drones-air-defense-security/33626646.html"},
        ],
    },
    "grupe_te_armatosura": {
        "emri": "Grupe të armatosura dhe paraushtarake",
        "pershkrimi": "Grupe të armatosura ose paraushtarake që sulmojnë policinë, FSK-në ose "
                      "KFOR-in, ose fshehin armë e eksploziv në veri.",
        "fusha_hibride": ["Military/Defence", "Intelligence", "Social/Societal"],
        "treguesit": [
            "Pritë ose sulm i armatosur ndaj patrullave të policisë (rrugë e bllokuar me kamionë)",
            "Zbulim depo armësh, eksplozivi, uniformash ose lansuesish raketash në veri",
            "Aktivitet i grupeve si 'Civilna zaštita' ose 'Severna brigada'",
            "Përdorim uniformash pa shenja, radiondërlidhjeje dhe dronësh nga sulmuesit",
            "Ikje e sulmuesve drejt Serbisë dhe kërkesa për ekstradim",
        ],
        "fjale_kyce": {
            "sq": ["armatosur", "paraushtarak", "mbrojtja civile", "mbrojtjes civile",
                   "brigada veriore", "depo armësh", "depo të armëve", "uniforma ushtarake",
                   "eksploziv", "shpërthyes", "lansues raketash", "banjsk"],
            "sr": ["naoružan", "oružan", "paravojn", "civilna zaštita", "civilne zaštite",
                   "severna brigada", "severne brigade", "skladište oružja", "vojne uniforme",
                   "eksploziv", "bacač raket", "banjsk"],
            "sr_cyr": ["наоружан", "оружан", "паравојн", "цивилна заштита", "цивилне заштите",
                       "северна бригада", "северне бригаде", "складиште оружја", "војне униформе",
                       "експлозив", "бацач ракет", "бањск"],
            "en": ["armed group", "gunmen", "paramilitar", "civil protection", "northern brigade",
                   "weapons cache", "arms cache", "explosive", "rocket launcher", "banjska",
                   "ambush", "armed attack"],
        },
        "aktoret_tipike": ["grupe_te_armatosura", "shteti_serb", "krim_i_organizuar"],
        "shenjestrat_tipike": ["institucione", "kfor_nato", "fsk", "komunitete"],
        # 5: sulm me viktima (Banjska, shtator 2023) dhe arsenal i mbetur në veri
        "rrezikshmeria_baze": 5,
        "burimet_e_mbledhjes": [
            "Zyrtare: Policia e Kosovës (kosovopolice.com), Prokuroria Speciale, KFOR, EULEX",
            "Media lokale: Kallxo, Koha, KoSSev, Kosovo Online",
            "Media serbe: N1 Serbia, RTS, Novosti (latin dhe cirilik)",
            "GDELT: kërkim 'armed group' OR 'naoružana grupa' me Kosovo",
        ],
        "shembuj": [
            {"pershkrimi": "24 shtator 2023, Banjskë: rreth 30 persona të armatosur rëndë sulmojnë "
                           "policinë, një polic vritet; Kosova akuzon mbështetje nga Beogradi, "
                           "Serbia e mohon.",
             "url": "https://www.aljazeera.com/news/2023/9/24/one-police-officer-killed-in-kosovo-attack-blamed-on-serbia"},
            {"pershkrimi": "14 maj 2024: policia sekuestron pushkë, granata shokuese dhe eksploziv "
                           "në veri, që sipas saj i përkasin grupit të sulmit në Banjskë.",
             "url": "https://www.rferl.org/a/kosovo-weapons-seized-serbian-group/32947419.html"},
        ],
    },
    "dron_hapesire_ajrore": {
        "emri": "Dronë dhe shkelje të hapësirës ajrore",
        "pershkrimi": "Fluturime të paautorizuara dronësh mbi objekte të FSK-së, infrastrukturë "
                      "kritike, kufi ose institucione; zbulim para sulmit ose provokim.",
        "fusha_hibride": ["Military/Defence", "Intelligence", "Infrastructure"],
        "treguesit": [
            "Dron i paidentifikuar mbi kazerma, baza ose depo të FSK-së ose KFOR-it",
            "Dron mbi infrastrukturë kritike (termocentralet e KEK-ut, Ujmani/Gazivoda, kanali "
            "Ibër-Lepenc, nënstacione)",
            "Kalim dronësh nga Serbia mbi vijën kufitare",
            "Shpallje zone ndalim-fluturimi nga KFOR ose autoritetet",
            "Pamje nga dronë të objekteve sensitive të publikuara në media ose Telegram",
            "Rrëzim ose neutralizim dronësh me luftë elektronike",
        ],
        "fjale_kyce": {
            "sq": ["dron", "hapësirë ajrore", "hapësira ajrore", "hapësirën ajrore",
                   "hapësirës ajrore", "mbrojtje ajrore", "mbrojtjes ajrore", "ndalim fluturimi",
                   "ndalim-fluturimi", "pa pilot", "bayraktar", "kundërdron"],
            "sr": ["dron", "bespilot", "vazdušni prostor", "vazdušnog prostora",
                   "vazdušnom prostoru", "zabrana letenja", "zabrane letenja", "zabranu letenja",
                   "protivvazdušn", "protivdronsk", "nadlet", "ometač"],
            "sr_cyr": ["дрон", "беспилот", "ваздушни простор", "ваздушног простора",
                       "ваздушном простору", "забрана летења", "забране летења", "забрану летења",
                       "противваздушн", "противдронск", "надлет", "ометач"],
            "en": ["drone", "uav", "unmanned aerial", "airspace", "no-fly zone", "no fly zone",
                   "overflight", "air defence", "air defense", "anti-drone", "counter-drone",
                   "bayraktar"],
        },
        "aktoret_tipike": ["shteti_serb", "grupe_te_armatosura", "i_panjohur"],
        "shenjestrat_tipike": ["fsk", "infrastrukture_kritike", "kfor_nato", "institucione"],
        # 4: tregues i hershëm para sulmit mbi FSK-në dhe infrastrukturën kritike; mentorët e veçuan
        "rrezikshmeria_baze": 4,
        "burimet_e_mbledhjes": [
            "Zyrtare: Ministria e Punëve të Brendshme, Policia e Kosovës, KFOR",
            "Media lokale (Koha, KoSSev, Kallxo) dhe serbe (N1 Serbia, Novosti)",
            "Kanale publike Telegram ku publikohen pamje dronësh (lista miratohet nga njeriu)",
        ],
        "shembuj": [
            {"pershkrimi": "Shtator 2025: Ministri i Brendshëm i Kosovës deklaron fluturime të "
                           "paautorizuara të dronëve nga Serbia, në hetim me KFOR-in.",
             "url": "https://n1info.rs/vesti/sveclja-srpski-dronovi-prelecu-kosovo/"},
        ],
    },
    "kibernetik": {
        "emri": "Sulme kibernetike",
        "pershkrimi": "DDoS, depërtime, ransomware ose rrjedhje të dhënash ndaj institucioneve, "
                      "FSK-së dhe operatorëve të energjisë, ujit e telekomit në Kosovë.",
        "fusha_hibride": ["Cyber", "Infrastructure", "Public Administration", "Information"],
        "treguesit": [
            "Faqe qeveritare ose institucionale jashtë funksionit (DDoS) ose të deformuara",
            "Pretendim përgjegjësie nga grupe hakerësh në Telegram (p.sh. grupe pro-ruse)",
            "Rrjedhje të dhënash të institucioneve ose ndërmarrjeve publike",
            "Ransomware ndaj energjisë, ujit, telekomit ose shëndetësisë",
            "Njoftime nga Agjencia për Siguri Kibernetike ose Policia e Kosovës",
            "Fushata phishing që imitojnë institucionet",
        ],
        "fjale_kyce": {
            "sq": ["kibernetik", "haker", "ddos", "ransomware", "malware", "phishing",
                   "rrjedhje të dhënash", "rrjedhje e të dhënave", "rrjedhjen e të dhënave",
                   "faqet qeveritare", "faqet zyrtare", "sistemet informatike"],
            "sr": ["sajber", "haker", "ddos", "ransomver", "malver", "fišing", "curenje podataka",
                   "curenja podataka", "ukradeni podaci", "informacioni sistem", "napad na sajt",
                   "kibernetičk"],
            "sr_cyr": ["сајбер", "хакер", "ддос", "рансомвер", "малвер", "фишинг", "цурење података",
                       "цурења података", "украдени подаци", "информациони систем", "напад на сајт",
                       "кибернетичк"],
            "en": ["cyber", "hacker", "hacked", "hacking", "ddos", "denial of service",
                   "ransomware", "malware", "phishing", "spyware", "data breach", "data leak"],
        },
        "aktoret_tipike": ["rusia", "shteti_serb", "krim_i_organizuar", "i_panjohur"],
        "shenjestrat_tipike": ["institucione", "infrastrukture_kritike", "fsk", "ekonomi"],
        # 3: DDoS-et e njohura ishin ndërprerje të përkohshme; rritet kur prek energjinë ose FSK-në
        "rrezikshmeria_baze": 3,
        "burimet_e_mbledhjes": [
            "EuRepoC (kontekst_kibernetik.py, PR#6)",
            "Media të specializuara: The Record, Security Affairs",
            "Kanale publike Telegram të grupeve hakere, vetëm lexim (lista miratohet nga njeriu)",
            "Zyrtare: Qeveria, Agjencia për Siguri Kibernetike, Policia e Kosovës",
            "GDELT: kërkim 'cyberattack' OR 'sajber napad' me Kosovo",
        ],
        "shembuj": [
            {"pershkrimi": "Maj 2024: sulme DDoS nxjerrin përkohësisht jashtë funksionit faqet "
                           "qeveritare; Qeveria i atribuon hakerëve rusë, pas ndihmës për Ukrainën.",
             "url": "https://therecord.media/russian-hackers-kosovo-ddos-pristina"},
        ],
    },
    "infrastrukture_kritike": {
        "emri": "Sabotim i infrastrukturës kritike",
        "pershkrimi": "Sabotim ose sulm fizik ndaj ujit, energjisë, transportit ose telekomit, "
                      "p.sh. kanali Ibër-Lepenc që furnizon termocentralet.",
        "fusha_hibride": ["Infrastructure", "Economy", "Social/Societal"],
        "treguesit": [
            "Shpërthim ose dëmtim në kanale uji, diga, ujësjellës (Ujmani/Gazivoda, Ibër-Lepenc)",
            "Ndërprerje e energjisë pa shkak teknik të qartë; dëmtim nënstacionesh ose largpërçuesish",
            "Dëmtim urash, hekurudhe ose kabllosh të telekomit",
            "Masa shtesë sigurie nga KFOR ose policia te objektet kritike",
            "Arrestime për sabotim ose eksploziv i gjetur pranë objekteve",
        ],
        "fjale_kyce": {
            "sq": ["sabot", "ujësjellës", "ibër-lepenc", "iber-lepenc", "ujman", "nënstacion",
                   "largpërçues", "termocentral", "ndërprerje e rrymës", "ndërprerje të energjisë",
                   "infrastrukturë kritike", "infrastrukturës kritike"],
            "sr": ["sabot", "diverzij", "diverzant", "ibar-lepenac", "gazivod", "vodovod",
                   "trafostanic", "dalekovod", "termoelektran", "nestanak struje",
                   "kritična infrastruktur", "kritične infrastruktur"],
            "sr_cyr": ["сабот", "диверзиј", "диверзант", "ибар-лепенац", "газивод", "водовод",
                       "трафостаниц", "далековод", "термоелектран", "нестанак струје",
                       "критична инфраструктур", "критичне инфраструктур"],
            "en": ["sabotage", "ibar-lepenac", "iber-lepenc", "gazivod", "water canal",
                   "water supply", "power plant", "substation", "power line", "blackout",
                   "power outage", "critical infrastructure"],
        },
        "aktoret_tipike": ["grupe_te_armatosura", "shteti_serb", "i_panjohur"],
        "shenjestrat_tipike": ["infrastrukture_kritike", "ekonomi", "shoqeri"],
        # 5: nëntor 2024 ndali ujin për termocentralet që prodhojnë pothuajse gjithë rrymën
        "rrezikshmeria_baze": 5,
        "burimet_e_mbledhjes": [
            "Njoftime të operatorëve: KEK, KOSTT, KEDS, Ibër-Lepenc, ujësjellësit rajonalë",
            "Zyrtare: Policia, Prokuroria, KFOR",
            "Media lokale dhe serbe (latin dhe cirilik)",
            "GDELT: kërkim 'sabotage' OR 'diverzija' me Kosovo",
        ],
        "shembuj": [
            {"pershkrimi": "29 nëntor 2024: shpërthim në kanalin Ibër-Lepenc te Zubin Potoku; "
                           "Kosova e quan akt terrorist të Serbisë, Serbia e mohon; 8 të arrestuar.",
             "url": "https://www.aljazeera.com/news/2024/11/30/kosovo-pm-blames-serbia-for-explosion-at-canal-supplying-power-plants"},
        ],
    },
    "dezinformim": {
        "emri": "Dezinformim dhe manipulim informativ",
        "pershkrimi": "Narrativa të rreme ose manipuluese kundër Kosovës, FSK-së, KFOR-it e BE-së, "
                      "nga media shtetërore ruse, media pro-qeveritare serbe dhe kanale Telegram.",
        "fusha_hibride": ["Information", "Political", "Social/Societal", "Culture"],
        "treguesit": [
            "Narrativa 'spastrim etnik', 'pogrom' ose 'eksod' i serbëve pa prova",
            "FSK paraqitet si armatim i paligjshëm ose përgatitje sulmi ndaj Serbisë",
            "KFOR/EULEX si forca pushtuese; NATO si nxitëse e krizës",
            "Paralele Kosovë–Ukrainë ose pretendime për luftëtarë nga Kosova në Ukrainë",
            "E njëjta përmbajtje njëkohësisht te Sputnik Srbija, RT Balkan, Pravda dhe Telegram",
            "Lajm i rremë për incident sigurie që e mohon policia",
        ],
        "fjale_kyce": {
            "sq": ["dezinform", "lajm i rremë", "lajmi i rremë", "lajme të rreme", "lajmet e rreme",
                   "propagand", "spastrim etnik", "spastrimit etnik", "demant",
                   "sputnik", "krypometr"],
            "sr": ["dezinform", "lažn", "propagand", "etničko čišćenje", "etničkog čišćenja",
                   "progon srba", "egzodus", "pogrom", "sputnjik", "rt balkan", "šiptar",
                   "demant"],
            "sr_cyr": ["дезинформ", "лажн", "пропаганд", "етничко чишћење", "етничког чишћења",
                       "прогон срба", "егзодус", "погром", "спутњик", "рт балкан", "шиптар",
                       "демант"],
            "en": ["disinform", "misinform", "propaganda", "fake news", "false claim",
                   "ethnic cleansing", "exodus", "pogrom", "sputnik", "rt balkan", "debunk",
                   "fact-check"],
        },
        "aktoret_tipike": ["media_propagandistike", "rusia", "shteti_serb"],
        "shenjestrat_tipike": ["shoqeri", "fsk", "kfor_nato", "institucione", "komunitete"],
        # 3: rrallë dëm i drejtpërdrejtë, por përgatit terrenin për trazira; rritet pranë incidenteve
        "rrezikshmeria_baze": 3,
        "burimet_e_mbledhjes": [
            "EUvsDisinfo (kontekst_dezinformim.py, CSV manual)",
            "Verifikues faktesh: Krypometri (Kallxo), Hibrid.info, Raskrikavanje (Serbi)",
            "Monitorim me besueshmëri të ulët: Sputnik Srbija, RT Balkan, tabloidë serbë",
            "Kanale publike Telegram pro-ruse (lista miratohet nga njeriu)",
            "Raporte: EEAS (FIMI), ISD, CEP, BCSP, KCSS",
        ],
        "shembuj": [
            {"pershkrimi": "Shtator–tetor 2025: Krypometri numëron 353 artikuj me narrativa "
                           "dezinformuese për Kosovën nga Sputnik, RT Balkan dhe Pravda.",
             "url": "https://prishtinainsight.com/russian-controlled-media-flood-kosovos-information-space-with-disinformation-mag/"},
            {"pershkrimi": "Janar 2025: fushatë e lidhur me Kremlinin që barazon Kosovën me "
                           "Ukrainën dhe pretendon plane për dëbimin e serbëve.",
             "url": "https://prishtinainsight.com/russia-driven-disinformation-campaign-aims-at-drawing-parallels-between-kosovo-and-ukraine-mag/"},
        ],
    },
    "trazira_bllokada": {
        "emri": "Trazira, barrikada dhe bllokada",
        "pershkrimi": "Protesta të dhunshme, barrikada, bllokim rrugësh ose pikash kufitare dhe "
                      "përplasje me policinë ose KFOR-in.",
        "fusha_hibride": ["Social/Societal", "Political", "Public Administration"],
        "treguesit": [
            "Barrikada me kamionë ose makineri në rrugë kryesore ose pika kalimi (Jarinjë, Bërnjak)",
            "Thirrje për mobilizim në rrjete sociale ose Telegram; tubime para objekteve komunale",
            "Përdorim molotovësh, mjetesh shpërthyese ose gurësh ndaj policisë ose KFOR-it",
            "Të plagosur nga radhët e KFOR-it ose policisë",
        ],
        "fjale_kyce": {
            "sq": ["barrikad", "bllokad", "bllokuan rrugën", "protest", "trazir",
                   "molotov", "gaz lotsjellës", "jarinj", "bërnjak", "turma"],
            "sr": ["barikad", "blokad", "protest", "nered", "molotov", "suzavac",
                   "suzavca", "okupljanje srba", "jarinj", "brnjak", "demonstrant"],
            "sr_cyr": ["барикад", "блокад", "протест", "неред", "молотов", "сузавац",
                       "сузавца", "окупљање срба", "јарињ", "брњак", "демонстрант"],
            "en": ["barricade", "blockade", "roadblock", "protest", "riot", "clash", "molotov",
                   "tear gas", "unrest", "jarinje", "brnjak", "demonstrator"],
        },
        "aktoret_tipike": ["shteti_serb", "grupe_te_armatosura", "i_panjohur"],
        "shenjestrat_tipike": ["kfor_nato", "institucione", "komunitete"],
        # 4: maj 2023 në Zveçan, dhjetëra ushtarë të KFOR-it të plagosur
        "rrezikshmeria_baze": 4,
        "burimet_e_mbledhjes": [
            "Zyrtare: KFOR, Policia e Kosovës",
            "Media lokale: KoSSev, Kosovo Online, Kallxo, Koha",
            "Media serbe: N1 Serbia, RTS (latin dhe cirilik)",
            "Kanale publike Telegram për thirrje mobilizimi (lista miratohet nga njeriu)",
        ],
        "shembuj": [
            {"pershkrimi": "29 maj 2023, Zveçan: 25 paqeruajtës të KFOR-it plagosen në përplasje "
                           "me protestues serbë para zyrave komunale (më vonë KFOR tha 30).",
             "url": "https://www.pbs.org/newshour/world/25-nat0-led-peacekeepers-injured-in-kosovo-amid-ethnic-tensions"},
        ],
    },
    "kufi_kontrabande": {
        "emri": "Kufiri, kontrabanda dhe trafikimi",
        "pershkrimi": "Kalime ilegale, kontrabandë armësh, eksplozivi, droge e mallrash dhe "
                      "incidente me forcat serbe në vijën kufitare.",
        "fusha_hibride": ["Military/Defence", "Economy", "Legal"],
        "treguesit": [
            "Sekuestrim armësh, municioni ose eksplozivi në kufi ose në veri",
            "Rrugë ilegale të përdorura për kalime ose të mbyllura nga policia",
            "Kontrabandë karburanti, cigaresh ose droge përmes pikave Jarinjë, Bërnjak, Merdare",
            "Arrestim ose ndalim i policëve të Kosovës nga forcat serbe pranë kufirit",
            "Arrestime për trafikim me lidhje me grupe të armatosura",
        ],
        "fjale_kyce": {
            "sq": ["kontraband", "trafikim", "rrugë ilegale", "rrugët ilegale", "kalim ilegal",
                   "pika kufitare", "pikën kufitare", "vija kufitare", "vijën kufitare", "sekuestr",
                   "municion", "merdar"],
            "sr": ["šverc", "krijumčar", "trgovina oružjem", "ilegalni prelaz", "ilegalnih prelaza",
                   "alternativni put", "administrativni prelaz", "administrativna linija",
                   "administrativne linije", "zaplen", "municij", "merdar"],
            "sr_cyr": ["шверц", "кријумчар", "трговина оружјем", "илегални прелаз",
                       "илегалних прелаза", "алтернативни пут", "административни прелаз",
                       "административна линија", "административне линије", "заплен", "мунициј",
                       "мердар"],
            "en": ["smuggl", "trafficking", "illegal crossing", "border crossing", "boundary line",
                   "administrative line", "weapons seized", "seized weapons", "ammunition",
                   "merdare", "contraband", "border police"],
        },
        "aktoret_tipike": ["krim_i_organizuar", "grupe_te_armatosura", "shteti_serb"],
        "shenjestrat_tipike": ["institucione", "ekonomi", "fsk"],
        # 2: kryesisht krim; rritet përmes aktorit/shkallës kur lidhet me armë për grupe
        "rrezikshmeria_baze": 2,
        "burimet_e_mbledhjes": [
            "Zyrtare: Policia Kufitare e Kosovës, Dogana, Prokuroria",
            "Media lokale dhe serbe (latin dhe cirilik)",
            "GDELT: kërkim 'smuggling' OR 'šverc' me Kosovo",
        ],
        "shembuj": [
            {"pershkrimi": "14 qershor 2023: forcat serbe ndalojnë tre policë të Kosovës pranë "
                           "kufirit; Kosova thotë se u rrëmbyen brenda Kosovës, Serbia thotë "
                           "brenda Serbisë.",
             "url": "https://www.aljazeera.com/news/2023/6/14/serbia-arrests-kosovo-police-officers-as-tensions-soar"},
        ],
    },
    "struktura_paralele": {
        "emri": "Struktura paralele në veri",
        "pershkrimi": "Institucione dhe shërbime të drejtuara nga Serbia që veprojnë jashtë "
                      "sistemit ligjor të Kosovës: komuna, posta, banka, zyra dokumentesh.",
        "fusha_hibride": ["Public Administration", "Political", "Legal", "Economy"],
        "treguesit": [
            "Zyra komunale, posta ose banka me licencë serbe pa regjistrim në Kosovë",
            "Lëshim dokumentesh ose targash nga zyrat paralele",
            "Pagesa në dinarë dhe transferime fondesh nga Beogradi",
            "Aksione policore për mbylljen e tyre dhe reagime nga Beogradi, BE ose SHBA",
            "Roli koordinues i Zyrës për Kosovën të Qeverisë së Serbisë",
        ],
        "fjale_kyce": {
            "sq": ["strukturat paralele", "strukturave paralele", "institucionet paralele",
                   "institucionet serbe", "institucioneve serbe", "posta e serbisë",
                   "dinarit", "zyra për kosovën",
                   "targa serbe", "targat serbe", "dokumente serbe", "letërnjoftime serbe"],
            "sr": ["paralelne institucije", "paralelnih institucija", "srpske institucije",
                   "srpskih institucija", "pošta srbije", "ukidanje dinara", "kancelarija za kosovo",
                   "kancelarije za kosovo", "privremeni organ", "privremenih organa", "srpske tablice",
                   "zatvaranje institucija"],
            "sr_cyr": ["паралелне институције", "паралелних институција", "српске институције",
                       "српских институција", "пошта србије", "укидање динара", "канцеларија за косово",
                       "канцеларије за косово", "привремени орган", "привремених органа", "српске таблице",
                       "затварање институција"],
            "en": ["parallel institution", "parallel structure", "serbian institutions",
                   "post of serbia", "serbian post", "dinar ban", "office for kosovo",
                   "provisional authorit", "temporary bodies", "serbian-run", "license plates",
                   "serbian documents"],
        },
        "aktoret_tipike": ["shteti_serb"],
        "shenjestrat_tipike": ["institucione", "komunitete", "ekonomi"],
        # 2: kërcënim afatgjatë për sovranitetin, rrallë dhunë e drejtpërdrejtë
        "rrezikshmeria_baze": 2,
        "burimet_e_mbledhjes": [
            "Zyrtare: Qeveria e Kosovës, MPB, Banka Qendrore; Zyra për Kosovën e Serbisë (kim.gov.rs)",
            "Media lokale dhe serbe (latin dhe cirilik)",
            "Deklarata të BE-së dhe ambasadave",
        ],
        "shembuj": [
            {"pershkrimi": "5 gusht 2024: policia mbyll nëntë zyra të Postës së Serbisë në veri; "
                           "BE dhe SHBA e kritikojnë si hap të njëanshëm.",
             "url": "https://www.rferl.org/a/kosovo-serb-post-raid-mitrovica-leposavic-zvecan/33066625.html"},
        ],
    },
    "diplomatik_ligjor": {
        "emri": "Presion diplomatik dhe ligjor",
        "pershkrimi": "Fushata kundër njohjeve dhe anëtarësimit të Kosovës në organizata "
                      "ndërkombëtare, dhe përdorimi i forumeve dhe fletarrestimeve kundër saj.",
        "fusha_hibride": ["Diplomacy", "Legal", "Political"],
        "treguesit": [
            "Tërheqje e njohjes së Kosovës nga ndonjë shtet",
            "Bllokim i anëtarësimit (Këshilli i Evropës, Interpol, UNESCO)",
            "Seanca të Këshillit të Sigurimit të OKB-së me akuza ndaj institucioneve ose FSK-së",
            "Fletarrestime ose padi serbe ndaj zyrtarëve ose pjesëtarëve të forcave të Kosovës",
            "Deklarata ruse ose kineze në OKB në mbështetje të Serbisë",
        ],
        "fjale_kyce": {
            "sq": ["çnjoh", "tërheqje e njohjes", "tërheqjen e njohjes", "anëtarësim",
                   "këshilli i evropës", "këshillit të evropës", "interpol", "unesco",
                   "këshilli i sigurimit", "këshillit të sigurimit", "rezoluta 1244", "fletarrest"],
            "sr": ["povlačenje priznanja", "povukla priznanje", "povukle priznanje", "savet evrope",
                   "saveta evrope", "savetu evrope", "unesko", "savet bezbednosti",
                   "saveta bezbednosti", "1244", "poternic", "članstv"],
            "sr_cyr": ["повлачење признања", "повукла признање", "повукле признање", "савет европе",
                       "савета европе", "савету европе", "унеско", "савет безбедности",
                       "савета безбедности", "1244", "потерниц", "чланств"],
            "en": ["derecogni", "withdrew recognition", "withdraw recognition", "council of europe",
                   "interpol", "unesco", "security council", "resolution 1244", "membership bid",
                   "arrest warrant", "non-recognition", "lobbying against"],
        },
        "aktoret_tipike": ["shteti_serb", "rusia", "kina"],
        "shenjestrat_tipike": ["institucione"],
        # 2: dëm politik afatgjatë, pa rrezik fizik të drejtpërdrejtë
        "rrezikshmeria_baze": 2,
        "burimet_e_mbledhjes": [
            "Zyrtare: Ministria e Punëve të Jashtme e Kosovës dhe e Serbisë, OKB, Këshilli i Evropës",
            "Media rajonale dhe ndërkombëtare",
            "GDELT: kërkim 'Kosovo recognition' OR 'Council of Europe' me Serbia",
        ],
        "shembuj": [
            {"pershkrimi": "Maj 2024: Ministria e Jashtme e Kosovës fajëson një fushatë lobimi "
                           "serbe pasi votimi për anëtarësim në Këshillin e Evropës shtyhet.",
             "url": "https://www.yahoo.com/news/kosovo-criticizes-council-europe-not-153006481.html"},
            {"pershkrimi": "Maj 2018: Ministri i Jashtëm i Serbisë deklaron se Serbia do të "
                           "kundërshtojë çdo përpjekje të Kosovës për t'u anëtarësuar në KiE.",
             "url": "https://n1info.rs/english/news/a389033-Dacic-says-Serbia-will-block-Kosovos-membership-in-Council-of-Europe/"},
        ],
    },
    "ekonomik_energjetik": {
        "emri": "Presion ekonomik dhe energjetik",
        "pershkrimi": "Përdorimi i tregtisë, energjisë dhe financave si mjet presioni, si bllokimi "
                      "i interkonjeksionit, ndalimi i mallrave ose investime strategjike të huaja.",
        "fusha_hibride": ["Economy", "Infrastructure", "Political"],
        "treguesit": [
            "Mosmarrëveshje KOSTT–EMS: kapacitet interkonjeksioni zero ose devijime frekuence",
            "Ndalim ose bllokim mallrash në pikat kufitare dhe kundërmasa",
            "Mospagesë ose ndërprerje e furnizimit me energji në veri",
            "Investime ose blerje strategjike nga kompani shtetërore ruse ose kineze në energji, "
            "telekom ose miniera në rajon",
        ],
        "fjale_kyce": {
            "sq": ["kostt", "interkonjeksion", "embargo", "mallrat serbe", "mallrave serbe",
                   "ndalimi i importit", "ndalim të importit", "kompani kineze", "kompanitë kineze",
                   "kompani ruse", "investime kineze", "furnizimi me energji"],
            "sr": ["elektromreža srbije", "elektromreže srbije", "interkonekcij", "embargo",
                   "zabrana uvoza", "zabranu uvoza", "srpska roba", "srpske robe",
                   "kineska kompanij", "kineske kompanij", "kineske investicij", "ruska kompanij"],
            "sr_cyr": ["електромрежа србије", "електромреже србије", "интерконекциј", "ембарго",
                       "забрана увоза", "забрану увоза", "српска роба", "српске робе",
                       "кинеска компаниј", "кинеске компаниј", "кинеске инвестициј",
                       "руска компаниј"],
            "en": ["kostt", "interconnector", "energy community", "embargo", "trade ban",
                   "import ban", "serbian goods", "chinese compan", "chinese investment",
                   "russian compan", "gazprom", "frequency deviation"],
        },
        "aktoret_tipike": ["shteti_serb", "rusia", "kina"],
        "shenjestrat_tipike": ["ekonomi", "infrastrukture_kritike"],
        # 2: presion i ngadaltë; rritet kur prek furnizimin me energji
        "rrezikshmeria_baze": 2,
        "burimet_e_mbledhjes": [
            "Zyrtare: Energy Community Secretariat, ENTSO-E, KOSTT, Banka Qendrore e Kosovës",
            "Media energjetike: Balkan Green Energy News",
            "Media rajonale (latin dhe cirilik)",
        ],
        "shembuj": [
            {"pershkrimi": "Korrik 2022: Sekretariati i Komunitetit të Energjisë hap procedurë "
                           "kundër Serbisë, sepse EMS mban kapacitet zero në dy linja me Kosovën.",
             "url": "https://energy-community.org/news/Energy-Community-News/2022/09/06a.html"},
        ],
    },
    "spiunazh_ndikim": {
        "emri": "Spiunazh dhe ndikim i huaj",
        "pershkrimi": "Mbledhje inteligjence nga shërbime të huaja (p.sh. BIA e Serbisë) dhe "
                      "ndikim përmes teknologjisë së mbikëqyrjes, rrjeteve politike e mediatike.",
        "fusha_hibride": ["Intelligence", "Political", "Cyber", "Culture"],
        "treguesit": [
            "Arrestime ose aktakuza për spiunazh në favor të BIA-s ose shërbimeve të tjera",
            "Mbledhje informacioni për FSK-në, policinë, zyrtarët ose infrastrukturën",
            "Rekrutim me pagesa, shantazh ose përmes rrjeteve sociale",
            "Teknologji kineze mbikëqyrjeje (Huawei Safe City, njohje fytyre) në Serbi",
            "Bashkëpunim i shërbimeve serbe me ato ruse",
            "Financim i mediave, organizatave ose partive nga burime të huaja",
        ],
        "fjale_kyce": {
            "sq": ["spiun", "agjencia e inteligjencës", "agjencisë së inteligjencës",
                   "shërbimet sekrete", "shërbimit sekret", "njohjes së fytyrës",
                   "njohje të fytyrës", "huawei", "safe city", "ndikimi rus", "ndikimi kinez"],
            "sr": ["špijun", "obaveštajn", "bezbednosno-informativn", "prepoznavanje lica",
                   "prepoznavanja lica", "masovni nadzor", "huavej", "ruski uticaj",
                   "ruskog uticaja", "kineski uticaj", "kineskog uticaja", "regrutovan"],
            "sr_cyr": ["шпијун", "обавештајн", "безбедносно-информативн", "препознавање лица",
                       "препознавања лица", "масовни надзор", "хуавеј", "руски утицај",
                       "руског утицаја", "кинески утицај", "кинеског утицаја", "регрутован"],
            "en": ["espionage", "spying", "spy ring", "intelligence agency",
                   "security information agency", "facial recognition", "surveillance", "huawei",
                   "safe city", "russian influence", "chinese influence", "spied"],
        },
        "aktoret_tipike": ["shteti_serb", "rusia", "kina"],
        "shenjestrat_tipike": ["fsk", "institucione", "shoqeri"],
        # 4: dëm i fshehur; informacioni për FSK-në dhe institucionet mund të përgatisë sulme
        "rrezikshmeria_baze": 4,
        "burimet_e_mbledhjes": [
            "Zyrtare: Prokuroria Speciale, Policia e Kosovës, gjykatat (vetëm rolet, pa emra privatë)",
            "Media: BIRN/Prishtina Insight, RFE/RL, Kallxo",
            "Raporte: KCSS, BCSP, CEP",
        ],
        "shembuj": [
            {"pershkrimi": "Maj 2025: Prokuroria Speciale arreston një të dyshuar për spiunazh në "
                           "favor të BIA-s, me informacione për institucionet e sigurisë.",
             "url": "https://prishtinainsight.com/kosovo-detains-a-suspected-spy-for-serbias-intelligence-agency/"},
            {"pershkrimi": "Gusht 2025: dokumente të rrjedhura tregojnë zgjerimin e sistemit "
                           "kinez të mbikëqyrjes Safe City (Huawei) në Serbi.",
             "url": "https://www.rferl.org/a/exclusive-safe-city-china-surveillance-huawei-facial-recognition/33501155.html"},
        ],
    },
    "ekstremizem_terrorizem": {
        "emri": "Ekstremizëm i dhunshëm dhe terrorizëm",
        "pershkrimi": "Radikalizim dhe planifikim sulmesh nga grupe ekstremiste fetare ose "
                      "etno-nacionaliste, përfshirë luftëtarët e kthyer nga zonat e konfliktit.",
        "fusha_hibride": ["Social/Societal", "Culture", "Information"],
        "treguesit": [
            "Arrestime për planifikim sulmesh; sekuestrim eksplozivi, armësh ose dronësh",
            "Propagandë ekstremiste ose thirrje për dhunë në rrjete sociale ose Telegram",
            "Kthim ose lirim i luftëtarëve të huaj",
            "Sulme ndaj objekteve fetare ose kulturore",
            "Shpallje e një organizate si terroriste nga Qeveria",
        ],
        "fjale_kyce": {
            "sq": ["terror", "ekstremist", "ekstremiz", "radikaliz", "isis", "shteti islamik",
                   "shtetit islamik", "luftëtarë të huaj", "luftëtarëve të huaj", "xhihad",
                   "kalifat", "objekte fetare"],
            "sr": ["teror", "ekstremist", "ekstremiz", "radikaliz", "isis", "islamska država",
                   "islamske države", "strani borci", "stranih boraca", "džihad", "kalifat",
                   "verski objekt"],
            "sr_cyr": ["терор", "екстремист", "екстремиз", "радикализ", "исис", "исламска држава",
                       "исламске државе", "страни борци", "страних бораца", "џихад", "калифат",
                       "верски објект"],
            "en": ["terror", "extremis", "radicali", "isis", "islamic state", "daesh",
                   "foreign fighter", "jihad", "caliphate", "returnee", "hate crime",
                   "religious site"],
        },
        "aktoret_tipike": ["grupe_ekstremiste", "grupe_te_armatosura"],
        "shenjestrat_tipike": ["shoqeri", "institucione", "kfor_nato", "komunitete"],
        # 4: rrezik për jetë, por rastet e njohura u ndaluan para sulmit
        "rrezikshmeria_baze": 4,
        "burimet_e_mbledhjes": [
            "Zyrtare: Prokuroria Speciale, Policia e Kosovës",
            "Media: BIRN/Prishtina Insight, Kallxo, Koha",
            "Raporte: KCSS, Europol TE-SAT",
        ],
        "shembuj": [
            {"pershkrimi": "Tetor 2021: policia arreston pesë të dyshuar për planifikim sulmesh "
                           "terroriste dhe sekuestron eksploziv, armë, dronë dhe armë antitank.",
             "url": "https://prishtinainsight.com/kosovo-police-arrests-five-suspects-for-plotting-terrorist-attacks/"},
        ],
    },
    "tjeter": {
        "emri": "Tjetër",
        "pershkrimi": "Ngjarje sigurie që s'përputhet me asnjë kategori tjetër; analisti e "
                      "rishikon dhe, nëse përsëritet, propozon kategori të re.",
        "fusha_hibride": [],
        "treguesit": [
            "Ngjarje sigurie pa lidhje të qartë me kategoritë e tjera",
            "Krim i zakonshëm pa lidhje me aktorë hibridë",
            "Aksident ose incident teknik",
            "Ngjarje që modeli s'e klasifikoi me siguri",
        ],
        "fjale_kyce": {"sq": [], "sr": [], "sr_cyr": [], "en": []},
        "aktoret_tipike": ["i_panjohur"],
        "shenjestrat_tipike": [],
        "rrezikshmeria_baze": 1,
        "burimet_e_mbledhjes": ["Të gjitha burimet ekzistuese"],
        "shembuj": [],
    },
}


def fjale_kyce_regex():
    """Të gjitha fjalët kyçe në një regex; përputhen në fillim të fjalës, pa dallim shkronjash."""
    fjalet = {f for k in KATEGORITE.values() for lista in k["fjale_kyce"].values() for f in lista}
    # Më të gjatat të parat, që "ushtria serbe" të fitojë para rrënjëve të shkurtra
    return re.compile(r"\b(?:" + "|".join(map(re.escape, sorted(fjalet, key=len, reverse=True)))
                      + ")", re.I)


def kategoria_valide(id):
    return id in KATEGORITE


def emri(id):
    """Emri i kategorisë; për ID të tjera kthen emrin e aktorit ose shenjestrës, ose vetë ID-në.
    Kujdes: "grupe_te_armatosura" dhe "infrastrukture_kritike" janë edhe aktor/shenjestër;
    për to përdor AKTORET[id] ose SHENJESTRAT[id] drejtpërdrejt."""
    if id in KATEGORITE:
        return KATEGORITE[id]["emri"]
    return AKTORET.get(id) or SHENJESTRAT.get(id) or str(id)


if __name__ == "__main__":
    ID = ["ushtarak_serbia", "grupe_te_armatosura", "dron_hapesire_ajrore", "kibernetik",
          "infrastrukture_kritike", "dezinformim", "trazira_bllokada", "kufi_kontrabande",
          "struktura_paralele", "diplomatik_ligjor", "ekonomik_energjetik", "spiunazh_ndikim",
          "ekstremizem_terrorizem", "tjeter"]
    assert list(KATEGORITE) == ID
    assert list(AKTORET) == ["shteti_serb", "grupe_te_armatosura", "krim_i_organizuar", "rusia",
                             "kina", "grupe_ekstremiste", "media_propagandistike", "i_panjohur"]
    assert list(SHENJESTRAT) == ["fsk", "infrastrukture_kritike", "institucione", "kfor_nato",
                                 "komunitete", "shoqeri", "ekonomi"]
    assert NIVELET == ["i lartë", "i mesëm", "i ulët"]
    assert PRIORITETET == ["URGJENTE", "RAPORT", "MONITORIM", "ARKIV"]
    assert len(FUSHAT_HIBRIDE) == 13

    # sr_cyr duhet të jetë transliterimi i saktë i sr (kap gabime shtypi në cirilik)
    CIR = dict(zip("абвгдђежзијклмнопрстћуфхцчш",
                   "a b v g d đ e ž z i j k l m n o p r s t ć u f h c č š".split()))
    CIR.update({"љ": "lj", "њ": "nj", "џ": "dž"})
    FUSHAT = {"emri", "pershkrimi", "fusha_hibride", "treguesit", "fjale_kyce", "aktoret_tipike",
              "shenjestrat_tipike", "rrezikshmeria_baze", "burimet_e_mbledhjes", "shembuj"}
    for id, k in KATEGORITE.items():
        assert set(k) == FUSHAT, id
        assert isinstance(k["rrezikshmeria_baze"], int) and 1 <= k["rrezikshmeria_baze"] <= 5, id
        assert set(k["fusha_hibride"]) <= set(FUSHAT_HIBRIDE), id
        assert k["aktoret_tipike"] and set(k["aktoret_tipike"]) <= set(AKTORET), id
        assert set(k["shenjestrat_tipike"]) <= set(SHENJESTRAT), id
        assert k["emri"] and k["pershkrimi"] and 4 <= len(k["treguesit"]) <= 6, id
        assert all(s["pershkrimi"] and s["url"].startswith("https://") for s in k["shembuj"]), id
        assert set(k["fjale_kyce"]) == {"sq", "sr", "sr_cyr", "en"}, id
        for gjuha, lista in k["fjale_kyce"].items():
            assert id == "tjeter" or 8 <= len(lista) <= 12, (id, gjuha)
            assert len(set(lista)) == len(lista), (id, gjuha)  # pa dyfishime
            assert all(f == f.lower().strip() and len(f) >= 3 for f in lista), (id, gjuha)
            # cirilikja pa shkronja latine, gjuhët e tjera pa shkronja cirilike
            alfabeti_tjeter = "[a-zčćđšžçë]" if gjuha == "sr_cyr" else "[абвгдђежзијклљмнњопрстћуфхцчџш]"
            assert not any(re.search(alfabeti_tjeter, f) for f in lista), (id, gjuha)
        latin = ["".join(CIR.get(c, c) for c in f) for f in k["fjale_kyce"]["sr_cyr"]]
        assert latin == k["fjale_kyce"]["sr"], (id, [p for p in zip(latin, k["fjale_kyce"]["sr"])
                                                     if p[0] != p[1]])
        assert id == "tjeter" or k["shembuj"], id

    r = fjale_kyce_regex()
    for t in ["Vojska Srbije podigla je borbenu gotovost", "ВОЈСКА СРБИЈЕ у копненој зони",
              "Dronë mbi kazermën e FSK-së", "DDoS attack on government websites",
              "Shpërthim në kanalin Ibër-Lepenc", "Sputnik Srbija: etničko čišćenje Srba",
              "Policia sekuestroi municion në veri", "Kosovo Police seized weapons near Jarinje",
              "Хакерски напад на сајт владе", "Pošta Srbije zatvorena u Zvečanu",
              "Arrested over ISIS propaganda", "Саботажа на каналу Ибар-Лепенац",
              "Policija demantovala vesti o napadu", "Një mjet shpërthyes pranë stacionit"]:
        assert r.search(t), t
    for t in ["The crisis in the Middle East", "Festivali i filmit në Prizren",
              "Gatishmëria për dialog", "Arsenal fitoi ndeshjen", "A suave new restaurant",
              "Koncert u Beogradu", "Ekstremisht nxehtë sot në Prishtinë",
              "Cene goriva više za tri dinara po litru"]:
        assert not r.search(t), (t, r.search(t))

    assert kategoria_valide("dezinformim") and kategoria_valide("tjeter")
    assert not kategoria_valide("Dezinformim") and not kategoria_valide(None)
    assert emri("dezinformim") == "Dezinformim dhe manipulim informativ"
    assert emri("rusia") == AKTORET["rusia"] and emri("fsk") == SHENJESTRAT["fsk"]
    assert emri("panjohur_fare") == "panjohur_fare"
    print(f"Kontrollet kaluan: {len(KATEGORITE)} kategori, "
          f"{len(r.pattern.split('|'))} fjalë kyçe unike.")
