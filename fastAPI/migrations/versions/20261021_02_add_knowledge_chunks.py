"""Store document chunks and their real 512-dimensional embeddings."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "20261021_02"
down_revision: str | Sequence[str] | None = "20261021_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_chunk",
        sa.Column("source", sa.String(512), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("section", sa.String(512), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("embedding_model", sa.String(128), nullable=False),
        sa.Column("embedding", Vector(512), nullable=False),
        sa.Column(
            "indexed_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("knowledge_chunk")