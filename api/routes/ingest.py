"""Роут для индексации данных"""
from fastapi import APIRouter, HTTPException
from api.models.response import IngestResponse
from api.chroma.ingest import run_ingest

router = APIRouter(prefix="/api", tags=["Ingest"])


@router.post("/ingest", response_model=IngestResponse)
async def ingest():
    """
    Индексирует статьи из JSON файла в векторную базу данных
    
    Returns:
        Количество проиндексированных чанков
    """
    try:
        count = run_ingest()
        return IngestResponse(indexed_chunks=count)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при индексации: {str(e)}")

