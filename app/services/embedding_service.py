from threading import Lock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

from app.config import settings


_model = None
_model_lock = Lock()
_inference_lock = Lock()


def get_embedding_model() -> "SentenceTransformer":
    global _model

    with _model_lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(settings.embedding_model, device="cpu")

    return _model


def generate_embedding(text: str) -> list[float]:
    return generate_embeddings([text])[0]


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    # Limit simultaneous inference and activation memory on small CPU instances.
    with _inference_lock:
        model = get_embedding_model()
        embeddings = model.encode(texts, batch_size=1, show_progress_bar=False)
        return embeddings.tolist()
