import uuid
from datetime import datetime
from typing import List
from pydantic import BaseModel, Field

# --- Схемы для позиций товара ---
class OrderItemCreateSchema(BaseModel):
    product_name: str = Field(..., min_length=1, description="Название товара")
    quantity: int = Field(..., gt=0, description="Количество должно быть больше 0")
    price: float = Field(..., ge=0, description="Цена не может быть отрицательной")

class OrderItemResponseSchema(BaseModel):
    id: uuid.UUID
    product_name: str
    quantity: int
    price: float

    class Config:
        from_attributes = True

# --- Схемы для самого заказа ---
class OrderCreateSchema(BaseModel):
    items: List[OrderItemCreateSchema] = Field(..., min_length=1, description="Список товаров в заказе")

class OrderResponseSchema(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    status_id: int
    total_price: float
    created_at: datetime
    updated_at: datetime
    items: List[OrderItemResponseSchema]

    class Config:
        from_attributes = True

# --- Схема для обновления статуса ---
class OrderStatusUpdateSchema(BaseModel):
    status_id: int = Field(..., ge=1, le=5, description="ID статуса от 1 до 5")