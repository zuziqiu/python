# 允许 ChatConversation 在声明 ChatMessage 前使用其类型名称，运行时延后解析。
from __future__ import annotations

# datetime 表示消息和会话的数据库创建时间类型。
from datetime import datetime

# uuid 生成主键并标注 PostgreSQL UUID 字段的 Python 类型。
from uuid import UUID, uuid4

# SQLAlchemy 定义数据表字段、外键、约束和默认时间。
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func

# PostgreSQL 方言提供 UUID 数据库字段类型。
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID

# SQLAlchemy ORM 提供模型字段声明与表关系定义。
from sqlalchemy.orm import Mapped, mapped_column, relationship

# 数据库基类将下方 Python 类注册为 SQLAlchemy 可管理的数据表。
from src.db.base import Base


# AI 对话会话表；一条会话拥有多条按时间排序的消息。
class ChatConversation(Base):
    __tablename__ = "chat_conversations"

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="ChatMessage.created_at"
    )


# AI 对话消息表；role 区分用户、助手和系统消息。
class ChatMessage(Base):
    __tablename__ = "chat_messages"
    # 在数据库层限制角色取值，避免写入无法用于模型上下文的消息。
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant', 'system')", name="ck_chat_messages_role"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        # 删除会话时级联删除所属消息，避免留下孤立的历史记录。
        ForeignKey("chat_conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    conversation: Mapped[ChatConversation] = relationship(back_populates="messages")