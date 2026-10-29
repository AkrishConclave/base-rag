"""Конфигурация приложения через переменные окружения."""
from functools import cached_property

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки RAG и Yandex AI Studio."""

    model_config = SettingsConfigDict(
        env_file=("api/.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Yandex AI Studio через OpenAI-совместимый Responses API.
    yandex_cloud_folder: str = ""
    yandex_cloud_api_key: str = ""
    yandex_cloud_model: str = "deepseek-v4-flash/latest"
    yandex_cloud_base_url: str = "https://ai.api.cloud.yandex.net/v1"
    yandex_cloud_temperature: float = 0.3
    yandex_cloud_max_output_tokens: int = 65536

    # ChromaDB.
    chroma_dir: str = "./chroma_db"
    chroma_collection_name: str = "support_articles"

    # Embedding model.
    embed_model: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"

    # Search.
    top_k: int = 10
    max_distance: float = 0.8

    llm_provider: str = "yandex_ai_studio"

    # Logging and cache.
    log_level: str = "INFO"
    cache_enabled: bool = True
    cache_ttl: int = 3600
    cache_type: str = "sqlite"
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # Authorization.
    admin_token: str = ""
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"

    @cached_property
    def yandex_cloud_model_uri(self) -> str:
        """Полный URI модели, ожидаемый Yandex AI Studio."""
        if not self.yandex_cloud_folder:
            return ""
        return f"gpt://{self.yandex_cloud_folder}/{self.yandex_cloud_model}"


settings = Settings()
