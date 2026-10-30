"""Тесты производительности и асинхронности"""
import pytest
import json
from unittest.mock import patch, MagicMock, mock_open
from fastapi.testclient import TestClient

from api.main import app
from api.llm.prompt_refine import expand_query_with_llm
from api.chroma.ingest import run_ingest
from api.vector_engine.index import InMemoryVectorIndex

client = TestClient(app)


def test_heuristic_query_expansion_fast():
    """Тест: эвристическое расширение запроса работает быстро и без вызова LLM"""
    expanded = expand_query_with_llm("Как настроить автообжалование?")
    assert "настроить" in expanded
    assert "автообжалование" in expanded
    assert "автоматическое обжалование" in expanded or "подключить" in expanded


def test_ask_endpoint_async_nonblocking():
    """Тест: эндпоинт /api/ask вызывает search и LLM в asyncio.to_thread"""
    with patch("api.routes.rag.hybrid_search") as mock_hybrid_search, \
         patch("api.routes.rag.get_llm_provider") as mock_get_llm:

        mock_hit = MagicMock()
        mock_hit.doc = "Тестовый документ"
        mock_hit.meta = {"title": "Тест", "article_id": "1"}
        mock_hit.dist = 0.1
        mock_hybrid_search.return_value = [mock_hit]

        mock_provider = MagicMock()
        mock_provider.complete_with_fallback.return_value = "Тестовый ответ LLM"
        mock_get_llm.return_value = mock_provider

        response = client.post("/api/ask", json={"q": "тест", "use_hybrid": True})

        assert response.status_code == 200
        assert response.json()["answer"] == "Тестовый ответ LLM"
        assert len(response.json()["sources"]) == 1
        assert mock_hybrid_search.called
        assert mock_provider.complete_with_fallback.called


def test_batch_ingest_execution():
    """Тест: пакетирование в run_ingest вызывает embedder.encode с пакетами"""
    test_data = {
        "support": [
            {"id": i, "status": 1, "title": f"Article {i}", "text": f"<p>Content for article {i}</p>"}
            for i in range(10)
        ]
    }
    json_bytes = json.dumps(test_data).encode("utf-8")

    with patch("api.chroma.ingest.find_support_json", return_value="/dummy/path/support_test.json"), \
         patch("api.chroma.ingest.enrich_missing_search_phrases", return_value=0), \
         patch("api.chroma.ingest.get_embedder") as mock_get_embedder, \
         patch("chromadb.PersistentClient") as mock_chroma_client, \
         patch("builtins.open", mock_open(read_data=json_bytes)):

        mock_embedder = MagicMock()
        mock_embedder.encode.side_effect = lambda docs, batch_size=64, show_progress_bar=False, normalize_embeddings=False: MagicMock(
            tolist=lambda: [[0.1] * 384 for _ in docs]
        )
        mock_get_embedder.return_value = mock_embedder

        mock_client_inst = MagicMock()
        mock_collection = MagicMock()
        mock_client_inst.get_or_create_collection.return_value = mock_collection
        mock_chroma_client.return_value = mock_client_inst

        chunk_count = run_ingest()
        assert chunk_count == 10
        assert mock_embedder.encode.called
        call_args = mock_embedder.encode.call_args[0]
        assert isinstance(call_args[0], list)
        assert all(text.startswith("passage: ") for text in call_args[0])
        assert mock_embedder.encode.call_args.kwargs["normalize_embeddings"] is True


def test_native_memory_index_returns_only_public_documents_without_admin_access():
    """The C candidate list enforces visibility before any result is returned."""
    index = InMemoryVectorIndex.create(
        embeddings=[[1.0, 0.0], [0.99, 0.01], [0.0, 1.0]],
        documents=["public", "staff", "other public"],
        metadatas=[{"status": 1}, {"status": 0}, {"status": 1}],
    )

    public_hits = index.search([1.0, 0.0], top_k=3, admin_mode=False)
    admin_hits = index.search([1.0, 0.0], top_k=3, admin_mode=True)

    assert [hit.doc for hit in public_hits] == ["public", "other public"]
    assert [hit.doc for hit in admin_hits][:2] == ["public", "staff"]
