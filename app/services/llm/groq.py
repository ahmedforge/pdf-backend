from collections.abc import Iterator
import json

import httpx

from app.config import settings
from app.services.llm.base import LLMProvider


class GroqProvider(LLMProvider):
    API_URL = "https://api.groq.com/openai/v1/chat/completions"
    TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)

    def _headers(self) -> dict[str, str]:
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not configured.")
        return {
            "Authorization": f"Bearer {settings.groq_api_key}",
            "Content-Type": "application/json",
        }

    def _payload(self, prompt: str, *, stream: bool = False) -> dict:
        payload = {
            "model": settings.groq_model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if stream:
            payload.update(stream=True, include_reasoning=False)
        return payload

    def generate(self, prompt: str) -> str:
        try:
            response = httpx.post(
                self.API_URL, headers=self._headers(),
                json=self._payload(prompt), timeout=self.TIMEOUT,
            )
            response.raise_for_status()
            answer = response.json()["choices"][0]["message"]["content"]
            if not isinstance(answer, str):
                raise ValueError("Missing answer")
            return answer
        except httpx.TimeoutException as exc:
            raise RuntimeError("Groq request timed out. Please try again.") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError("Groq is unavailable. Please try again later.") from exc
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Groq returned an invalid response.") from exc

    def stream(self, prompt: str) -> Iterator[str]:
        try:
            with httpx.stream(
                "POST", self.API_URL, headers=self._headers(),
                json=self._payload(prompt, stream=True), timeout=self.TIMEOUT,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[len("data:"):].strip()
                    if payload == "[DONE]":
                        return
                    data = json.loads(payload)
                    if "error" in data:
                        raise RuntimeError("Groq could not complete the answer.")
                    choices = data.get("choices", [])
                    if not choices:
                        continue
                    content = choices[0].get("delta", {}).get("content")
                    if content is not None and not isinstance(content, str):
                        raise ValueError("Invalid content")
                    if content:
                        yield content
                raise RuntimeError("Groq ended the stream before completing the answer.")
        except httpx.TimeoutException as exc:
            raise RuntimeError("Groq request timed out. Please try again.") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError("Groq is unavailable. Please try again later.") from exc
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise RuntimeError("Groq returned an invalid response.") from exc
