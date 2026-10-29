"""Add nullable physical PDF page numbers to chunks."""
from alembic import op
import sqlalchemy as sa

revision = "b23c45d67e89"
down_revision = "a12b34c56d78"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("chunks", sa.Column("page_number", sa.Integer(), nullable=True))
    op.create_check_constraint("ck_chunks_page_number_positive", "chunks", "page_number IS NULL OR page_number >= 1")


def downgrade():
    op.drop_constraint("ck_chunks_page_number_positive", "chunks", type_="check")
    op.drop_column("chunks", "page_number")
