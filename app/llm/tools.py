import json
from typing import Any

import google.generativeai as genai
from groq import Groq

from app.config import get_settings

settings = get_settings()


def build_profile_summary(signals: dict[str, Any]) -> str:
    lines = [
        f"Name: {signals.get('name')}",
        f"Public repos: {signals.get('public_repos')}",
        f"Followers: {signals.get('followers')}",
        f"Founder keyword present: {signals.get('has_founder_keyword')}",
        f"Years experience: {signals.get('years_experience')}",
        f"Speaking mentions: {signals.get('speaking_mentions')}",
        f"Blog count: {signals.get('blog_count')}",
        f"Source count: {signals.get('source_count')}",
    ]
    return "\n".join(lines)


def reflective_score_adjustment(signals: dict[str, Any], deterministic_score: int) -> tuple[int, str]:
    if not settings.llm_reflection_enabled or not settings.groq_api_key:
        return 0, "LLM reflection disabled."

    client = Groq(api_key=settings.groq_api_key)
    summary = build_profile_summary(signals)

    prompt = (
        "You are evaluating whether a candidate is top 1% in their field using proxy public signals. "
        "Return strict JSON with keys: adjustment (integer between -15 and 15), reasoning (string). "
        "Adjustment should critique the deterministic score for context.\n\n"
        f"Deterministic score: {deterministic_score}\n"
        f"Signals:\n{summary}"
    )

    try:
        completion = client.chat.completions.create(
            model=settings.groq_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        payload_text = completion.choices[0].message.content
        payload = json.loads(payload_text)
        adjustment = int(payload.get("adjustment", 0))
        adjustment = max(-15, min(15, adjustment))
        reasoning = str(payload.get("reasoning", "No reasoning provided."))
        return adjustment, reasoning
    except Exception:
        return 0, "LLM reflection unavailable, deterministic score used."


def generate_scraper_script(
    source: str,
    url: str,
    html_sample: str,
    previous_errors: list[str],
) -> tuple[str | None, str | None]:
    if not settings.gemini_api_key:
        return None, "Gemini API key missing. Set GEMINI_API_KEY."

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(settings.gemini_model)
    sample = html_sample[:5000]
    errors = "\n".join(f"- {e}" for e in previous_errors[:5]) or "- none"

    prompt = (
        "Generate a Python scraper function for BeautifulSoup parsing. "
        "Return strict JSON only with key script_code. "
        "The code must define extract(html: str, url: str) -> dict with keys 'text' and 'metadata'. "
        "Note: 'html' is a raw HTML string. You MUST initialize BeautifulSoup inside the function: "
        "soup = BeautifulSoup(html, 'html.parser'). "
        "IMPORTANT: 'BeautifulSoup' and 're' are already available globally. DO NOT 'import' anything. "
        "DO NOT use 'eval()'. Keep it robust to missing fields. "
        "Do not include triple backticks around the json.\n\n"
        f"Source: {source}\n"
        f"URL: {url}\n"
        f"Previous errors:\n{errors}\n\n"
        f"HTML sample:\n{sample}"
    )

    try:
        completion = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.1,
                "response_mime_type": "application/json",
            },
        )
        payload_text = completion.text or ""
        payload = json.loads(payload_text)
        script_code = payload.get("script_code")
        if isinstance(script_code, str) and "def extract" in script_code:
            return script_code, None
        return None, "Gemini response missing a valid extract(html, url) function."
    except Exception as exc:
        return None, f"Gemini script generation failed: {exc}"
