from collections.abc import Iterator

import httpx

from app.config import settings
from app.services.llm.base import LLMProvider


class GroqProvider(LLMProvider):
    API_URL = "https://api.groq.com/openai/v1/chat/completions"

    def _headers(self) -> dict[str, str]:
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not configured.")

        return {
            "Authorization": f"Bearer {settings.groq_api_key}",
            "Content-Type": "application/json",
        }

    def generate(self, prompt: str) -> str:
        response = httpx.post(
            self.API_URL,
            headers=self._headers(),
            json={
                "model": settings.groq_model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            },
            timeout=60.0,
        )

        response.raise_for_status()
        data = response.json()

        return data["choices"][0]["message"]["content"]

    def stream(self, prompt: str) -> Iterator[str]:
        with httpx.stream(
            "POST",
            self.API_URL,
            headers=self._headers(),
            json={
                "model": settings.groq_model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                "stream": True,
                "include_reasoning": False,
            },
            timeout=httpx.Timeout(
                connect=10.0,
                read=None,
                write=30.0,
                pool=10.0,
            ),
        ) as response:
            response.raise_for_status()

            for line in response.iter_lines():
                print(f"[GROQ STREAM RAW] {line!r}")

                if not line:
                    continue

                line = line.strip()

                if not line.startswith("data:"):
                    continue

                payload = line[len("data:"):].strip()

                if payload == "[DONE]":
                    break

                try:
                    data = httpx.Response(
                        200,
                        content=payload,
                    ).json()
                except ValueError:
                    continue

                choices = data.get("choices", [])

                if not choices:
                    continue

                delta = choices[0].get("delta", {})
                content = delta.get("content")

                if content:
                    yield content
