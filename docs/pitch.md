# Pitch: The Silent Fixers (3–5 minuta)

**Mesazhi në një fjali:** *Sistemi kthen mijëra lajme në shqip, serbisht dhe anglisht në pak kërcënime hibride për FSK-në, të renditura sipas rrezikut dhe besueshmërisë, me burime dhe arsyetim, plotësisht lokalisht, dhe vendimin final e merr gjithmonë analisti.*

## Struktura

| Koha | Pjesa | Çfarë thuhet / tregohet |
|---|---|---|
| 0:00–0:30 | **Problemi** | Analisti i FSK-së ndjek lajme në tri gjuhë nga dhjetëra burime. Kërcënimet hibride nga Serbia (lëvizje ushtarake, dronë, sabotim, dezinformim, sulme kibernetike) humbasin në zhurmë, dhe s'dihet çfarë është e vërtetë. |
| 0:30–2:45 | **Demo** | Shih rrjedhën më poshtë. |
| 2:45–3:30 | **Si punon dhe pse i besohet** | Pipeline lokal me Ollama, pa cloud. LLM-i vetëm nxjerr faktet. Rreziku vjen nga rregulla të qarta, besueshmëria nga provat (origjina të pavarura, gjuhë, kontradikta), dhe ripostimet s'numërohen si konfirmim. Admiralty sipas standardit NATO. Modeli i besueshmërisë është gati të mësojë nga vendimet e analistëve. |
| 3:30–4:15 | **Prova** | Metrikat nga skeda Vlerësimi, me shënimin "mbi artikuj sintetikë": recall 100%, precision 92%, URGJENTE 9 nga 10, 0 bashkime të gabuara (shih "Metrikat e verifikuara"). Testi i ripostimeve (91% → 54%). Testi me mentorin (docs/validimi.md): koha para/pas, besimi 1–5. |
| 4:15–5:00 | **Ligji, kufizimet dhe hapi tjetër** | "E lexuam ligjin dhe kushtet e platformave." Sinqerisht: të dhënat sintetike, aktori nga modeli duhet verifikuar, lista e EUvsDisinfo kërkon eksport. Hapi tjetër: më shumë etiketa nga analistë të vërtetë, burime sociale vetëm përmes API-ve zyrtare që e lejojnë, pilot me FSK-në. |

## Metrikat e verifikuara (thuaji ashtu siç janë)

**Lloji i provës:** vlerësim me model mbi gold set sintetik (`python eval/evaluate.py`), jo me lajme reale. Modeli `deepseek-r1:8b` lokal përmes Ollama; 63 artikuj sintetikë në shqip, serbisht dhe anglisht, 28 ngjarje të pritura; ekzekutuar më 21.11.2026. Skeda Vlerësimi tregon të njëjtat vlera nga `eval/rezultati.json`.

| Metrika | Rezultati | Interval 95% (Wilson) |
|---|---|---|
| Zbulimi i ngjarjeve: precision | 49/53 = 92% | 0.82–0.97 |
| Zbulimi i ngjarjeve: recall | 49/49 = 100% | 0.93–1.00 |
| Alarme të rreme | 4 nga 14 artikuj pa kërcënim | |
| Sipas gjuhës (precision / recall) | en 0.91 / 1.00 · sq 0.91 / 1.00 · sr 0.95 / 1.00 | |
| Kategoria e saktë | 34/49 | 0.55–0.80 |
| Niveli i rrezikut i saktë | 18/28 | 0.46–0.79 |
| URGJENTE | precision 13/20 (65%) · recall 9/10 (90%) | 0.43–0.82 · 0.60–0.98 |
| Ngjarje të bashkuara saktë | 17/28 (shumëgjuhëshe 9/18); bashkime të gabuara: 0 | |
| Koha e pipeline-it | 40.4 s për artikull (2 546 s për 63) | |

**Fjalia për jurinë:** *"Mbi 63 artikuj sintetikë në tri gjuhë, sistemi gjeti të gjitha ngjarjet e sigurisë, me precision 92% dhe pa asnjë bashkim të gabuar. Për URGJENTE kap 9 nga 10, por rreth një e treta e alarmeve urgjente janë të tepërta: prandaj vendos analisti."*

