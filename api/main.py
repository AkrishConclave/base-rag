"""Точка входа FastAPI приложения"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
from api.routes import rag_router, ingest_router
from api.routes.embed import router as embed_router
from api.routes.debug import router as debug_router
from api.routes.upload import router as upload_router
from api.config import settings

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan для инициализации и очистки ресурсов при старте/остановке"""
    # Startup: предзагрузка ChromaDB клиента и embedder
    logger.info("🚀 Starting RAG Support API...")
    try:
        from api.chroma.client import get_collection, get_embedder
        from api.vector_engine import load_index_from_collection
        # Предзагружаем для быстрого первого запроса
        try:
            get_embedder()
            logger.info("✅ Embedder initialized")
        except Exception as e:
            logger.warning(f"⚠️  Embedder initialization warning: {e}")
        # Пробуем подключиться к коллекции (может не быть, если не индексировали)
        try:
            collection = get_collection()
            vector_count = load_index_from_collection(collection)
            logger.info("✅ ChromaDB collection ready; native memory index loaded: %s vectors", vector_count)
        except Exception as e:
            logger.warning(f"⚠️  ChromaDB collection not found - run /api/ingest first: {e}")
    except Exception as e:
        logger.warning(f"⚠️  Initialization warning: {e}", exc_info=True)
    
    yield
    
    # Shutdown: очистка ресурсов (если нужно)
    try:
        from api.llm.cache import close_cache
        close_cache()
    except Exception:
        pass
    logger.info("🛑 Shutting down RAG Support API...")


app = FastAPI(
    title="RAG Support API",
    description="RAG-система для ответов на вопросы пользователей на основе базы знаний статей поддержки Support",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Обработчики ошибок для унификации сообщений клиенту
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Кастомная обработка ошибок валидации запросов с русскоязычными сообщениями"""
    logger.warning(f"Ошибка валидации запроса: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Ошибка валидации входных данных",
            "errors": jsonable_encoder(exc.errors())
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Кастомная обработка HTTP исключений"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail
        },
        headers=exc.headers
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Обработчик всех неожидаемых серверных ошибок"""
    logger.error(f"Необработанное исключение: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Внутренняя ошибка сервера"
        }
    )


# Router registry - централизованная регистрация роутов
def register_routers():
    """Регистрация всех роутов приложения"""
    app.include_router(rag_router)
    app.include_router(ingest_router)
    app.include_router(embed_router)
    app.include_router(debug_router)
    app.include_router(upload_router)

register_routers()

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check для мониторинга и load balancer"""
    try:
        from api.chroma.client import get_collection
        # Проверяем доступность ChromaDB
        try:
            get_collection()
            db_status = "ready"
        except Exception:
            db_status = "not_initialized"
    except Exception:
        db_status = "error"
    
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "version": "1.0.0",
            "chroma_db": db_status
        }
    )

if __name__ == "__main__":
    uvicorn.run("api.main:app", host="0.0.0.0", port=9001, reload=False)

