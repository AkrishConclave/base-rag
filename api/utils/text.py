"""Утилиты для обработки текста"""
import re
import html


def html_to_text(html_str: str) -> str:
    """
    Преобразует HTML в чистый текст, удаляя теги и base64 изображения
    
    Обрабатывает:
    - Удаляет base64 изображения (очень длинные и засоряют текст)
    - Удаляет все HTML теги
    - Декодирует HTML entities (&nbsp;, &lt;, &gt; и т.д.)
    - Сохраняет структуру текста (переносы строк после заголовков, списков)
    - Нормализует пробелы
    """
    if not html_str:
        return ""
    
    # Удаляем base64 изображения (они очень длинные и засоряют текст)
    text = re.sub(r'<img[^>]*src=["\']data:image/[^"\']*["\'][^>]*>', '', html_str, flags=re.S|re.I)
    # Удаляем все теги img с base64 в атрибуте src (более полный паттерн)
    text = re.sub(r'<img[^>]*src=["\']data:[^"\']*["\'][^>]*/?>', '', text, flags=re.S|re.I)
    
    # Удаляем script и style блоки
    text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.S|re.I)
    text = re.sub(r'<style.*?>.*?</style>', '', text, flags=re.S|re.I)
    
    # Удаляем комментарии
    text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
    
    # Заменяем блочные элементы на переносы строк для сохранения структуры
    # Заголовки, параграфы, списки, div - добавляем перенос
    text = re.sub(r'</(h[1-6]|p|div|li|ul|ol|blockquote|br)[^>]*>', '\n', text, flags=re.I)
    text = re.sub(r'<(h[1-6]|p|div|li|ul|ol|blockquote|br)[^>]*>', '\n', text, flags=re.I)
    
    # Удаляем все остальные HTML теги
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # Декодируем HTML entities (&nbsp; -> пробел, &lt; -> <, &gt; -> >, и т.д.)
    text = html.unescape(text)
    
    # Нормализуем пробелы (но сохраняем переносы строк)
    text = re.sub(r'[ \t]+', ' ', text)  # Множественные пробелы -> один
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)  # Множественные переносы -> два
    text = re.sub(r'[ \t]+\n', '\n', text)  # Пробелы перед переносом
    text = re.sub(r'\n[ \t]+', '\n', text)  # Пробелы после переноса
    
    return text.strip()


def chunk_text(text: str, max_words: int = 220, overlap: int = 40, title: str = "") -> list[str]:
    """Разбивает текст на чанки с перекрытием. Если указан заголовок, добавляет его в начало каждого чанка."""
    words = text.split()
    chunks = []
    i = 0
    n = len(words)
    prefix = f"Заголовок: {title.strip()}\n\n" if title and title.strip() else ""
    while i < n:
        chunk = words[i:i+max_words]
        chunk_str = " ".join(chunk)
        if prefix:
            chunk_str = f"{prefix}{chunk_str}"
        chunks.append(chunk_str)
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

