from sqlalchemy import select

# SQLAlchemy 异步会话用于在 controllers 层执行数据库操作。
from sqlalchemy.ext.asyncio import AsyncSession

# profile controller 复用 profile 存在性校验规则。
from src.controllers.profile import get_profile_by_user_id_controller

# message ORM 模型对应 message 数据表。
from src.db.models.message import Message

# profile ORM 模型对应 profile 数据表。
from src.db.models.profile import Profile


async def receive_message_controller(db: AsyncSession, *, user_id: str, text: str) -> tuple[Profile, Message]:
    """确认 profile 存在后，在同一事务中新增 message 记录。"""
    profile = await get_profile_by_user_id_controller(db, user_id=user_id)
    message = Message(user_id=profile.user_id, text=text)
    db.add(message)
    return profile, message


async def list_message_by_user_id_controller(db: AsyncSession, *, user_id: str) -> tuple[Profile, list[Message]]:
    """确认 profile 存在后，按 user_id 查询 message 列表。"""
    profile = await get_profile_by_user_id_controller(db, user_id=user_id)
    message_list = list(await db.scalars(select(Message).where(Message.user_id == user_id).order_by(Message.id)))
    return profile, message_list
