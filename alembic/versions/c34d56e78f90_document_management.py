"""Per-owner filenames and optional display names."""
from alembic import op
import sqlalchemy as sa

revision = "c34d56e78f90"
down_revision = "b23c45d67e89"
branch_labels = None
depends_on = None


def _check_duplicates(bind, columns, message):
    names = ", ".join(columns)
    duplicate = bind.execute(sa.text(
        f"SELECT 1 FROM documents GROUP BY {names} HAVING COUNT(*) > 1 LIMIT 1"
    )).first()
    if duplicate:
        raise RuntimeError(message)


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("LOCK TABLE documents IN ACCESS EXCLUSIVE MODE"))
    _check_duplicates(bind, ["owner_id", "filename"],
                      "Document management migration aborted: duplicate (owner_id, filename) rows exist. Resolve duplicates before retrying.")
    constraints = sa.inspect(bind).get_unique_constraints("documents")
    global_names = [item["name"] or "uq_documents_filename" for item in constraints
                    if item["column_names"] == ["filename"]]
    if not global_names:
        raise RuntimeError("Document management migration aborted: global filename unique constraint was not found.")
    with op.batch_alter_table("documents", naming_convention={"uq": "uq_%(table_name)s_%(column_0_name)s"}) as batch:
        for name in global_names:
            batch.drop_constraint(name, type_="unique")
        batch.create_unique_constraint("uq_documents_owner_filename", ["owner_id", "filename"])
        batch.add_column(sa.Column("display_name", sa.String(120), nullable=True))


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("LOCK TABLE documents IN ACCESS EXCLUSIVE MODE"))
    _check_duplicates(bind, ["filename"],
                      "Document management downgrade aborted: filenames are shared across owners. Resolve duplicate filenames before restoring global uniqueness.")
    with op.batch_alter_table("documents") as batch:
        batch.drop_constraint("uq_documents_owner_filename", type_="unique")
        batch.create_unique_constraint("uq_documents_filename", ["filename"])
        batch.drop_column("display_name")
