import asyncio
import re
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import get_settings
from app.logger import logger
from app.llm.tools import generate_search_queries

settings = get_settings()

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}

NEWS_DOMAINS = {
    "techcrunch.com",
    "forbes.com",
    "businessinsider.com",
    "economictimes.indiatimes.com",
    "livemint.com",
    "moneycontrol.com",
    "ndtv.com",
    "timesofindia.indiatimes.com",
    "reuters.com",
    "bloomberg.com",
}

TRUST_BY_SOURCE = {
    "linkedin": 0.9,
    "github": 0.86,
    "youtube": 0.75,
    "news": 0.8,
    "about_me": 0.8,
    "x_twitter": 0.65,
    "website": 0.68,
    "other": 0.55,
}


@dataclass
class SearchHit:
    url: str
    title: str
    snippet: str
    source: str
    relevance: float


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _normalize_link(url: str) -> str:
    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path == "/l/":
        target = parse_qs(parsed.query).get("uddg", [])
        if target:
            return unquote(target[0])
    return url


def _source_from_url(url: str) -> str:
    netloc = (urlparse(url).netloc or "").lower()
    if "linkedin.com" in netloc:
        return "linkedin"
    if "github.com" in netloc:
        return "github"
    if "youtube.com" in netloc or "youtu.be" in netloc:
        return "youtube"
    if "about.me" in netloc:
        return "about_me"
    if "twitter.com" in netloc or "x.com" in netloc:
        return "x_twitter"
    if any(domain in netloc for domain in NEWS_DOMAINS):
        return "news"
    if netloc:
        return "website"
    return "other"


