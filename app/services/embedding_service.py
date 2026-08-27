from sentence_transformers import SentenceTransformer

from app.config import settings


_model = None


def get_embedding_model() -> SentenceTransformer:
    global _model

    if _model is None:
        _model = SentenceTransformer(
            settings.embedding_model
        )

    return _model


def generate_embedding(text: str) -> list[float]:
    model = get_embedding_model()

    embedding = model.encode(text)

    return embedding.tolist()


def generate_embeddings(
    texts: list[str]
) -> list[list[float]]:
    model = get_embedding_model()

    embeddings = model.encode(texts)

    return embeddings.tolist()