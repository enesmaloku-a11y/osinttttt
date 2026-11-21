# OSINT Kosova: prototip

Prototip për sfidën **01 · AI-Powered OSINT & Hybrid Threat Intelligence** (EDTH Prishtina 2026), nga ekipi **The Silent Fixers**.

Fokusi: **kërcënimet hibride ndaj FSK-së dhe sigurisë së Kosovës, sidomos nga Serbia.** Sistemi mbledh lajme në shqip, serbisht dhe anglisht, nxjerr ngjarjet e sigurisë dhe i klasifikon sipas taksonomisë së kërcënimeve, bashkon raportimet e së njëjtës ngjarje nga burime dhe gjuhë të ndryshme, i rendit sipas **rrezikut** dhe **besueshmërisë** në **Urgjente** dhe **Raporte**, dhe i tregon analistit me burime, kronologji, kod NATO Admiralty, boshllëqe informacioni dhe raport ditor. **Analisti vendos gjithmonë; sistemi vetëm sugjeron.**

## Si punon

| Hapi | Skedari | Çfarë bën |
|---|---|---|
| 1 | `collector.py` | Mbledh artikuj nga RSS (RTK, Koha, Kallxo, Telegrafi, Gazeta Express, N1 Serbia, Balkan Insight) dhe GDELT, pa dublikatë |
| 2 | `processor.py` | Heq email-et dhe telefonat, përkthen në anglisht me model lokal |
| 3 | `extractor.py` | Filtër me fjalë kyçe, pastaj modeli nxjerr ngjarjen si JSON (kategoria, aktori, shenjestra, lidhja me FSK); emrat e personave maskohen |
| 4 | `correlator.py` | Bashkon artikujt e së njëjtës ngjarje (lloji, data, vendi, ngjashmëria) dhe gjen boshllëqet |
| 5 | `kontekst_*.py` | Konteksti i jashtëm: raste të ngjashme nga EUvsDisinfo dhe EuRepoC |
| 6 | `scoring.py` | Besueshmëria: rregulla të qarta, ose modeli i kalibruar (`trajno.py`) kur ka vendime të analistit; jo nga LLM-i |
| 7 | `rreziku.py` | Rreziku 0–100 me rregulla, prioriteti (URGJENTE/RAPORT/MONITORIM/ARKIV) dhe kodi NATO Admiralty |
| - | `kercenimet.py` | Taksonomia: 14 kategori kërcënimesh hibride, aktorët, shenjestrat, fjalët kyçe sq/sr/en |
| - | `raporti.py` | Raporti ditor një faqe: BLUF, Urgjente, Raporte, trendet, boshllëqet, burimet |
| - | `dashboard.py` | Pamja e analistit: Urgjente, Raporte, harta, kronologjia, taksonomia, burimet, vlerësimi |
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

Modeli ndryshohet te `MODELI` në `processor.py`.

## Përdorimi

```powershell
ollama serve              # në një dritare tjetër, nëse Ollama s'po punon
python main.py            # mbledh dhe përpunon deri në 20 artikuj
python main.py 50         # deri në 50
streamlit run dashboard.py
python raporti.py         # raporti ditor te raportet/ (e bën edhe main.py në fund)
```

Artikujt që s'arrihen në një ekzekutim përpunohen herën tjetër, sepse rezultatet ruhen në `osint.db`. Çdo hap mund të niset edhe veçmas, p.sh. `python collector.py` ose `python extractor.py 10`.

**Nga dashboard-i (skeda "Ekzekutimi"):** butoni **▶️ Ekzekuto tani** nis `ekzekuto.py` në sfond (log-u te `pipeline.log`, dy ekzekutime njëkohësisht nuk lejohen). Te **Automatikisht** zgjidhet çdo 1/2/3/6/12/24 orë: krijohet detyra "OSINT Kosova" në Windows Task Scheduler, që punon edhe kur dashboard-i është i mbyllur (kompjuteri ndezur dhe Ollama duke punuar).

## Mjetet për analistin

- **Urgjente / Raporte:** prioriteti vjen nga matrica rrezik × besueshmëri (`rreziku.py`). Rrezik i lartë me besueshmëri nën 80% del si *URGJENTE për verifikim, jo për veprim*. Çdo ngjarje tregon pse ky rrezik, pse kjo besueshmëri, kodin Admiralty (p.sh. B2), boshllëqet dhe kontekstin e jashtëm.
- **Filtrat:** zona (Kosovë/rajonale), prioriteti, kategoria, niveli i rrezikut dhe vendimi i analistit.
- **Kërcënimet:** taksonomia me treguesit, aktorët tipikë dhe shembuj publikë me burim. **Burimet:** sa ngjarje sjell çdo medium dhe çfarë vendosi analisti, plus burimet me raste dezinformimi sipas EUvsDisinfo (pa llogari individuale). **Vlerësimi:** metrikat e `eval/rezultati.json` dhe të modelit të besueshmërisë.
- **Raporti ditor:** butoni te skeda Urgjente ose `python raporti.py`; shkarkohet si Markdown.
- **Vendimi i analistit:** te çdo ngjarje në dashboard zgjidhet ✅ e konfirmuar, ❓ e pakonfirmuar ose ❌ e hedhur poshtë, me shënim. Vendimet ruhen në tabelën `vendimet` (çelësi = një URL e ngjarjes, gjendet me `db.url_i_vendimit`), ndaj nuk humbin kur `correlator.py` i rindërton ngjarjet. Sidebar-i filtron sipas vendimit.
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

- Vetëm burime publike. `osint.db` ka tekstin e plotë të artikujve, prandaj nuk publikohet (është te `.gitignore`).
- Email-et, numrat e telefonit dhe emrat e personave privatë hiqen me rregulla, jo duke i besuar modelit.
- Çdo ngjarje duhet të ketë të paktën një URL burimi.

## Kufizime të njohura

- `rreziku.py` gjen vendimin e analistit vetëm te URL-ja e parë e ngjarjes; duhet të përdorë `db.url_i_vendimit` si dashboard-i.
- Lista e burimeve të dezinformimit dhe kodi Admiralty "E" kërkojnë `data/euvsdisinfo.csv` (eksport manual).
- Aktori i kërcënimit vjen nga modeli gjuhësor dhe duhet verifikuar nga analisti.
- Besueshmëria e mediave te `scoring.py` është vlerë fillestare që duhet ta rishikojë analisti.
- Numrat e vlerësimit vijnë nga të dhëna sintetike; me lajme reale pritet të jenë më të ulët.
- `patterns.py` jep alarme vetëm pas 5 javësh mbledhjeje (para kësaj mesatarja s'dihet); deri atëherë dashboard-i e thotë këtë.
- Hash-i ndryshon edhe kur portali shton vetëm reklama; krahasimi rresht për rresht bëhet vetëm për artikujt ende të papërkthyer (processor.py e pastron tekstin).
