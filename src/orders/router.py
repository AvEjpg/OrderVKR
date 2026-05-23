import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from src.database import get_async_session
from src.models.models import Order, OrderItem, User
from src.auth.jwt import get_current_user
from src.orders.schemas import OrderCreateSchema, OrderResponseSchema, OrderStatusUpdateSchema
from src.bot import send_status_update_notification  # Фоновая отправка уведомлений

router = APIRouter(prefix="/api/orders", tags=["Orders"])


# 1. POST /api/orders — Создание заказа (Доступно любому авторизованному клиенту)
@router.post("/", response_model=OrderResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_order(
    order_data: OrderCreateSchema,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    # Вычисляем общую стоимость заказа на основе пришедших позиций
    total_price = sum(item.price * item.quantity for item in order_data.items)
    
    # Создаем объект заказа (по дефолту статус_ид = 1 ("Создан"))
    new_order = Order(
        user_id=current_user.id,
        total_price=total_price,
        status_id=1 
    )
    session.add(new_order)
    await session.flush() # flush генерирует id для new_order, но не закрывает транзакцию

    # Создаем позиции заказа, привязанные к сгенерированному id заказа
    for item in order_data.items:
        new_item = OrderItem(
            order_id=new_order.id,
            product_name=item.product_name,
            quantity=item.quantity,
            price=item.price
        )
        session.add(new_item)
    
    await session.commit()
    
    # Отправляем уведомление о создании заказа (статус "Создан" = 1)
    background_tasks.add_task(
        send_status_update_notification,
        order_id=new_order.id,
        status_id=1
    )
    
    # Подгружаем связанные items для корректного ответа схемы
    query = select(Order).where(Order.id == new_order.id).options(selectinload(Order.items))
    result = await session.execute(query)
    return result.scalar_one()


# 2. GET /api/orders — Получение списка заказов (Разделение прав)
@router.get("/", response_model=List[OrderResponseSchema])
async def get_orders(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    # Строим базовый запрос с жадной загрузкой позиций товаров (selectinload)
    query = select(Order).options(selectinload(Order.items)).order_by(Order.created_at.desc())
    
    # Если это обычный клиент, фильтруем заказы — отдаем только его собственные
    if current_user.role == "client":
        query = query.where(Order.user_id == current_user.id)
    # Если это manager или admin — фильтрацию не применяем (видят все заказы)
    elif current_user.role not in ["manager", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Недостаточно прав для просмотра"
        )
        
    result = await session.execute(query)
    return result.scalars().all()


# 3. PATCH /api/orders/{id}/status — Изменение статуса заказа (Только manager или admin)
@router.patch("/{order_id}/status", response_model=OrderResponseSchema)
async def update_order_status(
    order_id: uuid.UUID,
    status_data: OrderStatusUpdateSchema,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),  # ТРЕБУЕМ АВТОРИЗАЦИЮ (JWT ТОКЕН)
    session: AsyncSession = Depends(get_async_session)
):
    # Проверка роли: только менеджер или админ имеют доступ
    if current_user.role not in ["manager", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Данное действие доступно только менеджеру или администратору"
        )
        
    # Ищем заказ в БД
    query = select(Order).where(Order.id == order_id).options(selectinload(Order.items))
    result = await session.execute(query)
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Заказ не найден"
        )
        
    # Обновляем статус заказа
    order.status_id = status_data.status_id
    await session.commit()
    await session.refresh(order)
    
    # Публикуем отправку уведомления в фоновые задачи FastAPI
    background_tasks.add_task(
        send_status_update_notification,
        order_id=order.id,
        status_id=order.status_id
    )
    
    return order