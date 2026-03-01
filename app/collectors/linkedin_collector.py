from typing import Any, Dict

from app.collectors.base import CollectorBase


class LinkedInCollector(CollectorBase):
    """
    Mock LinkedIn collector returning structured data.
    """

    async def collect(self, linkedin_url: str) -> Dict[str, Any]:
        """
        Mock implementation. In later phases this will use scraping or APIs.
        """
        # Simulated delay
        import asyncio

        await asyncio.sleep(0.5)

        return {
            "source": "linkedin",
            "raw_data": {
                "full_name": "John Doe",
                "current_role": "Founder",
                "current_company": "Stealth AI",
                "headline": "Building the future of agentic systems | Ex-Google",
                "location": "San Francisco, CA",
                "experience_years": 8,
                "skills": [
                    "Distributed Systems",
                    "Artificial Intelligence",
                    "Back-end Engineering",
                ],
                "education": [
                    {
                        "institution": "Stanford University",
                        "degree": "MS in Computer Science",
                    }
                ],
            },
            "confidence": 0.98,
        }
