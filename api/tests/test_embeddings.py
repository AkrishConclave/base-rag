"""Input contracts for asymmetric multilingual E5 retrieval."""
from unittest.mock import MagicMock

from api.chroma.embeddings import as_passage, as_query, encode_passages, encode_query


def test_e5_uses_different_prefixes_for_queries_and_passages():
    assert as_query(" Как включить уведомления? ") == "query: Как включить уведомления?"
    assert as_passage(" Инструкция ") == "passage: Инструкция"


def test_e5_encoding_requests_normalised_embeddings():
    embedder = MagicMock()
    embedder.encode.return_value = [[0.1, 0.2]]

    encode_query(embedder, "тест")
    assert embedder.encode.call_args.args[0] == ["query: тест"]
    assert embedder.encode.call_args.kwargs == {"normalize_embeddings": True}

    encode_passages(embedder, ["один", "два"], batch_size=64)
    assert embedder.encode.call_args.args[0] == ["passage: один", "passage: два"]
    assert embedder.encode.call_args.kwargs == {
        "batch_size": 64,
        "show_progress_bar": False,
        "normalize_embeddings": True,
    }
