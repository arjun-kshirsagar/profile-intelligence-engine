import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup
from openai import OpenAI

from app.config import get_settings

settings = get_settings()

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}

ATTRIBUTE_WEIGHTS = {
    "name": 0.4,
    "company": 0.3,
    "designation": 0.2,
    "location": 0.1,
}

SOURCE_WEIGHTS = {
    "linkedin": 1.0,
    "company_website": 0.9,
    "major_news": 0.8,
    "github": 0.7,
    "youtube": 0.6,
    "personal_blog": 0.4,
    "other": 0.5,
}

MAJOR_NEWS_DOMAINS = {
    "reuters.com",
    "bloomberg.com",
    "forbes.com",
    "techcrunch.com",
    "wsj.com",
    "nytimes.com",
    "economictimes.indiatimes.com",
    "business-standard.com",
}


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source_domain: str


@dataclass
class Candidate:
    result: SearchResult
    extracted: dict[str, Optional[str]]
    attribute_match_score: float
    source_type: str
    source_confidence: float


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _normalize_link(url: str) -> str:
    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path == "/l/":
        target = parse_qs(parsed.query).get("uddg", [])
        if target:
            return unquote(target[0])
    return url


def _domain(url: str) -> str:
    return (urlparse(url).netloc or "").lower()


def _source_type(domain: str, company_hint: Optional[str]) -> str:
    if "linkedin.com" in domain:
        return "linkedin"
    if "github.com" in domain:
        return "github"
    if "youtube.com" in domain or "youtu.be" in domain:
        return "youtube"
    if any(news in domain for news in MAJOR_NEWS_DOMAINS):
        return "major_news"
    if "blog" in domain or "medium.com" in domain or "substack.com" in domain:
        return "personal_blog"
    if company_hint:
        normalized = re.sub(r"[^a-z0-9]", "", company_hint.lower())
        domain_no_tld = re.sub(r"[^a-z0-9]", "", domain.split(":")[0].split(".")[0])
        if normalized and domain_no_tld and normalized in domain_no_tld:
            return "company_website"
    return "other"