def _name_tokens(name: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", name.lower()) if token]


def _score_hit_identity(
    hit_text: str,
    name_tokens: list[str],
    qualifiers: list[str],
    linkedin_url: Optional[str],
    hit_url: str,
) -> float:
    name_score = 0.0
    if name_tokens:
        token_matches = sum(1 for token in name_tokens if token in hit_text)
        name_score = token_matches / len(name_tokens)

    qualifier_score = 0.0
    for qualifier in qualifiers[:4]:
        q = qualifier.lower().strip()
        if q and q in hit_text:
            qualifier_score += 0.14
    qualifier_score = min(0.42, qualifier_score)

    linkedin_direct_bonus = 0.0
    if linkedin_url and "linkedin.com" in hit_url.lower():
        if _normalize_whitespace(linkedin_url.lower()) in hit_url.lower():
            linkedin_direct_bonus = 0.35

    source_bonus = 0.0
    source = _source_from_url(hit_url)
    if source in {"linkedin", "github", "news"}:
        source_bonus = 0.1

    fallback_base = 0.3 if (not name_tokens and linkedin_url and linkedin_direct_bonus > 0) else 0.0
    raw = fallback_base + (0.48 * name_score) + qualifier_score + linkedin_direct_bonus + source_bonus
    return round(min(1.0, max(0.0, raw)), 3)


def _extract_name_from_linkedin(linkedin_url: str) -> Optional[str]:
    parsed = urlparse(linkedin_url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if "in" in path_parts:
        idx = path_parts.index("in")
        if idx + 1 < len(path_parts):
            slug = path_parts[idx + 1]
            cleaned = re.sub(r"[-_]+", " ", slug)
            cleaned = re.sub(r"\b\d+\b", "", cleaned)
            cleaned = _normalize_whitespace(cleaned)
            return cleaned.title() if cleaned else None
    return None


async def _search_duckduckgo(client: httpx.AsyncClient, query: str, limit: int) -> list[dict[str, str]]:
    try:
        response = await client.get(
            "https://duckduckgo.com/html/",
            params={"q": query},
            follow_redirects=True,
            timeout=httpx.Timeout(settings.request_timeout_seconds),
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    out: list[dict[str, str]] = []
    for block in soup.select(".result"):
        link_el = block.select_one(".result__a")
        if not link_el:
            continue
        href = link_el.get("href", "").strip()
        if not href:
            continue
        snippet = ""
        snippet_el = block.select_one(".result__snippet")
        if snippet_el:
            snippet = _normalize_whitespace(snippet_el.get_text(" ", strip=True))
        out.append(
            {
                "url": _normalize_link(href),
                "title": _normalize_whitespace(link_el.get_text(" ", strip=True)),
                "snippet": snippet,
            }
        )
        if len(out) >= limit:
            break
    return out


async def _search_google_html(client: httpx.AsyncClient, query: str, limit: int) -> list[dict[str, str]]:
    try:
        response = await client.get(
            "https://www.google.com/search",
            params={"q": query, "num": str(limit)},
            follow_redirects=True,
            timeout=httpx.Timeout(settings.request_timeout_seconds),
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    out: list[dict[str, str]] = []
    for block in soup.select("div.g"):
        link_el = block.select_one("a[href]")
        title_el = block.select_one("h3")
        if not link_el or not title_el:
            continue
        href = link_el.get("href", "").strip()
        if not href or href.startswith("/search?"):
            continue
        snippet_el = block.select_one("div.VwiC3b") or block.select_one("span.aCOpRe")
        snippet = _normalize_whitespace(snippet_el.get_text(" ", strip=True)) if snippet_el else ""
        out.append(
            {
                "url": _normalize_link(href),
                "title": _normalize_whitespace(title_el.get_text(" ", strip=True)),
                "snippet": snippet,
            }
        )
        if len(out) >= limit:
            break
    return out


async def _fetch_page_text(client: httpx.AsyncClient, url: str, max_chars: int = 2800) -> str:
    try:
        response = await client.get(url, follow_redirects=True, timeout=httpx.Timeout(10.0))
        response.raise_for_status()
    except httpx.HTTPError:
        return ""

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = _normalize_whitespace(soup.get_text(" ", strip=True))
    return text[:max_chars]


def _candidate_key(url: str, name: str, snippet: str) -> str:
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    path = parsed.path.strip("/").lower()
    if "linkedin.com" in netloc and "/in/" in parsed.path.lower():
        slug = path.split("/")[-1]
        return f"linkedin:{slug}"
    if "github.com" in netloc and path:
        return f"github:{path.split('/')[0]}"
    company_hint = _extract_company_hint(snippet)
    if company_hint:
        return f"name+company:{name.lower()}:{company_hint.lower()}"
    return f"name:{name.lower()}"


def _extract_company_hint(text: str) -> Optional[str]:
    matches = re.findall(r"\b(?:at|with|from)\s+([A-Z][A-Za-z0-9&.\- ]{1,40})", text)
    if matches:
        return _normalize_whitespace(matches[0]).rstrip(".,;")
    return None


def _build_clarification_questions(
    name: str,
    qualifiers: list[str],
    candidates: list[dict[str, Any]],
) -> list[str]:
    questions: list[str] = []
    if not qualifiers:
        questions.append(
            f"I found multiple people named {name}. What is their current or past company?"
        )
        questions.append("What is their role/title (for example, Engineer, Founder, PM)?")
        questions.append("Do you have a LinkedIn profile URL for the exact person?")
        return questions

    if len(candidates) > 1:
        options = []
        for candidate in candidates[:3]:
            option = candidate.get("company_hint") or candidate.get("profile_url") or candidate["label"]
            options.append(option)
        questions.append(
            "I still see overlapping profiles. Which one matches your target person: "
            + " | ".join(options)
            + " ?"
        )
        questions.append("Can you add one more qualifier like location, school, or exact title?")

    questions.append("If possible, share the LinkedIn URL to remove ambiguity.")
    return questions


def _build_summary(
    name: str,
    disambiguated: bool,
    candidates: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> str:
    if not disambiguated:
        if not candidates:
            return (
                f"Unable to reliably resolve {name}. Additional qualifiers are required before crawling "
                "and aggregation can be trusted."
            )
        top = candidates[0]
        return (
            f"Partial match for {name} (best candidate confidence {top['confidence']:.2f}), "
            "but multiple close profiles remain. Clarification is required."
        )

    if not sources:
        return f"Identity for {name} appears resolved, but no source pages could be fetched."

    top_sources = sorted(sources, key=lambda item: item["confidence"], reverse=True)[:5]
    labels = [f"{item['source']} ({item['confidence']:.2f})" for item in top_sources]
    return (
        f"Identity resolved for {name}. Aggregated evidence from {len(sources)} sources. "
        f"Strongest sources: {', '.join(labels)}."
    )


async def build_profile_intelligence(
    *,
    linkedin_url: Optional[str],
    name: Optional[str],
    qualifiers: list[str],
    max_sources: int,
) -> dict[str, Any]:
    logger.info(f"Building profile intelligence for name='{name}' linkedin='{linkedin_url}'")
    inferred_name = name or (linkedin_url and _extract_name_from_linkedin(linkedin_url)) or ""
    inferred_name = _normalize_whitespace(inferred_name)
    query_name = inferred_name

    query_input = linkedin_url or query_name
    qualifiers = [q.strip() for q in qualifiers if q and q.strip()]

    if not query_input:
        return {
            "status": "needs_clarification",
            "query": "",
            "disambiguated": False,
            "clarification_questions": ["Please provide at least a name or a LinkedIn profile URL."],
            "candidates": [],
            "sources": [],
            "summary": "Insufficient input.",
        }

    base = query_name or " ".join(qualifiers) or (linkedin_url or "")
    
    logger.info("Generating search queries via agent for intelligence report...")
    search_queries = generate_search_queries(
        name=query_name or base,
        linkedin_url=linkedin_url,
    )
    if not search_queries:
        search_queries = [base]
    
    if linkedin_url:
        search_queries.append(linkedin_url)
    search_queries = list(dict.fromkeys(_normalize_whitespace(item) for item in search_queries if item.strip()))

    timeout = httpx.Timeout(settings.request_timeout_seconds)
    dedup_by_url: dict[str, SearchHit] = {}

    async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=timeout) as client:
        tasks = [_search_google_html(client, query, limit=8) for query in search_queries[:6]]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        if not any(results):
            fallback_tasks = [_search_duckduckgo(client, query, limit=8) for query in search_queries[:6]]
            results = await asyncio.gather(*fallback_tasks, return_exceptions=False)
        for hits in results:
            for item in hits:
                hit_url = item["url"]
                blob = f"{item['title']} {item['snippet']} {hit_url}".lower()
                relevance = _score_hit_identity(
                    hit_text=blob,
                    name_tokens=_name_tokens(query_name or base),
                    qualifiers=qualifiers,
                    linkedin_url=linkedin_url,
                    hit_url=hit_url,
                )
                if relevance <= 0:
                    continue
                hit = SearchHit(
                    url=hit_url,
                    title=item["title"],
                    snippet=item["snippet"],
                    source=_source_from_url(hit_url),
                    relevance=relevance,
                )
                current = dedup_by_url.get(hit.url)
                if current is None or hit.relevance > current.relevance:
                    dedup_by_url[hit.url] = hit

        ranked_hits = sorted(dedup_by_url.values(), key=lambda value: value.relevance, reverse=True)

        grouped: dict[str, list[SearchHit]] = {}
        for hit in ranked_hits[:30]:
            key = _candidate_key(hit.url, query_name or base, hit.snippet)
            grouped.setdefault(key, []).append(hit)

        candidates: list[dict[str, Any]] = []
        for key, items in grouped.items():
            top = sorted(items, key=lambda item: item.relevance, reverse=True)[:3]
            confidence = round(sum(item.relevance for item in top) / len(top), 3)
            lead = top[0]
            company_hint = _extract_company_hint(lead.snippet or lead.title)
            candidates.append(
                {
                    "label": (lead.title[:120] if lead.title else key),
                    "confidence": confidence,
                    "profile_url": lead.url if lead.source in {"linkedin", "github"} else None,
                    "company_hint": company_hint,
                    "evidence": [item.snippet for item in top if item.snippet][:3],
                }
            )

        candidates.sort(key=lambda item: item["confidence"], reverse=True)

        disambiguated = False
        if linkedin_url:
            disambiguated = True
        elif candidates:
            if len(candidates) == 1 and candidates[0]["confidence"] >= 0.55:
                disambiguated = True
            elif len(candidates) >= 2:
                margin = candidates[0]["confidence"] - candidates[1]["confidence"]
                disambiguated = candidates[0]["confidence"] >= 0.7 and margin >= 0.15

        if not disambiguated:
            clarification_questions = _build_clarification_questions(
                name=query_name or base,
                qualifiers=qualifiers,
                candidates=candidates,
            )
            return {
                "status": "needs_clarification",
                "query": query_input,
                "disambiguated": False,
                "clarification_questions": clarification_questions,
                "candidates": candidates[:5],
                "sources": [
                    {
                        "source": hit.source,
                        "url": hit.url,
                        "title": hit.title,
                        "snippet": hit.snippet,
                        "text": "",
                        "confidence": hit.relevance,
                    }
                    for hit in ranked_hits[: min(10, max_sources)]
                ],
                "summary": _build_summary(query_name or base, False, candidates, []),
            }

        selected_name = query_name or base
        crawl_candidates = ranked_hits[: min(30, max_sources * 3)]
        final_sources: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for hit in crawl_candidates:
            if hit.url in seen_urls:
                continue
            seen_urls.add(hit.url)
            page_text = await _fetch_page_text(client, hit.url)
            trust = TRUST_BY_SOURCE.get(hit.source, TRUST_BY_SOURCE["other"])
            confidence = round(min(1.0, (0.65 * hit.relevance) + (0.35 * trust)), 3)
            final_sources.append(
                {
                    "source": hit.source,
                    "url": hit.url,
                    "title": hit.title,
                    "snippet": hit.snippet,
                    "text": page_text,
                    "confidence": confidence,
                }
            )
            if len(final_sources) >= max_sources:
                break

    final_sources.sort(key=lambda item: item["confidence"], reverse=True)
    summary = _build_summary(selected_name, True, candidates, final_sources)
    return {
        "status": "resolved",
        "query": query_input,
        "disambiguated": True,
        "clarification_questions": [],
        "candidates": candidates[:5],
        "sources": final_sources,
        "summary": summary,
    }
