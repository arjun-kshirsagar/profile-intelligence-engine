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
2. Check `scraper_scripts` for active scripts and try them (best-performing first).
3. If a script succeeds, use it and update success metrics.
4. If active scripts exist but fail, return failure diagnostics from those attempts.
5. If no script succeeds, use Gemini (`GEMINI_MODEL`, default `gemini-3-flash`) to generate parser code.
6. Run generated code immediately. If it fails, capture full traceback and send that error back to Gemini for the next attempt.
7. Retry generation up to `SCRIPT_GENERATION_MAX_ATTEMPTS`.
8. If a generated script succeeds, save it as active in DB and use it immediately.
9. If all attempts fail, return full failure diagnostics in API response.

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

### `POST /intelligence`
Accepts either:
- `linkedin_url`, or
- `name` + optional `qualifiers` (company/title/location etc).

If identity is ambiguous, API returns `needs_clarification` with targeted questions.
If identity is resolved, API runs Google search discovery (with fallback), crawls multi-source web evidence, and returns confidence-scored source records plus a merged summary.

Request body:
```json
{
  "name": "Amit Sharma",
  "qualifiers": ["Delhivery"],
  "max_sources": 12
}
```

Resolved response shape:
```json
{
  "status": "resolved",
  "query": "Amit Sharma",
  "disambiguated": true,
  "clarification_questions": [],
  "candidates": [],
  "sources": [
    {
      "source": "linkedin",
      "url": "https://www.linkedin.com/in/...",
      "title": "...",
      "snippet": "...",
      "text": "...",
      "confidence": 0.86
    }
  ],
  "summary": "Identity resolved for Amit Sharma. Aggregated evidence from 10 sources..."
}
```

Clarification response shape:
```json
{
  "status": "needs_clarification",
  "query": "Amit Sharma",
  "disambiguated": false,
  "clarification_questions": [
    "I found multiple people named Amit Sharma. What is their current or past company?",
    "What is their role/title (for example, Engineer, Founder, PM)?",
    "Do you have a LinkedIn profile URL for the exact person?"
  ],
  "candidates": [],
  "sources": [],
  "summary": "Partial match..."
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
      "script_name": "generated_github",
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
- Gemini-based script generation requires `GEMINI_API_KEY` in environment.
