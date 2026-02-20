import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import get_settings

settings = get_settings()

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}


@dataclass
class ScrapeResult:
    source: str
    url: str
    ok: bool
    text: str
    metadata: dict


async def fetch_html(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        return response.text
    except httpx.HTTPError:
        return None


def clean_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))


def parse_github(html: str, url: str) -> ScrapeResult:
    soup = BeautifulSoup(html, "html.parser")
    page_text = clean_text(soup)

    name = ""
    h1 = soup.find("h1")
    if h1:
        name = h1.get_text(" ", strip=True)

    followers = 0
    followers_match = re.search(r"([\d,]+)\s+followers", page_text, flags=re.IGNORECASE)
    if followers_match:
        followers = int(followers_match.group(1).replace(",", ""))

    public_repos = 0
    repos_match = re.search(r"([\d,]+)\s+repositories", page_text, flags=re.IGNORECASE)
    if repos_match:
        public_repos = int(repos_match.group(1).replace(",", ""))

    bio = ""
    bio_node = soup.select_one("div.p-note")
    if bio_node:
        bio = bio_node.get_text(" ", strip=True)

    return ScrapeResult(
        source="github",
        url=url,
        ok=True,
        text=page_text,
        metadata={
            "display_name": name,
            "bio": bio,
            "followers": followers,
            "public_repos": public_repos,
        },
    )


def parse_website(html: str, url: str) -> ScrapeResult:
    soup = BeautifulSoup(html, "html.parser")
    page_text = clean_text(soup)

    title = soup.title.get_text(strip=True) if soup.title else ""
    description = ""
    desc_tag = soup.find("meta", attrs={"name": "description"})
    if desc_tag:
        description = desc_tag.get("content", "")

    blog_links = 0
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        label = a.get_text(" ", strip=True).lower()
        if "blog" in href or "blog" in label or "article" in href:
            blog_links += 1

    return ScrapeResult(
        source="website",
        url=url,
        ok=True,
        text=page_text,
        metadata={
            "title": title,
            "description": description,
            "blog_links": blog_links,
        },
    )


def parse_twitter(html: str, url: str) -> ScrapeResult:
    soup = BeautifulSoup(html, "html.parser")
    page_text = clean_text(soup)

    description = ""
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc:
        description = meta_desc.get("content", "")

    return ScrapeResult(
        source="twitter",
        url=url,
        ok=True,
        text=page_text,
        metadata={"bio": description},
    )


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme:
        return f"https://{url}"
    return url


async def scrape_sources(
    github_url: Optional[str], website_url: Optional[str], twitter_url: Optional[str]
) -> list[ScrapeResult]:
    urls: list[tuple[str, str]] = []
    if github_url:
        urls.append(("github", _normalize_url(github_url)))
    if website_url:
        urls.append(("website", _normalize_url(website_url)))
    if twitter_url:
        urls.append(("twitter", _normalize_url(twitter_url)))

    if not urls:
        return []

    out: list[ScrapeResult] = []
    timeout = httpx.Timeout(settings.request_timeout_seconds)
    async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=timeout) as client:
        for source, url in urls:
            html = await fetch_html(client, url)
            if not html:
                out.append(ScrapeResult(source=source, url=url, ok=False, text="", metadata={}))
                continue

            if source == "github":
                out.append(parse_github(html, url))
            elif source == "website":
                out.append(parse_website(html, url))
            elif source == "twitter":
                out.append(parse_twitter(html, url))

    return out
