# Validimi: a i hyn kujt në punë?

Qëllimi: të provojmë me një përdorues të vërtetë (mentor, ish-ushtarak ose analist) që sistemi kursen kohë dhe jep informacion që i besohet. Këto numra hyjnë në pitch si **provë nga përdoruesi**, veçmas nga metrikat e gold set-it sintetik.

## 1. Testi me mentor (20–30 minuta)

**Përgatitja**
- Laptopi i demos me dashboard-in hapur (`streamlit run dashboard.py`), mbi bazën reale ose mbi `demo.db` (`$env:OSINT_DB="demo.db"`).
- Një shfletues tjetër për kërkimin manual (Google, faqet e lajmeve).
- Një kronometër dhe kjo fletë.

**Detyrat.** Secila bëhet dy herë, me rend të ndryshëm për persona të ndryshëm: një herë me kërkim manual, një herë me aplikacionin.

| # | Detyra | Përgjigjja që presim |
|---|---|---|
| 1 | Cilat janë 3 kërcënimet më urgjente për FSK-në në 7 ditët e fundit? | 3 ngjarje me vend, datë dhe burim |
| 2 | A është e vërtetë ngjarja X? Sa burime të pavarura e raportojnë dhe në cilat gjuhë? | Po/jo/e paqartë, me burimet |
| 3 | A ka pasur incidente kibernetike ose të infrastrukturës kritike këtë javë? | Lista ose "jo", me burime |
| 4 | Cila ngjarje duket dezinformim dhe a ngjan me një rast të njohur? | Ngjarja + rasti i ngjashëm, ose "s'ka" |
| 5 | Shkruaj një përmbledhje 5-rreshtash për komandantin. | Raporti ditor ose një tekst i shkurtër |

**Fleta e regjistrimit** (një rresht për detyrë dhe person)

| Personi (roli) | Detyra | Koha manualisht | Koha me app | Përgjigje e saktë? (manual / app) | Dobia 1–5 | Besimi 1–5 | Shënim |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

**Pyetjet në fund (1–5, plus koment)**
1. Sa e dobishme do ishte kjo për punën tuaj të përditshme?
2. A i besoni prioritetit dhe besueshmërisë që tregon? Pse po ose pse jo?
3. A e kuptoni pse një ngjarje del URGJENTE? (arsyet, Admiralty, burimet)
4. Çfarë mungon që do t'ju duhej patjetër?
5. Çfarë do të hiqnit?

**Rregulla**
- Mos i ndihmo gjatë detyrës. Vetëm shëno ku ngec.
- Mos regjistro emra ose të dhëna personale. Vetëm rolin (p.sh. "ish-oficer").
- Shëno edhe gabimet e aplikacionit: alarm i rremë, ngjarje e humbur, bashkim i gabuar.

**Si raportohet në pitch:** "Me N persona: koha mesatare për detyrën 1 ra nga X min në Y min; besimi mesatar Z/5." Nëse N = 1, thuaje: "një test i parë me një mentor". Mos e paraqit si studim.

## 2. Udhëzimet e etiketimit (sot 14:00–17:00)

Etiketat i mësojnë modelit të besueshmërisë (`trajno.py`) çfarë është e vërtetë. Ato janë edhe prova që numri i besueshmërisë matet.

**Si:** hap ngjarjen, lexo **burimet** (lidhjet), pastaj zgjidh:
- ✅ **e konfirmuar**: ngjarja ndodhi ashtu siç përshkruhet. E konfirmon një burim zyrtar (Policia, KFOR, ministria) ose të paktën dy media të pavarura serioze me detaje që përputhen.
- ❌ **e hedhur poshtë**: e rreme, e mohuar zyrtarisht, ose nuk ndodhi siç përshkruhet (vend, kohë ose numra thelbësisht të gabuar).
- ❓ **e pakonfirmuar**: s'mund ta vendosësh. Nuk përdoret për trajnim. Përdore pa hezitim kur s'je i sigurt.

**Rregulla të rëndësishme**
1. **Vendos sipas burimeve, JO sipas përqindjes ose prioritetit në ekran.** Përndryshe modeli mëson rregullat e vjetra, jo të vërtetën.
2. Shkruaj në "Shënim" pse vendose (p.sh. "e konfirmoi Policia në faqen zyrtare").
3. Rreth 1 minutë për ngjarje. Qëllimi: **të paktën 80** ngjarje me të paktën 20 ✅ dhe 20 ❌; ideale 150–300.
4. Dy persona punojnë mbi ngjarje të ndryshme (njëri nga lart, tjetri nga poshtë). Kur s'pajtoheni, zgjidhni ❓.
5. Gjatë 14:00–18:00 askush s'ekzekuton `main.py` mbi bazën reale, sepse correlator.py i rindërton ngjarjet.
6. Mos etiketo rrezikun. Rreziku vjen nga rregullat e `rreziku.py`.

Pas 18:00: `python trajno.py` (Albios). Rezultati shfaqet te skeda **Vlerësimi**.
