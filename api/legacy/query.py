# query.py
import os, json
import chromadb
from sentence_transformers import SentenceTransformer
import requests
from dotenv import load_dotenv

load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat")  # Основная модель
# Список резервных моделей на случай отказа основной
FALLBACK_MODELS = [
    'openai/gpt-5-mini',
    'openai/gpt-3.5-turbo',
    'anthropic/claude-3-haiku',
    'google/gemini-pro',
    'mistralai/mistral-7b-instruct:free',
    'microsoft/phi-3-mini-128k-instruct:free',
    'qwen/qwen-2.5-0.5b-instruct:free',
    'qwen/qwen-2.5-1.5b-instruct:free'
]
CHROMA_DIR = os.getenv("CHROMA_DIR", "./chroma_db")
EMBED_MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/paraphrase-multilingual-mpnet-base-v2")  # Хорошая мультиязычная модель для русского
TOP_K = int(os.getenv("TOP_K", "10"))  # Увеличено для лучшего поиска
MAX_DISTANCE = float(os.getenv("MAX_DISTANCE", "0.8"))  # Максимальное расстояние для фильтрации

# Инициализация происходит лениво при первом использовании
embedder = None
client = None
collection = None

def get_collection():
    """Ленивая загрузка коллекции ChromaDB"""
    global embedder, client, collection
    if embedder is None:
        embedder = SentenceTransformer(EMBED_MODEL)
    if client is None:
        client = chromadb.PersistentClient(path=CHROMA_DIR)
    if collection is None:
        try:
            collection = client.get_collection("support_articles")
        except Exception as e:
            raise Exception("Коллекция 'support_articles' не найдена. Сначала выполните индексацию через /ingest endpoint.") from e
    return collection

def extract_keywords(query):
    """Извлекает ключевые слова из запроса, убирая служебные слова"""
    import re
    # Список служебных слов на русском
    stop_words = {
        'что', 'как', 'где', 'когда', 'почему', 'зачем', 'куда', 'откуда',
        'делать', 'делает', 'делаю', 'делаешь', 'делают',
        'если', 'не', 'нет', 'ни', 'нельзя',
        'приходят', 'приходит', 'пришло', 'пришел', 'пришла',
        'работает', 'работают', 'работаю',
        'можно', 'нужно', 'надо', 'должен', 'должна', 'должны',
        'это', 'этот', 'эта', 'эти', 'такой', 'такая', 'такие',
        'для', 'про', 'о', 'об', 'от', 'до', 'из', 'в', 'на', 'с', 'по', 'к', 'у'
    }
    
    # Убираем знаки препинания и разбиваем на слова
    clean_query = re.sub(r'[^\w\s]', ' ', query.lower())
    words = clean_query.split()
    keywords = [w for w in words if w not in stop_words and len(w) > 2]
    result = ' '.join(keywords) if keywords else query
    print(f"🔍 Извлеченные ключевые слова: {result}")
    return result

def expand_query_with_llm(query):
    """Использует LLM для расширения запроса синонимами и вариантами формулировок"""
    if not OPENROUTER_API_KEY:
        # Если нет API ключа, возвращаем оригинальный запрос
        return query
    
    # Сначала извлекаем ключевые слова из запроса
    keywords = extract_keywords(query)
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/your-repo",
        "X-Title": "Pinbox RAG Query Expansion"
    }
    
    prompt = f"""Пользователь задал вопрос для поиска в базе знаний Pinbox: "{query}"

Извлеки ключевые слова и сгенерируй синонимы для улучшения поиска.

ВАЖНО:
- Для вопросов типа "что делать если не работает X" - ищи статьи про X (ключевое слово - X)
- Добавь синонимы ключевых слов (например: настроить=подключить, оповещения=уведомления)
- НЕ добавляй слова про проблемы/неисправности - они мешают поиску
- Фокус на СУТИ запроса, а не на формулировке вопроса
- Учитывай контекст Pinbox и синонимы:
  * "прайс" = "товары и услуги" = "товар" = "услуга"
  * "разместить" = "добавить" = "загрузить" = "создать"
  * "отзыв" = "рецензия" = "комментарий"
  * "настроить" = "подключить" = "установить" = "активировать"

Верни ТОЛЬКО список ключевых слов и синонимов через запятую, без дополнительных объяснений.
Пример для "Что делать если не приходят оповещения?": оповещения, уведомления, email, telegram
Пример для "Как настроить автообжалование?": автообжалование, автоматическое обжалование, обжалование отзывов
Пример для "Как разместить товар?": товар, прайс, товары и услуги, добавить товар, добавить прайс, загрузить товар, разместить прайс, создать прайс"""

    models_to_try = [OPENROUTER_MODEL] + FALLBACK_MODELS[:2]  # Используем только первые 2 резервные для экономии
    
    for model in models_to_try:
        try:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "Ты помощник для расширения поисковых запросов. Отвечай кратко, только ключевые слова через запятую."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 80,
                "temperature": 0.3  # Снижаем температуру для более точных результатов
            }
            r = requests.post(url, headers=headers, json=payload, timeout=10)
            r.raise_for_status()
            data = r.json()
            expanded_text = data["choices"][0]["message"]["content"].strip()
            
            # Парсим результат: берем ключевые слова
            variants = [v.strip() for v in expanded_text.replace('.', ',').split(',') if v.strip() and len(v.strip()) > 2]
            # Объединяем ключевые слова из запроса с синонимами от LLM
            original_words = set(keywords.lower().split())
            new_words = [v for v in variants if v.lower() not in original_words]
            # Используем ключевые слова из запроса + синонимы от LLM
            expanded_query = f"{keywords} {' '.join(new_words[:8])}"  # Ограничиваем до 8 дополнительных слов
            print(f"✅ LLM расширил запрос: {expanded_query[:200]}...")
            return expanded_query
        except Exception as e:
            print(f"⚠️ Ошибка расширения запроса через {model}: {e}")
            continue
    
    # Если LLM не сработал, используем извлеченные ключевые слова
    print("⚠️ LLM расширение не удалось, используем извлеченные ключевые слова")
    return keywords

