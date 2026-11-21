# Modeli i kërcënimit: taksonomia, rreziku dhe kodi Admiralty

Dokument për `kercenimet.py`, `rreziku.py` dhe `kontekst_dezinformim.burimet_e_dezinformimit()`.
Gjithçka këtu llogaritet me rregulla të qarta, pa model. Analisti njeri vendos gjithmonë.

## 1. Qëllimi dhe korniza

Mentorët kërkuan një fokus të vetëm: kërcënimet hibride nga Serbia, dhe lidhjet me Rusinë e Kinën, ndaj FSK-së dhe sigurisë së Kosovës. Kërkuan:
- listë kërcënimesh të kategorizuar;
- mbledhje sipas kërcënimeve;
- një rrezikshmëri të matur: i lartë, i mesëm ose i ulët.

`kercenimet.py` është burimi i vetëm i së vërtetës për kategoritë, aktorët, shenjestrat, nivelet dhe prioritetet. E përdorin extractor (C), collector (B), rreziku dhe dashboard/raporti (D).

**Korniza:** modeli konceptual i JRC dhe Hybrid CoE (2021, EUR 30585 EN), me 13 fusha. Emrat e tyre origjinalë ruhen te `FUSHAT_HIBRIDE`: Infrastructure, Cyber, Space, Economy, Military/Defence, Culture, Social/Societal, Public Administration, Legal, Intelligence, Diplomacy, Political, Information.
- https://publications.jrc.ec.europa.eu/repository/handle/JRC123305
- https://www.hybridcoe.fi/publications/the-landscape-of-hybrid-threats-a-conceptual-model/

**Për Kosovën:** KCSS, *Dealing with Hybrid Threats in Kosovo* (2025), plus raportet e medias me URL te shembujt.

## 2. Kategoritë (14)

`rrezikshmeria_baze` (1–5) është gjykim i ekipit dhe arsyeja shkruhet në kod. Validohet me mentorin dhe me ish-ushtarakun (G7).

