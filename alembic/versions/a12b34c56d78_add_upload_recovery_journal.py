"""Add owned storage keys and durable upload recovery journal."""
from alembic import op
import sqlalchemy as sa

revision = "a12b34c56d78"
down_revision = "d66ca0540e8b"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documents", sa.Column("storage_key", sa.String(255), nullable=True))
    op.create_table(
        "pending_uploads",
        sa.Column("storage_key", sa.String(255), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("pending_uploads")
    op.drop_column("documents", "storage_key")
