"""
Зависимости FastAPI для DI
"""
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.security import decode_access_token, TokenData
from app.models.database import get_db

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> dict:
    """
    Получить текущего пользователя из токена
    
    В текущей реализации возвращает mock пользователя.
    В production нужно добавить проверку пользователя в БД.
    """
    token = credentials.credentials
    token_data = decode_access_token(token)
    
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # TODO: Получить пользователя из БД
    # user = db.query(User).filter(User.username == token_data.username).first()
    # if user is None:
    #     raise HTTPException(status_code=404, detail="User not found")
    
    # Временная реализация для разработки
    return {
        "username": token_data.username or "test_user",
        "id": 1,
        "is_active": True
    }


async def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: Session = Depends(get_db)
) -> Optional[dict]:
    """Получить текущего пользователя, если токен предоставлен"""
    if credentials is None:
        return None
    
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None
