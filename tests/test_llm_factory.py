import pytest

from app.config import Settings
from app.services.llm.factory import get_llm_provider
from app.services.llm.groq import GroqProvider


@pytest.mark.parametrize("legacy_provider", ["ollama", "groq", "unknown"])
def test_legacy_provider_env_cannot_select_ollama(monkeypatch, legacy_provider):
    monkeypatch.setenv("LLM_PROVIDER", legacy_provider)
    config = Settings(_env_file=None, database_url="sqlite://", jwt_secret_key="test")
    assert not hasattr(config, "llm_provider")
    assert isinstance(get_llm_provider(), GroqProvider)


def test_missing_key_fails_without_local_fallback(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "groq_api_key", None)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY is not configured"):
        get_llm_provider().generate("test")
