from typing import Any, Dict

from app.collectors.base import CollectorBase


class GitHubCollector(CollectorBase):
    """
    Mock GitHub collector returning structured data.
    """

    async def collect(self, input_value: str) -> Dict[str, Any]:
        """
        Mock implementation. In Phase 2 this will use Google Search API/GitHub API.
        """
        # Simulated delay
        import asyncio

        await asyncio.sleep(0.5)

        return {
            "source": "github",
            "raw_data": {
                "username": "johndoe",
                "repo_count": 42,
                "total_stars": 380,
                "followers": 120,
                "contribution_frequency": "high",
                "top_languages": ["Python", "Go", "TypeScript"],
                "recent_projects": ["distributed-kv-store", "ai-agent-framework"],
            },
            "confidence": 0.92,
        }
