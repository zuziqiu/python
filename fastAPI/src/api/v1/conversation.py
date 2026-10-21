import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.openai import (
    OpenAIClient,
    OpenAIError,
    get_openai_client,
)
from src.api.v1.responses import ERROR_RESPONSES
from src.controllers.conversation import (
    delete_conversation_controller,
    get_conversation_controller,
    list_conversation_by_user_id_controller,
    save_completed_turn_controller,
)
from src.controllers.profile import get_profile_by_user_id_controller
from src.db.session import get_db_session, session_factory
from src.schemas.conversation import ConversationRequest, ConversationResponse

router = APIRouter(tags=["conversation"])
SYSTEM_PROMPT = "You are a helpful assistant."


def _sse_event(event: str, data: dict[str, str]) -> str:
    """将结构化事件编码为单条 SSE 消息。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post(
    "/conversation",
    status_code=200,
    responses=ERROR_RESPONSES,
)
async def stream_conversation(
    payload: ConversationRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    # Annotated 携带 FastAPI 依赖元数据；OpenAIClient 是参数类型，Depends 将 getter 返回值注入 ai_client。
    ai_client: Annotated[OpenAIClient | None, Depends(get_openai_client)],
) -> StreamingResponse:
    """流式返回推理和回答，仅在完整结束后持久化本轮问答。"""
    await get_profile_by_user_id_controller(db, user_id=payload.user_id)
    conversation_id = payload.conversation_id or uuid4()
    if payload.conversation_id is not None:
        await get_conversation_controller(
            db,
            user_id=payload.user_id,
            conversation_id=payload.conversation_id,
        )

    async def event_stream() -> AsyncIterator[str]:
        """转发模型增量，并在收到完整结束信号后提交一次事务。"""
        assistant_parts: list[str] = []
        ai_messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *[
                message.model_dump()
                for message in payload.messages
                if message.role != "system"
            ],
        ]
        ai_messages.append({"role": "user", "content": payload.content})

        try:
            try:
                if ai_client is None:
                    raise OpenAIError("OpenAI is not configured", code="AI_NOT_CONFIGURED")
                async for chunk in ai_client.stream_chat(ai_messages):
                    if chunk.kind == "content":
                        assistant_parts.append(chunk.delta)
                    yield _sse_event(chunk.kind, {"delta": chunk.delta})

                assistant_content = "".join(assistant_parts)
                if not assistant_content:
                    raise OpenAIError("OpenAI returned no answer content")
            except OpenAIError:
                mock_answer = f"模拟数据 {datetime.now().astimezone():%Y-%m-%d %H:%M:%S}"
                assistant_content = "".join(assistant_parts) + mock_answer
                yield _sse_event("content", {
                    "delta": mock_answer,
                    "question": payload.content,
                    "answer": assistant_content,
                })

            async with session_factory() as write_db:
                await save_completed_turn_controller(
                    write_db,
                    user_id=payload.user_id,
                    conversation_id=conversation_id,
                    user_content=payload.content,
                    assistant_content=assistant_content,
                )
                await write_db.commit()

            yield _sse_event("done", {"conversation_id": str(conversation_id)})
        finally:
            assistant_parts.clear()
            ai_messages.clear()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/conversation",
    response_model=list[ConversationResponse],
    status_code=200,
    responses=ERROR_RESPONSES,
)
async def list_conversation(
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[ConversationResponse]:
    """读取固定 profile 01 的全部对话窗口。"""
    conversation_list = await list_conversation_by_user_id_controller(
        db, user_id="01"
    )
    return [
        ConversationResponse(
            conversation_id=conversation.id,
            title=conversation.title,
            messages=conversation.messages,
        )
        for conversation in conversation_list
    ]


@router.delete(
    "/conversation/{conversation_id}",
    status_code=204,
    responses=ERROR_RESPONSES,
)
async def delete_conversation(
    conversation_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """删除固定 profile 01 的指定对话窗口。"""
    await delete_conversation_controller(
        db, user_id="01", conversation_id=conversation_id
    )
    return Response(status_code=204)