def _extract_name_from_linkedin_url(linkedin_url: Optional[str]) -> Optional[str]:
    if not linkedin_url:
        return None
    parsed = urlparse(linkedin_url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if "in" in path_parts:
        idx = path_parts.index("in")
        if idx + 1 < len(path_parts):
            slug = path_parts[idx + 1]
            slug = re.sub(r"[-_]+", " ", slug)
            slug = re.sub(r"\d+", "", slug)
            cleaned = _normalize_whitespace(slug)
            if cleaned:
                return cleaned.title()
    return None


def _string_match(input_value: Optional[str], extracted_value: Optional[str]) -> float:
    if not input_value:
        return 0.0
    if not extracted_value:
        return 0.0

    left = _normalize_whitespace(input_value).lower()
    right = _normalize_whitespace(extracted_value).lower()
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if left in right or right in left:
        return 0.5

    left_tokens = {tok for tok in re.split(r"[^a-z0-9]+", left) if tok}
    right_tokens = {tok for tok in re.split(r"[^a-z0-9]+", right) if tok}
    if not left_tokens or not right_tokens:
        return 0.0

    overlap = len(left_tokens & right_tokens) / len(left_tokens)
    if overlap >= 0.7:
        return 0.5
    return 0.0


def _weighted_attribute_match(input_payload: dict[str, Optional[str]], extracted: dict[str, Optional[str]]) -> float:
    active_weights = {
        key: weight
        for key, weight in ATTRIBUTE_WEIGHTS.items()
        if input_payload.get(key) and _normalize_whitespace(str(input_payload.get(key)))
    }
    if not active_weights:
        active_weights = {"name": ATTRIBUTE_WEIGHTS["name"]}

    score = 0.0
    total = 0.0
    for key, weight in active_weights.items():
        total += weight
        score += _string_match(input_payload.get(key), extracted.get(key)) * weight

    if total <= 0:
        return 0.0
    return round(score / total, 3)


def _build_queries(input_payload: dict[str, Optional[str]]) -> tuple[list[str], bool]:
    name = _normalize_whitespace(input_payload.get("name") or "")
    company = _normalize_whitespace(input_payload.get("company") or "")
    designation = _normalize_whitespace(input_payload.get("designation") or "")
    location = _normalize_whitespace(input_payload.get("location") or "")
    linkedin_url = input_payload.get("linkedin_url")

    ambiguity_risk = False
    queries: list[str] = []

    if linkedin_url:
        queries.append(linkedin_url)

    if name:
        qualifiers = " ".join(filter(None, [company, designation, location]))
        if company:
            queries.extend(
                [
                    f'"{name}" "{company}"',
                    f'"{name}" "{company}" interview',
                    f'"{name}" "{company}" site:linkedin.com',
                    f'"{name}" "{company}" site:github.com',
                    f'"{name}" "{company}" site:youtube.com',
                    f'"{name}" "{company}" news',
                ]
            )
        else:
            ambiguity_risk = True
            queries.extend(
                [
                    f'"{name}" linkedin',
                    f'"{name}" profile',
                    f'"{name}" github',
                    f'"{name}" interview',
                ]
            )

        if qualifiers:
            queries.append(f'"{name}" {qualifiers}')

    return list(dict.fromkeys(q for q in queries if q.strip())), ambiguity_risk


async def _search_duckduckgo(client: httpx.AsyncClient, query: str, limit: int) -> list[SearchResult]:
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
    results: list[SearchResult] = []
    for block in soup.select(".result"):
        link_el = block.select_one(".result__a")
        if not link_el:
            continue
        href = _normalize_link(link_el.get("href", "").strip())
        if not href:
            continue

        snippet_el = block.select_one(".result__snippet")
        snippet = _normalize_whitespace(snippet_el.get_text(" ", strip=True) if snippet_el else "")

        results.append(
            SearchResult(
                title=_normalize_whitespace(link_el.get_text(" ", strip=True)),
                url=href,
                snippet=snippet,
                source_domain=_domain(href),
            )
        )
        if len(results) >= limit:
            break

    return results


async def _search_web(queries: list[str], max_per_query: int) -> list[SearchResult]:
    timeout = httpx.Timeout(settings.request_timeout_seconds)
    async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=timeout) as client:
        tasks = [_search_duckduckgo(client, query, max_per_query) for query in queries]
        grouped_results = await asyncio.gather(*tasks, return_exceptions=False)

    dedup: dict[str, SearchResult] = {}
    for hits in grouped_results:
        for hit in hits:
            if hit.url not in dedup:
                dedup[hit.url] = hit
    return list(dedup.values())


async def _fetch_page_text(client: httpx.AsyncClient, url: str, max_chars: int = 5000) -> str:
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


def _heuristic_extract(result: SearchResult, page_text: str) -> dict[str, Optional[str]]:
    blob = _normalize_whitespace(f"{result.title}. {result.snippet}. {page_text}")

    company_match = re.search(r"\b(?:at|with|from)\s+([A-Z][A-Za-z0-9&.\- ]{1,40})", blob)
    location_match = re.search(r"\b(?:based in|located in|from)\s+([A-Z][A-Za-z .\-]{1,40})", blob)

    return {
        "name": None,
        "company": _normalize_whitespace(company_match.group(1)).rstrip(".,;") if company_match else None,
        "designation": None,
        "location": _normalize_whitespace(location_match.group(1)).rstrip(".,;") if location_match else None,
        "education": None,
        "short_bio": blob[:280] if blob else None,
    }