def search(query, top_k=TOP_K):
    global embedder
    if embedder is None:
        embedder = SentenceTransformer(EMBED_MODEL)
    collection = get_collection()
    
    # Извлекаем ключевые слова из запроса
    keywords = extract_keywords(query)
    query_lower = query.lower()
    keywords_lower = keywords.lower()
    
    # Для коротких запросов (1-2 слова) используем их напрямую, для длинных - расширяем через LLM
    is_short_query = len(query.split()) <= 2
    
    if is_short_query:
        # Для коротких запросов используем оригинальный запрос + синонимы от LLM
        expanded_query = expand_query_with_llm(query)
        expanded_words = set(expanded_query.lower().split())
        search_query = expanded_query
    else:
        # Для длинных запросов используем комбинацию ключевых слов и расширенного запроса
        expanded_query = expand_query_with_llm(query)
        expanded_words = set(expanded_query.lower().split())
        search_query = f"{keywords} {expanded_query}" if keywords != query else expanded_query
    
    q_emb = embedder.encode([search_query])[0].tolist()
    # Запрашиваем больше результатов для фильтрации
    resp = collection.query(query_embeddings=[q_emb], n_results=top_k * 10, include=["documents","metadatas","distances"])  # Увеличиваем до 10x для лучшего покрытия
    docs = resp["documents"][0]
    metas = resp["metadatas"][0]
    dists = resp["distances"][0]
    
    # Сортируем и фильтруем результаты
    results_with_scores = []
    query_words = set(query_lower.split())
    keywords_set = set(keywords_lower.split())
    
    # Дополнительно проверяем совпадение ключевых слов из расширенного запроса
    expanded_keywords = set([w for w in expanded_query.lower().split() if len(w) > 3])
    
    # Извлекаем ключевые слова из расширенного запроса для лучшего сопоставления
    # Например, из "разместить товар прайс добавить прайс" извлекаем: прайс, добавить, товар
    important_words = set()
    for word in expanded_keywords:
        if word in ['прайс', 'товар', 'добавить', 'разместить', 'загрузить', 'создать']:
            important_words.add(word)
    
    for doc, meta, dist in zip(docs, metas, dists):
        score = 1.0 - dist  # Преобразуем расстояние в score (чем больше, тем лучше)
        
        # Бонус за совпадение ключевых слов в заголовке
        title = (meta.get('title') or '').lower()
        menu = (meta.get('menu') or '').lower()
        
        # Проверяем совпадения в заголовке и меню
        title_words = set(title.split())
        menu_words = set(menu.split())
        
        # Большой бонус за прямое совпадение ключевых слов в заголовке
        keyword_matches = keywords_set & title_words
        expanded_keyword_matches = expanded_keywords & title_words
        important_word_matches = important_words & title_words
        
        if keyword_matches:
            # Чем больше ключевых слов совпадает, тем больше бонус
            score += 0.8 * len(keyword_matches)  # Значительно увеличиваем бонус для ключевых слов
        elif important_word_matches:
            # Очень большой бонус за совпадение важных слов (прайс, товар, добавить и т.д.)
            score += 1.0 * len(important_word_matches)  # Еще больше увеличиваем бонус
        elif expanded_keyword_matches:
            # Бонус за совпадение расширенных ключевых слов (например, "прайс" из расширенного запроса)
            score += 0.6 * len(expanded_keyword_matches)
        elif query_words & title_words or expanded_words & title_words:
            score += 0.15
        
        # Бонус за совпадение слов в меню
        if keywords_set & menu_words:
            score += 0.4
        elif query_words & menu_words or expanded_words & menu_words:
            score += 0.1
        
        # Дополнительный бонус, если ключевое слово является частью заголовка (например, "оповещения" в "Оповещение Email")
        # Это особенно важно для коротких запросов, где склонения могут отличаться
        for kw in keywords_set:
            if len(kw) > 3:  # Уменьшаем минимальную длину для лучшего покрытия
                # Проверяем, содержится ли ключевое слово в заголовке (с учетом склонений)
                # Используем более гибкую проверку: ищем корень слова
                kw_root = kw[:min(6, len(kw))]  # Берем первые 6 символов как корень
                if kw in title or any(kw_root in word or word.startswith(kw_root) or kw.startswith(word[:min(6, len(word))]) for word in title_words if len(word) > 3):
                    score += 0.5  # Увеличиваем бонус для частичного совпадения
        
        # Бонус за частичное совпадение (например, "автообжалование" в запросе и "автоматическое обжалование" в заголовке)
        all_query_words = keywords_set | expanded_words
        for q_word in all_query_words:
            if len(q_word) > 4:  # Только для слов длиннее 4 символов
                if any(q_word in t_word or t_word in q_word for t_word in title_words if len(t_word) > 4):
                    score += 0.05
        
        results_with_scores.append({"doc": doc, "meta": meta, "dist": dist, "score": score})
    
    # Сортируем по score и берем лучшие
    results_with_scores.sort(key=lambda x: x["score"], reverse=True)
    results = []
    for r in results_with_scores[:top_k]:
        results.append({"doc": r["doc"], "meta": r["meta"], "dist": r["dist"]})
    
    return results

