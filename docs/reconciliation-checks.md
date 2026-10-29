# Local reconciliation checks - October 30, 2026

This update reconciles local workspace `a8af3b8` with public branch `c068aac`.
The public branch's cache removal, ignore rules, and credential placeholders are
preserved. The local billing/subscription audit is excluded; the replacement
[demo-boundaries guide](public-demo-readiness.md) describes source behavior only.

## Checks run

| Check | Result |
| --- | --- |
| Backend, isolated SQLite and mocked external services | 128 tests passed |
| Backend with disposable PostgreSQL 16/pgvector configured | 128 tests passed |
| Fresh PostgreSQL migrations | Full chain upgraded to `c34d56e78f90` |
| PostgreSQL migration round trip | Downgrade to `b23c45d67e89`, then upgrade to head passed |
| Frontend tests | All six test files passed under `node --test` |
| Frontend lint | Passed after adding the explicit Node Buffer import in the guest test |
| Production frontend build | Passed with a non-production HTTPS API origin |
| Source hygiene | No tracked Python caches; credential-pattern and documentation link checks passed |

Some backend tests create their own SQLite fixtures even when PostgreSQL is
configured. The real PostgreSQL migration round trip is a separate check; the
suite is not a claim of complete PostgreSQL concurrency coverage. A production
build checks bundling, not live API/model behavior.

The existing Vite warning about JavaScript chunks larger than 500 kB remains.
The local checks did not call Groq, use production data, change cloud settings, or
redeploy the live app. Hosted CI status must be checked separately on GitHub.

## Data compatibility

Physical page numbers are nullable for legacy chunks. New uploads retain page
metadata; older documents need an explicit, owner-scoped re-ingestion to gain it.
The document migration replaces global filename uniqueness with per-owner
uniqueness and adds display names. Downgrade refuses conflicting shared filenames.
See [migration and maintenance instructions](document-management.md) before using
these migrations on an existing deployment. Guest demo access stays disabled
unless a public sample document is explicitly configured.
