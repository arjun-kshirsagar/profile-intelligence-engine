from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import get_settings
from app.logger import logger

settings = get_settings()

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source_domain: str


def _normalize_whitespace(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _normalize_link(url: str) -> str:
    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path == "/l/":
        target = parse_qs(parsed.query).get("uddg", [])
        if target:
            return unquote(target[0])
    return url


def _domain(url: str) -> str:
    return (urlparse(url).netloc or "").lower()


async def google_cse_search(query: str, limit: int = 5) -> list[SearchResult]:
    if not settings.google_cse_api_key or not settings.google_cse_cx:
        return []

    num = max(1, min(10, limit))
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.request_timeout_seconds)) as client:
            response = await client.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "q": query,
                    "key": settings.google_cse_api_key,
                    "cx": settings.google_cse_cx,
                    "num": num,
                },
            )
            response.raise_for_status()
    except httpx.HTTPError as e:
        logger.error(f"Google CSE search failed for query '{query}': {e}")
        return []

    logger.info(f"Google CSE returned {len(response.json().get('items', []))} items for query '{query}'")
    payload = response.json()
    items = payload.get("items", [])
    results: list[SearchResult] = []
    for item in items:
        url = _normalize_link(str(item.get("link", "")).strip())
        if not url:
            continue
        results.append(
            SearchResult(
                title=_normalize_whitespace(str(item.get("title", ""))),
                url=url,
                snippet=_normalize_whitespace(str(item.get("snippet", ""))),
                source_domain=_domain(url),
            )
        )
        if len(results) >= num:
            break

    return results


async def duckduckgo_search_html(query: str, limit: int = 5) -> list[SearchResult]:
    try:
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            timeout=httpx.Timeout(settings.request_timeout_seconds),
            follow_redirects=True,
        ) as client:
            response = await client.get("https://duckduckgo.com/html/", params={"q": query})
            response.raise_for_status()
    except httpx.HTTPError as e:
        logger.error(f"DuckDuckGo search failed for query '{query}': {e}")
        return []

    logger.info(f"DuckDuckGo search successful for query '{query}'")
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


async def search_web(query: str, limit: int = 5) -> list[SearchResult]:
    google_results = await google_cse_search(query, limit=limit)
    if google_results:
        return google_results

    return await duckduckgo_search_html(query, limit=limit)
