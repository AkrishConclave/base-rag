"""Фабрика для создания LLM провайдеров"""
from api.config import settings
from api.llm.base import LLMProvider
from api.llm.openrouter import OpenRouterProvider


def get_llm_provider() -> LLMProvider:
    """
    Создает и возвращает LLM провайдер на основе настроек
    
    Returns:
        Экземпляр LLM провайдера
        
    Raises:
        ValueError: Если указан неизвестный провайдер
    """
    provider_name = settings.llm_provider.lower()
    
    if provider_name == "openrouter":
        return OpenRouterProvider()
    else:
        raise ValueError(
            f"Неизвестный LLM провайдер: {provider_name}. "
            f"Доступные провайдеры: openrouter"
        )

