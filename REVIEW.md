# REVIEW: tech lead, 2026-11-21 (branch `lead/review-p0`)

## 1. What the project is (confidence: high)

**OSINT Kosova**: a prototype for EDTH Prishtina 2026, challenge 01 (AI-powered OSINT & hybrid threat intelligence), team The Silent Fixers.
It is for a security analyst who has to follow Kosovo news in sq/sr/en.

Data flow: `collector.py` (7 RSS feeds + GDELT → SQLite) → `processor.py` (removes PII, translates to EN with local Ollama) → `extractor.py` (keyword filter, then the LLM returns JSON, validated with rules) → `correlator.py` (merges articles into events, finds gaps, geocodes from a hand-made gazetteer) → `kontekst_*.py` (EUvsDisinfo/EuRepoC context) → `scoring.py` (rule-based credibility) → `patterns.py` (spike alarms) → `dashboard.py` (Streamlit: map, timeline, analyst decision).
Entry points: `main.py`, `ekzekuto.py` (background run and schedule), `streamlit run dashboard.py`, `eval/evaluate.py`, and `demo.py` (new).
Stack: Python 3.11+, SQLite, Ollama `deepseek-r1:8b`, Streamlit/folium/altair. There are no secrets and no hosted APIs.

Current state: the pipeline is complete and the self-checks pass (`python <module>.py` runs asserts). Eval on 33–36 synthetic articles reports recall 1.00.
Before this branch, the dashboard **did not start outside Windows**, and a live demo depended on a slow 8B model (~1 min per article).

## 2. Roadmap

**P0: working end-to-end demo**
- [x] Dashboard starts on Linux/macOS (`ekzekuto.py` msvcrt → fcntl)
- [x] Offline demo DB with no Ollama or network (`demo.py`, `OSINT_DB=demo.db`)
- [x] Run instructions for Linux/macOS, `.env.example`
- [x] EUvsDisinfo context is actually called by the pipeline and shown in the dashboard
- [ ] Merge the open branches in this order: `kontekst-kibernetik` → `besueshmeria-model` → `klasifikimi-taksonomia`. All three merge cleanly into main and into each other (`git merge-tree`, checked).
- [ ] One full live run on the demo laptop: `ollama pull`, then `python main.py 20`, then the dashboard. Record the time.
- [ ] Freeze `eval/rezultati.json` from a real model run for the pitch slide.

**P1**
- Pin versions in `requirements.txt`. Streamlit already warns that `use_container_width` is going away after 2025-12-31.
- A faster model for extraction (see table 4). Re-run the eval to compare.
- A stable key for analyst decisions (finding F3).
- One `check` script that runs every module's self-check.

**P2**
- Multilingual embeddings for correlation and less translation work.
- GeoNames gazetteer in place of the hand-made `VENDET`/`RAJONI`.
- Detect syndicated or copied stories, so that copies don't count as independent sources.

## 3. Findings

