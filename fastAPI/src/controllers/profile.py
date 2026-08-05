from sqlalchemy import select

# SQLAlchemy 异步会话用于在 controllers 层执行数据库操作。
from sqlalchemy.ext.asyncio import AsyncSession

# 业务异常模块用于把业务失败转换为统一接口错误。
from src.core.errors import AppError

# profile ORM 模型对应 profile 数据表。
from src.db.models.profile import Profile


async def get_profile_by_user_id_controller(db: AsyncSession, *, user_id: str) -> Profile:
    """按接口传入的 user_id 查询 profile。"""
    profile = await db.scalar(select(Profile).where(Profile.user_id == user_id))
    if profile is None:
        raise AppError(code="PROFILE_NOT_FOUND", message="Profile not found", status_code=404)

    return profile


async def update_profile_name_controller(db: AsyncSession, *, user_id: str, name: str) -> Profile:
    """按不可变的 user_id 定位 profile，只更新 name。"""
    profile = await get_profile_by_user_id_controller(db, user_id=user_id)

    profile.name = name
    return profile
