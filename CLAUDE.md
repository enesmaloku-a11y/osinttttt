\# Projekti: Prototip AI-OSINT për KSF (Kosovë)



\## Qëllimi

Sistem që mbledh lajme në shqip, serbisht dhe anglisht, nxjerr ngjarje sigurie,

i grupon, vlerëson besueshmërinë me rregulla dhe i tregon analistit në dashboard.

Analisti njeri vendos gjithmonë; sistemi vetëm ndihmon.



\## Rregulla

\- Windows PowerShell, jo bash. Mos jep komanda si export, source, rm -rf.

\- Python 3.11+, SQLite, Streamlit, folium, Ollama (model lokal).

\- Çdo ngjarje duhet të ketë URL burimi, datë dhe gjuhë.

\- Besueshmëria llogaritet me rregulla të qarta (numri i burimeve të pavarura,

&#x20; besueshmëria e burimit, përputhja e detajeve), JO nga modeli.

\- Çdo ngjarje duhet të ketë fushë "boshllëqet" (p.sh. "vetëm një burim").

\- Cache: mos e përpuno të njëjtin artikull dy herë, ruaje JSON-in në SQLite.

\- Mos ruaj të dhëna personale.

\- Kod i thjeshtë, i shkurtër, me komente në shqip.



\## Struktura

collector.py, processor.py, extractor.py, correlator.py, scoring.py,

patterns.py, db.py, main.py, dashboard.py



\## Dosja reference/

Është e madhe (10,000+ skedarë, TypeScript) dhe vetëm për inspirim.

MOS e lexo të gjithën. Lexo vetëm skedarët që të kërkoj. Mos kopjo kod,

merr vetëm idenë dhe shkruaje në Python.

