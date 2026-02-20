# Profile Intelligence Engine (MVP)

## 1. Problem statement
Build a minimal engine that ingests a person's public profile links, extracts structured signals, computes a transparent score, and returns `ACCEPT` or `REJECT` with concise reasoning.

## 2. Assumptions
- Inputs include `name` and optional `github_url`, `website_url`, `twitter_url`.
- Only publicly accessible pages are evaluated.
- Top-tier profile quality is approximated using proxy internet signals.
- LinkedIn scraping avoided due to ToS and anti-bot protections.

## 3. Architecture
`Client -> FastAPI -> Scraper -> Signal Extractor -> Scoring Engine -> PostgreSQL -> Response`

Components:
- `app/main.py`: API routes and persistence.
- `app/scrapers.py`: Async scraping with `httpx` + HTML parsing (`BeautifulSoup`).
- `app/extractors.py`: Signal extraction from scraped text and metadata.
- `app/scoring.py`: Deterministic weighted scoring and decisioning.
- `app/llm.py`: Optional reflective layer (OpenAI) to critique deterministic score.
- `app/models.py`: SQLAlchemy evaluation record.

## 4. Scoring philosophy
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

Example output:
```json
{
  "score": 78,
  "decision": "ACCEPT",
  "reasoning": "Strong public impact + leadership indicators"
}
```

### Why hybrid evaluation
Deterministic scoring provides consistency and transparency.
The optional reflective LLM step critiques edge cases where context matters (for example, non-GitHub signals for elite operators).

Top 1% is relative - this MVP uses proxy signals.

## 5. Tradeoffs
- Twitter/X pages can be partially dynamic, so extraction quality can vary.
- Public internet signals can over-represent people who publish more content.
- Bias and fairness concerns must be addressed.
- Manual review loop recommended.
- Cold start problem exists for private individuals.

## 6. Future improvements
- Add robust adapters per source (GitHub API mode, richer website crawling constraints).
- Add confidence intervals and uncertainty scoring.
- Add evaluator calibration dataset and regression tests.
- Future: network graph centrality scoring.
- Add human-in-the-loop override workflow.

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

Response body:
```json
{
  "score": 78,
  "decision": "ACCEPT",
  "reasoning": "Strong signals in impact, leadership.",
  "deterministic_score": 74,
  "llm_score_adjustment": 4,
  "signals": {
    "name": "Jane Doe",
    "public_repos": 42,
    "followers": 820,
    "has_founder_keyword": true,
    "years_experience": 9,
    "speaking_mentions": 3,
    "blog_count": 5,
    "twitter_bio_present": true,
    "source_count": 3
  }
}
```

## Local run
1. Create Postgres DB (example: `profile_engine`).
2. Install deps:
```bash
python -m venv .venv
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
