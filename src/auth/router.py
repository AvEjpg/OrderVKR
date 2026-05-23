from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.database import get_async_session
from src.models.models import User
from src.auth.hash import get_password_hash, verify_password
from src.auth.jwt import create_access_token
from src.config import settings

router = APIRouter(prefix="/api/auth", tags=["Auth"])

# --- Pydantic Схемы ---
class UserRegisterSchema(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, description="Пароль не менее 6 символов")
    role: str = Field(default="client", description="Роли: client, manager, admin")

class UserLoginSchema(BaseModel):
    email: EmailStr
    password: str

class TokenSchema(BaseModel):
    access_token: str
    token_type: str

# --- Эндпоинты ---

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(user_data: UserRegisterSchema, session: AsyncSession = Depends(get_async_session)):
    # Проверяем, существует ли уже пользователь с таким email
    query = select(User).where(User.email == user_data.email)
    result = await session.execute(query)
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пользователь с таким email уже зарегистрирован"
        )
    
    # Хешируем пароль и создаем запись
    hashed_password = get_password_hash(user_data.password)
    new_user = User(
        email=user_data.email,
        password_hash=hashed_password,
        role=user_data.role
    )
    
    session.add(new_user)
    await session.commit()
    return {"status": "success", "message": "Пользователь успешно зарегистрирован"}


@router.post("/login", response_model=TokenSchema)
async def login(user_data: UserLoginSchema, session: AsyncSession = Depends(get_async_session)):
    # Ищем пользователя в базе
    query = select(User).where(User.email == user_data.email)
    result = await session.execute(query)
    user = result.scalar_one_or_none()
    
    # Проверяем пользователя и его пароль
    if not user or not verify_password(user_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Генерируем JWT-токен (в поле 'sub' закладываем ID пользователя)
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "role": user.role}, 
        expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}


### ТЕСТОВЫЕ !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

from uuid import UUID  # если ещё не импортирован
from src.auth.jwt import get_current_user  # импорт зависимости

@router.get("/users", tags=["User Management"])
async def get_users(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Только для менеджера: список всех пользователей."""
    if current_user.role != "manager":
        raise HTTPException(status_code=403, detail="Доступ только для менеджеров")
    
    query = select(User)
    result = await session.execute(query)
    users = result.scalars().all()
    
    return [
        {"id": str(u.id), "email": u.email, "role": u.role, "created_at": u.created_at.isoformat()}
        for u in users
    ]


@router.patch("/users/{user_id}/role", tags=["User Management"])
async def update_user_role(
    user_id: UUID,
    new_role: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """Только для менеджера: изменить роль пользователя."""
    if current_user.role != "manager":
        raise HTTPException(status_code=403, detail="Доступ только для менеджеров")
    
    if new_role not in ["client", "manager", "admin"]:
        raise HTTPException(status_code=400, detail="Недопустимая роль")
    
    query = select(User).where(User.id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    user.role = new_role
    await session.commit()
    return {"status": "ok", "new_role": new_role}