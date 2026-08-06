from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConversationMessage(BaseModel):
    """表示发送给 AI 或保存在会话中的一条消息。"""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1, max_length=10_000)


class ConversationRequest(BaseModel):
    """校验一次流式 AI 对话请求。"""

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=64)
    conversation_id: UUID | None = None
    messages: list[ConversationMessage] = Field(default_factory=list, max_length=9)
    content: str = Field(min_length=1, max_length=10_000)

    @model_validator(mode="after")
    def validate_single_user(self) -> ConversationRequest:
        """限制接口只能访问私人助手的固定 profile。"""
        if self.user_id != "01":
            raise ValueError("user_id must be 01")
        return self


class ConversationResponse(BaseModel):
    """返回对话窗口及其完整持久化上下文。"""

    conversation_id: UUID
    title: str | None
    messages: list[ConversationMessage]
