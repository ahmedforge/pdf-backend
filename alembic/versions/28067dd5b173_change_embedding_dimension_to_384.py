"""change embedding dimension to 384

Revision ID: 28067dd5b173
Revises: 37d82f817ffd
Create Date: 2026-08-16 18:13:53.965811

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '28067dd5b173'
down_revision: Union[str, Sequence[str], None] = '37d82f817ffd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
