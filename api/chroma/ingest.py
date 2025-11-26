"""Индексация данных в ChromaDB"""
import os
import json
import glob
import chromadb
from api.config import settings
from api.chroma.client import get_embedder
from api.utils.text import html_to_text, chunk_text


def find_support_json() -> str:
    """Находит JSON файл, начинающийся с support_ в корне проекта"""
    search_paths = [
        "/project_root",  # Docker контейнер
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),  # Локальный запуск
        os.path.dirname(os.path.abspath(__file__)),  # Текущая директория
    ]
    
    for project_root in search_paths:
        pattern = os.path.join(project_root, "support_*.json")
        files = glob.glob(pattern)
        if files:
            # Берем самый новый файл по времени модификации
            return max(files, key=os.path.getmtime)
    
    raise FileNotFoundError(f"Не найден файл support_*.json. Проверенные пути: {search_paths}")


def run_ingest() -> int:
    """Загружает данные из JSON файла и индексирует их в ChromaDB"""
    # Загружаем JSON файл
    json_file = find_support_json()
    print(f"Loading JSON file: {json_file}")
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Фильтруем статьи со status = 1
    rows = [article for article in data.get("support", []) if article.get("status") == 1]
    print(f"Found {len(rows)} articles")
    
    # Инициализируем embedder и chroma
    embedder = get_embedder()
    client = chromadb.PersistentClient(path=settings.chroma_dir)
    collection = client.get_or_create_collection(name=settings.chroma_collection_name)
    
    # Очищаем коллекцию (при каждом запуске перезаписываем)
    try:
        collection.delete()
        collection = client.get_or_create_collection(name=settings.chroma_collection_name)
    except Exception:
        pass
    
    # Индексируем данные
    all_ids = []
    all_docs = []
    all_embs = []
    metadatas = []
    
    for row in rows:
        aid = str(row["id"])
        raw_html = row.get("text") or ""
        plain = html_to_text(raw_html)
        if not plain:
            continue
        chunks = chunk_text(plain)
        for idx, chunk in enumerate(chunks):
            doc_id = f"{aid}_{idx}"
            all_ids.append(doc_id)
            all_docs.append(chunk)
            emb = embedder.encode(chunk).tolist()
            all_embs.append(emb)
            metadatas.append({
                "article_id": aid,
                "title": row.get("title"),
                "seo": row.get("seo"),
                "menu": row.get("menu"),
                "chunk_index": idx
            })
    
    print("Adding to Chroma:", len(all_docs), "chunks")
    collection.add(documents=all_docs, embeddings=all_embs, ids=all_ids, metadatas=metadatas)
    print("Done. Persisted to", settings.chroma_dir)
    
    return len(all_docs)

