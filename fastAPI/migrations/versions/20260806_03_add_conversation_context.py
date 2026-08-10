"""将 message 改造为按 conversation 隔离的多轮对话结构。"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260806_03"
down_revision: str | Sequence[str] | None = "20260806_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """合并旧消息结构，并以 conversation_id 作为上下文边界。"""
    connection = op.get_bind()
    profile_user_ids = list(connection.execute(sa.text("SELECT user_id FROM profile")).scalars())
    if "01" not in profile_user_ids:
        connection.execute(
            sa.text("INSERT INTO profile (user_id, name) VALUES (:user_id, :name)"),
            {"user_id": "01", "name": "Private Assistant"},
        )

    op.create_table(
        "conversation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["profile.user_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_conversation_user_id", "conversation", ["user_id"])

    op.create_table(
        "message_new",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('user', 'assistant', 'system')", name="ck_message_role"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversation.id"], ondelete="CASCADE"
        ),
    )

    for user_id in profile_user_ids:
        conversation_id = uuid4()
        connection.execute(
            sa.text(
                """
                INSERT INTO conversation (id, user_id, title)
                SELECT :conversation_id, :user_id, :title
                WHERE EXISTS (SELECT 1 FROM message WHERE user_id = :user_id)
                """
            ).bindparams(
                sa.bindparam(
                    "conversation_id", type_=postgresql.UUID(as_uuid=True)
                ),
                sa.bindparam("user_id", type_=sa.String(length=64)),
                sa.bindparam("title", type_=sa.String(length=255)),
            ),
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "title": "Migrated history",
            },
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO message_new (conversation_id, role, text)
                SELECT :conversation_id, 'user', text
                FROM message
                WHERE user_id = :user_id
                ORDER BY id
                """
            ).bindparams(
                sa.bindparam(
                    "conversation_id", type_=postgresql.UUID(as_uuid=True)
                ),
                sa.bindparam("user_id", type_=sa.String(length=64)),
            ),
            {"conversation_id": conversation_id, "user_id": user_id},
        )

    connection.execute(
        sa.text(
            """
            INSERT INTO conversation (id, user_id, title, created_at)
            SELECT id, '01', title, created_at FROM chat_conversations
            """
        )
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO message_new (conversation_id, role, text, created_at)
            SELECT conversation_id, role, content, created_at
            FROM chat_messages
            ORDER BY created_at, id
            """
        )
    )

    op.drop_index("ix_message_user_id", table_name="message")
    op.drop_table("message")
    op.drop_index("ix_chat_messages_conversation_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_table("chat_conversations")
    op.rename_table("message_new", "message")
    op.create_index("ix_message_conversation_id", "message", ["conversation_id"])


def downgrade() -> None:
    """恢复两套旧消息结构，conversation 消息回退到 chat 表。"""
    op.create_table(
        "chat_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'system')",
            name="ck_chat_messages_role",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["chat_conversations.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_chat_messages_conversation_id", "chat_messages", ["conversation_id"]
    )
    op.create_table(
        "message_old",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["profile.user_id"], ondelete="CASCADE"),
    )

    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            INSERT INTO chat_conversations (id, title, created_at)
            SELECT id, title, created_at FROM conversation
            """
        )
    )
    message_rows = connection.execute(
        sa.text(
            """
            SELECT conversation_id, role, text, created_at
            FROM message
            ORDER BY id
            """
        )
    ).mappings()
    for message in message_rows:
        connection.execute(
            sa.text(
                """
                INSERT INTO chat_messages
                    (id, conversation_id, role, content, created_at)
                VALUES
                    (:id, :conversation_id, :role, :content, :created_at)
                """
            ),
            {
                "id": uuid4(),
                "conversation_id": message["conversation_id"],
                "role": message["role"],
                "content": message["text"],
                "created_at": message["created_at"],
            },
        )

    op.drop_index("ix_message_conversation_id", table_name="message")
    op.drop_table("message")
    op.rename_table("message_old", "message")
    op.create_index("ix_message_user_id", "message", ["user_id"])
    op.drop_index("ix_conversation_user_id", table_name="conversation")
    op.drop_table("conversation")