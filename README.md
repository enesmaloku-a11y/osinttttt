# OSINT Kosova: prototip

Prototip për sfidën **01 · AI-Powered OSINT & Hybrid Threat Intelligence** (EDTH Prishtina 2026), nga ekipi **The Silent Fixers**.

Sistemi mbledh lajme në shqip, serbisht dhe anglisht, nxjerr ngjarjet e sigurisë, bashkon raportimet e së njëjtës ngjarje nga burime dhe gjuhë të ndryshme, dhe i tregon analistit me burime, kronologji, besueshmëri dhe boshllëqe informacioni. **Analisti vendos gjithmonë; sistemi vetëm sugjeron.**

## Si punon

| Hapi | Skedari | Çfarë bën |
|---|---|---|
| 1 | `collector.py` | Mbledh artikuj nga RSS (RTK, Koha, Kallxo, Telegrafi, Gazeta Express, N1 Serbia, Balkan Insight) dhe GDELT, pa dublikatë |
| 2 | `processor.py` | Heq email-et dhe telefonat, përkthen në anglisht me model lokal |
| 3 | `extractor.py` | Filtër me fjalë kyçe, pastaj modeli nxjerr ngjarjen si JSON; emrat e personave maskohen |
| 4 | `correlator.py` | Bashkon artikujt e së njëjtës ngjarje (lloji, data, vendi, ngjashmëria) dhe gjen boshllëqet |
| 5 | `scoring.py` | Besueshmëria me rregulla të qarta, jo nga modeli: burime të pavarura, besueshmëria e mediave, përputhja e detajeve |
| - | `dashboard.py` | Pamja e analistit: hartë, kronologji, ngjarje me burime dhe arsyetim |
| - | `db.py` | Ruajtja në SQLite (`osint.db`) |

