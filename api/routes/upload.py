"""Роут для загрузки и управления файлами support_*.json"""
import os
import glob
import logging
import tempfile

import ijson
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from api.chroma.ingest import find_support_json
from api.config import settings
from api.utils.security import verify_admin_token

logger = logging.getLogger(__name__)
UPLOAD_CHUNK_SIZE = 1024 * 1024
router = APIRouter(
    prefix="/api",
    tags=["Upload"],
    dependencies=[Depends(verify_admin_token)],
)


def get_project_root() -> str:
    """Находит корень проекта"""
    if settings.support_dir:
        support_dir = os.path.abspath(settings.support_dir)
        os.makedirs(support_dir, exist_ok=True)
        return support_dir

    current_file = os.path.abspath(__file__)
    project_root_from_file = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
    current_work_dir = os.getcwd()
    
    search_paths = [
        "/project_root",  # Docker контейнер
        project_root_from_file,
        current_work_dir,
    ]
    
    for path in search_paths:
        if path and os.path.exists(path):
            # Проверяем наличие support_*.json в этой директории
            pattern = os.path.join(path, "support_*.json")
            if glob.glob(pattern):
                return path
    
    # Если не нашли, возвращаем текущую рабочую директорию
    return current_work_dir if os.path.exists(current_work_dir) else project_root_from_file


def validate_support_json(file_path: str) -> None:
    """Потоково проверяет JSON и наличие корневого массива support."""
    root_is_object = False
    support_is_array = False

    try:
        with open(file_path, "rb") as source:
            for prefix, event, _ in ijson.parse(source):
                if prefix == "" and event == "start_map":
                    root_is_object = True
                elif prefix == "support" and event == "start_array":
                    support_is_array = True
    except (ijson.JSONError, UnicodeError, OSError) as error:
        raise ValueError(f"Невалидный JSON файл: {error}") from error

    if not root_is_object or not support_is_array:
        raise ValueError("JSON должен быть объектом с массивом support")


@router.post("/upload-support")
async def upload_support_file(file: UploadFile = File(...)):
    """
    Загружает новый файл support_*.json.
    Ранее загруженные экспорты остаются без изменений.
    
    Args:
        file: JSON файл для загрузки
        
    Returns:
        Информация о сохранённом файле
    """
    filename = os.path.basename(file.filename or "")
    if filename != file.filename:
        raise HTTPException(status_code=400, detail="Имя файла не должно содержать путь")

    # Проверяем, что это JSON файл
    if not filename.casefold().endswith('.json'):
        raise HTTPException(status_code=400, detail="Файл должен быть в формате JSON")
    
    # Проверяем, что имя файла начинается с support_
    if not filename.casefold().startswith('support_'):
        raise HTTPException(
            status_code=400, 
            detail="Имя файла должно начинаться с 'support_'"
        )

    project_root = get_project_root()
    new_file_path = os.path.join(project_root, filename)
    temporary_path = None
    uploaded_size = 0
    
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=project_root,
            prefix=f".{filename}.",
            suffix=".upload",
            delete=False,
        ) as temporary_file:
            temporary_path = temporary_file.name
            while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                uploaded_size += len(chunk)
                if uploaded_size > settings.max_support_upload_bytes:
                    limit_mib = settings.max_support_upload_bytes // (1024 * 1024)
                    raise HTTPException(
                        status_code=413,
                        detail=f"Размер файла превышает допустимый лимит {limit_mib} MiB",
                    )
                temporary_file.write(chunk)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        try:
            validate_support_json(temporary_path)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        # os.replace атомарно публикует полностью записанный и проверенный файл.
        os.replace(temporary_path, new_file_path)
        temporary_path = None
        
        logger.info(f"Загружен новый файл: {new_file_path}")
        
        return JSONResponse(
            status_code=200,
            content={
                "message": "Файл успешно загружен",
                "new_file": filename,
                "size_bytes": uploaded_size,
                "old_file_renamed": None,
                "project_root": project_root
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при загрузке файла: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при загрузке файла: {str(e)}")
    finally:
        await file.close()
        if temporary_path and os.path.exists(temporary_path):
            try:
                os.unlink(temporary_path)
            except OSError:
                logger.warning("Не удалось удалить временный файл: %s", temporary_path)


@router.get("/download-support")
async def download_support_file():
    """
    Скачивает текущий файл support_*.json, который используется для индексации.
    
    Returns:
        JSON файл для скачивания
    """
    try:
        # Находим текущий файл support_*.json
        current_file = find_support_json()
        
        if not os.path.exists(current_file):
            raise HTTPException(status_code=404, detail="Файл support_*.json не найден")
        
        # Получаем имя файла для заголовка Content-Disposition
        filename = os.path.basename(current_file)
        
        logger.info(f"Скачивание файла: {current_file}")
        
        return FileResponse(
            path=current_file,
            filename=filename,
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка при скачивании файла: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при скачивании файла: {str(e)}")