def _llm_extract(result: SearchResult, page_text: str) -> Optional[dict[str, Optional[str]]]:
    if not settings.openai_api_key:
        return None

    client = OpenAI(api_key=settings.openai_api_key)
    prompt = (
        "Extract the following fields from the text and return strict JSON only with keys: "
        "name, company, designation, location, education, short_bio. "
        "If unknown, set null.\n\n"
        f"Title: {result.title}\n"
        f"Snippet: {result.snippet}\n"
        f"URL: {result.url}\n"
        f"Text: {page_text[:3500]}"
    )

    try:
        completion = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        content = completion.choices[0].message.content or "{}"
        parsed = json.loads(content)
        return {
            "name": parsed.get("name"),
            "company": parsed.get("company"),
            "designation": parsed.get("designation"),
            "location": parsed.get("location"),
            "education": parsed.get("education"),
            "short_bio": parsed.get("short_bio"),
        }
    except Exception:
        return None


async def _extract_candidates(
    search_results: list[SearchResult],
    input_payload: dict[str, Optional[str]],
    max_sources: int,
) -> list[Candidate]:
    timeout = httpx.Timeout(settings.request_timeout_seconds)
    async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=timeout) as client:
        tasks = [_fetch_page_text(client, result.url) for result in search_results[: max_sources * 2]]
        page_texts = await asyncio.gather(*tasks, return_exceptions=False)

    candidates: list[Candidate] = []

    for result, page_text in zip(search_results[: max_sources * 2], page_texts):
        extracted = _llm_extract(result, page_text) or _heuristic_extract(result, page_text)

        if not extracted.get("name") and input_payload.get("name"):
            extracted["name"] = input_payload["name"]

        attribute_score = _weighted_attribute_match(input_payload, extracted)
        source_type = _source_type(result.source_domain, input_payload.get("company"))
        source_weight = SOURCE_WEIGHTS.get(source_type, SOURCE_WEIGHTS["other"])
        source_confidence = round(attribute_score * source_weight, 3)

        candidates.append(
            Candidate(
                result=result,
                extracted=extracted,
                attribute_match_score=attribute_score,
                source_type=source_type,
                source_confidence=source_confidence,
            )
        )

    candidates.sort(key=lambda item: item.attribute_match_score, reverse=True)
    return candidates[:max_sources]


def _build_clarification_question(input_payload: dict[str, Optional[str]], top_candidate: Optional[Candidate]) -> str:
    name = input_payload.get("name") or "this person"
    company = top_candidate.extracted.get("company") if top_candidate else None
    role = top_candidate.extracted.get("designation") if top_candidate else None
    location = top_candidate.extracted.get("location") if top_candidate else None

    hints = [part for part in [company, role, location] if part]
    if hints:
        return f"Multiple profiles match. Is this the {name} associated with {' | '.join(hints)}?"
    return f"Multiple profiles match for {name}. Can you confirm company, role, or location?"


def _resolve_identity(candidates: list[Candidate], input_payload: dict[str, Optional[str]]) -> tuple[bool, Optional[str], float]:
    if not candidates:
        return True, None, 0.0

    top_score = candidates[0].attribute_match_score
    second_score = candidates[1].attribute_match_score if len(candidates) > 1 else 0.0

    ambiguous = top_score < 0.6 or (len(candidates) > 1 and (top_score - second_score) < 0.15)
    if ambiguous:
        return False, _build_clarification_question(input_payload, candidates[0]), top_score

    return True, None, top_score


def _aggregate_identity(candidates: list[Candidate], resolved_confidence: float) -> dict[str, Any]:
    if not candidates:
        return {
            "name": None,
            "company": None,
            "designation": None,
            "location": None,
            "confidence": round(resolved_confidence, 3),
        }

    top = sorted(candidates, key=lambda item: item.source_confidence, reverse=True)

    def pick(field: str) -> Optional[str]:
        for candidate in top:
            value = candidate.extracted.get(field)
            if value:
                return _normalize_whitespace(value)
        return None

    return {
        "name": pick("name"),
        "company": pick("company"),
        "designation": pick("designation"),
        "location": pick("location"),
        "confidence": round(resolved_confidence, 3),
    }


