from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=10)
    min_similarity: float | None = Field(
        default=None,
        ge=-1.0,
        le=1.0,
    )