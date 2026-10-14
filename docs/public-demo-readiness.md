# Public-demo readiness audit

Audited 2026-10-14. This audit reads backend code and Azure settings; it does not
silently add backend quotas or change a running deployment.

| Protection | Actual state | Practical limitation |
| --- | --- | --- |
| Upload body | 10 MiB / 10485760 bytes enforced by backend | Whole synchronous ingestion can still be expensive |
| PDF validation | Filename extension, `%PDF-` header, parser errors; no searchable text rejected | OCR not implemented; no page-count/text-length/embedding-work cap |
| Chat | 10 requests per 60 seconds per authenticated user | Process-memory state resets on restart; not shared across workers/replicas; multiple accounts bypass a per-user limit |
| Upload requests | No rate limit | Repeated/concurrent uploads can consume CPU and embedding work |
| Stored documents/bytes per user | No quota | 10 MiB per file does not bound total storage |
| Login/registration | No rate limit | Brute-force and mass-account abuse are not adequately controlled |
| Ask request | top_k bounded 1–10 | Question length has no explicit maximum |
| Ownership | Document reads, chat, rename and delete are owner-scoped | Verified previously with two users; this is access control, not cost control |
| Storage | Private Supabase originals; server credentials stay on backend | Supabase usage/plan limits must be checked separately |
| Azure scaling | minReplicas=0, maxReplicas=1; 1 CPU / 2 GiB | Scale-to-zero can introduce cold starts; one replica is not a spending cap |
| Student subscription | Spending limit On; subscription Enabled | Exhausting credit can disable resources; do not remove the limit |
| Azure budget alerts | No existing budget at audit time | Proposed monthly 10 USD at 50/80/100%; recipient/amount confirmation pending |
| Groq spend | Real external model calls | Azure budgets do not cover Groq; provider plan/rate limits need a separate check |

At the audit query, Azure month-to-date pre-tax cost was approximately **0.1436 USD** for the entire subscription. Billing data can be delayed; this is not a real-time meter or a remaining-credit balance.

## Recommended next backend change

For a small public demo, proposed defaults are 10 documents and 50 MiB of stored
original PDFs per owner, two uploads per minute, one in-flight ingestion per user,
and a reasonable extracted-text/page limit. Login and registration need a shared
IP/account limiter. Keep question size and global concurrency bounded.

These values are **proposals, not active limits**. Quota enforcement must be atomic
(for example, lock the owner row while reserving upload capacity) so concurrent
requests cannot bypass it. It needs integration tests for concurrency, deletion
releasing capacity, failed-upload rollback, and multiple users. A durable/shared
limiter is preferable to a module-global dictionary when scaling. Do not claim
these protections on the resume until implemented and verified.

## Cost alerts

Azure budgets are notifications, not an app shutdown mechanism. The existing
student spending limit remains on. A reviewable monthly budget proposal is
10 USD with actual-cost alerts at 50%, 80% and 100%, for the subscription; this
covers all its Azure projects, not just PDF RAG. The notification email and amount
must be confirmed before activation. No budget has been created by this audit.
Supabase and Groq costs/usage are outside the Azure subscription budget.

References: [Azure spending limits](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/spending-limit),
[Azure budgets](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets).

## CI activation

The workflow now runs on every branch push, pull request, and manual dispatch.
Backend CI installs the pinned requirements, uses a disposable pgvector service,
does upgrade/downgrade/upgrade, then runs the test suite. Frontend CI uses Node 22,
`npm ci`, tests, lint, and a production build with the required HTTPS API origin.
No production API calls or production secrets are needed. Read-only repository
permissions, timeouts and cancellation of superseded runs constrain CI activity.
The new workflow is prepared locally; a hosted run requires committing/pushing it.
Local validation is not represented as a successful new GitHub-hosted run.

Local verification passed 110 backend tests against PostgreSQL, 33 frontend tests, frontend lint and build, and a fresh PostgreSQL migration round trip. The existing bundle-size warning remains.
