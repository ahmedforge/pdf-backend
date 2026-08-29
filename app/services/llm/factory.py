from app.config import settings
from app.services.llm.base import LLMProvider
from app.services.llm.groq import GroqProvider
from app.services.llm.ollama import OllamaProvider


def get_llm_provider() -> LLMProvider:
    if settings.llm_provider == "ollama":
        return OllamaProvider()

    if settings.llm_provider == "groq":
        return GroqProvider()

    raise RuntimeError(
        f"Unsupported LLM provider: {settings.llm_provider}"
    )