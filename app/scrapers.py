import re
import json
import traceback
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.config import get_settings
from app.llm import generate_scraper_script
from app.models import ScraperExecutionLog, ScraperScript

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
    script_id: Optional[int] = None
    script_name: Optional[str] = None


@dataclass
class ScrapeFailure:
    source: str
    url: str
    script_id: Optional[int]
    script_name: Optional[str]
    script_code: str
    error: str


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme:
        return f"https://{url}"
    return url


async def fetch_html(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        return response.text
    except httpx.HTTPError:
        return None


def _candidate_scripts(db: Session, source: str) -> list[ScraperScript]:
    return (
        db.query(ScraperScript)
        .filter(ScraperScript.source == source, ScraperScript.is_active.is_(True))
        .order_by(ScraperScript.success_count.desc(), ScraperScript.created_at.desc())
        .all()
    )


def _remove_legacy_default_scripts(db: Session) -> None:
    deleted = (
        db.query(ScraperScript)
        .filter(ScraperScript.name.like("default\\_%", escape="\\"))
        .delete(synchronize_session=False)
    )
    if deleted:
        db.commit()


def _run_script(script_code: str, html: str, url: str) -> tuple[str, dict[str, Any]]:
    safe_builtins = {
        "len": len,
        "min": min,
        "max": max,
        "sum": sum,
        "any": any,
        "all": all,
        "int": int,
        "float": float,
        "str": str,
        "bool": bool,
        "dict": dict,
        "list": list,
        "set": set,
        "sorted": sorted,
        "Exception": Exception,
    }
    globals_dict: dict[str, Any] = {
        "__builtins__": safe_builtins,
        "BeautifulSoup": BeautifulSoup,
        "re": re,
        "json": json,
    }
    locals_dict: dict[str, Any] = {}

    exec(script_code, globals_dict, locals_dict)
    extract_fn = locals_dict.get("extract") or globals_dict.get("extract")
    if not callable(extract_fn):
        raise ValueError("Script must define callable extract(html, url)")

    payload = extract_fn(html, url)
    if not isinstance(payload, dict):
        raise ValueError("extract() must return a dict")

    text = str(payload.get("text", ""))
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be a dict")
    return text, metadata


def _log_execution(
    db: Session,
    source: str,
    url: str,
    script_id: Optional[int],
    script_name: Optional[str],
    script_code: str,
    success: bool,
    error: Optional[str],
) -> None:
    db.add(
        ScraperExecutionLog(
            source=source,
            url=url,
            script_id=script_id,
            script_name=script_name,
            script_code=script_code,
            success=success,
            error=error,
        )
    )
    db.commit()


def _try_script(
    db: Session,
    source: str,
    url: str,
    html: str,
    script: ScraperScript,
) -> tuple[Optional[ScrapeResult], Optional[ScrapeFailure]]:
    try:
        text, metadata = _run_script(script.script_code, html, url)
        script.success_count += 1
        script.last_error = None
        script.last_status = "success"
        db.commit()
        _log_execution(
            db=db,
            source=source,
            url=url,
            script_id=script.id,
            script_name=script.name,
            script_code=script.script_code,
            success=True,
            error=None,
        )
        return (
            ScrapeResult(
                source=source,
                url=url,
                ok=True,
                text=text,
                metadata=metadata,
                script_id=script.id,
                script_name=script.name,
            ),
            None,
        )
    except Exception:
        error = traceback.format_exc()
        script.failure_count += 1
        script.last_error = error
        script.last_status = "failed"
        db.commit()
        _log_execution(
            db=db,
            source=source,
            url=url,
            script_id=script.id,
            script_name=script.name,
            script_code=script.script_code,
            success=False,
            error=error,
        )
        return (
            None,
            ScrapeFailure(
                source=source,
                url=url,
                script_id=script.id,
                script_name=script.name,
                script_code=script.script_code,
                error=error,
            ),
        )


def _try_generated_script_with_retries(
    db: Session,
    source: str,
    url: str,
    html: str,
    previous_errors: list[str],
) -> tuple[Optional[ScrapeResult], list[ScrapeFailure]]:
    all_failures: list[ScrapeFailure] = []
    retry_errors = list(previous_errors)
    max_attempts = max(1, settings.script_generation_max_attempts)

    for attempt in range(1, max_attempts + 1):
        generated_script, generation_error = generate_scraper_script(
            source=source,
            url=url,
            html_sample=html,
            previous_errors=retry_errors,
        )
        script_name = f"generated_candidate_attempt_{attempt}"

        if generation_error:
            failure = ScrapeFailure(
                source=source,
                url=url,
                script_id=None,
                script_name=script_name,
                script_code=generated_script or "",
                error=generation_error,
            )
            _log_execution(
                db=db,
                source=source,
                url=url,
                script_id=None,
                script_name=script_name,
                script_code=generated_script or "",
                success=False,
                error=generation_error,
            )
            all_failures.append(failure)
            retry_errors.append(generation_error)
            continue

        if not generated_script:
            empty_error = "Gemini returned empty script."
            failure = ScrapeFailure(
                source=source,
                url=url,
                script_id=None,
                script_name=script_name,
                script_code="",
                error=empty_error,
            )
            _log_execution(
                db=db,
                source=source,
                url=url,
                script_id=None,
                script_name=script_name,
                script_code="",
                success=False,
                error=empty_error,
            )
            all_failures.append(failure)
            retry_errors.append(empty_error)
            continue

        try:
            text, metadata = _run_script(generated_script, html, url)
            row = ScraperScript(
                source=source,
                name=f"generated_{source}_v{attempt}",
                script_code=generated_script,
                is_active=True,
                success_count=1,
                failure_count=0,
                last_status="success",
                last_error=None,
            )
            db.add(row)
            db.commit()
            db.refresh(row)

            _log_execution(
                db=db,
                source=source,
                url=url,
                script_id=row.id,
                script_name=row.name,
                script_code=row.script_code,
                success=True,
                error=None,
            )

            return (
                ScrapeResult(
                    source=source,
                    url=url,
                    ok=True,
                    text=text,
                    metadata=metadata,
                    script_id=row.id,
                    script_name=row.name,
                ),
                all_failures,
            )
        except Exception:
            execution_error = traceback.format_exc()
            _log_execution(
                db=db,
                source=source,
                url=url,
                script_id=None,
                script_name=script_name,
                script_code=generated_script,
                success=False,
                error=execution_error,
            )
            failure = ScrapeFailure(
                source=source,
                url=url,
                script_id=None,
                script_name=script_name,
                script_code=generated_script,
                error=execution_error,
            )
            all_failures.append(failure)
            retry_errors.append(execution_error)

    return None, all_failures


async def scrape_sources(
    db: Session,
    github_url: Optional[str],
    website_url: Optional[str],
    twitter_url: Optional[str],
) -> tuple[list[ScrapeResult], list[dict[str, Any]]]:
    _remove_legacy_default_scripts(db)

    urls: list[tuple[str, str]] = []
    if github_url:
        urls.append(("github", _normalize_url(github_url)))
    if website_url:
        urls.append(("website", _normalize_url(website_url)))
    if twitter_url:
        urls.append(("twitter", _normalize_url(twitter_url)))

    if not urls:
        return [], []

    out: list[ScrapeResult] = []
    failures: list[dict[str, Any]] = []

    timeout = httpx.Timeout(settings.request_timeout_seconds)
    async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=timeout) as client:
        for source, url in urls:
            source_errors: list[str] = []
            html = await fetch_html(client, url)
            if not html:
                failures.append(
                    {
                        "source": source,
                        "url": url,
                        "script_id": None,
                        "script_name": None,
                        "script_code": "",
                        "error": "Unable to fetch HTML from source URL",
                    }
                )
                out.append(ScrapeResult(source=source, url=url, ok=False, text="", metadata={}))
                continue

            scripts = _candidate_scripts(db, source)
            success_result: Optional[ScrapeResult] = None

            if scripts:
                for script in scripts:
                    result, failure = _try_script(db, source, url, html, script)
                    if result:
                        success_result = result
                        break
                    if failure:
                        source_errors.append(failure.error)
                        failures.append(failure.__dict__)
            elif not settings.gemini_api_key:
                failures.append(
                    {
                        "source": source,
                        "url": url,
                        "script_id": None,
                        "script_name": None,
                        "script_code": "",
                        "error": "No active scraper script found and Gemini generation unavailable",
                    }
                )

            if not success_result and settings.gemini_api_key:
                gen_result, gen_failures = _try_generated_script_with_retries(
                    db=db,
                    source=source,
                    url=url,
                    html=html,
                    previous_errors=source_errors,
                )
                for failure in gen_failures:
                    failures.append(failure.__dict__)
                if gen_result:
                    success_result = gen_result

            if success_result:
                out.append(success_result)
            else:
                out.append(ScrapeResult(source=source, url=url, ok=False, text="", metadata={}))

    return out, failures