def _build_summary(candidates: list[Candidate], ambiguity_flag: bool, clarification_question: Optional[str]) -> str:
    if ambiguity_flag:
        question = clarification_question or "Please provide one more qualifier to resolve identity."
        return f"Identity is ambiguous across discovered sources. {question}"

    if not candidates:
        return "No reliable public sources were found to build a summary."

    top_sources = sorted(candidates, key=lambda item: item.source_confidence, reverse=True)[:4]
    fragments = []
    for item in top_sources:
        info = item.extracted
        role = info.get("designation") or "professional"
        company = info.get("company") or "unknown company"
        fragments.append(f"{role} at {company}")

    summary_seed = "; ".join(fragments)

    if settings.openai_api_key:
        client = OpenAI(api_key=settings.openai_api_key)
        try:
            completion = client.chat.completions.create(
                model=settings.openai_model,
                temperature=0.2,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Using the structured extracted information from all validated sources, "
                            "generate a concise professional summary of the individual. "
                            "If conflicting information exists, prioritize higher confidence sources.\n\n"
                            f"Data: {summary_seed}"
                        ),
                    }
                ],
            )
            content = completion.choices[0].message.content
            if content:
                return _normalize_whitespace(content)
        except Exception:
            pass

    return f"Resolved profile using multi-source evidence: {summary_seed}."


async def resolve_profile(
    *,
    linkedin_url: Optional[str],
    name: Optional[str],
    company: Optional[str],
    designation: Optional[str],
    location: Optional[str],
    max_sources: int,
) -> dict[str, Any]:
    inferred_name = name or _extract_name_from_linkedin_url(linkedin_url)
    input_payload = {
        "linkedin_url": linkedin_url,
        "name": inferred_name,
        "company": company,
        "designation": designation,
        "location": location,
    }

    queries, ambiguity_risk = _build_queries(input_payload)
    search_results = await _search_web(queries=queries[:8], max_per_query=8)

    # Always include direct LinkedIn URL as a high-priority candidate when supplied.
    if linkedin_url and all(linkedin_url != item.url for item in search_results):
        search_results.insert(
            0,
            SearchResult(
                title="LinkedIn profile",
                url=linkedin_url,
                snippet="Direct profile URL provided by user.",
                source_domain=_domain(linkedin_url),
            ),
        )

    candidates = await _extract_candidates(
        search_results=search_results,
        input_payload=input_payload,
        max_sources=max_sources,
    )

    is_resolved, clarification_question, top_attribute_score = _resolve_identity(
        candidates=candidates,
        input_payload=input_payload,
    )

    ambiguity_flag = (not is_resolved) or ambiguity_risk
    if ambiguity_risk and not input_payload.get("company") and not clarification_question:
        clarification_question = (
            "Name-only input has high ambiguity. Can you share company, designation, or location?"
        )

    resolved_confidence = top_attribute_score
    if not ambiguity_flag and candidates:
        top_sources = sorted(candidates, key=lambda item: item.source_confidence, reverse=True)[:5]
        resolved_confidence = round(sum(item.source_confidence for item in top_sources) / len(top_sources), 3)

    resolved_identity = _aggregate_identity(candidates, resolved_confidence)
    source_payload = [
        {
            "url": candidate.result.url,
            "domain": candidate.result.source_domain,
            "type": candidate.source_type,
            "confidence": candidate.source_confidence,
            "extracted_info": candidate.extracted,
        }
        for candidate in sorted(candidates, key=lambda item: item.source_confidence, reverse=True)
    ]

    summary = _build_summary(candidates, ambiguity_flag, clarification_question)

    return {
        "resolved_identity": resolved_identity,
        "ambiguity_flag": ambiguity_flag,
        "clarification_question": clarification_question,
        "sources": source_payload,
        "aggregated_summary": summary,
    }