| Sev | File:line | Problem | Fix |
|---|---|---|---|
| **P0** | `ekzekuto.py:10` (old) | `import msvcrt` is Windows-only, and `dashboard.py` imports `ekzekuto`, so the dashboard crashed on Linux/macOS | **Fixed** a2d8268: fcntl on POSIX; schtasks gives a cron message |
| **P0** | — | No demo possible without Ollama plus the 8B model plus network | **Fixed** 78f6433: `demo.py` |
| High | `kontekst_dezinformim.py:194` | `pasuro_te_gjitha()` was never called (dead code); the dashboard did not show `konteksti` | **Fixed** 078ccb0 |
| Med | `dashboard.py:38` + `db.py` `vendimet` | The decision key is the URL of the *earliest* article. If a later run adds an older article to the event, the key changes and the analyst's decision silently disappears from the event | Use a stable event id: keep the key, but on lookup match any URL in `burimet` (owner: dashboard) |
| Med | `correlator.py:153` | Compares only with `grup[0]`, so the merge is not transitive (A~B, B~C, but A≁C makes 2 events) | Compare with any member of the group (owner: correlator) |
| Med | `scoring.py:24,19` | Every GDELT domain counts as an independent source at 0.4. Republished wire copy pushes credibility up | Merge near-duplicate texts first (P2); add `MEDIAT` for kossev.info and rts.rs |
| Med | `processor.py:107` | Overwrites the raw `teksti` with the cleaned/cut text, so `verifiko` is weaker after translation (README says this) | Store the cleaned text in its own column (schema change: the team decides) |
| Med (legal) | `collector.py:55`, `db.py:18` | Full article text is scraped (no robots.txt check) and stored together with personal names; only `summary` is masked | Keep `*.db` out of git (already done); state in the pitch "research use, public sources"; P2: store only translation/summary |
| Med (legal) | `kontekst_kibernetik.py` (branch) | EuRepoC terms: non-commercial/scientific use only | Keep it as written in the docstring; mention it if the project becomes commercial |
| Low (sec) | `dashboard.py` folium popup | Article/LLM titles went raw into popup HTML | **Fixed** 11a3f85 + e3753c0: `html.escape` plus `` ` ``/`$`, because folium places the text inside a JS template literal |
| Low | `eval/evaluate.py:29` | The comment says "the dashboard reads rezultati.json", but nothing reads it | Owner of eval/dashboard: show it or delete the comment (file is hot, not touched) |
| Low | `processor.py:73` | 300 s timeout × 3 tries per chunk; one slow article blocks the run | Lower it, or move it to env |
| Low | `.gitignore` | `CLAUDE.md` is ignored, so agent instructions are not shared between agents | Put team rules in a committed `AGENTS.md` |
| Info | — | No secrets in the repo (grep for key/token/password: 0) | — |

## 4. Better options

| Area | Current | Better | Why | Cost | Decision |
|---|---|---|---|---|---|
| LLM | Ollama `deepseek-r1:8b` (reasoning model, `think=False`) | `qwen2.5:7b-instruct` or `llama3.1:8b` | Extraction does not need reasoning; instruct models are faster and steadier at JSON. Now a single env var: `OLLAMA_MODEL` | S | **Try now** with `eval/evaluate.py`, switch if recall holds |
| Translate→extract | 2+ LLM calls per article | Extract directly from the original language | Halves the time, but small models are weak in Albanian | M | Later, after the eval |
| Correlation | Jaccard on English summaries | `paraphrase-multilingual-MiniLM` embeddings | Works across languages without exact words | M | Later (P2) |
| Geocoding | Hand-made dictionary | GeoNames XK/RS/MK/AL offline | Covers villages | M | Later; current one is deterministic and tested |
| Storage | SQLite | — | Fine for a prototype | — | Keep |
| UI | Streamlit | — | Fast; the team knows it | — | Keep |
| Scheduler | schtasks (Windows) / cron | — | Simple | — | Keep |
| Collection | feedparser + trafilatura + gdeltdoc | — | The right standard libraries | — | Keep |
| Credibility | Rules → logistic model (`besueshmeria-model` branch) | — | Calibrated from analyst decisions; falls back to rules when there is no model | — | Keep, merge |

## 5. Work split (by file, no overlap)

| Owner | Files | Task now |
|---|---|---|
| Afron (`klasifikimi-taksonomia`) | `extractor.py`, `correlator.py`, `eval/*` | Open the PR and merge; then fix the transitive correlation (F `correlator.py:153`) |
| Albios (`besueshmeria-model`, `kontekst-kibernetik`) | `scoring.py`, `trajno.py`, `vektori.py`, `kontekst_kibernetik.py` | Merge the two PRs; call `kontekst_kibernetik` from `main.py` next to EUvsDisinfo (one line) |
| Enes | `dashboard.py`, `patterns.py`, `ekzekuto.py` | Stable decision key (F3), show `eval/rezultati.json`, `width="stretch"` |
| Lead | `main.py`, `db.py`, `demo.py`, `processor.py`, `collector.py`, `README.md`, `REVIEW.md` | Merge order, pinned requirements, check script |

**Shared contracts (don't change them without telling the others)**
- `articles.rezultati_json` = the keys of `extractor.FUSHAT` (+ `arsyeja` / `demo`).
- `events.detajet_json`: `rajonale, mediat, gjuhet, aktoret, saktesia_vendit, saktesia_dates, killed/injured/arrested[], arsyetimi[], konteksti[]`.
  Each item in `konteksti`: `{burimi, lloji: "rast_i_ngjashem"|"statistike", titulli, url|null, data, ngjashmeria, arsyeja}`. Each module deletes only its own items (by `burimi`).
- `vendimet.url_kryesor` = any URL of the event; the lookup uses `db.url_i_vendimit(burimet, vendimet)` (the URL with the newest decision, otherwise `burimet[0]`).
- Env: `OSINT_DB` (default `osint.db`), `OLLAMA_URL`, `OLLAMA_MODEL`, `EUREPOC_XLSX`.
- Order in `main.py`: correlator → kontekst_* → scoring (scoring keeps the other keys in `detajet_json`).

## 6. What I built (this branch)

| Commit | What |
|---|---|
| a2d8268 | `ekzekuto.py` cross-platform; the dashboard starts on Linux/macOS (tested with Streamlit AppTest, and lock tested across 2 processes) |
| 903328a | `OSINT_DB` / `OLLAMA_URL` / `OLLAMA_MODEL` + `.env.example` |
| 78f6433 | `demo.py`: 36 synthetic articles → 15 events (cross-language merges, regional events) without Ollama |
| 11a3f85, e3753c0 | Map popups: escape HTML and JS template-literal characters (tested with a payload) |
| 02dc861 | README: Linux/macOS, demo, cron, outdated limitations removed |
| 078ccb0 | EUvsDisinfo context in the pipeline and in the dashboard |

I did **not** touch the hot files (`extractor.py`, `correlator.py`, `eval/*`, changed at 11:28 today), or `scoring.py` (open branch).
