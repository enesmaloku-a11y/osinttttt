# OSINT Kosova: prototip

Prototip për sfidën **01 · AI-Powered OSINT & Hybrid Threat Intelligence** (EDTH Prishtina 2026), nga ekipi **The Silent Fixers**.

Fokusi: **kërcënimet hibride ndaj FSK-së dhe sigurisë së Kosovës, sidomos nga Serbia.** Sistemi mbledh lajme në shqip, serbisht dhe anglisht, nxjerr ngjarjet e sigurisë dhe i klasifikon sipas taksonomisë së kërcënimeve, bashkon raportimet e së njëjtës ngjarje nga burime dhe gjuhë të ndryshme, i rendit sipas **rrezikut** dhe **besueshmërisë** në **Urgjente** dhe **Raporte**, dhe i tregon analistit me burime, kronologji, kod NATO Admiralty, boshllëqe informacioni dhe raport ditor. **Analisti vendos gjithmonë; sistemi vetëm sugjeron.**

## Si punon

| Hapi | Skedari | Çfarë bën |
|---|---|---|
| 1 | `collector.py` | Mbledh artikuj nga RSS dhe GDELT, pa dublikatë, dhe filtron ata pa lidhje me Kosovën ose sigurinë (burimet më poshtë) |
| 2 | `processor.py` | Heq email-et dhe telefonat, përkthen në anglisht me model lokal |
| 3 | `extractor.py` | Filtër me fjalë kyçe, pastaj modeli nxjerr ngjarjen si JSON (kategoria, aktori, shenjestra, lidhja me FSK); emrat e personave maskohen |
| 4 | `correlator.py` | Bashkon artikujt e së njëjtës ngjarje (lloji, data, vendi, ngjashmëria) dhe gjen boshllëqet |
| 5 | `kontekst_*.py` | Konteksti i jashtëm: raste të ngjashme nga EUvsDisinfo dhe EuRepoC |
| 6 | `scoring.py` | Besueshmëria: rregulla të qarta, ose modeli i kalibruar (`trajno.py`) kur ka vendime të analistit; jo nga LLM-i |
| 7 | `rreziku.py` | Rreziku 0–100 me rregulla, prioriteti (URGJENTE/RAPORT/MONITORIM/ARKIV) dhe kodi NATO Admiralty |
| - | `kercenimet.py` | Taksonomia: 14 kategori kërcënimesh hibride, aktorët, shenjestrat, fjalët kyçe sq/sr/en |
| - | `raporti.py` | Raporti ditor një faqe: BLUF, Urgjente, Raporte, trendet, boshllëqet, burimet |
| - | `dashboard.py` | Pamja e analistit: Përmbledhja (rrezik × besueshmëri, Serbia, zonat), Urgjente, Raporte, harta, kronologjia, taksonomia, burimet, vlerësimi |
| - | `db.py` | Ruajtja në SQLite (`osint.db`) |

**Burimet RSS (`FEEDS` te `collector.py`):** RTK, Koha, Kallxo, Telegrafi, Gazeta Express, N1 Serbia, Balkan Insight, Hibrid.info, Policia e Kosovës, RTS, Kosovo Online, KoSSev, Novosti (rubrika Politika), Danas, RSE (edicioni "Kosovo" i Radio Evropa e Lirë), Informer (rubrika Politika) dhe MO Srbije (Ministria e Mbrojtjes së Serbisë, burim zyrtar). Mediat nga Serbia pranohen vetëm kur përmendin Kosovën ose FSK-në (edhe si "KBS"/"КБС"); MO Srbije edhe për aktivitet ushtarak ose dronë. GDELT plotëson me kërkime sipas kategorive.

