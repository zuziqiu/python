from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, TypedDict

from openai import APIError, APIStatusError, AsyncOpenAI

from src.core.config import get_settings
from src.core.errors import AppError


class AIMessageInput(TypedDict):
    """SiliconFlow Chat Completions 接受的单条上下文消息。"""

    role: Literal["user", "assistant", "system"]
    content: str


@dataclass(frozen=True, slots=True)
class AIStreamChunk:
    """统一表示模型输出的推理或正文增量。"""

    kind: Literal["reasoning", "content"]
    delta: str


class SiliconFlowError(Exception):
    """表示 SiliconFlow 请求失败或流未完整结束。"""

    def __init__(self, message: str, *, code: str = "AI_STREAM_FAILED") -> None:
        """保存可安全返回给客户端的稳定错误码。"""
        super().__init__(message)
        self.code = code


class SiliconFlowClient:
    """通过 SiliconFlow 的 OpenAI 兼容接口异步生成流式回答。"""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def stream_chat(
        self, messages: list[AIMessageInput]
    ) -> AsyncIterator[AIStreamChunk]:
        """通过 OpenAI SDK 转发推理和正文增量。"""
        try:
            async with AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=300.0,
            ) as client:
                stream = await client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    stream=True,
                )
                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    reasoning = getattr(choice.delta, "reasoning_content", None)
                    content = choice.delta.content
                    if reasoning:
                        yield AIStreamChunk(kind="reasoning", delta=reasoning)
                    if content:
                        yield AIStreamChunk(kind="content", delta=content)
                    finish_reason = choice.finish_reason
                    if finish_reason == "stop":
                        return
                    if finish_reason is not None:
                        raise SiliconFlowError(
                            f"SiliconFlow stopped with reason: {finish_reason}"
                        )
        except APIStatusError as exc:
            raise SiliconFlowError(
                f"SiliconFlow returned HTTP {exc.status_code}",
                code=(
                    "AI_PAYMENT_REQUIRED"
                    if exc.status_code == 402
                    else "AI_STREAM_FAILED"
                ),
            ) from exc
        except APIError as exc:
            raise SiliconFlowError("SiliconFlow stream failed") from exc

        raise SiliconFlowError("SiliconFlow stream ended before completion")


def get_siliconflow_client() -> SiliconFlowClient:
    """从环境配置创建 SiliconFlow 客户端。"""
    settings = get_settings()
    if not settings.siliconflow_api_key:
        raise AppError(
            code="AI_NOT_CONFIGURED",
            message="SiliconFlow API key is not configured",
            status_code=503,
        )
    return SiliconFlowClient(
        api_key=settings.siliconflow_api_key,
        base_url=settings.siliconflow_base_url,
        model=settings.siliconflow_model,
        temperature=settings.siliconflow_temperature,
        max_tokens=settings.siliconflow_max_tokens,
    )
