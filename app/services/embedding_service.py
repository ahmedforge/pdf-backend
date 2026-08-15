from openai import OpenAI

from app.config import settings


client = OpenAI(api_key=settings.openai_api_key)


def generate_embedding(text: str) -> list[float]:
    response = client.embeddings.create(
        model=settings.embedding_model,
        input=text,
    )

    return response.data[0].embedding