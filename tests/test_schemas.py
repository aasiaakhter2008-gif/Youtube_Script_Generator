import pytest
from pydantic import ValidationError

from app.schemas.script import (
    CriticAssessment,
    Outline,
    OutlineSection,
    RegenerateSectionRequest,
    ScriptFormat,
    ScriptLanguage,
    ScriptRequest,
    SectionType,
    Tone,
    WriterSection,
    WrittenScript,
)


def test_valid_request_defaults() -> None:
    req = ScriptRequest(topic="Why the sky is blue", duration_minutes=8)
    assert req.tone is Tone.EDUCATIONAL
    assert req.language is ScriptLanguage.ENGLISH
    assert req.format is ScriptFormat.LONG_FORM
    assert req.audience == "General audience"


def test_topic_is_required() -> None:
    with pytest.raises(ValidationError):
        ScriptRequest(duration_minutes=5)  # type: ignore[call-arg]


def test_duration_minutes_bounds() -> None:
    with pytest.raises(ValidationError):
        ScriptRequest(topic="Valid topic", duration_minutes=0)
    with pytest.raises(ValidationError):
        ScriptRequest(topic="Valid topic", duration_minutes=31)


def test_tone_enum_values() -> None:
    assert {t.value for t in Tone} == {"educational", "funny", "storytelling", "motivational"}
    with pytest.raises(ValueError):
        Tone("bogus")


def test_language_enum_values() -> None:
    assert {lang.value for lang in ScriptLanguage} == {"English", "Urdu", "Roman Urdu", "Hindi"}


def test_format_enum_values() -> None:
    assert {f.value for f in ScriptFormat} == {"long_form", "shorts"}


def test_outline_requires_core_sections() -> None:
    with pytest.raises(ValidationError):
        Outline(
            hook=OutlineSection(section_type=SectionType.HOOK, title="Hook"),
            intro=OutlineSection(section_type=SectionType.INTRO, title="Intro"),
            retention_loop=OutlineSection(section_type=SectionType.RETENTION_LOOP, title="Loop"),
            cta=OutlineSection(section_type=SectionType.CTA, title="CTA"),
            # outro missing -> invalid
        )


def test_critic_assessment_bounds() -> None:
    ok = CriticAssessment(hook_strength=8.0, pacing=8.0, clarity=8.0, repetition=8.0, passed=True)
    assert ok.passed is True
    with pytest.raises(ValidationError):
        CriticAssessment(hook_strength=11.0, pacing=5.0, clarity=5.0, repetition=5.0)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        CriticAssessment(hook_strength=5.0, pacing=5.0, clarity=5.0, repetition=-1.0)  # type: ignore[arg-type]


def test_written_script_word_count_optional() -> None:
    ws = WriterSection(section_type=SectionType.HOOK, title="Hook", content="Hello world")
    assert ws.word_count == 0
    written = WrittenScript(sections=[ws], word_count=2)
    assert written.word_count == 2


def test_regenerate_request_validates_section_type() -> None:
    regen = RegenerateSectionRequest(section_type=SectionType.OUTRO, instruction="Make it shorter")
    assert regen.instruction == "Make it shorter"
    with pytest.raises(ValidationError):
        RegenerateSectionRequest(section_type="bogus")  # type: ignore[arg-type]
