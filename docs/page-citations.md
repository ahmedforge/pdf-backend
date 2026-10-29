# Page-aware chunk sources (backend Step 1)

Apply Alembic revision `b23c45d67e89` before running the updated backend. It adds nullable `chunks.page_number` with a positive-page check. Existing rows remain NULL; downgrade drops the page column/check and preserves other chunk data.

New uploads extract, clean, and chunk each page separately. Physical page indexes start at 1, independent of printed PDF labels. Empty pages and chunks with fewer than 20 non-whitespace characters are skipped. `chunk_index` stays zero-based, sequential, and unique within the whole document. Full chunk text was already stored; it remains in `chunk_text`.

## JSON answer

`POST /files/{document_id}/ask` keeps its request and top-level fields. Sources retain `chunk_index`, `similarity`, and `preview`, and add `page` and full `text`:

```json
{
  "document_id": 1,
  "question": "What is explained?",
  "answer": "Explanation. [Chunk 25]",
  "sources": [{"chunk_index": 25, "page": 7, "text": "Stored passage.", "similarity": 0.8, "preview": "Stored passage."}]
}
```

Sources represent the exact retrieved context for this answer. Match `[Chunk N]` to `chunk_index`, not the database primary key. No source field named `id` is added. `page` is NULL for historical chunks without metadata.

## Optional structured stream

`POST /files/{document_id}/ask/stream?format=sse` uses the same Bearer authentication, ownership checks, rate limit, and JSON request (`question`, `top_k`, optional `min_similarity`). The default endpoint without the query parameter still emits the existing `text/plain` answer.

The opt-in stream uses `text/event-stream` and JSON event data:

```text
event: sources
data: {"sources":[{"chunk_index":25,"page":7,"text":"Stored passage.","similarity":0.8,"preview":"Stored passage."}]}

event: token
data: {"text":"Explanation. [Chunk 25]"}

event: done
data: {"complete":true}
```

Markers outside the retrieved context are removed even when split across provider tokens. Only potential citation fragments are buffered; normal answer text streams through. JSON answers already validate their markers; the legacy plain-text stream keeps its existing behavior.

Retrieval/generation failures emit an `error` event with `{ "message": "..." }`, followed by `done` with `{ "complete": false }`. Clients must treat this as a failed/partial answer, not success. Authentication/ownership/validation failures retain normal HTTP errors. No matching chunks produce empty sources, a grounded fallback answer, and successful done.

## Existing documents

The migration does not guess pages or rewrite existing chunks. `scripts/reingest_page_chunks.py` opens originals using the existing local/Supabase storage adapter. It preserves document IDs, owner, filename, upload metadata, storage key, and original PDF bytes.

Default is dry-run; `--apply` replaces chunks/embeddings in one transaction after extraction and embedding finish. Missing originals, unusable text, embedding failures, or database failures leave existing chunks untouched. Re-runs skip already page-aware documents unless `--force` is supplied. Source text/row IDs/chunk indexes may change after re-ingestion; historic messages without saved sources must continue rendering as plain text.

```bash
python scripts/reingest_page_chunks.py --document-id 1
python scripts/reingest_page_chunks.py --document-id 1 --apply
# Omit --document-id to inspect/process all documents in the configured database.
```

Use the same FILE_STORAGE_BACKEND/Supabase configuration that stores the originals. Downloaded temporary originals are automatically removed. No production migration or re-ingestion has been run as part of this patch.

## Local verification

Use a disposable PostgreSQL database with pgvector, not the production .env database. With the project's virtual environment active:

```bash
export DATABASE_URL=postgresql://postgres:citation-test@127.0.0.1:55432/postgres
export FILE_STORAGE_BACKEND=local
export JWT_SECRET_KEY=local-citation-test-only
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

Register/login locally and upload a multi-page text PDF (include a blank page). Check JSON sources and both stream formats:

```bash
curl -N http://localhost:8000/files/1/ask/stream\?format=sse \
  -H "Authorization: Bearer $PDF_TEST_TOKEN" -H 'Content-Type: application/json' \
  -d '{"question":"Summarize the document","top_k":3}'
```

The test token must come from this local database. Legacy `/ask/stream` without `?format=sse` must remain plain text. Existing frontend files/env configuration have not changed.

The automated suite avoids external service writes:

```bash
DATABASE_URL=sqlite:// FILE_STORAGE_BACKEND=local JWT_SECRET_KEY=test-only GROQ_API_KEY=test-only python -m pytest -q
```

Tests cover physical page gaps, page-bound chunks, sequential indexes, additive source fields, NULL legacy pages, split marker filtering, SSE order/errors/auth/default compatibility, and atomic dry-run/re-ingestion behavior. The migration was also verified on disposable PostgreSQL through upgrade, downgrade, and re-upgrade.
