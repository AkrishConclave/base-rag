"""Интеграционные тесты для API (/health, /api/ask и валидация)."""
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health_check_endpoint():
    """Тест эндпоинта /health: проверка статуса 200 и структуры JSON"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "chroma_db" in data


def test_ask_endpoint_success():
    """Тест успешного запроса к /api/ask с мокингом поиска и LLM"""
    with patch("api.routes.rag.search") as mock_search, \
         patch("api.routes.rag.get_llm_provider") as mock_get_llm:

        mock_hit = MagicMock()
        mock_hit.doc = "Текст найденной статьи поддержки"
        mock_hit.meta = {"title": "Настройка интеграции", "article_id": "42"}
        mock_hit.dist = 0.15
        mock_search.return_value = [mock_hit]

        mock_provider = MagicMock()
        mock_provider.complete_with_fallback.return_value = "Для настройки интеграции перейдите в раздел Настройки."
        mock_get_llm.return_value = mock_provider

        response = client.post("/api/ask", json={"q": "Как настроить интеграцию?"})

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert data["answer"] == "Для настройки интеграции перейдите в раздел Настройки."
        assert len(data["sources"]) == 1
        assert data["sources"][0]["title"] == "Настройка интеграции"
        assert data["sources"][0]["id"] == "42"


@pytest.mark.parametrize("invalid_payload", [
    {},
    {"q": ""},
    {"q": "   "},
    {"q": None},
])
def test_ask_empty_or_missing_question_validation(invalid_payload):
    """Тест валидации пустых или отсутствующих вопросов в /api/ask"""
    response = client.post("/api/ask", json=invalid_payload)
    assert response.status_code in (400, 422)
    data = response.json()
    assert "detail" in data
    assert "ошибка" in data["detail"].lower() or "пустым" in data["detail"].lower() or "вопрос" in data["detail"].lower()
