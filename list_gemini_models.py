import google.generativeai as genai

from app.config import get_settings

settings = get_settings()
genai.configure(api_key=settings.gemini_api_key)

try:
    models = genai.list_models()
    for m in models:
        if "generateContent" in m.supported_generation_methods:
            print(m.name)
except Exception as e:
    print(f"Error: {e}")
