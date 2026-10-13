# Document management

Uploads remain synchronous. PDF extraction, page-local cleaning/chunking,
embedding, ask endpoints, and both answer stream formats are unchanged.

## Migration

Revision `c34d56e78f90` follows `b23c45d67e89`. It replaces global filename
uniqueness with `uq_documents_owner_filename (owner_id, filename)` and adds
nullable `documents.display_name VARCHAR(120)`. Existing display names remain
NULL; no originals are moved and no storage keys are backfilled.

The migration checks for duplicate `(owner_id, filename)` groups before changing
anything, including groups with a NULL owner, and aborts with an actionable
message. PostgreSQL takes a table lock through the transaction to prevent writes
racing the check/constraint change. Owner nullability is unchanged; standard SQL
NULL uniqueness semantics still apply. Authenticated uploads always have an owner.

Downgrade restores global filename uniqueness and removes `display_name`. It
first checks for filenames shared across owners and fails clearly if any exist.
Resolve those conflicts before downgrading; it does not rename or delete data.
These data checks require an online migration, not offline SQL generation.

After approval, run against your intended database:

```bash
venv/bin/alembic upgrade head
# Only after resolving any cross-owner filename conflicts:
venv/bin/alembic downgrade b23c45d67e89
```

## Endpoints and fields

All endpoints require `Authorization: Bearer <token>`.

| Endpoint | Behavior |
| --- | --- |
| `POST /upload` | Multipart field `file`; blocks until ingestion/storage/commit complete; HTTP 200 on success. |
| `GET /files` | Returns `{"files": [...]}`, scoped to the authenticated owner, newest document ID first. |
| `PATCH /files/{document_id}` | JSON `{"display_name":"Annual report"}`; owner-scoped; returns document fields on success. |
| `DELETE /files/{document_id}` | Owner-scoped deletion with durable file cleanup; HTTP 200 even if storage cleanup must retry. |
| `GET /download/{document_id}` | Serves the owner's original PDF using its storage identity; download filename stays the original filename. |

List entries and rename responses contain `id`, `filename`, `display_name`,
`size_bytes`, and `uploaded_at`. `display_name` falls back to `filename` when NULL.
Upload success adds those same fields while preserving `message`, `filename`,
`document_id`, and `chunks_created`. Delete retains `message`, `document_id`, and
`filename`. Internal `storage_key` is not exposed by these responses.

Rename strips Unicode control/format characters (Cc/Cf), trims surrounding
whitespace, rejects the resulting empty string, and allows at most 120 characters
after cleaning. It never changes `filename` or `storage_key`. Missing or foreign
owner documents return 404. The original filename remains the per-owner duplicate
upload identity; changing a display name does not permit a duplicate original.

## Original file identity and legacy safety

Supabase keeps its existing server-generated `upload-<uuid4 hex>.pdf` keys.
New local uploads use server-generated `<uuid4 hex>.pdf` keys under the server's
`uploads` directory, recorded in `documents.storage_key`. Neither the original
filename nor owner input contributes to the path. Files use exclusive-create
mode; an existing file is never overwritten. Candidate keys are also checked
against live keys, legacy document filenames, and outstanding journal keys.

Legacy rows with NULL `storage_key` continue using `uploads/{filename}`. They are
not moved, renamed, or backfilled. New uploads never reuse a live legacy path or
an outstanding legacy deletion key. Retrying a deletion of a legacy filename
cannot delete a new upload with that original filename: the new upload resides
under its own UUID key. UUID/disk collisions fail without overwriting anything.

All local reads/deletions and new-upload cleanup use a common path resolver. It
rejects absolute paths, traversal/separators, empty/NUL keys, a symlinked uploads
root, symlinked files, and resolved paths outside uploads. A missing file counts
as successful deletion. Supabase deletion also treats an HTTP/semantic 404 as
success; other storage failures remain retryable.

File-resolution paths reviewed:

- New local upload allocation and failure cleanup: `app/routers/documents.py`.
- Stored local identity: `app/services/ingestion_service.py`.
- Delete journaling: `app/repositories/document_repository.py`.
- Viewer download plus extract/info/search: `readable_document` in
  `app/routers/documents.py`, using `storage_key or filename`.
- Local read/delete containment: `app/services/storage_service.py`.
- Journal cleanup: `cleanup_pending_uploads` in `app/services/ingestion_service.py`.
- Re-ingestion: `scripts/reingest_page_chunks.py` already uses `storage_key or
  filename`, including its concurrent-original-change check; unchanged.
