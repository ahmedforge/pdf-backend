"""Exercise the Alembic revision against an isolated database, including rollback gates."""
import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


@pytest.fixture
def revision():
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/c34d56e78f90_document_management.py'
    spec = importlib.util.spec_from_file_location('document_revision', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def database(unique=True):
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    sa.Table('documents', metadata,
             sa.Column('id', sa.Integer, primary_key=True),
             sa.Column('owner_id', sa.Integer, nullable=True),
             sa.Column('filename', sa.String(255), nullable=False),
             *([sa.UniqueConstraint('filename', name='documents_filename_key')] if unique else []))
    metadata.create_all(engine)
    return engine


def test_upgrade_and_downgrade_preserve_rows_and_restore_constraints(revision, monkeypatch):
    engine = database()
    try:
        with engine.begin() as db:
            db.execute(sa.text("INSERT INTO documents VALUES (1, 1, 'report.pdf')"))
            monkeypatch.setattr(revision, 'op', Operations(MigrationContext.configure(db)))
            revision.upgrade()
            assert db.execute(sa.text('SELECT display_name FROM documents')).scalar() is None
            constraints = sa.inspect(db).get_unique_constraints('documents')
            assert constraints == [{'name': 'uq_documents_owner_filename', 'column_names': ['owner_id', 'filename']}]
            # Different owner succeeds; same owner fails at the DB constraint.
            db.execute(sa.text("INSERT INTO documents (id, owner_id, filename) VALUES (2, 2, 'report.pdf')"))
            with pytest.raises(sa.exc.IntegrityError):
                db.execute(sa.text("INSERT INTO documents (id, owner_id, filename) VALUES (3, 1, 'report.pdf')"))
            with pytest.raises(RuntimeError, match='shared across owners'):
                revision.downgrade()
            assert 'display_name' in {c['name'] for c in sa.inspect(db).get_columns('documents')}
            db.execute(sa.text("UPDATE documents SET filename = 'second.pdf' WHERE id = 2"))
            revision.downgrade()
            assert 'display_name' not in {c['name'] for c in sa.inspect(db).get_columns('documents')}
            assert db.execute(sa.text('SELECT COUNT(*) FROM documents')).scalar() == 2
            assert sa.inspect(db).get_unique_constraints('documents') == [{'name': 'uq_documents_filename', 'column_names': ['filename']}]
            # A second upgrade can discover the restored constraint name.
            revision.upgrade()
    finally: engine.dispose()


@pytest.mark.parametrize('owner', [1, None])
def test_duplicate_gate_fails_before_any_schema_change(revision, monkeypatch, owner):
    engine = database(unique=False)
    try:
        with engine.begin() as db:
            db.execute(sa.text('INSERT INTO documents (id, owner_id, filename) VALUES (:id, :owner, :name)'),
                       [{'id': id, 'owner': owner, 'name': 'same.pdf'} for id in [1, 2]])
            monkeypatch.setattr(revision, 'op', Operations(MigrationContext.configure(db)))
            with pytest.raises(RuntimeError, match=r'duplicate \(owner_id, filename\)'):
                revision.upgrade()
            assert 'display_name' not in {c['name'] for c in sa.inspect(db).get_columns('documents')}
    finally: engine.dispose()
