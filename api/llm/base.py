"""Базовый класс для LLM провайдеров"""
from abc import ABC, abstractmethod
from typing import List


class LLMProvider(ABC):
    """Абстрактный базовый класс для LLM провайдеров"""
    
    @abstractmethod
    def complete(self, prompt: str, system_message: str | None = None, max_tokens: int = 700) -> str:
        """
        Генерирует ответ на основе промпта
        
        Args:
            prompt: Текст промпта
            system_message: Системное сообщение (опционально)
            max_tokens: Максимальное количество токенов в ответе
            
        Returns:
            Сгенерированный текст
            
        Raises:
            Exception: Если генерация не удалась
        """
        pass
    
    @abstractmethod
    def complete_with_fallback(self, prompt: str, system_message: str | None = None, max_tokens: int = 700) -> str:
        """
        Генерирует ответ с использованием резервных моделей при ошибках
        
        Args:
            prompt: Текст промпта
            system_message: Системное сообщение (опционально)
            max_tokens: Максимальное количество токенов в ответе
            
        Returns:
            Сгенерированный текст
            
        Raises:
            Exception: Если все модели недоступны
        """
        pass

