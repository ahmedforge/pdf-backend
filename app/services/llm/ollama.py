import httpx

from app.config import settings
from app.services.llm.base import LLMProvider


class OllamaProvider(LLMProvider):
    def generate(self, prompt: str) -> str:
        try:
            response = httpx.post(
                settings.ollama_url,
                json={
                    "model": settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                },
                timeout=120.0,
            )

            response.raise_for_status()

        except httpx.ConnectError as exc:
            raise RuntimeError(
                "Ollama is not running. Start it with 'ollama serve'."
            ) from exc

        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Ollama request failed: {exc}"
            ) from exc

        return response.json()["response"]