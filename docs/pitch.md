# Pitch: The Silent Fixers (3–5 minuta)

**Mesazhi në një fjali:** *Sistemi kthen mijëra lajme në shqip, serbisht dhe anglisht në pak kërcënime hibride për FSK-në, të renditura sipas rrezikut dhe besueshmërisë, me burime dhe arsyetim, plotësisht lokalisht, dhe vendimin final e merr gjithmonë analisti.*

## Struktura

| Koha | Pjesa | Çfarë thuhet / tregohet |
|---|---|---|
| 0:00–0:30 | **Problemi** | Analisti i FSK-së ndjek lajme në tri gjuhë nga dhjetëra burime. Kërcënimet hibride nga Serbia (lëvizje ushtarake, dronë, sabotim, dezinformim, sulme kibernetike) humbasin në zhurmë, dhe s'dihet çfarë është e vërtetë. |
| 0:30–2:30 | **Demo** | Shih rrjedhën më poshtë. |
| 2:30–3:30 | **Si punon dhe pse i besohet** | Pipeline lokal me Ollama, pa cloud. LLM-i vetëm nxjerr faktet. Rreziku vjen nga rregulla të qarta, besueshmëria nga provat (burime të pavarura, gjuhë, kontradikta) dhe kalibrohet nga vendimet e analistit. Admiralty sipas standardit NATO. |
| 3:30–4:15 | **Prova** | Metrikat nga skeda Vlerësimi, me shënimin "mbi artikuj sintetikë". Testi me mentorin (docs/validimi.md): koha para/pas, besimi 1–5. |
| 4:15–5:00 | **Kufizimet dhe hapi tjetër** | Sinqerisht: të dhënat sintetike, aktori nga modeli duhet verifikuar, lista e EUvsDisinfo kërkon eksport. Hapi tjetër: më shumë etiketa nga analistë të vërtetë, burime zyrtare, pilot me FSK-në. |

## Rrjedha e demos (rreth 2 minuta)

1. **Skeda Urgjente:** "Këto janë kërcënimet që kërkojnë vëmendje sot." Hap kartelën e parë.
2. **Brenda kartelës:** prioriteti, rreziku 0–100 me arsyet ("pse ky rrezik"), besueshmëria me arsyet, kodi Admiralty (p.sh. B2), burimet në disa gjuhë, boshllëqet e informacionit.
3. **Një URGJENTE "për verifikim":** "Rrezik i lartë, por vetëm një kanal Telegram. Sistemi nuk thotë vepro, thotë verifiko."
4. **Konteksti i jashtëm:** një dezinformim që ngjan me një rast të dokumentuar nga EUvsDisinfo, nëse CSV-ja është vendosur.
5. **Vendimi i analistit:** konfirmo një ngjarje. "Çdo vendim e mëson modelin."
6. **Harta dhe kronologjia:** ngjarjet rajonale (globi) dhe ato në veri.
7. **Raporti ditor:** butoni "Gjenero raportin ditor" → BLUF në një faqe për komandantin.

## Plani rezervë

- Para prezantimit: `python demo.py`, pastaj `$env:OSINT_DB="demo.db"; streamlit run dashboard.py`. Punon pa Ollama dhe pa internet.
- Bëj screenshot-e të çdo hapi, në rast se laptopi ose rrjeti dështon.
- Mos nis `main.py` gjatë prezantimit: modeli 8B kërkon rreth 1 minutë për artikull.

## Pyetje që mund të bëjë juria

| Pyetja | Përgjigjja |
|---|---|
| Si e dini që 85% do të thotë 85%? | Modeli kalibrohet nga vendimet e analistit dhe matet me validim të kryqëzuar. Deri sa të ketë mjaft etiketa, besueshmëria vjen nga rregulla të qarta dhe e themi hapur. |
| Pse s'e vendos LLM-i besueshmërinë? | Modelet gjuhësore e japin keq sigurinë e tyre. Ne e llogarisim nga provat që mund t'i kontrolloni. |
| Po nëse një lajm ripostohet 10 herë? | Kopjet e të njëjtit lajm s'duhet të numërohen si burime të pavarura. (Thuaj gjendjen e saktë të rregullimit në ditën e prezantimit.) |
| Të dhënat personale? | Emrat e personave maskohen me rregulla. Ruhet vetëm fragmenti dhe URL-ja, `robots.txt` respektohet, asgjë s'del nga kompjuteri. |
| A funksionon me lajme reale? | Po, pipeline-i mbledh nga mediat reale. Metrikat e sakta janë mbi të dhëna sintetike, dhe për to e themi qartë. |
| Pse Serbia? | Sipas mentorëve dhe ngjarjeve të viteve të fundit (p.sh. Banjska 2023, kanali Ibër-Lepenc 2024), aty është rreziku kryesor hibrid për FSK-në. Taksonomia mbulon edhe aktorë të tjerë (Rusi, Kinë, krim i organizuar). |

## Mos thuaj

- "Saktësi 100%" ose numra nga 200 ngjarjet sintetike si rezultate reale.
- "AI vendos": vendimi është i analistit.
- Emra personash ose akuza ndaj individëve.
