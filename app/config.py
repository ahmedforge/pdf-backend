from pydantic_settings import BaseSettings, SettingsConfigDict

groq_api_key: str | None = None
groq_model: str = "openai/gpt-oss-20b"
class Settings(BaseSettings):
    database_url: str
    jwt_secret_key: str

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    rag_min_similarity: float = 0.30
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-20b"

    llm_provider: str = "ollama"
    ollama_url: str = "http://127.0.0.1:11434/api/generate"
    ollama_model: str = "llama3.2:1b"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()