| ID | Emri | Baza | Arsyeja e bazës | Fushat JRC | Aktorët tipikë | Shenjestrat tipike | Shembull |
|---|---|---|---|---|---|---|---|
| `ushtarak_serbia` | Aktivitet ushtarak i Serbisë | 5 | Kërcënim konvencional; në shtator 2023 SHBA e quajti grumbullimin "të paparë" | Military/Defence, Diplomacy, Political | shteti_serb, rusia, kina | fsk, kfor_nato, institucione | [Al Jazeera, shtator 2023](https://www.aljazeera.com/news/2023/9/30/us-concerned-by-large-serbian-military-mobilisation-near-kosovo) |
| `grupe_te_armatosura` | Grupe të armatosura dhe paraushtarake | 5 | Sulm me viktima (Banjskë, shtator 2023) dhe arsenal i mbetur në veri | Military/Defence, Intelligence, Social/Societal | grupe_te_armatosura, shteti_serb, krim_i_organizuar | institucione, kfor_nato, fsk, komunitete | [Al Jazeera, shtator 2023](https://www.aljazeera.com/news/2023/9/24/one-police-officer-killed-in-kosovo-attack-blamed-on-serbia) |
| `dron_hapesire_ajrore` | Dronë dhe shkelje të hapësirës ajrore | 4 | Tregues i hershëm para sulmit mbi FSK-në dhe infrastrukturën kritike; mentorët e veçuan | Military/Defence, Intelligence, Infrastructure | shteti_serb, grupe_te_armatosura, i_panjohur | fsk, infrastrukture_kritike, kfor_nato, institucione | [N1, shtator 2025](https://n1info.rs/vesti/sveclja-srpski-dronovi-prelecu-kosovo/) |
| `kibernetik` | Sulme kibernetike | 3 | DDoS-et e njohura ishin ndërprerje të përkohshme; rritet kur prek energjinë ose FSK-në | Cyber, Infrastructure, Public Administration, Information | rusia, shteti_serb, krim_i_organizuar, i_panjohur | institucione, infrastrukture_kritike, fsk, ekonomi | [The Record, maj 2024](https://therecord.media/russian-hackers-kosovo-ddos-pristina) |
| `infrastrukture_kritike` | Sabotim i infrastrukturës kritike | 5 | Nëntor 2024: kanali që furnizon termocentralet u dëmtua nga shpërthimi | Infrastructure, Economy, Social/Societal | grupe_te_armatosura, shteti_serb, i_panjohur | infrastrukture_kritike, ekonomi, shoqeri | [Al Jazeera, nëntor 2024](https://www.aljazeera.com/news/2024/11/30/kosovo-pm-blames-serbia-for-explosion-at-canal-supplying-power-plants) |
| `dezinformim` | Dezinformim dhe manipulim informativ | 3 | Rrallë dëm i drejtpërdrejtë, por përgatit terrenin për trazira; rritet pranë incidenteve | Information, Political, Social/Societal, Culture | media_propagandistike, rusia, shteti_serb | shoqeri, fsk, kfor_nato, institucione, komunitete | [Prishtina Insight, 2025](https://prishtinainsight.com/russian-controlled-media-flood-kosovos-information-space-with-disinformation-mag/) |
| `trazira_bllokada` | Trazira, barrikada dhe bllokada | 4 | Maj 2023 në Zveçan: dhjetëra ushtarë të KFOR-it të plagosur | Social/Societal, Political, Public Administration | shteti_serb, grupe_te_armatosura, i_panjohur | kfor_nato, institucione, komunitete | [PBS/AP, maj 2023](https://www.pbs.org/newshour/world/25-nat0-led-peacekeepers-injured-in-kosovo-amid-ethnic-tensions) |
| `kufi_kontrabande` | Kufiri, kontrabanda dhe trafikimi | 2 | Kryesisht krim; rritet përmes aktorit dhe shkallës kur lidhet me armë për grupe | Military/Defence, Economy, Legal | krim_i_organizuar, grupe_te_armatosura, shteti_serb | institucione, ekonomi, fsk | [Al Jazeera, qershor 2023](https://www.aljazeera.com/news/2023/6/14/serbia-arrests-kosovo-police-officers-as-tensions-soar) |
| `struktura_paralele` | Struktura paralele në veri | 2 | Kërcënim afatgjatë për sovranitetin, rrallë dhunë e drejtpërdrejtë | Public Administration, Political, Legal, Economy | shteti_serb | institucione, komunitete, ekonomi | [RFE/RL, gusht 2024](https://www.rferl.org/a/kosovo-serb-post-raid-mitrovica-leposavic-zvecan/33066625.html) |
| `diplomatik_ligjor` | Presion diplomatik dhe ligjor | 2 | Dëm politik afatgjatë, pa rrezik fizik të drejtpërdrejtë | Diplomacy, Legal, Political | shteti_serb, rusia, kina | institucione | [AP/Yahoo, maj 2024](https://www.yahoo.com/news/kosovo-criticizes-council-europe-not-153006481.html) |
| `ekonomik_energjetik` | Presion ekonomik dhe energjetik | 2 | Presion i ngadaltë; rritet kur prek furnizimin me energji | Economy, Infrastructure, Political | shteti_serb, rusia, kina | ekonomi, infrastrukture_kritike | [Energy Community, 2022](https://energy-community.org/news/Energy-Community-News/2022/09/06a.html) |
| `spiunazh_ndikim` | Spiunazh dhe ndikim i huaj | 4 | Dëm i fshehur; informacioni për FSK-në dhe institucionet mund të përgatisë sulme | Intelligence, Political, Cyber, Culture | shteti_serb, rusia, kina | fsk, institucione, shoqeri | [Prishtina Insight, maj 2025](https://prishtinainsight.com/kosovo-detains-a-suspected-spy-for-serbias-intelligence-agency/) |
| `ekstremizem_terrorizem` | Ekstremizëm i dhunshëm dhe terrorizëm | 4 | Rrezik për jetë, por rastet e njohura u ndaluan para sulmit | Social/Societal, Culture, Information | grupe_ekstremiste, grupe_te_armatosura | shoqeri, institucione, kfor_nato, komunitete | [Prishtina Insight, tetor 2021](https://prishtinainsight.com/kosovo-police-arrests-five-suspects-for-plotting-terrorist-attacks/) |
| `tjeter` | Tjetër | 1 | Vlera e paracaktuar, pa fjalë kyçe dhe pa shembuj | – | i_panjohur | – | – |

- **Aktorët (8):** shteti_serb, grupe_te_armatosura, krim_i_organizuar, rusia, kina, grupe_ekstremiste, media_propagandistike, i_panjohur.
- **Shenjestrat (7):** fsk, infrastrukture_kritike, institucione, kfor_nato, komunitete, shoqeri, ekonomi.
- "grupe_te_armatosura" dhe "infrastrukture_kritike" janë njëkohësisht kategori dhe aktor/shenjestër. Për aktorin dhe shenjestrën përdoret `AKTORET[id]` / `SHENJESTRAT[id]`, sepse `emri(id)` kthen emrin e kategorisë.
- Atribuimi i kontestuar shkruhet "sipas ...". Për Banjskën dhe Ibër-Lepencin: Kosova akuzon, Serbia mohon.

## 3. Fjalët kyçe

**Si përputhen:**
- `fjale_kyce_regex()` bashkon të gjitha fjalët kyçe në një regex, pa dallim shkronjash.
- Fjalët janë **rrënjë** dhe përputhen vetëm **në fillim të fjalës** (`\b`), që "isis" të mos kapë "crisis".
- Më të gjatat provohen të parat, ndaj "ushtria serbe" fiton para rrënjëve të shkurtra.
- `sr_cyr` është transliterimi i saktë i `sr`, dhe kontrollohet te `__main__`.
- Çdo listë ka 8–12 fjalë, përveç "tjeter", që s'ka asnjë.
- Regex-i NUK i ka fjalët e përgjithshme të krimit ("polic", "vras", "arrest"). Extractor-i e bashkon me OR me `extractor.FJALE_KYCE`.

**Çfarë u provua:**
- **Gold (36 artikuj, para shtesës së C-së):** 24/26 artikuj sigurie kapen; mungojnë g10 dhe g11. Kapet edhe 1 nga 10 artikuj pa ngjarje sigurie. Numrat janë me 576 fjalë kyçe.
- Rifut provën pas bashkimit të gold-it të ri.
- **Të dhënat reale** (`osint.db`, 702 artikuj, vetëm lexim, 2026-11-21):
  - "paralel" kapte 5 nga 5 gabim ("paralelisht", "paralelno"), ndaj u zëvendësua me "strukturat paralele", "strukturave paralele", "institucionet paralele", "paralelne institucije" dhe "paralelnih institucija".
  - U hoqën "mbikëqyrj", "narrativ", "mobilizim", "përplasje" dhe "sukob", sepse kapnin kryesisht lajme pa lidhje me sigurinë. Numri ra 581 → 576.

**Fjalët e dyshimta që mbetën:**
- "protest" (46 raste, shumë protesta sociale);
- "teror" (sr: edhe "teror nad prirodom");
- "demant" (e kërkon assert-i "Policija demantovala vesti o napadu");
- "anëtarësim" / "članstv" (integrimi në BE).

Mbetën sepse janë rrënjë kryesore të kategorive të tyre. Kalibrohen pas etiketimit.

**I paverifikuar:** drejtshkrimi serb latin "ransomver", "malver", "fišing", "huavej" dhe "sputnjik" s'është krahasuar me mediat reale.

## 4. Rreziku (`rreziku.py`)

**Rreziku ≠ besueshmëri.**
- **Besueshmëria** (`scoring.py`, 0–1) = sa gjasa ka që ngjarja të jetë e vërtetë.
- **Rreziku** (0–100, kurrë me "%") = sa e rëndë do ishte ngjarja për FSK-në dhe sigurinë **nëse** është e vërtetë.

Të dy numrat nuk përzihen kurrë. Prioriteti del nga kryqëzimi i tyre.

**Formula:** pikët = shuma e faktorëve, e kufizuar në 0..100. Çdo faktor që jep pikë shkruhet si arsye ("... → +p").

| Faktori | Pikët |
|---|---|
| Kategoria | 8 × `rrezikshmeria_baze` (8–40). Kur kategoria mungon ose është "tjeter", baza merret nga `events.lloji` i vjetër (`LLOJI_RB`) |
| Shenjestra | Maksimumi, jo shuma: fsk 15, infrastrukture_kritike 12, kfor_nato 12, institucione 8, komunitete 6, ekonomi 4, shoqeri 3. Me `lidhje_me_fsk` dhe pa shenjestër më të lartë: 10 |
| Aktori | shteti_serb 10, grupe_te_armatosura 10, rusia 8, grupe_ekstremiste 7, kina 5, krim_i_organizuar 5, media_propagandistike 3 |
| Shkalla (maks. 15) | ≥1 i vdekur +10, ≥3 +3; ≥1 i plagosur +4, ≥5 +2; ≥1 i arrestuar +2 |
| Vendi (maks. 8) | +6 zonë e ndjeshme (veriu, pikat kufitare, komunat serbe ngjitur); +4 objekt kritik i përmendur (digë, nënstacion, kanal, kazermë...) |
| Koha | ≤1 ditë +7; ≤7 ditë +3 |
| Trendi (maks. 10) | +5 nëse ka ≥2 ngjarje të tjera të së njëjtës kategori në 7 ditë; +5 nëse ka ≥3 zona brenda ±1 dite |

**Pragjet:** i lartë ≥55, i mesëm ≥35, përndryshe i ulët.

**Ngjarjet rajonale pa lidhje me Kosovën** (`rajonale: True`, vendi jashtë zonave të ndjeshme, pa `lidhje_me_fsk`, pa shenjestër fsk/kfor_nato/institucione/infrastrukture_kritike) kufizohen te "i mesëm" (pikët kufizohen në 54). Arsyeja që shtohet: "rajonale pa lidhje të drejtpërdrejtë me Kosovën → maksimumi i mesëm". Pa këtë rregull, "Urgjente" mbushet me lajme të brendshme serbe.

**Brezat e besueshmërisë:**
- e lartë: ≥0.80, ose analisti e konfirmoi;
- e mesme: 0.50–0.79;
- e ulët: <0.50, ose mungon.

**Matrica e prioritetit:**

| Niveli \ besueshmëria | e lartë | e mesme | e ulët |
|---|---|---|---|
| i lartë | URGJENTE | URGJENTE | URGJENTE |
| i mesëm | RAPORT | RAPORT | MONITORIM |
| i ulët | MONITORIM | ARKIV | ARKIV |

- Analisti "e hedhur poshtë" → ARKIV.
- Rreshti i fundit i arsyeve dallon "URGJENTE për veprim" (besueshmëria ≥0.80 ose "e konfirmuar") nga "URGJENTE për verifikim, jo për veprim": kontrolloje menjëherë, mos vepro ende.

**Shembujt nga `__main__`** (sot = 2026-11-21):

| | Ngjarja (vendi, besueshmëria) | Pikët | Niveli | Prioriteti | Kodi |
|---|---|---|---|---|---|
| T1 | Njësi të ushtrisë serbe pranë vijës (Raška, 0.94) | 78 | i lartë | URGJENTE | B1 |
| T2 | Grup i armatosur sulmon patrullën te Banjska, 1 i vdekur (Zvečan, 0.79) | 85 | i lartë | URGJENTE (për verifikim) | B3 |
| T3 | Kanal Telegram pretendon kalim trupash serbe te Jarinja (0.40) | 78 | i lartë | URGJENTE (për verifikim) | F6 |
| T4 | DDoS rrëzon faqet e qeverisë (Prishtina, 0.80) | 35 | i mesëm | RAPORT | B2 |
| T5 | Pretendime të rreme se FSK përgatit sulm (pa vend, 0.40) | 54 | i mesëm | MONITORIM | E3 |
| T6 | Arrestim për kontrabandë cigaresh (Podujevo, 0.80) | 33 | i ulët | MONITORIM | B2 |
| T7 | Aksident trafiku (Prizren, 0.40) | 8 | i ulët | ARKIV | F6 |
| T8 | Si T1, por analisti e hodhi poshtë | 78 | i lartë | ARKIV | B5 |
| T9 | Dron i paidentifikuar mbi digën e Gazivodës, analisti e konfirmoi (Zubin Potok, 0.54) | 59 | i lartë | URGJENTE | B1 |
| T10 | Shpërthim në nënstacion, pa K3, baza nga `lloji` (Mitrovicë e Veriut, 0.86) | 47 | i mesëm | RAPORT | B1 |
| T11 | Barrikada në rrugë kryesore, 3 zona njëkohësisht (Zubin Potok, 0.62) | 63 | i lartë | URGJENTE (për verifikim) | B1 |
| T12 | Paradë ushtarake në Beograd, rajonale (0.90) | 54 | i mesëm | RAPORT | B1 |

## 5. Kodi Admiralty (NATO)

Dy boshte të pavarura: besueshmëria e **burimit** (shkronja) dhe vërtetësia e **informacionit** (shifra).
- Emrat vijnë nga JDP 2-00, Tabela 3.1, dhe kuptimi nga FM 2-22.3, Shtojca B.
- AJP-2.1 dhe STANAG 2511 s'janë publike.

| Burimi | Kuptimi | Informacioni | Kuptimi |
|---|---|---|---|
| A | Plotësisht i besueshëm (Completely reliable) | 1 | I konfirmuar nga burime të tjera (Confirmed) |
| B | Zakonisht i besueshëm (Usually reliable) | 2 | Ndoshta i vërtetë (Probably true) |
| C | Mjaft i besueshëm (Fairly reliable) | 3 | Mundësisht i vërtetë (Possibly true) |
| D | Zakonisht jo i besueshëm (Not usually reliable) | 4 | I dyshimtë (Doubtful) |
| E | I pabesueshëm (Unreliable) | 5 | I pamundshëm (Improbable) |
| F | S'mund të gjykohet (Reliability cannot be judged) | 6 | S'mund të gjykohet (Truth cannot be judged) |

**Rregullat tona për shkronjën:**
- ≥3 raste EUvsDisinfo për domenin → E.
- Medium që s'është te `scoring.MEDIAT` → F.
- Sipas vlerës te `scoring.MEDIAT`: ≥0.80 → B; ≥0.60 → C; ndryshe D.
- Telegram/YouTube, ose 1–2 raste EUvsDisinfo → jo më lart se D.
- Shkronja e ngjarjes është më e mira sipas renditjes B > C > D > F > E.

**Pse s'ka kurrë "A":** "A" kërkon histori të gjatë të verifikuar të burimit. Sistemi automatik për burime të hapura s'e ka atë provë, ndaj e jep vetëm njeriu.

**Shifra:**
- Analisti: e hedhur poshtë → 5, e konfirmuar → 1.
- ≥2 media të pavarura dhe 0 kontradikta:
  - 1, nëse ka ≥2 gjuhë ose ≥3 media;
  - përndryshe 2.
- 1 kontradiktë → 3; ≥2 kontradikta → 4.
- 1 burim + rast i ngjashëm te konteksti → 3.
- Ndryshe → 6.

Besueshmëria NUK hyn te shifra, që boshtet të mbeten të pavarura (JDP 2-00 §3.39c).

**Raportimi rrethor:** të gjitha kanalet sociale numërohen si një burim, sepse shpesh janë ripostime të njëri-tjetrit. Kështu një lajm që qarkullon në 10 kanale Telegram s'merr "1".

**F6 ≠ pa vlerë:** një burim i panjohur me rrezik të lartë (T3) del "URGJENTE për verifikim". Analisti e kontrollon menjëherë, por s'vepron derisa të konfirmohet.

## 6. Përkufizimet për etiketuesit

Përkufizimet për gold-in e C-së dhe për etiketimin offline të rrezikut (30 ngjarje, shih docs/validimi.md të D-së):
- **i lartë:** dëm i rëndë për FSK-në, infrastrukturën kritike ose rendin publik, ose veprim armiqësor i armatosur ose shtetëror.
- **i mesëm:** dëm serioz, por i kufizuar ose i tërthortë (p.sh. fushatë dezinformimi kundër FSK-së, bllokadë).
- **i ulët:** dëm i kufizuar (krim rutinë, incident i izoluar).

Etiketuesit vendosin pa parë output-in e sistemit. Etiketat përdorin saktësisht vargjet e `NIVELET` ("i lartë", "i mesëm", "i ulët", me "ë").

## 7. Kalibrimi pa mbipërshtatje

- Peshat e faktorëve nuk rregullohen sipas etiketave. Rregullohen vetëm pragjet, në rrjetin `PRAGU_LARTE` ∈ {50, 55, 60, 65} dhe `PRAGU_MESEM` ∈ {30, 35, 40, 45}, me leave-one-group-out (një ngjarje = një grup artikujsh).
- Pragu ndryshohet vetëm nëse fiton ≥2 ngjarje dhe recall-i i URGJENTE s'bie.
- Raportohen numra bruto + interval Wilson 95%: p.sh. 4/5 → [0.38, 0.96]; 9/10 → [0.60, 0.98].
- Gold-i është sintetik, ndaj numrat tregojnë drejtimin, jo saktësinë në terren.
- Shpërndarja te të dhënat reale (2026-11-21, 15 ngjarje, para K3): 14 i ulët/ARKIV, 1 i mesëm/MONITORIM, 0 URGJENTE. S'ka gjetje për kalibrim.

## 8. Burimet që përhapin kërcënimet (G6)

**Lista nga të dhënat:**
- `kontekst_dezinformim.burimet_e_dezinformimit()` e ndërton listën nga rastet EUvsDisinfo për Kosovën dhe rajonin (`data/euvsdisinfo.csv`).
- Tabela gjenerohet kur CSV-ja të jetë në repo-n lokal; më 2026-11-21 CSV-ja mungonte në këtë kompjuter, ndaj tabela s'është gjeneruar ende.
- Kanalet sociale grupohen sipas platformës, pa emra llogarish. Mediat pa domen grupohen te "pa domen (të tjera)".

**Shënim nga EUvsDisinfo:** një rast në databazë nuk do të thotë që media është e lidhur me Kremlinin. Rasti tregon vetëm që ajo publikoi një pretendim të dokumentuar si dezinformim.

**Mostra e kërkimit** (80 raste për "Kosovo", lexuar 2026-11-21). Është MOSTËR, jo listë e plotë:
- **Mediat:** Sputnik 27, RT 20, media shtetërore ruse 11, News Front 9, kanale YouTube 7, rrjeti "Pravda" 3, Telegram 3, media serbe/malazeze nga 1–2 secila.
- **Platformat:** web 155, YouTube 7, Telegram 6, VK 2, X 1, Facebook 0.

**Kufizimet e mbledhjes:**
- Sputnik dhe RT janë nën sanksionet e BE-së për transmetim. Monitorohen vetëm përmes EUvsDisinfo/GDELT, pa ripublikim.
- Mbledhja automatike nga Telegram NUK bëhet, sepse kushtet e Telegram-it ndalojnë scraping-un dhe përdorimin me AI (https://telegram.org/tos/content-licensing). Kanalet i ndjek me dorë analisti.

**Lista e kanaleve Telegram për ndjekje manuale:** listë në pritje të miratimit.

## 9. Boshllëqet dhe të paverifikuarat

- **Sputnik Srbija dhe RT Balkan:** domenet s'u hapën nga rrjeti ynë (DNS).
- **KoSSev dhe Kosovo Online:** kthejnë 403 për skriptet, por RSS-i i tyre punon.
- **Krypometri:** rruga e tij te kallxo.com kthen 404.
- **EUvsDisinfo dhe KFOR:** faqet e rasteve kthejnë 403 për botët. Për Zveçanin u përdor PBS/AP.
- **Dronët:** shembulli i vetëm është deklaratë e ministrit (shtator 2025). KFOR më herët ka thënë se s'ka identifikuar shkelje, por ai burim s'u hap.
- **Ekstremizmi:** shembulli më i ri i verifikuar është i 2021-shit.
- **Banjska dhe Ibër-Lepenci:** Kosova akuzon, Serbia mohon.
- **Gjykim i ekipit, për t'u validuar (G7):** `rrezikshmeria_baze`, `fusha_hibride` për çdo kategori, peshat dhe pragjet e rrezikut.
- **Supozime te `rreziku.py`:**
  - fqinjësia e Rashkës, Kurshumlisë, Medvegjës, Bujanocit dhe Preshevës me Kosovën;
  - lista `OBJEKTE` është fillestare;
  - "mitrovic" përfshin edhe jugun.
- **Kolona e mediave te CSV-ja e EUvsDisinfo:** emri real s'është verifikuar. Funksioni pranon "outlets", "outlet", "mediaoutlets" dhe "media".
- **CM-400AKG:** u verifikua (N1, duke cituar Reuters-in, 13.03.2026): https://n1info.rs/vesti/rojters-srbija-cm-400akg-kineske-rakete/

**Regjistri i ndryshimeve të peshave dhe pragjeve:**

| Data | Ndryshimi | Arsyeja |
|---|---|---|
| 2026-11-21 | `dron_hapesire_ajrore` 3→4, `kufi_kontrabande` 3→2 (nga drafti i kërkimit) | Rastet e testit japin rezultate të arsyeshme: dron mbi digë i konfirmuar = URGJENTE; arrestim kontrabande cigaresh = i ulët |
| 2026-11-21 | Fjalët kyçe 581 → 576 (pa ndryshim peshash) | Prova te të dhënat reale; shih §3 |
| 2026-11-21 | Ngjarjet rajonale pa lidhje me Kosovën: maksimumi "i mesëm" (pikët ≤54); rasti i ri T12 | Pa këtë, "Urgjente" mbushet me lajme të brendshme serbe; T1–T11 s'ndryshuan |

## 10. Burimet

- JRC / Hybrid CoE (2021), *The Landscape of Hybrid Threats: A Conceptual Model*, EUR 30585 EN, doi:10.2760/44985:
  - https://publications.jrc.ec.europa.eu/repository/handle/JRC123305
  - https://www.hybridcoe.fi/publications/the-landscape-of-hybrid-threats-a-conceptual-model/
- KCSS, *Secure Future Series No. 3: Dealing with Hybrid Threats in Kosovo* (2025): https://qkss.org/en/publikimet/secure-future-series-no-3-dealing-with-hybrid-threats-in-kosovo-and-potential-for-improvement
- UK MOD, *JDP 2-00*, bot. 4, gusht 2023: §3.39–3.40, Tabela 3.1; §3.47, Tabela 3.2 (PHIA); §3.51 shënimi 53. https://assets.publishing.service.gov.uk/media/653a4b0780884d0013f71bb0/JDP_2_00_Ed_4_web.pdf
- HQDA, *FM 2-22.3* (2006), Shtojca B, Tabelat B-1/B-2: https://maint.loc.gov/law/mlr/pdf/human-intell-collector-operations.pdf
- UN DPO, *Guidelines: Open-Source Peacekeeping-Intelligence (OPKI)* (2022): §14.1–14.3, §16.1.
- NIST SP 800-30 Rev. 1 (2012): §2.3.2; Tabelat D-3/D-4/D-5, H-3, I-2, I-3. https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-30r1.pdf
- ODNI, *ICD 203* (2015): https://archive.dni.gov/files/documents/ICD/ICD-203.pdf
- Cox (2008), "What's Wrong with Risk Matrices?", *Risk Analysis* 28(2), doi:10.1111/j.1539-6924.2008.01030.x
- Kelly, Budescu, Dhami & Mandel (2025), *Judgment and Decision Making* 20, e36, doi:10.1017/jdm.2025.10007
- Irwin & Mandel (2019), *Intelligence and National Security* 34(4), doi:10.1080/02684527.2019.1569343. U lexua vetëm përmbledhja.
- CEP, "Echoes of Moscow" (2024): https://cep.org.rs/en/publications/echoes-of-moscow-russian-telegramnetwork-in-serbia/
- Telegram, Content Licensing and AI Scraping Terms: https://telegram.org/tos/content-licensing
- Shembujt me URL te `kercenimet.py`: 19 artikuj nga Al Jazeera, Defense News, RFE/RL, N1, The Record, Prishtina Insight, PBS/AP, AP/Yahoo dhe Energy Community. Të gjithë kthyen HTTP 200 më 2026-11-21.
