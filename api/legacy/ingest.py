# ingest.py
import os
import re
import json
import glob
import chromadb
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()
CHROMA_DIR = os.getenv("CHROMA_DIR", "./chroma_db")
EMBED_MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/paraphrase-multilingual-mpnet-base-v2")  # Хорошая мультиязычная модель для русского
TOP_K = int(os.getenv("TOP_K", "10"))

# --------------- helpers ---------------
def html_to_text(html):
    # простая очистка — удаляем теги, оставляем текст
    # Сначала удаляем base64 изображения (они очень длинные и засоряют текст)
    text = re.sub(r'<img[^>]*src=["\']data:image/[^"\']*["\'][^>]*>', '', html, flags=re.S|re.I)
    # Удаляем все теги img с base64 в атрибуте src (более полный паттерн)
    text = re.sub(r'<img[^>]*src=["\']data:[^"\']*["\'][^>]*/?>', '', text, flags=re.S|re.I)
    # Удаляем script и style блоки
    text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.S|re.I)
    text = re.sub(r'<style.*?>.*?</style>', '', text, flags=re.S|re.I)
    # Удаляем комментарии
    text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
    # Удаляем все остальные HTML теги
    text = re.sub(r'<[^>]+>', ' ', text)
    # Нормализуем пробелы
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def chunk_text(text, max_words=220, overlap=40):
    words = text.split()
    chunks = []
    i = 0
    n = len(words)
    while i < n:
        chunk = words[i:i+max_words]
        chunks.append(" ".join(chunk))
        i += max_words - overlap
    return chunks

# --------------- load json file ---------------
def find_support_json():
    """Находит JSON файл, начинающийся с support_ в корне проекта"""
    # Пробуем несколько возможных путей
    search_paths = [
        "/project_root",  # Docker контейнер
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),  # Локальный запуск
        os.path.dirname(os.path.abspath(__file__)),  # Текущая директория
    ]
    
    for project_root in search_paths:
        pattern = os.path.join(project_root, "support_*.json")
        files = glob.glob(pattern)
        if files:
            # Берем первый найденный файл (самый новый по времени модификации)
            return max(files, key=os.path.getmtime)
    
    raise FileNotFoundError(f"Не найден файл support_*.json. Проверенные пути: {search_paths}")

def run_ingest():
    """Загружает данные из JSON файла и индексирует их в ChromaDB"""
    # --------------- load json file ---------------
    json_file = find_support_json()
    print(f"Loading JSON file: {json_file}")
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Фильтруем статьи со status = 1
    rows = [article for article in data.get("support", []) if article.get("status") == 1]
    print(f"Found {len(rows)} articles")
    
    # --------------- init embedder and chroma ---------------
    print("Loading embedder:", EMBED_MODEL)
    embedder = SentenceTransformer(EMBED_MODEL)
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_or_create_collection(name="support_articles")
    
    # очищаем коллекцию (при каждом запуске перезаписываем)
    try:
        collection.delete()
        collection = client.get_or_create_collection(name="support_articles")
    except Exception:
        pass
    
    # --------------- ingest ---------------
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
    print("Done. Persisted to", CHROMA_DIR)
    
    return len(all_docs)

if __name__ == "__main__":
    run_ingest()