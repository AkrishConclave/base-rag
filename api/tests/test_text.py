import pytest
from api.utils.text import chunk_text


def test_chunk_text_without_title():
    text = "Это первый фрагмент текста для тестирования разбиения на чанки."
    chunks = chunk_text(text, max_words=10, overlap=2)
    assert len(chunks) > 0
    assert not chunks[0].startswith("Заголовок:")
    assert "Это первый фрагмент" in chunks[0]


def test_chunk_text_with_title():
    text = "Это первый фрагмент текста для тестирования разбиения на чанки."
    title = "Настройка профиля"
    chunks = chunk_text(text, max_words=10, overlap=2, title=title)
    assert len(chunks) > 0
    assert chunks[0].startswith("Заголовок: Настройка профиля\n\n")
    assert "Это первый фрагмент" in chunks[0]


def test_chunk_text_with_empty_title():
    text = "Тестовый текст."
    chunks = chunk_text(text, title="   ")
    assert not chunks[0].startswith("Заголовок:")
    assert chunks[0] == "Тестовый текст."
