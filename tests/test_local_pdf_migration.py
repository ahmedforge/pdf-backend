from contextlib import contextmanager
from types import SimpleNamespace

import scripts.migrate_local_pdfs as migration


def test_dry_run_never_queries_or_writes_database(monkeypatch, tmp_path):
    (tmp_path/'sample.pdf').write_bytes(b'%PDF-example')
    monkeypatch.setattr(migration, 'validate_pdf', lambda path: None)
    def unexpected(*args): raise AssertionError('Dry run touched the database')
    monkeypatch.setattr(migration, 'get_user_by_email', unexpected)
    monkeypatch.setattr(migration, 'upload_file', unexpected)
    monkeypatch.setattr('sys.argv', ['migrate', '--uploads-dir', str(tmp_path), '--dry-run'])
    assert migration.main() == 0


def test_resume_skips_matching_pdf_and_ingests_only_new_file(monkeypatch, tmp_path):
    (tmp_path/'existing.pdf').write_bytes(b'%PDF-original')
    (tmp_path/'new.pdf').write_bytes(b'%PDF-new')
    monkeypatch.setattr(migration, 'validate_pdf', lambda path: None)
    monkeypatch.setattr(migration.storage_settings, 'file_storage_backend', 'supabase')
    monkeypatch.setattr(migration, 'get_user_by_email', lambda email: SimpleNamespace(id=1))
    monkeypatch.setattr(migration, 'get_all_documents', lambda owner: [{'filename':'existing.pdf','id':10}])
    monkeypatch.setattr(migration, 'get_document_by_id', lambda *args: SimpleNamespace(filename='existing.pdf',storage_key='owned-key.pdf'))
    @contextmanager
    def saved(key):
        assert key == 'owned-key.pdf'
        yield str(tmp_path/'existing.pdf')
    monkeypatch.setattr(migration, 'open_pdf', saved)
    calls=[]
    def upload(file, current_user):
        calls.append(file.filename)
        assert file.file.read() == b'%PDF-new' and current_user.id == 1
        return {'chunks_created':1}
    monkeypatch.setattr(migration, 'upload_file', upload)
    monkeypatch.setattr('sys.argv', ['migrate','--uploads-dir',str(tmp_path),'--owner-email','owner@example.com'])
    assert migration.main() == 0
    assert calls == ['new.pdf']
    assert len(list(tmp_path.glob('*.pdf'))) == 2


def test_resume_conflict_never_overwrites_existing_object(monkeypatch, tmp_path):
    (tmp_path/'existing.pdf').write_bytes(b'%PDF-local-change')
    remote=tmp_path/'remote.data'; remote.write_bytes(b'%PDF-original')
    monkeypatch.setattr(migration, 'validate_pdf', lambda path: None)
    monkeypatch.setattr(migration.storage_settings, 'file_storage_backend', 'supabase')
    monkeypatch.setattr(migration, 'get_user_by_email', lambda email: SimpleNamespace(id=1))
    monkeypatch.setattr(migration, 'get_all_documents', lambda owner: [{'filename':'existing.pdf','id':10}])
    monkeypatch.setattr(migration, 'get_document_by_id', lambda *args: SimpleNamespace(filename='existing.pdf',storage_key='owned-key.pdf'))
    @contextmanager
    def saved(key): yield str(remote)
    monkeypatch.setattr(migration, 'open_pdf', saved)
    def unexpected(*args, **kwargs): raise AssertionError('Existing PDF was overwritten')
    monkeypatch.setattr(migration, 'upload_file', unexpected)
    monkeypatch.setattr('sys.argv', ['migrate','--uploads-dir',str(tmp_path),'--owner-email','owner@example.com'])
    assert migration.main() == 1
    assert remote.read_bytes() == b'%PDF-original'


def test_shared_uploads_inventory_is_owner_scoped_and_uses_physical_key(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    folder = tmp_path/'uploads'; folder.mkdir()
    (folder/'owned-key.pdf').write_bytes(b'%PDF-owned')
    (folder/'foreign-key.pdf').write_bytes(b'%PDF-foreign')
    monkeypatch.setattr(migration, 'get_user_by_email', lambda email: SimpleNamespace(id=4))
    def listing(owner):
        assert owner == 4
        return [{'filename': 'report.pdf', 'id': 10}]
    monkeypatch.setattr(migration, 'get_all_documents', listing)
    def document(id, owner):
        assert (id, owner) == (10, 4)
        return SimpleNamespace(storage_key='owned-key.pdf', filename='report.pdf')
    monkeypatch.setattr(migration, 'get_document_by_id', document)
    seen=[]
    monkeypatch.setattr(migration, 'validate_pdf', lambda path: seen.append(path.name))
    monkeypatch.setattr('sys.argv', ['migrate', '--owner-email', 'owner@example.com', '--dry-run'])
    assert migration.main() == 0
    assert seen == ['owned-key.pdf']


def test_export_symlinks_are_rejected(monkeypatch, tmp_path):
    import pytest
    folder = tmp_path/'export'; folder.mkdir()
    target=tmp_path/'foreign.pdf'; target.write_bytes(b'%PDF-foreign')
    (folder/'linked.pdf').symlink_to(target)
    monkeypatch.setattr('sys.argv', ['migrate', '--uploads-dir', str(folder), '--dry-run'])
    with pytest.raises(SystemExit): migration.main()
