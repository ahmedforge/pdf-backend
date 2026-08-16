"""change embedding dimension to 384

Revision ID: d274d3a7172e
Revises: 28067dd5b173
Create Date: 2026-08-16 18:18:42.941880

"""
from typing import Sequence, Union
from pgvector.sqlalchemy import Vector
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd274d3a7172e'
down_revision: Union[str, Sequence[str], None] = '28067dd5b173'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("chunks", "embedding")
    op.add_column(
        "chunks",
        sa.Column("embedding", Vector(384), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chunks", "embedding")
    op.add_column(
        "chunks",
        sa.Column("embedding", Vector(1536), nullable=True),
    )
