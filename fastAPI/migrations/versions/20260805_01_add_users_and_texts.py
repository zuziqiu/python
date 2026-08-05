# Sequence 标注 Alembic 迁移链可能存在的多个父版本类型。
from collections.abc import Sequence

# SQLAlchemy 定义建表、字段、外键和索引操作需要的类型。
import sqlalchemy as sa

# Alembic 提供实际执行升级和回滚 SQL 的操作接口。
from alembic import op

# PostgreSQL 方言提供迁移中的 UUID 字段类型。
from sqlalchemy.dialects import postgresql

revision: str = "20260805_01"
down_revision: str | Sequence[str] | None = "20260804_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """新增 text API 所需的用户表和文本表。"""
    # 创建用户表和 text API 写入的文本表；文本通过 user_id 关联用户。
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
    )
    op.create_table(
        "texts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
    )
    # 后续按用户查询 text API 历史记录时使用此索引。
    op.create_index("ix_texts_user_id", "texts", ["user_id"])


def downgrade() -> None:
    """按依赖的反向顺序删除用户和文本表结构。"""
    op.drop_index("ix_texts_user_id", table_name="texts")
    op.drop_table("texts")
    op.drop_table("users")