**Çfarë s'është matur:** krahasimi me punën manuale. Evaluator-i shfaq "~189 min manualisht", por kjo është supozim (3 minuta për artikull), jo matje. Testi me pjesëmarrës (`docs/validimi.md`) s'është bërë ende. Modeli i besueshmërisë s'është trajnuar: duhen 80 vendime të analistit (20 të konfirmuara, 20 të hedhura poshtë), dhe baza e etiketimit ka 0; besueshmëria vjen nga rregullat.

## Rrjedha e demos (rreth 2 minuta e 15 sekonda)

1. **Skeda Përmbledhja:** "Ja situata me një shikim." Matrica rrezik × besueshmëri (lart djathtas = URGJENTE për veprim, lart majtas = URGJENTE për verifikim), paneli **Serbia** (ngjarjet me aktor shtetin serb në 7 ditë, rreziku mesatar, trendi) dhe tabela e zonave (veriu, kufiri, Prishtina, rajoni).
2. **Skeda Urgjente:** hap kartelën e parë: prioriteti, rreziku 0–100 me arsyet ("pse ky rrezik"), besueshmëria me arsyet, kodi Admiralty (p.sh. B2), burimet në disa gjuhë, boshllëqet e informacionit.
3. **Një URGJENTE "për verifikim":** "Rrezik i lartë, por një burim i vetëm i panjohur (F6). Sistemi nuk thotë vepro, thotë verifiko."
4. **Ripostimet:** hap një ngjarje që e raportojnë disa media. Te "Pse kjo besueshmëri": *"burime të pavarura: 1 nga 3 media (2 kopje)"*, Admiralty B6. "Tre media që kopjojnë njëra-tjetrën s'janë tre konfirmime. Sistemi s'mashtrohet nga ripostimet."
5. **Konteksti i jashtëm:** një dezinformim që ngjan me një rast të dokumentuar nga EUvsDisinfo, nëse CSV-ja është vendosur.
6. **Vendimi i analistit:** konfirmo një ngjarje. "Vendimi ruhet. Kur mblidhen 80 vendime (20 të konfirmuara, 20 të hedhura poshtë), modeli i besueshmërisë ritrajnohet prej tyre me `trajno.py`."
7. **Harta:** pamja Kosova → Rajoni. "Rrethi tregon që vendi dihet vetëm në nivel komune ose rajoni. S'pretendojmë saktësi që s'e kemi."
8. **Raporti ditor:** butoni "Gjenero raportin ditor" → BLUF në një faqe për komandantin.
9. **Demo live** (nëse ka kohë, ~20 s): te `demo_live.py` shkruaj një postim në forumin demo (p.sh. "dron mbi Gazivodë"). Brenda ~2 sekondave del si kërcënim me kategorinë, rrezikun dhe Admiralty F6. "Forumi është i simuluar. Vetëm postime të ekipit, me rregulla, pa model."

## Burimet dhe ligji (thuaje me një fjali, dhe përgjigju nëse pyesin)

- **Çfarë mbledhim:** media publike (RSS), GDELT, burime zyrtare dhe **postime publike nga rrjetet sociale**. Te mediat respektohet `robots.txt`, ruhet vetëm fragmenti dhe URL-ja, emrat e personave maskohen, dhe modeli punon lokalisht, pa cloud.
- **Rrjetet sociale (përmes Apify):** integrimi është gati për Reddit, X dhe Telegram: import nga dataset ekzistues, ruajtje pa autorin, Admiralty **F**, "për verifikim", dhe dy platforma me të njëjtin pretendim = një origjinë. **Statusi sot:** Reddit në pritje të lejes; X dhe Telegram të provuar vetëm me të dhëna sintetike. Në demo tregojmë shembuj sintetikë të ekipit dhe e themi qartë.
- **Telegram:** vetëm kanale publike të mediave, institucioneve dhe aktorëve shtetërorë, nga një listë që e miraton ekipi me FSK-në. Lista është ende bosh, ndaj sot nuk mblidhet asgjë nga Telegram. Kushtet e Telegram-it e kufizojnë scraping-un dhe përdorimin për AI, ndaj përdorimi operacional është vendim ligjor i FSK-së.
- **Demo live:** përdor **kanalin privat të ekipit** ose forumin demo, me postime që i shkruan ekipi, përmes Bot API-t zyrtar, pa model dhe pa trajnim.
- **Facebook dhe Instagram:** nuk mblidhen.
- **Individët privatë s'profilohen.** Ndiqen organizata, media, institucione dhe aktorë shtetërorë.

