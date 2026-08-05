# typing 的 Annotated 把数据库会话类型和 FastAPI 依赖声明绑定在一起。
from typing import Annotated

# FastAPI 提供路由注册器、依赖注入声明和请求对象。
from fastapi import APIRouter, Depends, Query, Request

# SQLAlchemy 异步会话用于在接口中读写 PostgreSQL。
from sqlalchemy.ext.asyncio import AsyncSession

# OpenAPI 响应配置声明接口可能返回的错误状态码。
from src.api.v1.responses import ERROR_RESPONSES

# message controller 负责按 profile 查询 message。
from src.controllers.message import list_message_by_user_id_controller

# profile controller 负责 profile 业务规则和数据库更新。
from src.controllers.profile import update_profile_name_controller

# 业务异常模块用于返回统一错误结构。
from src.core.errors import AppError

# 数据库会话依赖为每个请求提供独立事务。
from src.db.session import get_db_session

# profile schema 定义请求体和响应体。
from src.schemas.profile import (
    ProfileMessageResponse,
    ProfileResponse,
    ProfileUpdateRequest,
    ProfileWithMessageResponse,
)

router = APIRouter(tags=["profile"])


@router.get(
    "/profile",
    response_model=ProfileWithMessageResponse,
    status_code=200,
    responses=ERROR_RESPONSES,
)
async def get_profile_message(
    request: Request,
    user_id: Annotated[str, Query(min_length=1, max_length=64)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProfileWithMessageResponse:
    """按 user_id 查询 profile 以及关联 message。"""
    if set(request.query_params.keys()) != {"user_id"} or len(request.query_params.getlist("user_id")) != 1:
        raise AppError(code="INVALID_QUERY_PARAMS", message="Only user_id query parameter is allowed", status_code=400)

    profile, message_list = await list_message_by_user_id_controller(db, user_id=user_id)
    return ProfileWithMessageResponse(
        user_id=profile.user_id,
        name=profile.name,
        message=[ProfileMessageResponse(text=message.text) for message in message_list],
    )


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