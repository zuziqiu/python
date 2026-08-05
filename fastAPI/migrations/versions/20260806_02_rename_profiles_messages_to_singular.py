# Sequence 标注 Alembic 迁移链可能存在的多个父版本类型。
from collections.abc import Sequence

# Alembic 提供实际执行升级和回滚 SQL 的操作接口。
from alembic import op

revision: str = "20260806_02"
down_revision: str | Sequence[str] | None = "20260806_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """将业务表和约束从复数命名改为单数命名。"""
    op.rename_table("profiles", "profile")
    op.rename_table("messages", "message")

    op.execute("ALTER INDEX profiles_pkey RENAME TO profile_pkey")
    op.execute("ALTER INDEX messages_pkey RENAME TO message_pkey")
    op.execute("ALTER INDEX ix_profiles_user_id RENAME TO ix_profile_user_id")
    op.execute("ALTER INDEX ix_messages_user_id RENAME TO ix_message_user_id")
    op.execute("ALTER TABLE profile RENAME CONSTRAINT uq_profiles_user_id TO uq_profile_user_id")
    op.execute("ALTER TABLE message RENAME CONSTRAINT messages_user_id_fkey TO message_user_id_fkey")


def downgrade() -> None:
    """回滚到复数业务表和约束命名。"""
    op.execute("ALTER TABLE message RENAME CONSTRAINT message_user_id_fkey TO messages_user_id_fkey")
    op.execute("ALTER TABLE profile RENAME CONSTRAINT uq_profile_user_id TO uq_profiles_user_id")
    op.execute("ALTER INDEX ix_message_user_id RENAME TO ix_messages_user_id")
    op.execute("ALTER INDEX ix_profile_user_id RENAME TO ix_profiles_user_id")
    op.execute("ALTER INDEX message_pkey RENAME TO messages_pkey")
    op.execute("ALTER INDEX profile_pkey RENAME TO profiles_pkey")

    op.rename_table("message", "messages")
    op.rename_table("profile", "profiles")
