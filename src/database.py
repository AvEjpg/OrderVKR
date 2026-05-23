from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.config import settings
import sys

try:
    # Создаем асинхронный движок
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=True, # Показывает все SQL-запросы в консоли
        pool_pre_ping=True # Автоматически проверяет жива ли база перед запросом
    )
    
    async_session_maker = async_sessionmaker(
        bind=engine, 
        class_=AsyncSession, 
        expire_on_commit=False
    )
except Exception as e:
    print(f"❌ КРИТИЧЕСКАЯ ОШИБКА ИНИЦИАЛИЗАЦИИ ДВИЖКА БД: {e}", file=sys.stderr)

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
        except Exception as e:
            print(f"❌ ОШИБКА СЕССИИ БАЗЫ ДАННЫХ: {e}", file=sys.stderr)
            await session.rollback()
            raise e