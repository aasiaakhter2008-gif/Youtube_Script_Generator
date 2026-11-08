import pytest

from app.schemas.script import ScriptRequest


@pytest.fixture
def sample_request() -> ScriptRequest:
    return ScriptRequest(
        topic="The Science of Sleep",
        audience="College students",
        tone="educational",
        language="English",
        duration_minutes=8,
        format="long_form",
    )
