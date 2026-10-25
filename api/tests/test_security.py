"""Тесты безопасности и авторизации"""
import jwt
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from api.main import app
from api.config import settings

client = TestClient(app)


def test_ask_request_ignores_admin_mode_in_body():
    """Тест: передача admin_mode в теле запроса не включает админ режим без заголовка"""
    with patch("api.routes.rag.search") as mock_search:
        mock_search.return_value = []

        # Передаем admin_mode: true в body
        response = client.post("/api/ask", json={"q": "тест", "admin_mode": True})

        assert response.status_code == 200
        # Проверяем, что функция search была вызвана с admin_mode=False (поскольку заголовка авторизации нет)
        assert mock_search.called
        _, kwargs = mock_search.call_args
        assert kwargs.get("admin_mode") is False


def test_ask_with_x_admin_token():
    """Тест: заголовок X-Admin-Token дает доступ к admin_mode=True"""
    with patch("api.routes.rag.search") as mock_search:
        mock_search.return_value = []

        headers = {"X-Admin-Token": settings.admin_token}
        response = client.post("/api/ask", json={"q": "тест"}, headers=headers)

        assert response.status_code == 200
        assert mock_search.called
        _, kwargs = mock_search.call_args
        assert kwargs.get("admin_mode") is True


def test_ask_with_valid_jwt_token():
    """Тест: валидный JWT токен staff/admin в Authorization header дает доступ к admin_mode=True"""
    with patch("api.routes.rag.search") as mock_search:
        mock_search.return_value = []

        # Создаем JWT токен с ролью staff
        payload = {"sub": "user123", "role": "staff"}
        token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

        headers = {"Authorization": f"Bearer {token}"}
        response = client.post("/api/ask", json={"q": "тест"}, headers=headers)

        assert response.status_code == 200
        assert mock_search.called
        _, kwargs = mock_search.call_args
        assert kwargs.get("admin_mode") is True


def test_ask_with_invalid_jwt_token():
    """Тест: невалидный JWT токен не дает админ доступа"""
    with patch("api.routes.rag.search") as mock_search:
        mock_search.return_value = []

        headers = {"Authorization": "Bearer invalid.jwt.token"}
        response = client.post("/api/ask", json={"q": "тест"}, headers=headers)

        assert response.status_code == 200
        assert mock_search.called
        _, kwargs = mock_search.call_args
        assert kwargs.get("admin_mode") is False


def test_protected_ingest_without_token():
    """Тест: запрос к /api/ingest без токена возвращает 401"""
    response = client.post("/api/ingest")
    assert response.status_code == 401


def test_protected_ingest_with_token():
    """Тест: запрос к /api/ingest с X-Admin-Token проходит авторизацию"""
    with patch("api.routes.ingest.run_ingest") as mock_ingest:
        mock_ingest.return_value = 10
        headers = {"X-Admin-Token": settings.admin_token}
        response = client.post("/api/ingest", headers=headers)

        assert response.status_code == 200
        assert response.json() == {"indexed_chunks": 10}


def test_protected_debug_endpoint_without_token():
    """Тест: запрос к /api/debug/check-ids без токена возвращает 401"""
    response = client.post("/api/debug/check-ids", json={"start_id": 1, "end_id": 10})
    assert response.status_code == 401


def test_check_ids_dos_protection_large_range():
    """Тест защиты от DoS: разница между start_id и end_id > 1000 вызывает ошибку 422"""
    headers = {"X-Admin-Token": settings.admin_token}
    response = client.post(
        "/api/debug/check-ids",
        json={"start_id": 1, "end_id": 2000},
        headers=headers
    )
    assert response.status_code == 422


def test_check_ids_invalid_range():
    """Тест защиты от DoS: end_id < start_id вызывает ошибку 422"""
    headers = {"X-Admin-Token": settings.admin_token}
    response = client.post(
        "/api/debug/check-ids",
        json={"start_id": 100, "end_id": 10},
        headers=headers
    )
    assert response.status_code == 422


def test_check_ids_valid_range():
    """Тест: валидный диапазон в /api/debug/check-ids проходит проверку Pydantic"""
    headers = {"X-Admin-Token": settings.admin_token}
    with patch("api.chroma.client.get_collection") as mock_get_col:
        mock_collection = mock_get_col.return_value
        mock_collection.get.return_value = {"ids": [], "documents": [], "metadatas": []}

        response = client.post(
            "/api/debug/check-ids",
            json={"start_id": 1, "end_id": 10},
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["start_id"] == 1
        assert data["end_id"] == 10
        assert data["missing_count"] == 10
