"""Утилиты для обработки текста"""
import re


def html_to_text(html: str) -> str:
    """Преобразует HTML в чистый текст, удаляя теги и base64 изображения"""
    # Удаляем base64 изображения (они очень длинные и засоряют текст)
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


def chunk_text(text: str, max_words: int = 220, overlap: int = 40) -> list[str]:
    """Разбивает текст на чанки с перекрытием"""
    words = text.split()
    chunks = []
    i = 0
    n = len(words)
    while i < n:
        chunk = words[i:i+max_words]
        chunks.append(" ".join(chunk))
        i += max_words - overlap
    return chunks


def extract_keywords(query: str) -> str:
    """Извлекает ключевые слова из запроса, убирая служебные слова"""
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

