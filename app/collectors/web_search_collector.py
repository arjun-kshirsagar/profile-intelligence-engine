from typing import Any, Dict

from app.collectors.base import CollectorBase


class WebSearchCollector(CollectorBase):
    """
    Mock Web Search collector returning structured data.
    """

    async def collect(self, query: str) -> Dict[str, Any]:
        """
        Mock implementation. In Phase 2 this will use Google Search API.
        """
        # Simulated delay
        import asyncio

        await asyncio.sleep(0.5)

        return {
            "source": "google_search",
            "raw_data": {
                "snippets": [
                    "Found 5 mentions in tech blogs.",
                    "Speaker at PyCon 2023.",
                    "Featured in Wired: 'The future of backend is distributed'.",
                ],
                "news_count": 3,
                "media_mentions": ["Wired", "TechCrunch"],
                "conference_talks": ["PyCon 2023", "GopherCon 2022"],
            },
            "confidence": 0.85,
        }
