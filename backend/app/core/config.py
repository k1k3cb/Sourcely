from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "staging", "production"] = "development"
    app_port: int = 8000
    frontend_url: str = "http://localhost:3000"

    database_url: str

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 24 * 7

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_bucket: str = "documents"

    embeddings_provider: Literal["openai", "ollama", "gemini"] = "gemini"
    embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 768
    openai_api_key: str = ""
    gemini_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    llm_provider: Literal["groq", "openai"] = "groq"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    max_upload_mb: int = 20

    cookie_secure: bool = Field(default=False)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
