# Sequence 标注 Alembic 迁移链可能存在的多个父版本类型。
from collections.abc import Sequence

# SQLAlchemy 定义建表、字段、外键和索引操作需要的类型。
import sqlalchemy as sa

# Alembic 提供实际执行升级和回滚 SQL 的操作接口。
from alembic import op

revision: str = "20260806_01"
down_revision: str | Sequence[str] | None = "20260805_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """将 user/text 表替换为 profile/message 表，并改用自增 id 主键。"""
    op.drop_index("ix_texts_user_id", table_name="texts")
    op.drop_table("texts")
    op.drop_table("users")

    op.create_table(
        "profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_profiles_user_id"),
    )
    op.create_index("ix_profiles_user_id", "profiles", ["user_id"])

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.user_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_messages_user_id", "messages", ["user_id"])


def downgrade() -> None:
    """回滚到旧的 users/texts 表结构。"""
    op.drop_index("ix_messages_user_id", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_profiles_user_id", table_name="profiles")
    op.drop_table("profiles")

    op.create_table(
        "users",
        sa.Column("user_id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
    )
    op.create_table(
        "texts",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_texts_user_id", "texts", ["user_id"])
