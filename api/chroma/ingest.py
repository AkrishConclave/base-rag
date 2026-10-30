"""Индексация данных в ChromaDB"""
import os
import json
import glob
import chromadb
from api.config import settings
from api.chroma.client import get_embedder
from api.chroma.embeddings import encode_passages
from api.chroma.enrichment import enrich_missing_search_phrases
from api.llm.cache import get_cache
from api.utils.text import html_to_text, chunk_text
from api.vector_engine import InMemoryVectorIndex, replace_index


def find_support_json() -> str:
    """Находит JSON файл, начинающийся с support_ в корне проекта"""
    # Получаем корень проекта (3 уровня вверх от api/chroma/ingest.py)
    current_file = os.path.abspath(__file__)
    project_root_from_file = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
    
    # Текущая рабочая директория (может быть корень проекта)
    current_work_dir = os.getcwd()
    
    search_paths = [
        "/project_root",  # Docker контейнер
        project_root_from_file,  # Локальный запуск (из структуры api/chroma/ingest.py)
        current_work_dir,  # Текущая рабочая директория
        os.path.dirname(current_file),  # api/chroma/ (на случай если файл там)
    ]
    
    # Убираем дубликаты и проверяем существование путей
    unique_paths = []
    for path in search_paths:
        if path and os.path.exists(path) and path not in unique_paths:
            unique_paths.append(path)
    
    for project_root in unique_paths:
        pattern = os.path.join(project_root, "support_*.json")
        files = glob.glob(pattern)
        
        # Исключаем файлы с *old* в названии
        files = [
            f for f in files
            if "*old*" not in f
            and not f.endswith(".old.json")
            and os.path.basename(f) != "support_example.json"
        ]
        
        if files:
            # Берем самый новый файл по времени модификации
            return max(files, key=os.path.getmtime)
    
    raise FileNotFoundError(f"Не найден файл support_*.json. Проверенные пути: {unique_paths}")


def run_ingest() -> int:
    """Загружает данные из JSON файла и индексирует их в ChromaDB"""
    # Загружаем JSON файл
    json_file = find_support_json()
    print(f"Loading JSON file: {json_file}")
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    enriched = enrich_missing_search_phrases(data, json_file)
    if enriched:
        print(f"Generated search metadata for {enriched} articles")
    
    # Фильтруем статьи со status = 1 (для клиентов) и status = 0 (для staff)
    rows = [article for article in data.get("support", []) if article.get("status") in [0, 1]]
    rows_status_1 = [article for article in rows if article.get("status") == 1]
    rows_status_0 = [article for article in rows if article.get("status") == 0]
    print(f"Found {len(rows)} articles total:")
    print(f"  - Status 1 (для клиентов): {len(rows_status_1)}")
    print(f"  - Status 0 (для staff): {len(rows_status_0)}")
    
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
    
    # Собираем все документы и метаданные
    all_ids = []
    all_docs = []
    metadatas = []
    
    for row in rows:
        aid = str(row["id"])
        raw_html = row.get("text") or ""
        plain = html_to_text(raw_html)
        if not plain:
            continue
        search_phrases = row.get("search_phrases") or []
        if not isinstance(search_phrases, list):
            search_phrases = []
        search_phrases = [str(phrase).strip() for phrase in search_phrases if str(phrase).strip()]
        title = row.get("title") or ""
        if search_phrases:
            # Keep generated aliases in every embedded chunk.  A title prefix
            # alone can be lost when a backend normalises document content.
            plain = f"Поисковые формулировки: {'; '.join(search_phrases)}\n\n{plain}"
        chunks = chunk_text(plain, title=title)
        for idx, chunk in enumerate(chunks):
            doc_id = f"{aid}_{idx}"
            all_ids.append(doc_id)
            all_docs.append(chunk)
            metadatas.append({
                "article_id": aid,
                "title": row.get("title"),
                "seo": row.get("seo"),
                "menu": row.get("menu"),
                "chunk_index": idx,
                "status": row.get("status"),  # 0 = для staff, 1 = для клиентов
                "is_staff": str(row.get("status") == 0)  # Для удобной фильтрации
            })
    
    # Пакетное (batch) создание эмбеддингов по 64 штуки
    all_embs = []
    batch_size = 64
    print(f"Generating embeddings for {len(all_docs)} chunks in batches of {batch_size}...")
    for i in range(0, len(all_docs), batch_size):
        batch_docs = all_docs[i:i + batch_size]
        batch_embs = encode_passages(embedder, batch_docs, batch_size=len(batch_docs)).tolist()
        all_embs.extend(batch_embs)

    print("Adding to Chroma:", len(all_docs), "chunks")
    # Добавляем данные в ChromaDB пакетами для оптимальной работы
    chroma_batch_size = 500
    for i in range(0, len(all_docs), chroma_batch_size):
        collection.add(
            documents=all_docs[i:i + chroma_batch_size],
            embeddings=all_embs[i:i + chroma_batch_size],
            ids=all_ids[i:i + chroma_batch_size],
            metadatas=metadatas[i:i + chroma_batch_size]
        )
    # Chroma remains the durable copy. Publish the fully built RAM index only
    # after it has every vector, so concurrent searches never observe a half-index.
    replace_index(InMemoryVectorIndex.create(all_embs, all_docs, metadatas))
    # A new corpus changes the context for every answer, so no previous
    # response or provider cache entry may be reused.
    get_cache().clear()
    print("Done. Persisted to", settings.chroma_dir)
    
    # Подсчитываем статистику по статусам
    chunks_status_1 = sum(1 for meta in metadatas if meta.get("status") == 1)
    chunks_status_0 = sum(1 for meta in metadatas if meta.get("status") == 0)
    print(f"Chunks breakdown:")
    print(f"  - Status 1 (для клиентов): {chunks_status_1} chunks")
    print(f"  - Status 0 (для staff): {chunks_status_0} chunks")
    
    return len(all_docs)

