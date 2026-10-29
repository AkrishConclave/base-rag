"""Фабрика для создания LLM провайдеров"""
from api.config import settings
from api.llm.base import LLMProvider
from api.llm.yandex_ai_studio import YandexAIStudioProvider


def get_llm_provider() -> LLMProvider:
    """
    Создает и возвращает LLM провайдер на основе настроек
    
    Returns:
        Экземпляр LLM провайдера
        
    Raises:
        ValueError: Если указан неизвестный провайдер
    """
    provider_name = settings.llm_provider.lower()
    
    if provider_name == "yandex_ai_studio":
        return YandexAIStudioProvider()
    else:
        raise ValueError(
            f"Неизвестный LLM провайдер: {provider_name}. "
            "Доступные провайдеры: yandex_ai_studio"
        )

