"""Automatic generation of search metadata for support exports."""
from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path

import openai

from api.config import settings
from api.utils.text import html_to_text

logger = logging.getLogger(__name__)


def _generate_search_phrases(client: openai.OpenAI, article: dict) -> list[str]:
    text = html_to_text(article.get("text") or "")[:6000]
    prompt = f'''Сформируй от 5 до 8 коротких поисковых формулировок для статьи базы знаний.
Они должны покрывать перефразирования, синонимы и типичные вопросы пользователя.
Верни только JSON-массив строк, без Markdown и пояснений.

Заголовок: {article.get("title", "")}
Текст: {text}'''
    response = client.responses.create(
        model=settings.yandex_cloud_model_uri,
        temperature=0.1,
        instructions="Ты готовишь поисковые метаданные для русскоязычной базы знаний.",
        input=prompt,
        max_output_tokens=300,
        store=False,
        truncation="disabled",
    )
    match = re.search(r"\[[\s\S]*\]", response.output_text.strip())
    if not match:
        raise ValueError("Yandex did not return a JSON array for search_phrases")
    phrases = json.loads(match.group(0))
    if not isinstance(phrases, list) or not all(isinstance(item, str) for item in phrases):
        raise ValueError("Yandex returned an invalid search_phrases value")
    return list(dict.fromkeys(item.strip() for item in phrases if item.strip()))[:8]


def enrich_missing_search_phrases(data: dict, source_path: str) -> int:
    """Persist Yandex-generated phrases only for articles that have none yet."""
    missing = [
        article for article in data.get("support", [])
        if article.get("status") in (0, 1)
        and html_to_text(article.get("text") or "")
        and not article.get("search_phrases")
    ]
    if not missing:
        return 0
    if not settings.yandex_cloud_api_key or not settings.yandex_cloud_folder:
        logger.warning("Skipping search metadata enrichment: Yandex credentials are not configured")
        return 0

    source = Path(source_path)
    backup = source.with_suffix(source.suffix + ".before-metadata.bak")
    if not backup.exists():
        shutil.copy2(source, backup)
    client = openai.OpenAI(
        api_key=settings.yandex_cloud_api_key,
        base_url=settings.yandex_cloud_base_url,
        project=settings.yandex_cloud_folder,
    )
    enriched = 0
    for article in missing:
        try:
            article["search_phrases"] = _generate_search_phrases(client, article)
            enriched += 1
            logger.info("Generated search metadata for article %s", article.get("id"))
        except Exception as error:
            logger.warning("Could not enrich article %s: %s", article.get("id"), error)

    if enriched:
        source.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return enriched