- Local-to-Supabase migration: `scripts/migrate_local_pdfs.py` already opens
  existing documents using `storage_key or filename`; unchanged.
- `get_existing_file(filename)` in `app/services/file_service.py` is an unused
  legacy helper keyed by filename; it now uses the safe local resolver, and no
  current route calls it.

Other filename identities retained intentionally: per-owner upload uniqueness;
the migration script's per-owner filename map for resumability; re-ingestion's
original-filename consistency check; legacy lookup; and the original download
attachment filename. `insert_document` remains an unused legacy metadata helper
that does not perform ingestion or set a storage key.

## Durable deletion and recovery

One database transaction locks the owner-scoped document, adds/reuses its exact
key in the existing `pending_uploads` journal, and deletes the document. Chunks and
embeddings cascade through the database foreign key. Only after commit does the
route attempt storage cleanup and retire the marker. A failure in the first
transaction leaves the document, chunks, and file intact. A later storage or
marker-retirement failure leaves a durable retry marker and still returns 200.
Warnings do not contain keys, upstream exception details, or credentials.

`app/main.py` starts `recover_uploads()` in the FastAPI lifespan using
`asyncio.create_task`; shutdown cancels and awaits it. Startup does not wait for
recovery. Every 60 seconds it runs cleanup in a thread in both local and Supabase
modes. Entries older than five minutes are retried in batches of ten.
PostgreSQL `FOR UPDATE SKIP LOCKED` prevents concurrent workers processing the
same marker and avoids live upload locks. Savepoints keep one failed key from
rolling back successful cleanup of other entries in the batch. Missing objects
are successful, making repeated cleanup safe. Invalid keys remain journaled for
operator inspection. Failed entries are deferred for five minutes so they cannot
monopolize the oldest-first batches. No second journal or queue was introduced.

The journal uses the currently configured storage backend, as before. Drain it
before changing storage backends; it does not record provider identity. Recovery
needs a running process and will resume after restart. SQLite test fixtures
exercise transactions/cascades/idempotency; PostgreSQL provides the row-lock and
SKIP LOCKED behavior in deployment.

## Errors

Application HTTP errors retain `{"detail":"..."}`. FastAPI request-validation
errors retain `{"detail":[...]}`.

| Condition | HTTP status | Detail |
| --- | --- | --- |
| Missing/invalid filename | 400 | Existing filename validation message |
| Non-PDF extension | 400 | Only PDF files are allowed |
| Missing `%PDF-` signature (including zero bytes) | 400 | File content is not a valid PDF |
| More than 10 MiB / 10485760 bytes | 413 | File is too large. Maximum size is 10 MiB (10485760 bytes) |
| Corrupt/encrypted/unreadable PDF raising a pypdf read/parse error | 422 | This PDF is corrupt, encrypted, or unreadable. Upload an unencrypted, readable PDF. |
| No searchable chunks (blank/scanned/very short text) | 422 | Existing no-searchable-text explanation; OCR is not added |
| Missing multipart file or invalid rename input | 422 | FastAPI validation details |
| Same owner/original filename already present | 409 | A file with this name already exists |
| Missing/foreign-owner document | 404 | Document not found |
| Invalid/expired bearer token | 401 | Existing authentication detail |
| Unexpected ingestion exception | 500 | PDF upload processing failed. |
| Storage unavailable during upload | 503 | PDF storage is unavailable. Please try again later. |
| Storage unavailable after committed document deletion | 200 | File deleted successfully; durable cleanup retries |

Only `pypdf.errors.PdfReadError` and `ParseError` are translated to the new parser
422; unexpected exceptions still use the existing generic 500 path. Password/
file-not-decrypted errors inherit PdfReadError. Error cleanup removes only the
new upload's staging/key file, preserving other owners' originals.

## Local verification

The suite uses dummy configuration, isolated SQLite transactions and local files,
and mocked remote storage/embeddings; it does not need production credentials:

```bash
PYTHONDONTWRITEBYTECODE=1 DATABASE_URL=sqlite:// JWT_SECRET_KEY=unit-test-only-secret \
  venv/bin/python -m pytest -q -p no:cacheprovider
```

For curl verification after approving/applying the migration, start the backend
with your normal local configuration:

```bash
venv/bin/uvicorn app.main:app --reload
```

