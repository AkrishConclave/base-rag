"""Провайдер OpenRouter для работы с LLM"""
from __future__ import annotations
import requests
import logging
from typing import List
from api.config import settings
from api.llm.base import LLMProvider
from api.llm.cache import get_cache

logger = logging.getLogger(__name__)


class OpenRouterProvider(LLMProvider):
    """Реализация LLM провайдера через OpenRouter API"""
    
    def __init__(self, api_key: str | None = None, model: str | None = None, fallback_models: List[str] | None = None):
        self.api_key = api_key or settings.openrouter_api_key
        self.model = model or settings.openrouter_model
        self.fallback_models = fallback_models or settings.openrouter_fallback_models
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.timeout = 30  # Таймаут запроса в секундах
    
    def _make_request(self, prompt: str, system_message: str | None, max_tokens: int, model: str) -> str:
        """Выполняет запрос к OpenRouter API с обработкой всех типов ошибок"""
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
        
        try:
            response = requests.post(
                self.base_url, 
                headers=headers, 
                json=payload, 
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            
            # Проверяем наличие ответа в данных
            if not data.get("choices") or not data["choices"][0].get("message"):
                raise ValueError(f"Неожиданный формат ответа от модели {model}")
            
            return data["choices"][0]["message"]["content"]
        except requests.exceptions.Timeout:
            logger.warning(f"Таймаут при запросе к модели {model}")
            raise Exception(f"Таймаут при запросе к модели {model}")
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"Ошибка подключения к OpenRouter для модели {model}: {e}")
            raise Exception(f"Не удалось подключиться к OpenRouter: {e}")
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else None
            logger.warning(f"HTTP ошибка {status_code} от модели {model}: {e}")
            raise
        except requests.exceptions.RequestException as e:
            logger.warning(f"Ошибка запроса к модели {model}: {e}")
            raise Exception(f"Ошибка запроса к OpenRouter: {e}")
        except (KeyError, ValueError, IndexError) as e:
            logger.error(f"Ошибка парсинга ответа от модели {model}: {e}")
            raise Exception(f"Неожиданный формат ответа от модели {model}: {e}")
    
    def complete(self, prompt: str, system_message: str | None = None, max_tokens: int = 700) -> str:
        """Генерирует ответ используя основную модель"""
        if not self.api_key:
            logger.warning("OPENROUTER_API_KEY не установлен")
            raise ValueError("OPENROUTER_API_KEY не установлен. Укажите его в файле .env")
        
        # Проверяем кэш
        cache = get_cache()
        cached_response = cache.get(prompt, system_message, self.model)
        if cached_response:
            logger.debug("💾 Ответ из кэша")
            return cached_response
        
        # Генерируем ответ
        try:
            response = self._make_request(prompt, system_message, max_tokens, self.model)
            # Сохраняем в кэш
            cache.set(prompt, system_message, self.model, response)
            return response
        except Exception as e:
            logger.error(f"Ошибка при генерации ответа основной моделью {self.model}: {e}")
            raise
    
    def complete_with_fallback(self, prompt: str, system_message: str | None = None, max_tokens: int = 700) -> str:
        """
        Генерирует ответ с использованием резервных моделей при ошибках.
        Пробует все доступные модели, включая fallback.
        """
        if not self.api_key:
            logger.warning("OPENROUTER_API_KEY не установлен")
            raise ValueError("OPENROUTER_API_KEY не установлен. Укажите его в файле .env")
        
        # Проверяем кэш для основной модели
        cache = get_cache()
        cached_response = cache.get(prompt, system_message, self.model)
        if cached_response:
            logger.debug("💾 Ответ из кэша")
            return cached_response
        
        models_to_try = [self.model] + self.fallback_models
        last_error = None
        errors_by_model = {}
        
        for model in models_to_try:
            try:
                logger.debug(f"Попытка запроса к модели: {model}")
                response = self._make_request(prompt, system_message, max_tokens, model)
                
                # Сохраняем в кэш только если использовали основную модель
                if model == self.model:
                    cache.set(prompt, system_message, model, response)
                
                logger.info(f"✅ Успешный ответ от модели: {model}")
                return response
                
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response else None
                error_msg = f"HTTP {status_code}"
                
                # Если ошибка 401 (Unauthorized) или 403 (Forbidden), не пробуем другие модели
                if status_code in [401, 403]:
                    logger.error(f"Критическая ошибка авторизации для модели {model}: {status_code}")
                    raise Exception(f"Ошибка авторизации OpenRouter (код {status_code}). Проверьте API ключ.")
                
                # Если ошибка 402 (Payment Required) или 429 (Rate Limit), пробуем следующую модель
                if status_code in [402, 429]:
                    error_msg = f"Модель {model} недоступна (код {status_code})"
                    logger.warning(f"⚠️ {error_msg}, пробую следующую...")
                    errors_by_model[model] = error_msg
                    last_error = error_msg
                    continue
                
                # Для других ошибок HTTP пробуем следующую модель
                error_msg = f"Модель {model} вернула ошибку {status_code}"
                logger.warning(f"⚠️ {error_msg}, пробую следующую...")
                errors_by_model[model] = error_msg
                last_error = error_msg
                continue
                
            except Exception as e:
                # Для всех остальных ошибок (таймауты, сетевые ошибки и т.д.) пробуем следующую модель
                error_msg = f"Ошибка при вызове модели {model}: {str(e)}"
                logger.warning(f"⚠️ {error_msg}, пробую следующую...")
                errors_by_model[model] = str(e)
                last_error = error_msg
                continue
        
        # Если все модели не сработали, выбрасываем исключение с детальной информацией
        error_summary = "; ".join([f"{m}: {e}" for m, e in errors_by_model.items()])
        logger.error(f"❌ Все модели недоступны. Ошибки: {error_summary}")
        raise Exception(f"Все модели OpenRouter недоступны. Последняя ошибка: {last_error}")

