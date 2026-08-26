import httpx

from app.config import settings


OLLAMA_URL = "http://127.0.0.1:11434/api/generate"


def generate_answer(prompt: str) -> str:
    try:
        response = httpx.post(
            OLLAMA_URL,
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

    data = response.json()

    return data["response"]