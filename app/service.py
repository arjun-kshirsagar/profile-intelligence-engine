from typing import Any
import asyncio
from sqlalchemy.orm import Session

from app.extractors import extract_signals
from app.llm.tools import reflective_score_adjustment, generate_search_queries
from app.scoring import compute_deterministic_score, default_reasoning, make_decision
from app.scrapers import scrape_sources, ScrapeResult
from app.search_provider import search_web
from app.logger import logger
import httpx
from bs4 import BeautifulSoup
import re


async def _fetch_and_parse(url: str, source: str) -> ScrapeResult:
    """Helper to fetch search result content and create a ScrapeResult."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            text = response.text
            
            # Simple text extraction
            soup = BeautifulSoup(text, 'html.parser')
            for tag in soup(["script", "style", "noscript", "svg"]):
                tag.decompose()
            clean_text = " ".join(soup.get_text(" ", strip=True).split())
            
            return ScrapeResult(
                source=source,
                url=url,
                ok=True,
                text=clean_text[:5000], # Cap text size
                metadata={}
            )
    except Exception as e:
        logger.warning(f"Failed to fetch content from {url}: {e}")
        return ScrapeResult(source=source, url=url, ok=False, text="", metadata={})


async def evaluate_profile(
    db: Session,
    name: str,
    github_url: str | None,
    website_url: str | None,
    twitter_url: str | None,
) -> dict[str, Any]:
    logger.info(f"Starting evaluation for: {name}")

    # 1. Use Agent to determine search queries
    logger.info("Generating search queries via agent...")
    queries = generate_search_queries(
        name=name,
        github_url=github_url,
        website_url=website_url,
        twitter_url=twitter_url
    )
    logger.info(f"Queries generated: {queries}")

    # 2. Execute searches
    logger.info("Executing searches...")
    search_tasks = [search_web(q, limit=3) for q in queries[:3]] # limit to top 3 queries for perf
    search_results_lists = await asyncio.gather(*search_tasks)
    
    unique_urls = {}
    for results in search_results_lists:
        for res in results:
            if res.url not in unique_urls:
                unique_urls[res.url] = res
    
    logger.info(f"Found {len(unique_urls)} unique search results.")

    # 3. Fetch content from results (up to top 5)
    top_urls = list(unique_urls.keys())[:5]
    fetch_tasks = []
    for url in top_urls:
        source = unique_urls[url].source_domain
        fetch_tasks.append(_fetch_and_parse(url, source))
    
    scraped = await asyncio.gather(*fetch_tasks)
    scrape_failures = [s.__dict__ for s in scraped if not s.ok]

    # NOTE: Original scraping code is preserved in app/scrapers.py but not invoked here as per user request.
    # The 'scraped' list now contains results from Google search results content.

    logger.info("Extracting signals from fetched content...")
    signals = extract_signals(name=name, scraped=scraped)
    deterministic_score, components = compute_deterministic_score(signals)
    logger.info(f"Deterministic score: {deterministic_score}")

    llm_adjustment, llm_reasoning = reflective_score_adjustment(
        signals=signals,
        deterministic_score=deterministic_score,
    )
    logger.info(f"LLM adjustment: {llm_adjustment}")

    final_score = max(0, min(100, deterministic_score + llm_adjustment))
    decision = make_decision(final_score)
    logger.info(f"Final score: {final_score}, Decision: {decision}")

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
