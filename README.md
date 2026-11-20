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

Modeli ndryshohet te `MODELI` në `processor.py`.

## Përdorimi

```powershell
ollama serve              # në një dritare tjetër, nëse Ollama s'po punon
python main.py            # mbledh dhe përpunon deri në 20 artikuj
python main.py 50         # deri në 50
streamlit run dashboard.py
```

Artikujt që s'arrihen në një ekzekutim përpunohen herën tjetër, sepse rezultatet ruhen në `osint.db`. Çdo hap mund të niset edhe veçmas, p.sh. `python collector.py` ose `python extractor.py 10`.

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

- Ngjarjet jashtë Kosovës zbulohen, por nuk shfaqen në dashboard.
- Emrat e vendeve në cirilik nuk njihen për hartën.
- Besueshmëria e mediave te `scoring.py` është vlerë fillestare që duhet ta rishikojë analisti.
- Numrat e vlerësimit vijnë nga të dhëna sintetike; me lajme reale pritet të jenë më të ulët.
