from app.eval.benchmarks import BenchmarkTopic
from app.schemas.script import WriterSection


def script_word_count(sections: list[WriterSection]) -> int:
    return sum(len((s.content or "").split()) for s in sections if s.content)


def check_structure(sections: list[WriterSection], benchmark: BenchmarkTopic) -> list[str]:
    """Deterministic structural + length checks on a generated script for a benchmark topic."""
    issues: list[str] = []
    kinds = {s.section_type.value for s in sections}
    required = ["hook", "intro", "retention_loop", "cta", "outro"]
    for kind in required:
        if kind not in kinds:
            issues.append(f"missing required section: {kind}")
    for section in sections:
        if not section.b_roll_cues:
            issues.append(f"missing b-roll cues in section: {section.section_type.value}")
        if not section.on_screen_text:
            issues.append(f"missing on-screen text in section: {section.section_type.value}")
    word_count = script_word_count(sections)
    if not (benchmark.expected_min_words <= word_count <= benchmark.expected_max_words):
        issues.append(f"word count {word_count} outside expected range [{benchmark.expected_min_words}, {benchmark.expected_max_words}]")
    return issues
