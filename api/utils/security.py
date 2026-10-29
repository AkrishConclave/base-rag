"""Модуль безопасности и авторизации"""
import logging
from typing import Optional
import jwt
from fastapi import Header, HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from api.config import settings

logger = logging.getLogger(__name__)

x_admin_token_header = APIKeyHeader(name="X-Admin-Token", auto_error=False)


def verify_admin_token(x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token")) -> str:
    """
    Зависимость FastAPI для защиты служебных эндпоинтов.
    Проверяет наличие и валидность заголовка X-Admin-Token.
    """
    expected_token = settings.admin_token
    if not expected_token:
        # Если admin_token не сконфигурирован, запрещаем доступ
        raise HTTPException(
            status_code=401,
            detail="Доступ запрещен: X-Admin-Token не настроен на сервере"
        )

    if not x_admin_token or x_admin_token != expected_token:
        raise HTTPException(
            status_code=401,
            detail="Неверный или отсутствующий X-Admin-Token"
        )

    return x_admin_token


def decode_jwt_token(token: str) -> Optional[dict]:
    """
    Декодирует и проверяет JWT токен.
    Возвращает payload если токен валиден, иначе None.
    """
    if not token or not settings.jwt_secret:
        return None

    try:
        payload = jwt.decode(
            token,
            key=settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Срок действия JWT токена истек")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Невалидный JWT токен: {e}")
        return None
    except Exception as e:
        logger.error(f"Ошибка при декодировании JWT токена: {e}")
        return None


def is_admin_request(request: Request) -> bool:
    """
    Проверяет права администратора/staff на основе заголовков запроса.

    Админ доступ предоставляется, если:
    1. Заголовок X-Admin-Token совпадает с settings.admin_token
    2. Заголовок Authorization содержит валидный JWT токен (Bearer <token>)
       или передан заголовок X-JWT-Token / JWT token с правами staff/admin
    """
    # 1. Проверка X-Admin-Token
    x_admin_token = request.headers.get("X-Admin-Token") or request.headers.get("x-admin-token")
    if x_admin_token and settings.admin_token and x_admin_token == settings.admin_token:
        return True

    # 2. Проверка JWT токена
    token = None
    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    else:
        token = request.headers.get("X-JWT-Token") or request.headers.get("x-jwt-token")

    if token:
        payload = decode_jwt_token(token)
        if payload is not None:
            # Проверяем роль в payload (если есть) или признаем валидный токен с аккаунтом staff/admin
            role = str(payload.get("role", "")).lower()
            is_staff = payload.get("is_staff", False) or payload.get("is_admin", False) or payload.get("staff", False) or payload.get("admin", False)

            # Если токен валиден и роли/флаги совпадают с staff/admin ИЛИ если специальные роли не определены в payload
            if role in ["admin", "staff", "superuser"] or is_staff or ("role" not in payload and "is_staff" not in payload and "is_admin" not in payload):
                return True

    return False
