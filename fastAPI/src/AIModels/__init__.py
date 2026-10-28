"""AI 平台客户端与流式响应类型。"""

from typing import Annotated

from fastapi import Depends, Request

from src.AIModels.copilot import CopilotService
from src.AIModels.openai import (
    AIStreamChunk,
    OpenAIClient,
    OpenAIError,
    get_openai_client,
)
from src.core.config import get_settings
from src.core.errors import AppError


def get_ai_client(
    request: Request,
    openai_client: Annotated[OpenAIClient | None, Depends(get_openai_client)],
) -> OpenAIClient | CopilotService | None:
    if get_settings().ai_provider == "openai":
        return openai_client
    service: CopilotService | None = getattr(request.app.state, "copilot_service", None)
    if service is None:
        raise AppError("COPILOT_STARTING", "Copilot has not started yet.", 503)
    service.ensure_ready()
    return service

__all__ = [
    "AIStreamChunk",
    "OpenAIClient",
    "OpenAIError",
    "get_ai_client",
    "get_openai_client",
]