Modeli gjuhësor punon **lokalisht** përmes [Ollama](https://ollama.com), kështu që asnjë e dhënë nuk dërgohet te shërbime të jashtme.

## Instalimi (Windows PowerShell)

Kërkohet Python 3.11+ dhe Ollama.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
ollama pull deepseek-r1:8b
```

Linux/macOS:

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
ollama pull deepseek-r1:8b
```

Modeli ndryshohet me `OLLAMA_MODEL` (ose te `MODELI` në `processor.py`); shih `.env.example` për variablat e tjera.

## Demo pa Ollama (rezervë për prezantimin)

```bash
python demo.py                                   # krijon demo.db nga eval/gold.jsonl
OSINT_DB=demo.db streamlit run dashboard.py      # PowerShell: $env:OSINT_DB="demo.db"; streamlit run dashboard.py
```

`demo.db` ka 36 artikujt **sintetikë** të gold set-it, me etiketat e sakta në vend të përgjigjes së modelit, ndaj tregon vetëm pamjen e analistit (bashkimi, besueshmëria, boshllëqet, harta), jo saktësinë. `osint.db` nuk preket.

## Përdorimi

```powershell
ollama serve              # në një dritare tjetër, nëse Ollama s'po punon
python main.py            # mbledh dhe përpunon deri në 20 artikuj
python main.py 50         # deri në 50
streamlit run dashboard.py
```

Artikujt që s'arrihen në një ekzekutim përpunohen herën tjetër, sepse rezultatet ruhen në `osint.db`. Çdo hap mund të niset edhe veçmas, p.sh. `python collector.py` ose `python extractor.py 10`.

**Nga dashboard-i (skeda "Ekzekutimi"):** butoni **▶️ Ekzekuto tani** nis `ekzekuto.py` në sfond (log-u te `pipeline.log`, dy ekzekutime njëkohësisht nuk lejohen). Te **Automatikisht** zgjidhet çdo 1/2/3/6/12/24 orë: krijohet detyra "OSINT Kosova" në Windows Task Scheduler, që punon edhe kur dashboard-i është i mbyllur (kompjuteri ndezur dhe Ollama duke punuar). Në Linux/macOS butoni "Ekzekuto tani" punon, por orari bëhet me cron, p.sh. `0 */3 * * * cd /rruga/osint && venv/bin/python ekzekuto.py 20`.

## Mjetet për analistin

- **Vendimi i analistit:** te çdo ngjarje në dashboard zgjidhet ✅ e konfirmuar, ❓ e pakonfirmuar ose ❌ e hedhur poshtë, me shënim. Vendimet ruhen në tabelën `vendimet` (çelësi = URL-ja e artikullit më të hershëm), ndaj nuk humbin kur `correlator.py` i rindërton ngjarjet. Sidebar-i filtron sipas vendimit.
- **Zbulimi i rritjeve (`patterns.py`):** alarm kur një komunë ka ≥ 3 ngjarje në 7 ditët e fundit dhe ≥ 2 herë mesataren javore të 28 ditëve para tyre (dysheme 0.5). Shfaqet në krye të dashboard-it dhe në fund të `main.py`; `python patterns.py` e printon veçmas.
- **Saktësia e vendit dhe datës:** modeli jep `place_precision` (fshat/komunë/rajon) dhe `date_precision` (e saktë/e përafërt), të kontrolluara me rregulla. Ngjarjet e njohura vetëm në nivel rajoni ("veriu i Kosovës") vizatohen si rreth 15 km, jo si pikë, dhe marrin boshllëkun "vendi vetëm në nivel rajoni".
- **Hash-i i artikujve:** `collector.py` ruan SHA-256 të tekstit bruto kur e mbledh. Te leximi i artikullit, "Verifiko tani" e rishkarkon faqen dhe tregon nëse lajmi u ndryshua, u fshi, apo ndryshoi vetëm teksti rreth tij (reklama, "më të lexuarat").

## Vlerësimi

`eval/gold.jsonl` ka 33 artikuj **sintetikë** (të shkruar nga ekipi, jo lajme reale) me përgjigjen e saktë. Ata përfshijnë ngjarje shumëgjuhëshe, kibernetikë, infrastrukturë, dezinformim, një ngjarje rajonale dhe artikuj-kurth pa kërcënim.

```powershell
python eval/evaluate.py
```

Skripti kalon të njëjtin pipeline në bazë të veçantë (`eval/eval.db`) dhe printon precision/recall (gjithsej dhe sipas gjuhës), alarmet e rreme, llojin e saktë, ngjarjet e bashkuara saktë dhe kohën kundrejt punës manuale. `osint.db` nuk preket.

## Të dhënat dhe privatësia

- Vetëm burime publike. `collector.py` respekton `robots.txt` (RFC 9309): kur faqja e ndalon, s'shkarkohet dhe ruhet vetëm përmbledhja e RSS-së. Balkan Insight, p.sh., i ndalon të gjithë robotët e paemërtuar.
- Si parazgjedhje ruhet vetëm fragmenti i fillimit të artikullit (~1200 karaktere, paragrafë të plotë) + URL; teksti i plotë vetëm me `OSINT_FULL_TEXT=1`. Hash-i merret mbi tekstin e plotë kur mblidhet. Kolona `raw_text` mban tekstin siç u mblodh; `processor.py` pastron vetëm `teksti`.
- `osint.db` ka tekst nga artikujt dhe emra në të, prandaj nuk publikohet (është te `.gitignore`).
- Email-et, numrat e telefonit dhe emrat e personave privatë hiqen me rregulla, jo duke i besuar modelit.
- Çdo ngjarje duhet të ketë të paktën një URL burimi.

## Kufizime të njohura

- Ngjarjet jashtë Kosovës njihen vetëm për qytetet kryesore fqinje (`RAJONI` te `correlator.py`).
- Besueshmëria e mediave te `scoring.py` është vlerë fillestare që duhet ta rishikojë analisti.
- Numrat e vlerësimit vijnë nga të dhëna sintetike; me lajme reale pritet të jenë më të ulët.
- `patterns.py` jep alarme vetëm pas 5 javësh mbledhjeje (para kësaj mesatarja s'dihet); deri atëherë dashboard-i e thotë këtë.
- Hash-i ndryshon edhe kur portali shton vetëm reklama; krahasimi rresht për rresht bëhet mbi `raw_text` (fragmentin, si parazgjedhje), ndaj artikujt e mbledhur para kësaj kolone e kanë vetëm nëse s'ishin përkthyer.