## Plani rezervë

- Para prezantimit: `python demo.py`, pastaj `$env:OSINT_DB="demo.db"; python -m streamlit run dashboard.py`. Punon pa Ollama. Pa internet, harta del pa sfond, por skedat e tjera punojnë. Nëse `demo.db` ekziston, `demo.py` s'e prek: hape atë ose krijo `demo2.db`.
- `streamlit run demo_live.py --server.port 8505` punon pa internet dhe pa model.
- Bëj screenshot-e të çdo hapi, në rast se laptopi ose rrjeti dështon.
- Mos nis `main.py` gjatë prezantimit: modeli 8B kërkon rreth 1 minutë për artikull.

## Pyetje që mund të bëjë juria

| Pyetja | Përgjigjja |
|---|---|
| Si e dini që 85% do të thotë 85%? | Modeli kalibrohet nga vendimet e analistit dhe matet me validim të kryqëzuar. Përdoret vetëm nëse i kalon rregullat. Deri sa të ketë mjaft etiketa (80+), besueshmëria vjen nga rregulla të qarta, dhe e themi hapur. |
| Pse s'e vendos LLM-i besueshmërinë? | Modelet gjuhësore e japin keq sigurinë e tyre. Ne e llogarisim nga provat që mund t'i kontrolloni. |
| Po nëse një lajm ripostohet 10 herë? | Kopjet dhe përkthimet grupohen sipas origjinës (ngjashmëri teksti, përkthimi ose citim i qartë). Në testin tonë, Koha + ripostimi + përkthimi mbeti 54%, jo 91%, dhe Admiralty doli B6, jo B1. Kanalet sociale numërohen gjithsej si një burim. |
| A mblidhni nga rrjetet sociale? | Integrimi me Apify është gati (Reddit, X, Telegram), por përmbajtja reale hyn vetëm kur marrëveshja e platformës e lejon këtë përdorim. Sot: Reddit në pritje të lejes, X dhe Telegram vetëm me të dhëna sintetike. Postimet sociale marrin gjithmonë Admiralty F: sinjal për verifikim, jo konfirmim. Facebook dhe Instagram nuk mblidhen. |
| A profiloni njerëz? | Jo. Ndiqen organizata, media dhe aktorë shtetërorë. Emrat e personave privatë maskohen me rregulla, dhe ruhet vetëm fragmenti dhe URL-ja. |
| Pse Admiralty? | Është standardi i NATO-s: shkronja (A–F) për burimin, numri (1–6) për informacionin. Burimet e hapura s'marrin kurrë "A" automatikisht. |
| A funksionon me lajme reale? | Po, pipeline-i mbledh nga mediat reale. Metrikat e sakta janë mbi të dhëna sintetike, dhe për to e themi qartë. |
| Pse Serbia? | Sipas mentorëve dhe ngjarjeve të viteve të fundit (p.sh. Banjska 2023, kanali Ibër-Lepenc 2024), aty është rreziku kryesor hibrid për FSK-në. Taksonomia mbulon edhe aktorë të tjerë (Rusi, Kinë, krim i organizuar). |

## Mos thuaj

- "Saktësi 100%" ose numra nga ngjarjet sintetike si rezultate reale.
- "AI vendos": vendimi është i analistit.
- Që mbledhim nga Facebook/Instagram, ose nga Telegram para se lista të miratohet; që demo-ja live është platformë reale.
- Që një postim social "konfirmon" diçka: është gjithmonë F, për verifikim.
- Emra personash ose akuza ndaj individëve.
