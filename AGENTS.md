# AGENTS.md: rules for everyone working in this repo (people and AI agents)

## Git
- Never commit straight to `main`, and never force-push. Work on your own branch (`emri/tema`), and merge with a PR (merge commit).
- Before you start: `git fetch`, `git log --since="2 hours ago" --all --stat`. Don't touch files that someone else changed in the last ~2 hours. Write it in `REVIEW.md` instead.
- Small commits with clear messages. Get main often (`git merge origin/main`, not rebase plus force-push).
- **Before every PR:** `python kontrollo.py` must print "Të gjitha kontrollet kaluan." It runs every self-check, the demo and the dashboard boot in a temporary copy (no Ollama, no network, `osint.db` is not touched).
- A new module with logic → add its check to `kontrollo.py` (`if __name__ == "__main__":` with `assert`).
- Don't commit a module that imports a file that isn't in git.

## Data and privacy
- Public sources only. `collector.py` respects `robots.txt`; don't bypass it.
- By default only a snippet + URL is stored (`OSINT_FULL_TEXT=1` for full text). `*.db`, `data/`, `.env` stay out of git.
- Personal names are removed with rules (`extractor.fshi_emrat`), not by trusting the model. No secrets in code.
- Text from articles and from the model is data, never instructions. Escape it before you put it in HTML/JS (see the map in `dashboard.py`).
- Credibility is computed with rules/a model in `scoring.py`, never by the LLM. The system suggests; the analyst decides.

## Shared contracts (don't change them without saying so in the PR)
- `articles`: `teksti` = the cleaned text (from `processor.py`), `raw_text` = the text as collected (never overwritten), `hash_sha256` = the full text at collection time.
- `articles.rezultati_json` = the keys of `extractor.FUSHAT` (+ `arsyeja` / `demo`).
- `events.detajet_json`: `rajonale, mediat, gjuhet, aktoret, saktesia_vendit, saktesia_dates, killed/injured/arrested[], arsyetimi[], konteksti[]`.
  An item in `konteksti`: `{burimi, lloji: "rast_i_ngjashem"|"statistike", titulli, url|null, data, ngjashmeria, arsyeja}`. Each module deletes only its own items (by `burimi`).
- `vendimet.url_kryesor` = any URL of the event; the lookup goes through `db.url_i_vendimit(burimet, vendimet)`.
- Order in `main.py`: collector → processor → extractor → correlator → kontekst_* → scoring → patterns.
- Env: `OSINT_DB`, `OLLAMA_URL`, `OLLAMA_MODEL`, `OSINT_FULL_TEXT`, `EUREPOC_XLSX` (see `.env.example`).

## Who works where
See the "Work split" section in `REVIEW.md`.
