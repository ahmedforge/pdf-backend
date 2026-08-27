from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    jwt_secret_key: str

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    rag_min_similarity: float = 0.28

    llm_provider: str = "ollama"
    ollama_url: str = "http://127.0.0.1:11434/api/generate"
    ollama_model: str = "llama3.2:1b"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()