# typing 的 Annotated 把数据库会话类型和 FastAPI 依赖声明绑定在一起。
from typing import Annotated

# FastAPI 提供路由注册器和依赖注入声明。
from fastapi import APIRouter, Depends

# SQLAlchemy 异步会话用于在接口中读写 PostgreSQL。
from sqlalchemy.ext.asyncio import AsyncSession

# OpenAPI 响应配置声明接口可能返回的错误状态码。
from src.api.v1.responses import ERROR_RESPONSES

# profile controller 负责 profile 业务规则和数据库更新。
from src.controllers.profile import (
    update_profile_name_controller,
)

# 数据库会话依赖为每个请求提供独立事务。
from src.db.session import get_db_session

# profile schema 定义请求体和响应体。
from src.schemas.profile import (
    ProfileResponse,
    ProfileUpdateRequest,
)

router = APIRouter(tags=["profile"])


@router.post(
    "/profile",
    response_model=ProfileResponse,
    status_code=200,
    responses=ERROR_RESPONSES,
)
async def update_profile_name(
    payload: ProfileUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProfileResponse:
    """接收 HTTP 请求并委托 controllers 层更新 profile 名称。"""
    profile = await update_profile_name_controller(db, user_id=payload.user_id, name=payload.name)
    return ProfileResponse(user_id=profile.user_id, name=profile.name)