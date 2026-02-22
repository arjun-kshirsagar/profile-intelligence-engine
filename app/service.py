from typing import Any

from sqlalchemy.orm import Session

from app.extractors import extract_signals
from app.llm import reflective_score_adjustment
from app.scoring import compute_deterministic_score, default_reasoning, make_decision
from app.scrapers import scrape_sources


async def evaluate_profile(
    db: Session,
    name: str,
    github_url: str | None,
    website_url: str | None,
    twitter_url: str | None,
) -> dict[str, Any]:
    scraped, scrape_failures = await scrape_sources(
        db=db,
        github_url=github_url,
        website_url=website_url,
        twitter_url=twitter_url,
    )

    signals = extract_signals(name=name, scraped=scraped)
    deterministic_score, components = compute_deterministic_score(signals)

    llm_adjustment, llm_reasoning = reflective_score_adjustment(
        signals=signals,
        deterministic_score=deterministic_score,
    )

    final_score = max(0, min(100, deterministic_score + llm_adjustment))
    decision = make_decision(final_score)

    if llm_adjustment != 0 and "disabled" not in llm_reasoning.lower():
        reasoning = llm_reasoning
    else:
        reasoning = default_reasoning(final_score, components)

    return {
        "score": final_score,
        "decision": decision,
        "reasoning": reasoning,
        "deterministic_score": deterministic_score,
        "llm_score_adjustment": llm_adjustment,
        "signals": signals,
        "scrape_failures": scrape_failures,
    }