In another terminal, set `TOKEN` to a token from `POST /auth/login`, `OTHER_TOKEN`
to another registered owner's token, and use a real text PDF:

```bash
API=http://localhost:8000
curl -i -H "Authorization: Bearer $TOKEN" -F 'file=@/absolute/path/report.pdf' "$API/upload"
curl -i -H "Authorization: Bearer $OTHER_TOKEN" -F 'file=@/absolute/path/report.pdf' "$API/upload"
# Repeating the first upload with TOKEN must return 409.
curl -i -H "Authorization: Bearer $TOKEN" -F 'file=@/absolute/path/report.pdf' "$API/upload"
curl -sS -H "Authorization: Bearer $TOKEN" "$API/files"
# Set DOC_ID to the first upload's document_id.
curl -i -X PATCH -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  --data '{"display_name":"  Annual report  "}' "$API/files/$DOC_ID"
curl -i -X PATCH -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  --data '{"display_name":"   "}' "$API/files/$DOC_ID"
curl -i -X PATCH -H "Authorization: Bearer $OTHER_TOKEN" -H 'Content-Type: application/json' \
  --data '{"display_name":"Foreign"}' "$API/files/$DOC_ID"
curl -sS -H "Authorization: Bearer $TOKEN" "$API/download/$DOC_ID" --output /tmp/verified-original.pdf
curl -i -H "Authorization: Bearer $TOKEN" -F 'file=@/absolute/path/corrupt.pdf' "$API/upload"
curl -i -H "Authorization: Bearer $TOKEN" -F 'file=@/absolute/path/encrypted.pdf' "$API/upload"
curl -i -X DELETE -H "Authorization: Bearer $OTHER_TOKEN" "$API/files/$DOC_ID"
curl -i -X DELETE -H "Authorization: Bearer $TOKEN" "$API/files/$DOC_ID"
```

Expected: both owners can upload the same filename; rename trims without changing
filename; blank rename is 422; cross-owner rename/delete are 404; corrupt PDFs
with a valid PDF signature and password-protected unreadable PDFs are 422; own
delete is 200 and the other owner's download still works. The automated suite
covers injected storage/transaction failures, stale and missing keys, recovery
in local mode, migration upgrade/downgrade and traversal/symlink rejection.

## Backend review verification (2026-10-14)

The complete Alembic chain was exercised on isolated PostgreSQL 16.15 with
pgvector (`pgvector/pgvector:pg16`), not the production database. Upgrade to
`c34d56e78f90`, downgrade to `b23c45d67e89`, and upgrade again all succeeded.
Two owners could insert the same filename. Downgrade then refused with
`filenames are shared across owners`, preserving both the head revision and
`display_name`. After resolving names, downgrade succeeded. An intentionally
inconsistent pre-upgrade fixture with duplicate `(owner_id, filename)` rows
was refused before any column mutation; after fixture repair, upgrade succeeded.

### Owner-safe maintenance

`reingest_page_chunks.py` now requires `--owner-id`. Both the initial read and
final locked replacement filter that owner; `--document-id` cannot bypass it.
Use a dry run first:

```bash
venv/bin/python scripts/reingest_page_chunks.py --owner-id 123 --document-id 456
venv/bin/python scripts/reingest_page_chunks.py --owner-id 123 --document-id 456 --apply
```

For `migrate_local_pdfs.py`, the shared application `uploads` directory is
inventoried from the specified owner's database rows, using `storage_key` with
legacy filename fallback. It never adopts another owner's file or treats a UUID
physical key as the original filename. Shared-directory dry runs also require
`--owner-email`. An explicitly separate export directory retains the existing
operator-assigned import flow; PDFs must be regular files, not symlinks.
This script is an importer into Supabase, not an in-place storage-backend switch:
existing same-owner database records are verified and skipped, not rewritten.
Do not switch local metadata to remote mode without separately copying its
recorded physical objects. Such a bulk storage switch is outside this release.

The post-review full suite passed: **106 tests**, including additional foreign-owner
re-ingestion, shared-directory owner inventory, export symlink refusal, reader
traversal rejection, and foreign/symlink viewer tests. Two independent PostgreSQL
transactions also verified that a locked recovery marker is skipped by a second
worker's `FOR UPDATE SKIP LOCKED` query (pgvector 0.8.6). This checks database lock
coordination; storage calls remain covered with local files and mocked remote APIs.
