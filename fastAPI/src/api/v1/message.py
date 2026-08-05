from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.responses import ERROR_RESPONSES
from src.controllers.message import receive_message_controller
from src.db.session import get_db_session
from src.schemas.message import MessageRequest, MessageResponse

router = APIRouter(tags=["message"])


@router.post(
    "/message",
    response_model=MessageResponse,
    status_code=200,
    responses=ERROR_RESPONSES,
)
async def receive_message(
    payload: MessageRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    """接收 HTTP 请求并委托 controllers 层保存 message。"""
    profile, message = await receive_message_controller(db, user_id=payload.user_id, text=payload.text)
    return MessageResponse(user_id=profile.user_id, text=message.text)