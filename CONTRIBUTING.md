# Kontributi

## Kontrollet para çdo PR-je

```
python kontrollo.py
```

Ekzekuton vetëkontrollet e moduleve (`python <moduli>.py`), `demo.py` dhe, në Windows, nisjen e dashboard-it. Gjithçka punon në një kopje të përkohshme të projektit me bazë të përkohshme: `osint.db` dhe `data/` nuk preken. S'kërkon Ollama dhe rrjet. Duhet të përfundojë me "Të gjitha kontrollet kaluan."

Kur shton një modul me logjikë, shtoji kontrollet te `if __name__ == "__main__":` me `assert`, dhe shtoje modulin te `KONTROLLET` në `kontrollo.py`.

## Demo pa Ollama

```
python demo.py
```

PowerShell:

```
$env:OSINT_DB="demo.db"; streamlit run dashboard.py
```

`demo.db` mbushet me 36 artikujt **sintetikë** të `eval/gold.jsonl`. Në vend të përgjigjes së modelit përdoren etiketat e sakta, ndaj demo tregon pamjen e analistit, jo saktësinë. `demo.py` refuzon të shkruajë në `osint.db`.

## Variablat e mjedisit

| Variabla | Parazgjedhja | Për çfarë |
|---|---|---|
| `OSINT_DB` | `osint.db` | Baza SQLite, p.sh. `demo.db` ose një kopje për prova |
| `OLLAMA_URL` | `http://localhost:11434/api/generate` | Adresa e Ollama-s |
| `OLLAMA_MODEL` | `deepseek-r1:8b` | Modeli lokal |

## Baza e të dhënave

- `articles.raw_text` = teksti siç u mblodh; `processor.py` pastron dhe pret vetëm `teksti`.
  - Kolona shtohet vetë herën e parë që hapet baza, me `ALTER TABLE ... ADD COLUMN`.
  - Për artikujt e papërkthyer mbushet nga `teksti`.
  - Asnjë kolonë tjetër dhe tabela `vendimet` nuk ndryshojnë.
- `db.vendimet()` kthen `{url_kryesor: {...}}` si më parë. Çelësi i ngjarjes mbetet `json.loads(e["burimet"])[0]`.
- `db.url_i_vendimit(burimet, vendimet)` është shtesë: gjen vendimin te cilado URL e ngjarjes, nëse një artikull më i hershëm e ka zhvendosur `burimet[0]`.

## Commit-et

- `git add` vetëm me emra skedarësh. Asnjë force-push.
- Mesazhet e commit-eve dhe PR-ve pa rreshta atribuimi dhe pa emra mjetesh.
