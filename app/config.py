from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    jwt_secret_key: str
    cors_origins: list[str] = ["http://localhost:5173"]

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    rag_min_similarity: float = 0.30
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-20b"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()