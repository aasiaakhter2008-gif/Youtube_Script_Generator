from pydantic import BaseModel, Field

from app.schemas.script import ScriptFormat, ScriptLanguage, Tone


class BenchmarkTopic(BaseModel):
    """A topic with objective quality expectations for the offline eval suite."""

    topic: str = Field(min_length=3, max_length=300)
    audience: str = Field(default="General audience", max_length=200)
    tone: Tone = Tone.EDUCATIONAL
    language: ScriptLanguage = ScriptLanguage.ENGLISH
    duration_minutes: int = Field(ge=1, le=30)
    format: ScriptFormat = ScriptFormat.LONG_FORM
    expected_min_words: int = Field(default=300, ge=50)
    expected_max_words: int = Field(default=1400, le=5000)


BENCHMARK_TOPICS: list[BenchmarkTopic] = [
    # Technology
    BenchmarkTopic(topic="How neural networks learn", audience="Machine learning enthusiasts", tone=Tone.EDUCATIONAL, duration_minutes=10, format=ScriptFormat.LONG_FORM, expected_min_words=900, expected_max_words=1500),
    BenchmarkTopic(topic="Why your Wi-Fi is slow", audience="Everyday tech users", tone=Tone.EDUCATIONAL, duration_minutes=8, expected_min_words=700, expected_max_words=1200),
    BenchmarkTopic(topic="The future of quantum computing", audience="Science fans", tone=Tone.STORYTELLING, duration_minutes=12, expected_min_words=1100, expected_max_words=1800),
    BenchmarkTopic(topic="How SSDs improves loading times", audience="PC builders", tone=Tone.EDUCATIONAL, duration_minutes=6, expected_min_words=550, expected_max_words=950),
    # Health & fitness
    BenchmarkTopic(topic="Morning routines that stick", audience="Busy professionals", tone=Tone.MOTIVATIONAL, duration_minutes=8, expected_min_words=700, expected_max_words=1100),
    BenchmarkTopic(topic="Understanding calories in 15 minutes", audience="Health beginners", tone=Tone.EDUCATIONAL, duration_minutes=10, expected_min_words=800, expected_max_words=1300),
    BenchmarkTopic(topic="The science of muscle recovery", audience="Lifters", tone=Tone.EDUCATIONAL, duration_minutes=9, expected_min_words=800, expected_max_words=1300),
    BenchmarkTopic(topic="Sleep hygiene myths", audience="General audience", tone=Tone.EDUCATIONAL, duration_minutes=7, expected_min_words=650, expected_max_words=1000),
    # Finance
    BenchmarkTopic(topic="Index funds explained simply", audience="New investors", tone=Tone.EDUCATIONAL, duration_minutes=9, expected_min_words=800, expected_max_words=1300),
    BenchmarkTopic(topic="How compound interest works", audience="Young savers", tone=Tone.STORYTELLING, duration_minutes=8, expected_min_words=700, expected_max_words=1100),
    BenchmarkTopic(topic="Budgeting apps compared", audience="Budget-conscious viewers", tone=Tone.FUNNY, duration_minutes=6, expected_min_words=550, expected_max_words=900),
    # Education & science
    BenchmarkTopic(topic="How vaccines train the immune system", audience="General audience", tone=Tone.EDUCATIONAL, duration_minutes=12, expected_min_words=1000, expected_max_words=1600),
    BenchmarkTopic(topic="The water cycle in 10 minutes", audience="Students", tone=Tone.EDUCATIONAL, duration_minutes=6, expected_min_words=500, expected_max_words=800),
    BenchmarkTopic(topic="Why the sky is blue", audience="Curiosity-driven viewers", tone=Tone.STORYTELLING, duration_minutes=5, expected_min_words=450, expected_max_words=700),
    BenchmarkTopic(topic="How planes navigate", audience="Travel enthusiasts", tone=Tone.EDUCATIONAL, duration_minutes=8, expected_min_words=700, expected_max_words=1100),
    # History & storytelling
    BenchmarkTopic(topic="The fall of the Roman Empire", audience="History buffs", tone=Tone.STORYTELLING, duration_minutes=15, expected_min_words=1300, expected_max_words=2000),
    BenchmarkTopic(topic="Ancient Egypt daily life", audience="History enthusiasts", tone=Tone.STORYTELLING, duration_minutes=12, expected_min_words=1000, expected_max_words=1600),
    BenchmarkTopic(topic="How coffee changed history", audience="History fans", tone=Tone.STORYTELLING, duration_minutes=10, expected_min_words=800, expected_max_words=1300),
    # Food & culture
    BenchmarkTopic(topic="Why sourdough starters are alive", audience="Food lovers", tone=Tone.STORYTELLING, duration_minutes=8, expected_min_words=700, expected_max_words=1100),
    BenchmarkTopic(topic="The science of crispy fried food", audience="Food enthusiasts", tone=Tone.EDUCATIONAL, duration_minutes=7, expected_min_words=600, expected_max_words=950),
    # Fitness & motivation
    BenchmarkTopic(topic="How marathon training works", audience="Runners", tone=Tone.MOTIVATIONAL, duration_minutes=10, expected_min_words=800, expected_max_words=1300),
    BenchmarkTopic(topic="The psychology of motivation", audience="Self-improvers", tone=Tone.MOTIVATIONAL, duration_minutes=9, expected_min_words=750, expected_max_words=1200),
    # Productivity & tech
    BenchmarkTopic(topic="Building a second brain", audience="Knowledge workers", tone=Tone.EDUCATIONAL, duration_minutes=10, expected_min_words=800, expected_max_words=1300),
    BenchmarkTopic(topic="How to take better notes", audience="Students & professionals", tone=Tone.EDUCATIONAL, duration_minutes=7, expected_min_words=550, expected_max_words=900),
    BenchmarkTopic(topic="The greenhouse effect explained", audience="Climate-curious viewers", tone=Tone.EDUCATIONAL, duration_minutes=8, expected_min_words=700, expected_max_words=1100),
    BenchmarkTopic(topic="Why we dream", audience="Psychology fans", tone=Tone.STORYTELLING, duration_minutes=9, expected_min_words=750, expected_max_words=1200),
    # Finance & growth
    BenchmarkTopic(topic="How to start investing with $100", audience="Young investors", tone=Tone.MOTIVATIONAL, duration_minutes=8, expected_min_words=700, expected_max_words=1100),
    BenchmarkTopic(topic="Understanding inflation", audience="General audience", tone=Tone.EDUCATIONAL, duration_minutes=9, expected_min_words=750, expected_max_words=1200),
    # Language
    BenchmarkTopic(topic="How languages evolve", audience="Language enthusiasts", tone=Tone.EDUCATIONAL, duration_minutes=8, expected_min_words=700, expected_max_words=1100),
    BenchmarkTopic(topic="Roman Urdu language history", audience="Roman Urdu speakers", tone=Tone.STORYTELLING, duration_minutes=7, expected_min_words=600, expected_max_words=950),
    # Science & psychology
    BenchmarkTopic(topic="The psychology of habit formation", audience="Behavior change seekers", tone=Tone.MOTIVATIONAL, duration_minutes=9, expected_min_words=750, expected_max_words=1200),
    BenchmarkTopic(topic="How music affects the brain", audience="Music fans", tone=Tone.EDUCATIONAL, duration_minutes=8, expected_min_words=700, expected_max_words=1100),
]


def get_benchmarks(niche: str | None = None) -> list[BenchmarkTopic]:
    if not niche:
        return list(BENCHMARK_TOPICS)
    prefix = niche.strip().lower()
    return [b for b in BENCHMARK_TOPICS if prefix in b.topic.lower() or prefix in b.audience.lower()]
