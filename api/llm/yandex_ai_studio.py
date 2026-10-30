"""Yandex AI Studio provider via the OpenAI-compatible Responses API."""
from __future__ import annotations

import logging
import time

import openai

from api.config import settings
from api.llm.base import LLMProvider
from api.llm.cache import get_cache

logger = logging.getLogger(__name__)


class YandexAIStudioProvider(LLMProvider):
    """Generates answers with a model deployed in Yandex AI Studio."""

    def __init__(
        self,
        api_key: str | None = None,
        folder: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or settings.yandex_cloud_api_key
        self.folder = folder or settings.yandex_cloud_folder
        self.model = model or settings.yandex_cloud_model
        self.model_uri = f"gpt://{self.folder}/{self.model}" if self.folder else ""
        self.client: openai.OpenAI | None = None

    def _get_client(self) -> openai.OpenAI:
        """Creates the SDK client only after credentials have been validated."""
        if self.client is None:
            self.client = openai.OpenAI(
                api_key=self.api_key,
                base_url=settings.yandex_cloud_base_url,
                project=self.folder,
            )
        return self.client

    def _validate_configuration(self) -> None:
        if not self.api_key:
            raise ValueError("YANDEX_CLOUD_API_KEY не установлен. Укажите его в api/.env.")
        if not self.folder:
            raise ValueError("YANDEX_CLOUD_FOLDER не установлен. Укажите ID каталога в api/.env.")

    def _make_request(
        self,
        prompt: str,
        system_message: str | None,
        max_tokens: int,
    ) -> str:
        started_at = time.perf_counter()
        response = self._get_client().responses.create(
            model=self.model_uri,
            temperature=settings.yandex_cloud_temperature,
            instructions=system_message or "",
            input=prompt,
            max_output_tokens=max_tokens,
            store=True,
            truncation="disabled",
        )
        logger.info("Yandex AI Studio response received in %.3f s", time.perf_counter() - started_at)
        if not response.output_text:
            raise ValueError("Yandex AI Studio вернул ответ без текста")
        return response.output_text

    def complete(
        self,
        prompt: str,
        system_message: str | None = None,
        max_tokens: int = 65536,
    ) -> str:
        self._validate_configuration()
        cache = get_cache()
        cached_response = cache.get(prompt, system_message, self.model_uri)
        if cached_response:
            return cached_response

        try:
            response = self._make_request(prompt, system_message, max_tokens)
        except openai.APIStatusError as error:
            logger.error("Yandex AI Studio returned HTTP %s", error.status_code)
            raise RuntimeError(f"Ошибка Yandex AI Studio (HTTP {error.status_code})") from error
        except openai.APIError as error:
            logger.error("Yandex AI Studio request failed: %s", error)
            raise RuntimeError("Не удалось выполнить запрос к Yandex AI Studio") from error

        cache.set(prompt, system_message, self.model_uri, response)
        return response

    def complete_with_fallback(
        self,
        prompt: str,
        system_message: str | None = None,
        max_tokens: int = 65536,
    ) -> str:
        """Compatibility method: Yandex AI Studio uses the configured model only."""
        return self.complete(prompt, system_message, max_tokens)
