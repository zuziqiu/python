from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import AppError
from src.db.models.conversation import Conversation


async def get_conversation_controller(
    db: AsyncSession, *, user_id: str, conversation_id: UUID
) -> Conversation:
    """同时按用户和主键查询会话，防止跨用户访问上下文。"""
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    if conversation is None:
        raise AppError(
            code="CONVERSATION_NOT_FOUND",
            message="Conversation not found",
            status_code=404,
        )
    return conversation


async def list_conversation_by_user_id_controller(
    db: AsyncSession, *, user_id: str
) -> list[Conversation]:
    """按 profile 查询对话窗口列表。"""
    return list(
        await db.scalars(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.created_at, Conversation.id)
        )
    )


async def delete_conversation_controller(
    db: AsyncSession, *, user_id: str, conversation_id: UUID
) -> None:
    """删除指定用户的会话及其内嵌上下文。"""
    conversation = await get_conversation_controller(
        db, user_id=user_id, conversation_id=conversation_id
    )
    await db.delete(conversation)


async def save_completed_turn_controller(
    db: AsyncSession,
    *,
    user_id: str,
    conversation_id: UUID,
    user_content: str,
    assistant_content: str,
) -> None:
    """在 AI 完整结束后一次性追加本轮问答。"""
    conversation = await db.scalar(
        select(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
        .with_for_update()
    )
    if conversation is None:
        conversation = Conversation(
            id=conversation_id,
            user_id=user_id,
            title=user_content[:255],
            messages=[],
        )
        db.add(conversation)

    conversation.messages = [
        *conversation.messages,
        {"role": "user", "content": user_content},
        {"role": "assistant", "content": assistant_content},
    ]
