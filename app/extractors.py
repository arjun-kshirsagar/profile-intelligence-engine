import re
from typing import Any

from app.scrapers import ScrapeResult

FOUNDER_KEYWORDS = ["founder", "co-founder", "entrepreneur", "built", "startup"]
SPEAKING_KEYWORDS = ["speaker", "conference", "keynote", "talk", "panel"]


def _extract_years_experience(text: str) -> int:
    patterns = [
        r"(\d{1,2})\+?\s+years?\s+(?:of\s+)?experience",
        r"experience\s+of\s+(\d{1,2})\+?\s+years",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return 0


def extract_signals(name: str, scraped: list[ScrapeResult]) -> dict[str, Any]:
    combined_text = " ".join([result.text for result in scraped if result.ok]).lower()

    github_meta = next((r.metadata for r in scraped if r.source == "github" and r.ok), {})
    website_meta = next((r.metadata for r in scraped if r.source == "website" and r.ok), {})
    twitter_meta = next((r.metadata for r in scraped if r.source == "twitter" and r.ok), {})

    speaking_mentions = sum(combined_text.count(k) for k in SPEAKING_KEYWORDS)

    signals = {
        "name": name,
        "public_repos": int(github_meta.get("public_repos", 0) or 0),
        "followers": int(github_meta.get("followers", 0) or 0),
        "has_founder_keyword": any(k in combined_text for k in FOUNDER_KEYWORDS),
        "years_experience": _extract_years_experience(combined_text),
        "speaking_mentions": speaking_mentions,
        "blog_count": int(website_meta.get("blog_links", 0) or 0),
        "twitter_bio_present": bool(twitter_meta.get("bio")),
        "source_count": len([r for r in scraped if r.ok]),
    }
    return signals
