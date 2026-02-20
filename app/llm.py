import json
from typing import Any

from openai import OpenAI

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
    if not settings.llm_reflection_enabled or not settings.openai_api_key:
        return 0, "LLM reflection disabled."

    client = OpenAI(api_key=settings.openai_api_key)
    summary = build_profile_summary(signals)

    prompt = (
        "You are evaluating whether a candidate is top 1% in their field using proxy public signals. "
        "Return strict JSON with keys: adjustment (integer between -15 and 15), reasoning (string). "
        "Adjustment should critique the deterministic score for context.\n\n"
        f"Deterministic score: {deterministic_score}\n"
        f"Signals:\n{summary}"
    )

    try:
        response = client.responses.create(
            model=settings.openai_model,
            input=prompt,
            temperature=0.2,
        )
        payload_text = response.output_text.strip()
        payload = json.loads(payload_text)
        adjustment = int(payload.get("adjustment", 0))
        adjustment = max(-15, min(15, adjustment))
        reasoning = str(payload.get("reasoning", "No reasoning provided."))
        return adjustment, reasoning
    except Exception:
        return 0, "LLM reflection unavailable, deterministic score used."
