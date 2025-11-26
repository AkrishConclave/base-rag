"""Провайдер OpenRouter для работы с LLM"""
from __future__ import annotations
import requests
from typing import List
from api.config import settings
from api.llm.base import LLMProvider
from api.llm.cache import get_cache


class OpenRouterProvider(LLMProvider):
    """Реализация LLM провайдера через OpenRouter API"""
    
    def __init__(self, api_key: str | None = None, model: str | None = None, fallback_models: List[str] | None = None):
        self.api_key = api_key or settings.openrouter_api_key
        self.model = model or settings.openrouter_model
        self.fallback_models = fallback_models or settings.openrouter_fallback_models
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
    
    def _make_request(self, prompt: str, system_message: str | None, max_tokens: int, model: str) -> str:
        """Выполняет запрос к OpenRouter API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/your-repo",
            "X-Title": "Pinbox RAG Support"
        }
        
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens
        }
        
        response = requests.post(self.base_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    
    def complete(self, prompt: str, system_message: str | None = None, max_tokens: int = 700) -> str:
        """Генерирует ответ используя основную модель"""
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY не установлен. Укажите его в файле .env")
        
        # Проверяем кэш
        cache = get_cache()
        cached_response = cache.get(prompt, system_message, self.model)
        if cached_response:
            print("💾 Ответ из кэша")
            return cached_response
        
        # Генерируем ответ
        response = self._make_request(prompt, system_message, max_tokens, self.model)
        
        # Сохраняем в кэш
        cache.set(prompt, system_message, self.model, response)
        
        return response
    
    def complete_with_fallback(self, prompt: str, system_message: str | None = None, max_tokens: int = 700) -> str:
        """Генерирует ответ с использованием резервных моделей при ошибках"""
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY не установлен. Укажите его в файле .env")
        
        # Проверяем кэш для основной модели
        cache = get_cache()
        cached_response = cache.get(prompt, system_message, self.model)
        if cached_response:
            print("💾 Ответ из кэша")
            return cached_response
        
        models_to_try = [self.model] + self.fallback_models
        last_error = None
        
        for model in models_to_try:
            try:
                response = self._make_request(prompt, system_message, max_tokens, model)
                # Сохраняем в кэш только если использовали основную модель
                if model == self.model:
                    cache.set(prompt, system_message, model, response)
                return response
            except requests.exceptions.HTTPError as e:
                # Если ошибка 402 (Payment Required) или 429 (Rate Limit), пробуем следующую модель
                if e.response.status_code in [402, 429]:
                    last_error = f"Модель {model} недоступна (код {e.response.status_code}), пробую следующую..."
                    print(f"⚠️ {last_error}")
                    continue
                # Для других ошибок HTTP пробуем следующую модель
                last_error = f"Модель {model} вернула ошибку {e.response.status_code}, пробую следующую..."
                print(f"⚠️ {last_error}")
                continue
            except Exception as e:
                # Для других ошибок тоже пробуем следующую модель
                last_error = f"Ошибка при вызове модели {model}: {str(e)}, пробую следующую..."
                print(f"⚠️ {last_error}")
                continue
        
        # Если все модели не сработали, выбрасываем исключение
        raise Exception(f"Все модели недоступны. Последняя ошибка: {last_error}")

