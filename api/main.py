"""Точка входа FastAPI приложения"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
from api.routes import rag_router, ingest_router
from api.routes.embed import router as embed_router
from api.routes.debug import router as debug_router
from api.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan для инициализации и очистки ресурсов при старте/остановке"""
    # Startup: предзагрузка ChromaDB клиента и embedder
    print("🚀 Starting RAG Pinbox API...")
    try:
        from api.chroma.client import get_collection, get_embedder
        # Предзагружаем для быстрого первого запроса
        try:
            get_embedder()
            print("✅ Embedder initialized")
        except Exception as e:
            print(f"⚠️  Embedder initialization warning: {e}")
        # Пробуем подключиться к коллекции (может не быть, если не индексировали)
        try:
            get_collection()
            print("✅ ChromaDB collection ready")
        except Exception as e:
            print(f"⚠️  ChromaDB collection not found - run /api/ingest first: {e}")
    except Exception as e:
        print(f"⚠️  Initialization warning: {e}")
    
    yield
    
    # Shutdown: очистка ресурсов (если нужно)
    try:
        from api.llm.cache import close_cache
        close_cache()
    except Exception:
        pass
    print("🛑 Shutting down RAG Pinbox API...")


app = FastAPI(
    title="RAG Pinbox API",
    description="RAG-система для ответов на вопросы пользователей на основе базы знаний статей поддержки Pinbox",
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

# Router registry - централизованная регистрация роутов
def register_routers():
    """Регистрация всех роутов приложения"""
    app.include_router(rag_router)
    app.include_router(ingest_router)
    app.include_router(embed_router)
    app.include_router(debug_router)

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

# Обратная совместимость со старыми эндпоинтами
@app.post("/ask")
async def ask_legacy(payload: dict):
    """Legacy endpoint для обратной совместимости"""
    from api.routes.rag import ask
    from api.models.request import AskRequest
    
    question = payload.get("q", "").strip()
    if not question:
        return {"error": "empty question"}
    
    request = AskRequest(q=question)
    response = await ask(request)
    return response.dict()


@app.post("/ingest")
async def ingest_legacy():
    """Legacy endpoint для обратной совместимости"""
    from api.routes.ingest import ingest
    
    response = await ingest()
    return response.dict()


if __name__ == "__main__":
    uvicorn.run("api.main:app", host="0.0.0.0", port=9001, reload=False)

