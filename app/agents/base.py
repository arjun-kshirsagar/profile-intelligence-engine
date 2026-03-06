import asyncio
import json
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.llm.factory import get_llm
from app.logger import logger

T = TypeVar("T", bound=BaseModel)

settings = get_settings()


class AgentException(Exception):
    pass


class BaseAgent:
    """
    Base class for LLM-powered agents.
    Provides schema validation, retries, and timeout handling.
    """

    def __init__(
        self, provider: str = "groq", max_retries: int = 2, timeout_seconds: int = 15
    ):
        self.provider = provider
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds

        # Select appropriate API key based on provider
        if provider == "openai" and settings.openai_api_key:
            self.llm = get_llm("openai", settings.openai_api_key)
        elif provider == "claude" and settings.anthropic_api_key:
            self.llm = get_llm("claude", settings.anthropic_api_key)
        elif provider == "gemini" and settings.gemini_api_key:
            self.llm = get_llm("gemini", settings.gemini_api_key)
        else:
            logger.warning(
                f"No API key found for requested provider {provider}. Falling back to Gemini if available."
            )
            if settings.gemini_api_key:
                self.llm = get_llm("gemini", settings.gemini_api_key)
                self.provider = "gemini"
            else:
                raise AgentException("No valid LLM configuration found.")

    async def execute(
        self, system_prompt: str, user_prompt: str, response_model: Type[T]
    ) -> T:
        """
        Executes the LLM call, forces JSON output, and validates against the Pydantic model.
        """
        schema_json = json.dumps(response_model.model_json_schema(), indent=2)
        system_prompt += (
            f"\n\nYou MUST return your response as a valid JSON object matching exactly this schema:\n"
            f"{schema_json}\nDo not include markdown formatting like ```json."
        )

        for attempt in range(self.max_retries + 1):
            try:
                logger.info(
                    f"Agent execution attempt {attempt + 1}/{self.max_retries + 1}"
                )
                # Wrap sync LLM call in asyncio to enable timeouts
                # Note: Assuming underlying LLM clients are currently sync.
                # If they are async, we can just await them directly.
                task = asyncio.to_thread(self.llm.generate, system_prompt, user_prompt)
                response_text = await asyncio.wait_for(
                    task, timeout=self.timeout_seconds
                )

                # Strip potential markdown formatting if LLM ignores instructions
                response_text = response_text.strip()
                if response_text.startswith("```json"):
                    response_text = response_text[7:]
                elif response_text.startswith("```"):
                    response_text = response_text[3:]

                if response_text.endswith("```"):
                    response_text = response_text[:-3]

                response_text = response_text.strip()

                parsed_json = json.loads(response_text)
                validated_model = response_model(**parsed_json)
                return validated_model

            except asyncio.TimeoutError:
                logger.error(
                    f"Agent execution timed out after {self.timeout_seconds}s."
                )
                if attempt == self.max_retries:
                    raise AgentException("Agent timed out after maximum retries.")
            except json.JSONDecodeError as e:
                logger.error(f"Agent returned invalid JSON: {e}")
                if attempt == self.max_retries:
                    raise AgentException("Agent failed to return valid JSON.")
            except ValidationError as e:
                logger.error(f"Agent response failed schema validation: {e}")
                # Provide hinting for next retry
                system_prompt += f"\n\nPrevious attempt failed validation:\n{e.json()}\nPlease fix these errors."
                if attempt == self.max_retries:
                    raise AgentException("Agent failed schema validation.")
            except Exception as e:
                logger.error(f"Agent execution failed: {e}")
                if attempt == self.max_retries:
                    raise AgentException(f"Agent execution failed: {e}")

        raise AgentException("Agent execution failed completely.")
