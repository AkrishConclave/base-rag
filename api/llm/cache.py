"""Кэширование ответов LLM для экономии токенов и ускорения"""
from __future__ import annotations
import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Optional
from api.config import settings


class LLMCache:
    """Кэш для ответов LLM"""
    
    def __init__(self):
        self.enabled = settings.cache_enabled
        self.ttl = settings.cache_ttl
        self.cache_type = settings.cache_type
        
        if self.cache_type == "sqlite":
            self._init_sqlite()
        elif self.cache_type == "redis":
            self._init_redis()
    
    def _init_sqlite(self):
        """Инициализация SQLite кэша"""
        cache_dir = Path(settings.chroma_dir).parent / "cache"
        cache_dir.mkdir(exist_ok=True)
        self.cache_db = cache_dir / "llm_cache.db"
        
        # Создаем таблицу если не существует
        conn = sqlite3.connect(str(self.cache_db))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        conn.commit()
        conn.close()
    
    def _init_redis(self):
        """Инициализация Redis кэша"""
        try:
            import redis
            self.redis_client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                decode_responses=True
            )
            # Проверяем подключение
            self.redis_client.ping()
        except ImportError:
            raise ImportError("Redis не установлен. Установите: pip install redis")
        except Exception as e:
            print(f"⚠️  Redis недоступен, кэширование отключено: {e}")
            self.enabled = False
    
    def _generate_key(self, prompt: str, system_message: str | None, model: str) -> str:
        """Генерация ключа кэша из параметров запроса"""
        key_data = {
            "prompt": prompt,
            "system": system_message or "",
            "model": model
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()
    
    def get(self, prompt: str, system_message: str | None, model: str) -> Optional[str]:
        """Получить ответ из кэша"""
        if not self.enabled:
            return None
        
        key = self._generate_key(prompt, system_message, model)
        current_time = time.time()
        
        try:
            if self.cache_type == "sqlite":
                conn = sqlite3.connect(str(self.cache_db))
                cursor = conn.execute(
                    "SELECT value, created_at FROM cache WHERE key = ?",
                    (key,)
                )
                row = cursor.fetchone()
                conn.close()
                
                if row:
                    value, created_at = row
                    # Проверяем TTL
                    if current_time - created_at < self.ttl:
                        return value
                    else:
                        # Удаляем устаревший кэш
                        self._delete(key)
            
            elif self.cache_type == "redis":
                value = self.redis_client.get(f"llm_cache:{key}")
                if value:
                    return value
        
        except Exception as e:
            print(f"⚠️  Ошибка чтения кэша: {e}")
        
        return None
    
    def set(self, prompt: str, system_message: str | None, model: str, value: str):
        """Сохранить ответ в кэш"""
        if not self.enabled:
            return
        
        key = self._generate_key(prompt, system_message, model)
        current_time = time.time()
        
        try:
            if self.cache_type == "sqlite":
                conn = sqlite3.connect(str(self.cache_db))
                conn.execute(
                    "INSERT OR REPLACE INTO cache (key, value, created_at) VALUES (?, ?, ?)",
                    (key, value, current_time)
                )
                conn.commit()
                conn.close()
            
            elif self.cache_type == "redis":
                self.redis_client.setex(
                    f"llm_cache:{key}",
                    self.ttl,
                    value
                )
        
        except Exception as e:
            print(f"⚠️  Ошибка записи в кэш: {e}")
    
    def _delete(self, key: str):
        """Удалить запись из кэша"""
        try:
            if self.cache_type == "sqlite":
                conn = sqlite3.connect(str(self.cache_db))
                conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                conn.commit()
                conn.close()
            elif self.cache_type == "redis":
                self.redis_client.delete(f"llm_cache:{key}")
        except Exception:
            pass
    
    def clear(self):
        """Очистить весь кэш"""
        try:
            if self.cache_type == "sqlite":
                conn = sqlite3.connect(str(self.cache_db))
                conn.execute("DELETE FROM cache")
                conn.commit()
                conn.close()
            elif self.cache_type == "redis":
                # Удаляем все ключи с префиксом llm_cache:
                keys = self.redis_client.keys("llm_cache:*")
                if keys:
                    self.redis_client.delete(*keys)
        except Exception as e:
            print(f"⚠️  Ошибка очистки кэша: {e}")


# Глобальный экземпляр кэша
_cache_instance: LLMCache | None = None


def get_cache() -> LLMCache:
    """Получить экземпляр кэша (singleton)"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = LLMCache()
    return _cache_instance

