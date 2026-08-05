# Sequence 标注 Alembic 迁移链可能存在的多个父版本类型。
from collections.abc import Sequence

# SQLAlchemy 定义建表、字段、约束和索引操作需要的类型。
import sqlalchemy as sa

# Alembic 提供实际执行升级和回滚 SQL 的操作接口。
from alembic import op

# PostgreSQL 方言提供迁移中的 UUID 字段类型。
from sqlalchemy.dialects import postgresql

revision: str = "20260804_01"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 创建 AI 对话所需的会话表、消息表及消息查询索引。
    # 会话表是消息历史的归属单位。
    op.create_table(
        "chat_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant', 'system')", name="ck_chat_messages_role"),
        sa.ForeignKeyConstraint(["conversation_id"], ["chat_conversations.id"], ondelete="CASCADE"),
    )
    # 后续按会话读取历史消息时使用此索引。
    op.create_index("ix_chat_messages_conversation_id", "chat_messages", ["conversation_id"])


def downgrade() -> None:
    """按依赖的反向顺序删除初始对话表结构。"""
    op.drop_index("ix_chat_messages_conversation_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_table("chat_conversations")