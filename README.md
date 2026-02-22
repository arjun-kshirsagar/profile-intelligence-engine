# Profile Intelligence Engine (MVP)

## 1. Problem statement
Build a minimal engine that ingests a person's public profile links, extracts structured signals, computes a transparent score, and returns `ACCEPT` or `REJECT` with concise reasoning.

## 2. Assumptions
- Inputs include `name` and optional `github_url`, `website_url`, `twitter_url`.
- Only publicly accessible pages are evaluated.
- Top-tier profile quality is approximated using proxy internet signals.
- LinkedIn scraping avoided due to ToS and anti-bot protections.

## 3. Architecture
`Client -> FastAPI -> Scraper Agent -> Signal Extractor -> Scoring Engine -> PostgreSQL -> Response`

Components:
- `app/main.py`: API routes and persistence.
- `app/scrapers.py`: Agentic scraper runtime with `httpx` + `BeautifulSoup`.
- `app/extractors.py`: Signal extraction from scraped text and metadata.
- `app/scoring.py`: Deterministic weighted scoring and decisioning.
- `app/llm.py`: Optional reflective layer + optional scraper script generator.
- `app/models.py`: SQLAlchemy models for evaluations, scraper scripts, and execution logs.

## 4. Scraper-agent loop
For each source (`github`, `website`, `twitter`):
1. Fetch HTML.
2. Try active scripts from `scraper_scripts` (best-performing first).
3. If a script succeeds, use it and update success metrics.
4. If a script fails, capture `script_code` + `error` and keep trying.
5. If all fail, optionally ask LLM to generate a replacement parser script.
6. If generated script succeeds, save it to DB for future runs.
7. If generation fails, return failure diagnostics in API response.

This gives agent-like adaptation without full multi-agent orchestration.

## 5. Scoring philosophy
### Weighted model
```python
weights = {
    "experience": 0.3,
    "impact": 0.25,
    "leadership": 0.2,
    "reputation": 0.15,
    "signal_density": 0.1,
}
```

Score is normalized to `0..100`.
Threshold is `70`:
- `score >= 70` => `ACCEPT`
- `score < 70` => `REJECT`

Top 1% is relative - this MVP uses proxy signals.

## 6. Tradeoffs
- Twitter/X pages can be partially dynamic, so extraction quality can vary.
- Executing dynamic scraper scripts needs hardening before production sandboxing.
- Public internet signals can over-represent people who publish more content.
- Bias and fairness concerns must be addressed.
- Manual review loop recommended.
- Cold start problem exists for private individuals.

## 7. Future improvements
- Add strict sandboxing for script execution (separate process + resource limits).
- Add richer script quality checks before activation.
- Add confidence intervals and uncertainty scoring.
- Add evaluator calibration dataset and regression tests.
- Future: network graph centrality scoring.

## API
### `POST /evaluate`
Request body:
```json
{
  "name": "Jane Doe",
  "github_url": "https://github.com/janedoe",
  "website_url": "https://janedoe.dev",
  "twitter_url": "https://x.com/janedoe"
}
```

Response includes `scrape_failures` whenever any script attempts fail:
```json
{
  "score": 74,
  "decision": "ACCEPT",
  "reasoning": "Strong signals in impact, leadership.",
  "deterministic_score": 74,
  "llm_score_adjustment": 0,
  "signals": {},
  "scrape_failures": [
    {
      "source": "github",
      "url": "https://github.com/janedoe",
      "script_id": 1,
      "script_name": "default_github_v1",
      "script_code": "def extract(...)",
      "error": "ValueError: ..."
    }
  ]
}
```

## Local run
1. Create Postgres DB (example: `profile_engine`).
2. Install deps:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
3. Configure environment:
```bash
cp .env.example .env
```
4. Start server:
```bash
uvicorn app.main:app --reload
```

## Notes
- This is an MVP and intentionally avoids microservices, queues, and background workers.
- SQLAlchemy table creation happens at app startup for simplicity.
