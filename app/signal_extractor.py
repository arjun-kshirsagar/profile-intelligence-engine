from typing import Any, Dict, List

from app.schemas import SignalSchema


class SignalExtractor:
    """
    Module responsible for converting raw metadata from collectors into structured signals.
    This is Phase 3: Signal Extraction / Feature Engineering.
    """

    def extract(self, metadata: List[Dict[str, Any]]) -> SignalSchema:
        """
        Main extraction entry point. Aggregates signals from all sources.
        """
        raw_features = {}

        # 1. Parse LinkedIn signals
        linkedin_raw = self._get_source_data(metadata, "linkedin")
        execution_score = self._extract_execution_score(linkedin_raw)
        raw_features.update({f"li_{k}": v for k, v in linkedin_raw.items()})

        # 2. Parse GitHub signals
        github_raw = self._get_source_data(metadata, "github")
        tech_depth_score = self._extract_technical_depth_score(github_raw)
        raw_features.update({f"gh_{k}": v for k, v in github_raw.items()})

        # 3. Parse Web Search signals (Influence & Recognition)
        search_raw = self._get_source_data(metadata, "google_search")
        influence_score = self._extract_influence_score(search_raw)
        recognition_score = self._extract_recognition_score(search_raw)
        raw_features.update({f"ws_{k}": v for k, v in search_raw.items()})

        return SignalSchema(
            execution_score=execution_score,
            technical_depth_score=tech_depth_score,
            influence_score=influence_score,
            recognition_score=recognition_score,
            raw_features=raw_features,
        )

    def _get_source_data(
        self, metadata: List[Dict[str, Any]], source_name: str
    ) -> Dict[str, Any]:
        """Helper to find source-specific raw data."""
        for item in metadata:
            if item.get("source") == source_name:
                return item.get("raw_data", {})
        return {}

    def _extract_execution_score(self, li_data: Dict[str, Any]) -> float:
        """
        Calculates execution score (0-100) based on tenure, role, and bio.
        """
        if not li_data:
            return 0.0

        score = 0.0
        # 1. Title maturity
        role = li_data.get("current_role", "").lower()
        if any(keyword in role for keyword in ["founder", "cto", "ceo", "chief"]):
            score += 50
        elif any(keyword in role for keyword in ["senior", "lead", "staff"]):
            score += 30

        # 2. Tenure / Experience
        exp = li_data.get("experience_years", 0)
        score += min(exp * 5, 50)  # Max out at 10 years

        return min(score, 100.0)

    def _extract_technical_depth_score(self, gh_data: Dict[str, Any]) -> float:
        """
        Calculates tech depth score (0-100) based on repos, stars, and languages.
        """
        if not gh_data:
            return 0.0

        score = 0.0
        # 1. Repos & Stars
        stars = gh_data.get("total_stars", 0)
        score += min(stars / 10, 50)  # 500 stars = 50 pts

        # 2. Variety / Modern stack
        langs = gh_data.get("top_languages", [])
        if len(langs) >= 3:
            score += 20

        # 3. Repo count
        repos = gh_data.get("repo_count", 0)
        score += min(repos, 30)  # 30 repos = 30 pts

        return min(score, 100.0)

    def _extract_influence_score(self, search_data: Dict[str, Any]) -> float:
        """
        Calculates influence score (0-100) based on mentions and social signal.
        """
        if not search_data:
            return 0.0

        mentions = len(search_data.get("media_mentions", []))
        return min(mentions * 25, 100.0)  # 4 mentions = max

    def _extract_recognition_score(self, search_data: Dict[str, Any]) -> float:
        """
        Calculates recognition score (0-100) based on awards and talks.
        """
        if not search_data:
            return 0.0

        talks = len(search_data.get("conference_talks", []))
        return min(talks * 40, 100.0)  # 2.5 talks = max
