"""Тесты безопасности и авторизации"""
import jwt
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from api.main import app
from api.config import settings

client = TestClient(app)


@pytest.fixture(autouse=True)
def configured_admin_secrets(monkeypatch):
    """Each test opts into explicit, non-production authorization secrets."""
    monkeypatch.setattr(settings, "admin_token", "test-admin-token")
    monkeypatch.setattr(settings, "jwt_secret", "test-jwt-secret-with-at-least-32-characters")


@pytest.fixture(autouse=True)
def disable_query_rewrite_for_route_mocks():
    """Route authorization tests do not need a loaded vector index."""
    with patch("api.routes.rag._needs_query_rewrite", return_value=False):
        yield


def test_public_ask_searches_full_corpus_without_header():
    """Public ask endpoint intentionally searches the complete knowledge base."""
    with patch("api.routes.rag.search") as mock_search:
        mock_search.return_value = []

        response = client.post("/api/ask", json={"q": "тест", "admin_mode": True})

        assert response.status_code == 200
        assert mock_search.called
        _, kwargs = mock_search.call_args
        assert kwargs.get("admin_mode") is True


def test_ask_with_x_admin_token_keeps_public_search_scope():
    with patch("api.routes.rag.search") as mock_search:
        mock_search.return_value = []

        headers = {"X-Admin-Token": settings.admin_token}
        response = client.post("/api/ask", json={"q": "тест x-admin-token"}, headers=headers)

        assert response.status_code == 200
        assert mock_search.called
        _, kwargs = mock_search.call_args
        assert kwargs.get("admin_mode") is True


def test_ask_with_valid_jwt_token_keeps_public_search_scope():
    with patch("api.routes.rag.search") as mock_search:
        mock_search.return_value = []

        # Создаем JWT токен с ролью staff
        payload = {"sub": "user123", "role": "staff"}
        token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

        headers = {"Authorization": f"Bearer {token}"}
        response = client.post("/api/ask", json={"q": "тест valid-jwt"}, headers=headers)

        assert response.status_code == 200
        assert mock_search.called
        _, kwargs = mock_search.call_args
        assert kwargs.get("admin_mode") is True


def test_ask_with_invalid_jwt_token_keeps_public_search_scope():
    with patch("api.routes.rag.search") as mock_search:
        mock_search.return_value = []

        headers = {"Authorization": "Bearer invalid.jwt.token"}
        response = client.post("/api/ask", json={"q": "тест invalid-jwt"}, headers=headers)

        assert response.status_code == 200
        assert mock_search.called
        _, kwargs = mock_search.call_args
        assert kwargs.get("admin_mode") is True


def test_jwt_does_not_change_public_search_scope_when_secret_is_missing(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "")
    token = jwt.encode({"role": "staff"}, "untrusted-secret", algorithm="HS256")

    with patch("api.routes.rag.search") as mock_search:
        mock_search.return_value = []
        response = client.post("/api/ask", json={"q": "тест missing-jwt-secret"}, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert mock_search.call_args.kwargs["admin_mode"] is True


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


def test_upload_endpoints_require_admin_token():
    """Загрузка и скачивание базы знаний доступны только администратору."""
    assert client.post("/api/upload-support").status_code == 401
    assert client.get("/api/download-support").status_code == 401


def test_upload_keeps_existing_exports(monkeypatch, tmp_path):
    """Новая загрузка не переименовывает шаблон и прежние экспорты."""
    example_file = tmp_path / "support_example.json"
    real_export = tmp_path / "support_202610311200.json"
    example_file.write_text('{"support": []}', encoding="utf-8")
    real_export.write_text('{"support": [{"id": 1}]}', encoding="utf-8")
    monkeypatch.setattr("api.routes.upload.get_project_root", lambda: str(tmp_path))

    response = client.post(
        "/api/upload-support",
        headers={"X-Admin-Token": settings.admin_token},
        files={
            "file": (
                "support_202611011000.json",
                b'{"support": [{"id": 2}]}',
                "application/json",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["old_file_renamed"] is None
    assert response.json()["size_bytes"] > 0
    assert example_file.exists()
    assert real_export.exists()
    assert not list(tmp_path.glob("support_*old*.json"))
    assert (tmp_path / "support_202611011000.json").exists()


def test_upload_limit_keeps_previous_file(monkeypatch, tmp_path):
    """Превышение лимита возвращает 413 и не повреждает прежний экспорт."""
    target = tmp_path / "support_202611011000.json"
    target.write_text('{"support": [{"id": 1}]}', encoding="utf-8")
    monkeypatch.setattr("api.routes.upload.get_project_root", lambda: str(tmp_path))
    monkeypatch.setattr(settings, "max_support_upload_bytes", 16)

    response = client.post(
        "/api/upload-support",
        headers={"X-Admin-Token": settings.admin_token},
        files={
            "file": (
                target.name,
                b'{"support": [{"id": 22222222222222222222}]}',
                "application/json",
            )
        },
    )

    assert response.status_code == 413
    assert target.read_text(encoding="utf-8") == '{"support": [{"id": 1}]}'
    assert not list(tmp_path.glob("*.upload"))


def test_invalid_upload_keeps_previous_file(monkeypatch, tmp_path):
    """Невалидный JSON не публикуется поверх существующего экспорта."""
    target = tmp_path / "support_202611011000.json"
    target.write_text('{"support": [{"id": 1}]}', encoding="utf-8")
    monkeypatch.setattr("api.routes.upload.get_project_root", lambda: str(tmp_path))

    response = client.post(
        "/api/upload-support",
        headers={"X-Admin-Token": settings.admin_token},
        files={"file": (target.name, b'{"support": [', "application/json")},
    )

    assert response.status_code == 400
    assert target.read_text(encoding="utf-8") == '{"support": [{"id": 1}]}'
    assert not list(tmp_path.glob("*.upload"))


def test_embed_endpoint_requires_admin_token():
    """Ресурсоёмкое создание эмбеддингов не должно быть публичным."""
    assert client.post("/api/embed", json={"text": "тест"}).status_code == 401


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
