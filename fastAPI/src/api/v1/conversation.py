import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.rag_chat import RagContext, RagRetriever, get_rag_retriever
from src.AIModels import get_ai_client
from src.AIModels.copilot import CopilotError, CopilotService
from src.AIModels.openai import OpenAIClient, OpenAIError
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
logger = logging.getLogger(__name__)


def _sse_event(event: str, data: object) -> str:
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
    ai_client: Annotated[OpenAIClient | CopilotService | None, Depends(get_ai_client)],
    rag_retriever: Annotated[RagRetriever | None, Depends(get_rag_retriever)],
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
    rag_context: RagContext | None = None
    if rag_retriever is not None:
        rag_context = await rag_retriever.retrieve(payload.content)

    async def event_stream() -> AsyncIterator[str]:
        """转发模型增量，并在收到完整结束信号后提交一次事务。"""
        assistant_parts: list[str] = []
        ai_messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *(
                [{"role": "system", "content": rag_context.system_message()}]
                if rag_context is not None else []
            ),
            *[
                message.model_dump()
                for message in payload.messages
                if message.role != "system"
            ],
        ]
        ai_messages.append({"role": "user", "content": payload.content})

        try:
            if rag_context is not None:
                yield _sse_event("sources", rag_context.event_data())
            try:
                if ai_client is None:
                    raise OpenAIError("OpenAI is not configured", code="AI_NOT_CONFIGURED")
                async for chunk in ai_client.stream_chat(ai_messages):
                    if chunk.kind == "content":
                        assistant_parts.append(chunk.delta)
                    yield _sse_event(chunk.kind, {"delta": chunk.delta})

                assistant_content = "".join(assistant_parts)
                if not assistant_content:
                    if isinstance(ai_client, CopilotService):
                        raise CopilotError("Copilot returned no answer content")
                    raise OpenAIError("OpenAI returned no answer content")
            except CopilotError as exc:
                logger.exception("Copilot conversation failed; this turn will not be saved.")
                yield _sse_event("error", {"code": exc.code, "message": str(exc)})
                return
            except OpenAIError as exc:
                if rag_context is not None:
                    logger.exception("RAG answer generation failed; this turn will not be saved.")
                    yield _sse_event("error", {
                        "code": exc.code, "message": "AI answer generation failed.",
                    })
                    return
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
