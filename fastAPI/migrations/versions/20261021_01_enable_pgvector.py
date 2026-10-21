"""Enable pgvector for knowledge retrieval."""

from collections.abc import Sequence

from alembic import op

revision: str = "20261021_01"
down_revision: str | Sequence[str] | None = "20260807_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """An administrator must enable the extension before an app-role migration."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Require the extension owner and refuse to remove dependent objects."""
    op.execute("DROP EXTENSION IF EXISTS vector")