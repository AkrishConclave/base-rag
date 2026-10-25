"""Конфигурация приложения через переменные окружения"""
from pydantic_settings import BaseSettings
from pydantic import field_validator, Field, model_validator
from typing import List, Union, Any


class Settings(BaseSettings):
    """Настройки приложения из переменных окружения"""
    
    # OpenRouter настройки
    openrouter_api_key: str = ""  # Может быть пустым для тестов
    openrouter_model: str = "deepseek/deepseek-chat"
    openrouter_fallback_models: Union[str, List[str]] = Field(
        default=[
            'openai/gpt-5-mini',
            'openai/gpt-3.5-turbo',
            'anthropic/claude-3-haiku',
            'google/gemini-pro',
            'mistralai/mistral-7b-instruct:free',
            'microsoft/phi-3-mini-128k-instruct:free',
            'qwen/qwen-2.5-0.5b-instruct:free',
            'qwen/qwen-2.5-1.5b-instruct:free'
        ]
    )
    
    # ChromaDB настройки
    chroma_dir: str = "./chroma_db"
    chroma_collection_name: str = "support_articles"
    
    # Embedding модель
    embed_model: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
    
    # Поиск настройки
    top_k: int = 10
    max_distance: float = 0.8
    
    # LLM провайдер (openrouter, openai, anthropic и т.д.)
    llm_provider: str = "openrouter"
    
    # Логирование
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR
    
    # Кэширование
    cache_enabled: bool = True
    cache_ttl: int = 3600  # TTL кэша в секундах (1 час)
    cache_type: str = "sqlite"  # sqlite или redis
    
    # Redis настройки (если cache_type=redis)
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # Безопасность и авторизация
    admin_token: str = "secret-admin-token"
    jwt_secret: str = "secret-jwt-key"
    jwt_algorithm: str = "HS256"
    
    @field_validator('openrouter_fallback_models', mode='before')
    @classmethod
    def parse_fallback_models(cls, v: Any) -> List[str]:
        """Преобразует строку или список в List[str]"""
        default_models = [
            'openai/gpt-5-mini',
            'openai/gpt-3.5-turbo',
            'anthropic/claude-3-haiku',
            'google/gemini-pro',
            'mistralai/mistral-7b-instruct:free',
            'microsoft/phi-3-mini-128k-instruct:free',
            'qwen/qwen-2.5-0.5b-instruct:free',
            'qwen/qwen-2.5-1.5b-instruct:free'
        ]
        
        if v is None:
            return default_models
        
        if isinstance(v, list):
            parsed = [str(item).strip() for item in v if str(item).strip()]
            return parsed if parsed else default_models
        
        if isinstance(v, str):
            if not v.strip():
                return default_models
            
            # Пробуем распарсить как JSON (на случай, если передано как JSON массив)
            try:
                import json
                parsed_json = json.loads(v)
                if isinstance(parsed_json, list):
                    parsed = [str(item).strip() for item in parsed_json if str(item).strip()]
                    return parsed if parsed else default_models
            except (json.JSONDecodeError, ValueError):
                # Не JSON, продолжаем парсинг как строку с запятыми
                pass
            
            # Парсим строку с запятыми: "model1,model2,model3"
            parsed = [model.strip() for model in v.split(',') if model.strip()]
            return parsed if parsed else default_models
        
        return default_models
    
    @model_validator(mode='after')
    def ensure_fallback_models_list(self) -> 'Settings':
        """Гарантирует, что openrouter_fallback_models всегда List[str] после валидации"""
        if isinstance(self.openrouter_fallback_models, str):
            # Если все еще строка (не должно быть, но на всякий случай)
            parsed = [model.strip() for model in self.openrouter_fallback_models.split(',') if model.strip()]
            self.openrouter_fallback_models = parsed if parsed else [
                'openai/gpt-5-mini',
                'openai/gpt-3.5-turbo',
                'anthropic/claude-3-haiku',
                'google/gemini-pro',
                'mistralai/mistral-7b-instruct:free',
                'microsoft/phi-3-mini-128k-instruct:free',
                'qwen/qwen-2.5-0.5b-instruct:free',
                'qwen/qwen-2.5-1.5b-instruct:free'
            ]
        elif not isinstance(self.openrouter_fallback_models, list):
            # Если что-то другое, используем значение по умолчанию
            self.openrouter_fallback_models = [
                'openai/gpt-5-mini',
                'openai/gpt-3.5-turbo',
                'anthropic/claude-3-haiku',
                'google/gemini-pro',
                'mistralai/mistral-7b-instruct:free',
                'microsoft/phi-3-mini-128k-instruct:free',
                'qwen/qwen-2.5-0.5b-instruct:free',
                'qwen/qwen-2.5-1.5b-instruct:free'
            ]
        return self
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        
        @classmethod
        def customise_sources(cls, init_settings, env_settings, file_secret_settings):
            """Кастомизация источников настроек для поиска .env файла"""
            import os
            # Пробуем найти .env в нескольких местах
            env_paths = [
                os.path.join(os.path.dirname(__file__), ".env"),  # api/.env
                os.path.join(os.path.dirname(os.path.dirname(__file__)), "api", ".env"),  # ../api/.env
                ".env",  # Текущая директория
            ]
            for env_path in env_paths:
                if os.path.exists(env_path):
                    return (
                        init_settings,
                        env_settings._env_file_source(env_path),
                        file_secret_settings,
                    )
            return (init_settings, env_settings, file_secret_settings)


# Глобальный экземпляр настроек
settings = Settings()

