from sentence_transformers import SentenceTransformer

from app.config import settings


model = SentenceTransformer(settings.embedding_model)


def generate_embedding(text: str) -> list[float]:
    embedding = model.encode(text)
    return embedding.tolist()


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    embeddings = model.encode(texts)
    return embeddings.tolist()