from app.llm.base import BaseLLM
from app.llm.claude_client import ClaudeClient
from app.llm.gemini_client import GeminiClient
from app.llm.openai_client import OpenAIClient


def get_llm(provider: str, api_key: str) -> BaseLLM:
    if provider == "openai":
        return OpenAIClient(api_key=api_key)
    elif provider == "claude":
        return ClaudeClient(api_key=api_key)
    elif provider == "gemini":
        return GeminiClient(api_key=api_key)
    else:
        raise ValueError(f"Unsupported provider: {provider}")
