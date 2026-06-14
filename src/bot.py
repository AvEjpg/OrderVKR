import asyncio
import logging
import os
import sys
import uuid

from dotenv import load_dotenv 
load_dotenv()
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.future import select

sys.path.append(os.getcwd())
from src.config import settings
from src.database import async_session_maker
from src.models.models import User, TelegramProfile, Order, OrderStatus

logging.basicConfig(level=logging.INFO)

bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

class LinkState(StatesGroup):
    waiting_for_email = State()

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    chat_id = message.chat.id
    
    async with async_session_maker() as session:
        # Проверяем, есть ли такой chat_id в базе
        query = select(TelegramProfile).where(TelegramProfile.chat_id == chat_id)
        result = await session.execute(query)
        profile = result.scalar_one_or_none()

        if profile:
            # СЦЕНАРИЙ: Пользователь уже привязан
            await message.answer(
                "✅ Вы уже авторизованы в системе уведомлений!\n"
                "Я буду присылать вам информацию об изменениях статусов ваших заказов."
            )
        else:
            # СЦЕНАРИЙ: Новый пользователь
            await message.answer(
                "👋 Здравствуйте! Я бот системы уведомлений заказов.\n"
                "Введите ваш Email для привязки аккаунта:"
            )
            await state.set_state(LinkState.waiting_for_email)

@dp.message(lambda message: message.text == "/unlink")
async def unlink_telegram(message: types.Message):
    """Отвязывает Telegram аккаунт от учётной записи"""
    chat_id = message.chat.id
    
    async with async_session_maker() as session:
        # Ищем профиль по chat_id
        query = select(TelegramProfile).where(TelegramProfile.chat_id == chat_id)
        result = await session.execute(query)
        profile = result.scalar_one_or_none()
        
        if not profile:
            await message.answer(
                "❌ Ваш Telegram аккаунт не привязан к системе.\n"
                "Используйте команду /start для привязки."
            )
            return
        
        # Сохраняем email пользователя для сообщения
        user_query = select(User).where(User.id == profile.user_id)
        user_result = await session.execute(user_query)
        user = user_result.scalar_one_or_none()
        user_email = user.email if user else "неизвестный"
        
        # Удаляем профиль
        await session.delete(profile)
        await session.commit()
    
    await message.answer(
        f"✅ Ваш аккаунт ({user_email}) успешно отвязан от Telegram.\n\n"
        f"Вы больше не будете получать уведомления о заказах.\n"
        f"Если захотите снова привязать аккаунт, используйте команду /start."
    )

@dp.message(LinkState.waiting_for_email)
async def process_email(message: types.Message, state: FSMContext):
    email = message.text.strip().lower()
    chat_id = message.chat.id
    username = message.from_user.username

    async with async_session_maker() as session:
        query = select(User).where(User.email == email)
        result = await session.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            await message.answer("❌ Пользователь с таким Email не найден в системе. Попробуйте еще раз:")
            return

        # Проверяем, не привязан ли уже этот юзер
        tg_query = select(TelegramProfile).where(TelegramProfile.user_id == user.id)
        tg_result = await session.execute(tg_query)
        existing_profile = tg_result.scalar_one_or_none()

        if existing_profile:
            await message.answer("ℹ️ Этот аккаунт уже успешно привязан к Telegram!")
            await state.clear()
            return

        # Создаем запись в telegram_profiles
        new_profile = TelegramProfile(
            user_id=user.id,
            chat_id=chat_id,
            username=username
        )
        session.add(new_profile)
        await session.commit()

    await message.answer("🎉 Успешно! Ваш Telegram профиль привязан. Теперь вы будете получать уведомления об изменении статуса ваших заказов.")
    await state.clear()


async def send_status_update_notification(order_id: uuid.UUID, status_id: int):
    """
    Фоновая функция: запрашивает данные о заказе и отправляет пуш в Telegram
    """
    try:
        async with async_session_maker() as session:
            # 1. Получаем текстовое имя статуса
            status_query = select(OrderStatus).where(OrderStatus.id == status_id)
            status_res = await session.execute(status_query)
            status_obj = status_res.scalar_one_or_none()
            status_name = status_obj.name if status_obj else f"Статус №{status_id}"

            # 2. Получаем информацию о заказе (чтобы узнать владельца user_id и цену)
            order_query = select(Order).where(Order.id == order_id)
            order_res = await session.execute(order_query)
            order_obj = order_res.scalar_one_or_none()

            if not order_obj:
                logging.error(f"🎨 [ТГ Уведомление] Заказ {order_id} не найден в БД.")
                return

            # 3. Ищем, привязан ли Telegram у этого клиента
            tg_query = select(TelegramProfile).where(TelegramProfile.user_id == order_obj.user_id)
            tg_res = await session.execute(tg_query)
            tg_profile = tg_res.scalar_one_or_none()

            # 4. Если профиль есть шлем сообщение
            if tg_profile:
                # Берём только первые 8 символов от UUID (например, f91d4142)
                short_id = str(order_obj.id)[:8]
                
                message_text = (
                    f"📦 <b>Обновление статуса заказа!</b>\n\n"
                    f"🔢 <b>ID заказа:</b> <code>{short_id}</code>\n"
                    f"💰 <b>Сумма:</b> {order_obj.total_price} руб.\n"
                    f"🔔 <b>Новый статус:</b> {status_name}"
                )
                await bot.send_message(chat_id=tg_profile.chat_id, text=message_text, parse_mode="HTML")
                logging.info(f"🚀 [ТГ Уведомление] Успешно отправлено в чат {tg_profile.chat_id}")
            else:
                logging.info(f"ℹ️ [ТГ Уведомление] Пользователь {order_obj.user_id} не привязал Telegram.")

    except Exception as e:
        logging.error(f"❌ [ТГ Уведомление] Критическая ошибка при отправке: {e}")


# async def main():
#     print("Бот успешно запущен и слушает сервера Telegram...")
#     await dp.start_polling(bot)

# if __name__ == "__main__":
#     asyncio.run(main())