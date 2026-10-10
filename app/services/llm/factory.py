from app.services.llm.base import LLMProvider
from app.services.llm.groq import GroqProvider


def get_llm_provider() -> LLMProvider:
    return GroqProvider()
