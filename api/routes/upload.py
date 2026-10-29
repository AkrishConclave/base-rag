"""Роут для загрузки и управления файлами support_*.json"""
import os
import glob
import shutil
import json
import logging
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from api.chroma.ingest import find_support_json
from api.utils.security import verify_admin_token

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api",
    tags=["Upload"],
    dependencies=[Depends(verify_admin_token)],
)


def get_project_root() -> str:
    """Находит корень проекта"""
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


@router.post("/upload-support")
async def upload_support_file(file: UploadFile = File(...)):
    """
    Загружает новый файл support_*.json.
    Старый файл автоматически переименовывается с добавлением *old*.
    
    Args:
        file: JSON файл для загрузки
        
    Returns:
        Информация о загруженном файле и переименованном старом файле
    """
    # Проверяем, что это JSON файл
    if not file.filename.endswith('.json'):
        raise HTTPException(status_code=400, detail="Файл должен быть в формате JSON")
    
    # Проверяем, что имя файла начинается с support_
    if not file.filename.startswith('support_'):
        raise HTTPException(
            status_code=400, 
            detail="Имя файла должно начинаться с 'support_'"
        )
    
    project_root = get_project_root()
    new_file_path = os.path.join(project_root, file.filename)
    
    try:
        # Читаем содержимое файла для проверки валидности JSON
        content = await file.read()
        try:
            json.loads(content)  # Проверяем, что это валидный JSON
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Невалидный JSON файл: {str(e)}")
        
        # Ищем существующий файл support_*.json (без *old*)
        existing_files = [
            f for f in glob.glob(os.path.join(project_root, "support_*.json"))
            if "*old*" not in f and not f.endswith(".old.json")
        ]
        
        old_file_path = None
        old_file_renamed = None
        
        # Если есть существующий файл и он отличается от нового
        if existing_files:
            existing_file = max(existing_files, key=os.path.getmtime)
            
            # Если новый файл имеет то же имя, что и существующий
            if os.path.basename(existing_file) == file.filename:
                # Переименовываем существующий в *old*
                name, ext = os.path.splitext(file.filename)
                old_file_renamed = f"{name}*old*{ext}"
                old_file_path = os.path.join(project_root, old_file_renamed)
                shutil.move(existing_file, old_file_path)
                logger.info(f"Переименован существующий файл: {existing_file} -> {old_file_path}")
            else:
                # Переименовываем существующий файл
                existing_name = os.path.basename(existing_file)
                name, ext = os.path.splitext(existing_name)
                old_file_renamed = f"{name}*old*{ext}"
                old_file_path = os.path.join(project_root, old_file_renamed)
                shutil.move(existing_file, old_file_path)
                logger.info(f"Переименован существующий файл: {existing_file} -> {old_file_path}")
        
        # Сохраняем новый файл
        with open(new_file_path, 'wb') as f:
            f.write(content)
        
        logger.info(f"Загружен новый файл: {new_file_path}")
        
        return JSONResponse(
            status_code=200,
            content={
                "message": "Файл успешно загружен",
                "new_file": file.filename,
                "old_file_renamed": old_file_renamed,
                "project_root": project_root
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при загрузке файла: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при загрузке файла: {str(e)}")


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

