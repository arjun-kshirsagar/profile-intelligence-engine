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
                "full_name": "Prashant Parashar",
                "current_role": "Founder",
                "current_company": "Stealth AI",
                "headline": "Something brewing! [Previously: Head of Technology - Delhivery, Ola, Snapdeal, Zomato]",
                "location": "Bangalore, India",
                "experience_years": 20,
                "skills": [
                    "Distributed Systems",
                    "Artificial Intelligence",
                    "Back-end Engineering",
                ],
                "education": [
                    {
                        "institution": "B.I.E.T., Jhansi",
                        "degree": "B.Tech in Computer Science",
                    }
                ],
            },
            "confidence": 0.98,
        }
