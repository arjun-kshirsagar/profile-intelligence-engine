import asyncio

from app.agents.explanation import ExplanationAgent


async def main():
    agent = ExplanationAgent()
    res = await agent.generate_explanation(
        name="Test Candidate",
        final_score=85.0,
        decision="ADMIT",
        execution_score=90.0,
        technical_depth_score=80.0,
        influence_score=75.0,
        recognition_score=85.0,
        raw_features={"github_stars": 100, "media_mentions": 2},
    )
    print("Summary:", res.summary)
    print("Strengths:", res.strengths)
    print("Weaknesses:", res.weaknesses)


if __name__ == "__main__":
    asyncio.run(main())
