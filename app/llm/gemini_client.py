import google.generativeai as genai

from app.llm.base import BaseLLM

class GeminiClient(BaseLLM):

    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-1.5-pro")

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        response = self.model.generate_content(
            f"{system_prompt}\n\n{user_prompt}"
        )
        return response.text