Modeli gjuhësor punon **lokalisht** përmes [Ollama](https://ollama.com), kështu që asnjë e dhënë nuk dërgohet te shërbime të jashtme.

## Instalimi (Windows PowerShell)

Kërkohet Python 3.11+ dhe Ollama.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
ollama pull deepseek-r1:8b
```

Modeli ndryshohet te `MODELI` në `processor.py`.

## Përdorimi

```powershell
ollama serve                          # në një dritare tjetër, nëse Ollama s'po punon
python main.py                        # mbledh dhe përpunon deri në 20 artikuj
python main.py 50                     # deri në 50
python -m streamlit run dashboard.py
python raporti.py                     # raporti ditor te raportet/ (e bën edhe main.py në fund)
```

### Demo pa Ollama dhe pa internet

```powershell
python demo.py                                              # krijon demo.db në dosjen aktuale
$env:OSINT_DB="demo.db"; python -m streamlit run dashboard.py
```

`demo.py` mbush bazën me 63 artikujt sintetikë të `eval/gold.jsonl` (28 ngjarje, 5 urgjente). S'shkruan kurrë te `OSINT_DB` dhe s'mbishkruan asnjë skedar: nëse `demo.db` ekziston, e lë të paprekur dhe kërkon shteg tjetër (`python demo.py demo2.db`). Baza ndërtohet në skedar të përkohshëm dhe del me emrin përfundimtar vetëm pasi kontrollet kalojnë.

### Kontrollet në Windows

```powershell
python kontrollo.py                   # 20 kontrolle, pa Ollama dhe pa rrjet
python collector.py --kontrollo
```

Kalojnë edhe kur terminali përdor kodimin e vjetër `cp1252` (pa `PYTHONUTF8`).

Tema e errët e dashboard-it vjen nga `.streamlit/config.toml` (lexohet kur `streamlit run` niset nga dosja e projektit). Artikujt që s'arrihen në një ekzekutim përpunohen herën tjetër, sepse rezultatet ruhen në `osint.db`. Çdo hap mund të niset edhe veçmas, p.sh. `python collector.py` ose `python extractor.py 10`.

**Nga dashboard-i (skeda "Ekzekutimi"):** butoni **▶️ Ekzekuto tani** nis `ekzekuto.py` në sfond (log-u te `pipeline.log`, dy ekzekutime njëkohësisht nuk lejohen). Te **Automatikisht** zgjidhet çdo 1/2/3/6/12/24 orë: krijohet detyra "OSINT Kosova" në Windows Task Scheduler, që punon edhe kur dashboard-i është i mbyllur (kompjuteri ndezur dhe Ollama duke punuar).

### Demo në Streamlit Community Cloud

Në cloud (Linux, ose lokalisht me `OSINT_CLOUD=1`) dashboard-i krijon vetë `demo.db` nga 63 artikujt **sintetikë** të `eval/gold.jsonl`, shfaq njoftimin "Demo me të dhëna sintetike" dhe çaktivizon "Ekzekuto tani" dhe orarin, sepse aty s'ka Ollama. Vendimet e analistit ruhen vetëm deri në rinisjen e aplikacionit.

1. Te share.streamlit.io: **Create app**, repo `enesmaloku-a11y/osinttttt`, dega `main`, skedari `dashboard.py`. Te **Advanced settings** zgjidh Python 3.12.
2. Mos vendos `OSINT_DB`, `APIFY_TOKEN` apo `osint.db` në cloud: aty shkon vetëm demo-ja.
3. Te **Settings → Sharing**, lejo vetëm email-et e ekipit dhe të jurisë.

### Live në Railway (me Ollama)

Railway mund të mbajë edhe Ollama-n, ndaj aty dashboard-i mbledh dhe analizon lajme reale. Dy shërbime në të njëjtin projekt:

1. **Ollama:** shërbim nga imazhi Docker `ollama/ollama`, me volum te `/root/.ollama` dhe të paktën 8 GB RAM. Pas nisjes, te shërbimi ekzekuto një herë `ollama pull deepseek-r1:8b`. Mos i jep domen publik: e thërret vetëm aplikacioni, përmes rrjetit privat të Railway.
2. **Aplikacioni:** nga repo-ja (dega `main`). Nis me `Procfile`. Volum te `/data` dhe këto variabla:

| Variabla | Vlera |
|---|---|
| `OSINT_CLOUD` | `0` (pa të, Linux-i hapet si demo sintetike) |
| `OSINT_DB` | `/data/osint.db` (në volum, që të mos humbasë në rinisje) |
| `OLLAMA_URL` | `http://<emri-i-sherbimit-ollama>.railway.internal:11434/api/generate` |
| `OLLAMA_MODEL` | `deepseek-r1:8b` |
| `OSINT_FJALEKALIMI` | fjalëkalim i fortë: pa të, kushdo me URL-në mund të nisë mbledhjen dhe të ndryshojë vendimet |

Baza nis bosh: "Mblidh lajmet tani" e mbush nga mediat. Pa GPU modeli punon më ngadalë se në laptop, dhe kostoja e Railway rritet me RAM-in dhe kohën. `osint.db` lokale s'hyn në Git dhe s'ngarkohet në Railway. Orari automatik (Task Scheduler) punon vetëm në Windows.

## Rrjetet sociale (Apify)

`apify_burimi.py` importon postime nga Reddit, X dhe Telegram si **sinjale për shqyrtim**: burimi i gjurmueshëm (`Reddit:r/...`, `X:x.com`, `Telegram:kanali`), URL-ja origjinale, gjuha dhe data e publikimit (pa shpikur orën kur mungon). Autori, përmendjet dhe email-et s'ruhen. Burimet sociale marrin Admiralty F, numërohen si **një origjinë** (edhe kur i njëjti pretendim del në dy platforma) dhe konfirmimi vjen vetëm nga analisti. `main.py` dhe orari automatik s'nisin kurrë Actor-ë me pagesë.

| Platforma | Statusi | Çfarë do të thotë |
|---|---|---|
| Reddit | në pritje të lejes | Importi real hapet kur marrëveshja mbulon mbledhjen, ruajtjen, analizën me model dhe shfaqjen te FSK-ja |
| X | e provuar vetëm me të dhëna sintetike | Përmbajtja reale mbetet jashtë rrjedhës së FSK-së deri te një marrëveshje që e mbulon këtë përdorues |
| Telegram | e provuar vetëm me të dhëna sintetike | Kushtet e licencimit të Telegram-it kufizojnë përdorimin me AI; lista `KANALET_TELEGRAM` është bosh |

Statusi ndryshohet te `STATUSI` në `apify_burimi.py`, vetëm pasi leja të jetë verifikuar. Përmbajtja reale (dataset, run, nisje) refuzohet për çdo platformë që s'është "aktive me leje të verifikuar".

```powershell
python apify_burimi.py statusi
python apify_burimi.py importo reddit --skedar shembuj\apify_reddit.json     # skedar lokal, offline
python apify_burimi.py importo reddit --dataset DATASET_ID --maks 500         # dataset ekzistues (platformë aktive)
python apify_burimi.py importo reddit --run RUN_ID                            # nga një ekzekutim i përfunduar
python apify_burimi.py nis reddit 50                                          # me pagesë, vetëm me komandë
```

Token-i lexohet nga `APIFY_TOKEN` ose `~/.apify_token` dhe dërgohet vetëm në header (`Authorization: Bearer`), kurrë në URL, log ose Git. Dataset-i lexohet me faqe (`limit`/`offset`), deri në 2 000 rreshta për import. Nisja me pagesë ka kufi 200 rreshta dhe $0.30; nëse përgjigjja humbet, s'niset një e dytë derisa e para të importohet me `--run`. Gabimet 401/403/429, timeout dhe JSON i pavlefshëm japin status të qartë pa ndalur pjesën tjetër.

**Demo offline me shembuj sintetikë** (pa token, pa pagesë):

```powershell
python demo.py
python apify_burimi.py demo demo.db
$env:OSINT_DB="demo.db"; python -m streamlit run dashboard.py
```

Shembujt janë te `shembuj/apify_*.json` (të shkruar nga ekipi, në shqip, serbisht dhe anglisht, me formatin e Actor-ëve). Te kartela e ngjarjes del "Sinjal nga rrjetet sociale" dhe analisti e konfirmon ose e hedh poshtë si çdo ngjarje tjetër.

## Mjetet për analistin

- **Përmbledhja (skeda e parë):** një shikim që respekton filtrat e sidebar-it. **Ngjarjet më të reja:** 10 të fundit me prioritetin, datën, titullin dhe burimin. **Rreziku × besueshmëria:** çdo ngjarje është një pikë (ngjyra = prioriteti, madhësia = numri i burimeve); vija 80% ndan *URGJENTE për veprim* nga *URGJENTE për verifikim*, vijat 55 dhe 35 janë pragjet e rrezikut. Ngjarjet pa rrezik ose besueshmëri të llogaritur s'vizatohen dhe numërohen poshtë grafikut. **Serbia:** ngjarjet me aktor shtetin serb në 7 ditët deri te ngjarja më e re në bazë (jo deri sot), me ndryshimin kundrejt 7 ditëve para dhe 3 kategoritë më të shpeshta; aktori vjen nga modeli dhe duhet verifikuar. **Zonat:** Veriu, Kufiri/pikat kufitare, Prishtina, Kosova tjetër, Rajonale dhe Pa vend, sipas vendit që gjen `correlator.py` (lista te `ZONAT` në `dashboard.py`).
- **Urgjente / Raporte:** prioriteti vjen nga matrica rrezik × besueshmëri (`rreziku.py`). Rrezik i lartë me besueshmëri nën 80% del si *URGJENTE për verifikim, jo për veprim*. Çdo ngjarje tregon pse ky rrezik, pse kjo besueshmëri, kodin Admiralty (p.sh. B2), boshllëqet dhe kontekstin e jashtëm.
- **Filtrat:** zona (Kosovë/rajonale), prioriteti, kategoria, niveli i rrezikut dhe vendimi i analistit.
- **Kërcënimet:** taksonomia me treguesit, aktorët tipikë dhe shembuj publikë me burim. **Burimet:** sa ngjarje sjell çdo medium dhe çfarë vendosi analisti, plus burimet me raste dezinformimi sipas EUvsDisinfo (pa llogari individuale). **Vlerësimi:** metrikat e `eval/rezultati.json` dhe të modelit të besueshmërisë.
- **Raporti ditor:** butoni te skeda Urgjente ose `python raporti.py`; shkarkohet si Markdown.
- **Vendimi i analistit:** te çdo ngjarje në dashboard zgjidhet ✅ e konfirmuar, ❓ e pakonfirmuar ose ❌ e hedhur poshtë, me shënim. Vendimet ruhen në tabelën `vendimet` (çelësi = një URL e ngjarjes, gjendet me `db.url_i_vendimit`), ndaj nuk humbin kur `correlator.py` i rindërton ngjarjet. Sidebar-i filtron sipas vendimit.
- **Zbulimi i rritjeve (`patterns.py`):** alarm kur një komunë ka ≥ 3 ngjarje në 7 ditët e fundit dhe ≥ 2 herë mesataren javore të 28 ditëve para tyre (dysheme 0.5). Shfaqet në krye të dashboard-it dhe në fund të `main.py`; `python patterns.py` e printon veçmas.
- **Saktësia e vendit dhe datës:** modeli jep `place_precision` (fshat/komunë/rajon) dhe `date_precision` (e saktë/e përafërt), të kontrolluara me rregulla. Lajmet s'kanë GPS, prandaj harta e tregon vendin me saktësinë që dihet: rajoni ("veriu i Kosovës") si rreth ~15 km, komuna si rreth ~5 km rreth qendrës së saj, dhe vetëm fshati ose vendi i saktë si pikë. Ngjarjet e njohura vetëm në nivel rajoni marrin edhe boshllëkun "vendi vetëm në nivel rajoni". Harta hapet te Kosova, ka pamjet Rajoni, Ballkani dhe Evropa, dhe s'lëviz jashtë Evropës.
- **Hash-i i artikujve:** `collector.py` ruan SHA-256 të tekstit bruto kur e mbledh. Te leximi i artikullit, "Verifiko tani" e rishkarkon faqen dhe tregon nëse lajmi u ndryshua, u fshi, apo ndryshoi vetëm teksti rreth tij (reklama, "më të lexuarat").

## Vlerësimi

`eval/gold.jsonl` ka 63 artikuj **sintetikë** (të shkruar nga ekipi, jo lajme reale) me përgjigjen e saktë. Ata përfshijnë ngjarje shumëgjuhëshe, kibernetikë, infrastrukturë, dezinformim, një ngjarje rajonale dhe artikuj-kurth pa kërcënim.

```powershell
ollama serve                          # nëse s'po punon
python eval/evaluate.py               # rreth 1–2 minuta për artikull me deepseek-r1:8b
```

Skripti kalon të njëjtin pipeline në bazë të veçantë (`eval/eval.db`) dhe printon precision/recall (gjithsej dhe sipas gjuhës), alarmet e rreme, llojin e saktë, ngjarjet e bashkuara saktë dhe kohën. Rezultati ruhet te `eval/rezultati.json` dhe shfaqet te skeda Vlerësimi. Koha "manuale" aty është supozim (`MINUTA_MANUALE = 3` minuta për artikull), jo matje; krahasimi me analistë bëhet sipas `docs/validimi.md`. `osint.db` nuk preket.

## Të dhënat dhe privatësia

- Vetëm burime publike. `osint.db` ka tekstin e plotë të artikujve, prandaj nuk publikohet (është te `.gitignore`).
- Email-et, numrat e telefonit dhe emrat e personave privatë hiqen me rregulla, jo duke i besuar modelit.
- Çdo ngjarje duhet të ketë të paktën një URL burimi.

## Kufizime të njohura

- Lista e burimeve të dezinformimit dhe kodi Admiralty "E" kërkojnë `data/euvsdisinfo.csv` (eksport manual).
- Aktori i kërcënimit vjen nga modeli gjuhësor dhe duhet verifikuar nga analisti.
- Besueshmëria e mediave te `scoring.py` është vlerë fillestare që duhet ta rishikojë analisti.
- Modeli i besueshmërisë (`trajno.py`) trajnohet vetëm me komandë, kur ka të paktën 80 vendime të përdorshme (20 të konfirmuara dhe 20 të hedhura poshtë); deri atëherë besueshmëria vjen nga rregullat.
- Numrat e vlerësimit vijnë nga të dhëna sintetike; me lajme reale pritet të jenë më të ulët.
- Harta kërkon internet (Leaflet dhe sfondi OpenStreetMap ngarkohen nga rrjeti); pa internet nuk shfaqet, por Përmbledhja, kronologjia dhe listat punojnë.
- `patterns.py` jep alarme vetëm pas 5 javësh mbledhjeje (para kësaj mesatarja s'dihet); deri atëherë dashboard-i e thotë këtë.
- Hash-i ndryshon edhe kur portali shton vetëm reklama; krahasimi rresht për rresht bëhet vetëm për artikujt ende të papërkthyer (processor.py e pastron tekstin).
