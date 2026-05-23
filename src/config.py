import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# Находим корень проекта (папку OrderVKR)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENV_FILE_PATH = os.path.join(BASE_DIR, ".env")

# Намертво вшиваем загрузку переменных в ОС перед инициализацией классов
if os.path.exists(ENV_FILE_PATH):
    load_dotenv(ENV_FILE_PATH, override=True)
else:
    print(f"⚠️ ВНИМАНИЕ: Файл .env не найден по пути: {ENV_FILE_PATH}")

class Settings(BaseSettings):
    # Данные для PostgreSQL
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASS: str = "123"  
    DB_NAME: str = "OrderVKR"
    
    # Настройки безопасности для диплома
    JWT_SECRET: str = "super_secret_vkr_key_2026_flows"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Токен Telegram
    TELEGRAM_BOT_TOKEN: str = " "

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    model_config = SettingsConfigDict(env_file=ENV_FILE_PATH, extra="ignore")

settings = Settings()