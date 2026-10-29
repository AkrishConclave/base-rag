"""Кэширование ответов LLM для экономии токенов и ускорения"""
from __future__ import annotations
import hashlib
import json
import sqlite3
import time
import logging
from pathlib import Path
from typing import Optional
from api.config import settings

logger = logging.getLogger(__name__)


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
            logger.warning(f"⚠️  Redis недоступен, кэширование отключено: {e}")
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
                        logger.info(f"💾 Найдено в кэше: модель={model}, ключ={key[:16]}...")
                        return value
                    else:
                        # Удаляем устаревший кэш
                        logger.debug(f"⚠️  Кэш устарел для ключа {key[:16]}..., удаляю")
                        self._delete(key)
            
            elif self.cache_type == "redis":
                value = self.redis_client.get(f"llm_cache:{key}")
                if value:
                    logger.info(f"💾 Найдено в Redis кэше: модель={model}, ключ={key[:16]}...")
                    return value
        
        except Exception as e:
            logger.error(f"⚠️  Ошибка чтения кэша: {e}")
        
        return None
    
    def set(self, prompt: str, system_message: str | None, model: str, value: str):
        """Сохранить ответ в кэш"""
        if not self.enabled:
            logger.debug("⚠️  Кэш отключен, пропускаю сохранение")
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
                logger.info(f"💾 Сохранено в кэш: модель={model}, ключ={key[:16]}...")
            
            elif self.cache_type == "redis":
                self.redis_client.setex(
                    f"llm_cache:{key}",
                    self.ttl,
                    value
                )
                logger.info(f"💾 Сохранено в Redis кэш: модель={model}, ключ={key[:16]}...")
        
        except Exception as e:
            logger.error(f"⚠️  Ошибка записи в кэш: {e}")
    
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
            logger.error(f"⚠️  Ошибка очистки кэша: {e}")
    
    def get_stats(self) -> dict:
        """Получить статистику кэша"""
        stats = {
            "enabled": self.enabled,
            "cache_type": self.cache_type,
            "ttl_seconds": self.ttl,
            "total_entries": 0,
            "oldest_entry": None,
            "newest_entry": None,
            "total_size_bytes": 0
        }
        
        if not self.enabled:
            return stats
        
        try:
            if self.cache_type == "sqlite":
                conn = sqlite3.connect(str(self.cache_db))
                
                # Количество записей
                cursor = conn.execute("SELECT COUNT(*) FROM cache")
                stats["total_entries"] = cursor.fetchone()[0]
                
                if stats["total_entries"] > 0:
                    # Самая старая запись
                    cursor = conn.execute(
                        "SELECT datetime(created_at, 'unixepoch') FROM cache ORDER BY created_at ASC LIMIT 1"
                    )
                    oldest = cursor.fetchone()
                    if oldest:
                        stats["oldest_entry"] = oldest[0]
                    
                    # Самая новая запись
                    cursor = conn.execute(
                        "SELECT datetime(created_at, 'unixepoch') FROM cache ORDER BY created_at DESC LIMIT 1"
                    )
                    newest = cursor.fetchone()
                    if newest:
                        stats["newest_entry"] = newest[0]
                    
                    # Размер базы данных
                    import os
                    if os.path.exists(str(self.cache_db)):
                        stats["total_size_bytes"] = os.path.getsize(str(self.cache_db))
                
                conn.close()
            
            elif self.cache_type == "redis":
                # Получаем все ключи с префиксом llm_cache:
                keys = self.redis_client.keys("llm_cache:*")
                stats["total_entries"] = len(keys)
                
                if stats["total_entries"] > 0:
                    # Получаем TTL для первого ключа (примерное время создания)
                    if keys:
                        ttl = self.redis_client.ttl(keys[0])
                        if ttl > 0:
                            import time
                            # Приблизительное время создания = текущее время - (TTL - исходный TTL)
                            # Но мы не знаем исходный TTL, поэтому используем текущее время
                            stats["newest_entry"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                            # Старая запись - примерно TTL секунд назад
                            oldest_time = time.time() - (self.ttl - ttl)
                            stats["oldest_entry"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(oldest_time))
                    
                    # Размер всех значений (приблизительно)
                    total_size = 0
                    for key in keys[:100]:  # Ограничиваем для производительности
                        value = self.redis_client.get(key)
                        if value:
                            total_size += len(value.encode('utf-8'))
                    stats["total_size_bytes"] = total_size
                    
        except Exception as e:
            logger.error(f"⚠️  Ошибка получения статистики кэша: {e}")
            stats["error"] = str(e)
        
        return stats


# Глобальный экземпляр кэша
_cache_instance: LLMCache | None = None


def get_cache() -> LLMCache:
    """Получить экземпляр кэша (singleton)"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = LLMCache()
    return _cache_instance


def close_cache():
    """Закрыть соединения кэша (для cleanup при shutdown)"""
    global _cache_instance
    if _cache_instance is not None:
        try:
            if _cache_instance.cache_type == "redis" and hasattr(_cache_instance, 'redis_client'):
                _cache_instance.redis_client.close()
        except Exception as e:
            logger.warning(f"Ошибка при закрытии кэша: {e}")
        _cache_instance = None

