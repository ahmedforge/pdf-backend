"""add hnsw index to chunk embeddings

Revision ID: d66ca0540e8b
Revises: d274d3a7172e
Create Date: 2026-08-16 18:51:52.105065

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd66ca0540e8b'
down_revision: Union[str, Sequence[str], None] = 'd274d3a7172e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_chunks_embedding_hnsw
        ON chunks
        USING hnsw (embedding vector_cosine_ops)
        WHERE embedding IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS ix_chunks_embedding_hnsw;
        """
    )
