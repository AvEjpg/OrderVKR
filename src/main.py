import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Настройка логирования для вывода ошибок в консоль
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from src.auth.router import router as auth_router
from src.orders.router import router as orders_router
from src.bot import dp, bot  

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("🚀 [СТАРТ] Инициализация сервисов веб-приложения и чат-бота...")
    # Запуск Telegram-бота внутри единого асинхронного цикла событий
    bot_task = asyncio.create_task(dp.start_polling(bot))
    yield
    logging.info("🛑 [СТОП] Завершение работы сервисов...")
    await bot.session.close()
    bot_task.cancel()

app = FastAPI(
    title="Order Management System VKR",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роутеры без префикса, так как в твоем коде они уже лежат на /auth и /orders
app.include_router(auth_router)
app.include_router(orders_router)

# Корневой эндпоинт, чтобы при заходе на http://127.0.0.1:8000/ не было ошибки 404
@app.get("/")
async def root():
    return {
        "status": "online",
        "project": "OrderVKR",
        "documentation": "http://127.0.0.1:8000/docs"
    }