def build_prompt(question, results):
    if not results:
        return f"Вопрос: {question}\n\nОтвет: К сожалению, в базе знаний не найдено релевантной информации для ответа на ваш вопрос."
    
    prompt_parts = []
    prompt_parts.append("Ты — помощник поддержки Pinbox. Отвечай на вопросы пользователей на основе предоставленного контекста.")
    prompt_parts.append("")
    prompt_parts.append("ИНСТРУКЦИИ:")
    prompt_parts.append("1. Используй ТОЛЬКО информацию из контекста ниже")
    prompt_parts.append("2. Если в контексте есть прямой ответ — дай подробный, пошаговый ответ")
    prompt_parts.append("3. Структурируй ответ: используй списки, заголовки, выделяй важное")
    prompt_parts.append("4. Если информации недостаточно — скажи об этом, но используй то, что есть в контексте")
    prompt_parts.append("5. Отвечай на русском языке, дружелюбно и профессионально")
    prompt_parts.append("")
    prompt_parts.append("КОНТЕКСТ:")
    for idx, r in enumerate(results, 1):
        meta = r["meta"]
        title = meta.get('title', 'Без названия')
        prompt_parts.append(f"\n--- Источник {idx}: {title} ---")
        prompt_parts.append(r["doc"])
    prompt_parts.append("")
    prompt_parts.append(f"ВОПРОС: {question}")
    prompt_parts.append("")
    prompt_parts.append("ОТВЕТ:")
    return "\n".join(prompt_parts)

def call_openrouter(prompt):
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY не установлен. Укажите его в файле .env")
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/your-repo",  # Опционально, для отслеживания
        "X-Title": "Pinbox RAG Support"  # Опционально
    }
    
    # Список моделей для попыток: сначала основная, потом резервные
    models_to_try = [OPENROUTER_MODEL] + FALLBACK_MODELS
    
    last_error = None
    for model in models_to_try:
        try:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "Ты — помощник поддержки Pinbox. Отвечай по контексту."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 700
            }
            r = requests.post(url, headers=headers, json=payload, timeout=30)
            r.raise_for_status()
            data = r.json()
            # OpenRouter использует тот же формат что и OpenAI: choices[0].message.content
            return data["choices"][0]["message"]["content"]
        except requests.exceptions.HTTPError as e:
            # Если ошибка 402 (Payment Required) или 429 (Rate Limit), пробуем следующую модель
            if e.response.status_code in [402, 429]:
                last_error = f"Модель {model} недоступна (код {e.response.status_code}), пробую следующую..."
                print(f"⚠️ {last_error}")
                continue
            # Для других ошибок HTTP пробуем следующую модель
            last_error = f"Модель {model} вернула ошибку {e.response.status_code}, пробую следующую..."
            print(f"⚠️ {last_error}")
            continue
        except Exception as e:
            # Для других ошибок тоже пробуем следующую модель
            last_error = f"Ошибка при вызове модели {model}: {str(e)}, пробую следующую..."
            print(f"⚠️ {last_error}")
            continue
    
    # Если все модели не сработали, выбрасываем исключение
    raise Exception(f"Все модели недоступны. Последняя ошибка: {last_error}")

if __name__ == "__main__":
    q = input("Вопрос: ")
    hits = search(q)
    prompt = build_prompt(q, hits)
    print("----PROMPT PREVIEW----")
    print(prompt[:1500])
    print("----CALLING OPENROUTER----")
    ans = call_openrouter(prompt)
    print("----ANSWER----")
    print(ans)
    print("\nИсточники:")
    for h in hits:
        print(f"- {h['meta'].get('title')} (id={h['meta'].get('article_id')}), dist={h['dist']:.4f}")

def answer_question(question):
    hits = search(question)
    prompt = build_prompt(question, hits)
    ans = call_openrouter(prompt)
    sources = [
        {
            "title": h["meta"].get("title"),
            "id": h["meta"].get("article_id"),
            "dist": h["dist"]
        }
        for h in hits
    ]
    return ans, sources
