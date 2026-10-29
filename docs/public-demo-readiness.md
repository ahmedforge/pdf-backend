# Public demo boundaries

This guide describes the source protections and their limits. It is not an audit
of a live cloud account, provider billing, or current deployment settings.

| Protection | Implemented behavior | Limit |
| --- | --- | --- |
| Upload validation | 10 MiB limit, PDF header/extension validation, rejection of non-searchable text | No OCR or page/text/embedding-work cap |
| Authenticated chat | 10 requests per minute per owner | Process-local; resets on restart and is not shared across replicas |
| Guest access | 20-minute signed token for one configured public sample; read/chat routes only | Sample setup is explicit; guest access is disabled when unset |
| Guest model calls | Share the demo owner's limiter | Not a global durable cost or concurrency cap |
| Document operations | Owner-scoped read, chat, rename, and delete | Ownership checks do not bound account creation or resource usage |
| Original PDFs | Local disk or private object storage | Provider storage limits need separate configuration |
| User storage/upload quotas | Not implemented | Per-file limits do not bound total storage or ingestion work |
| Login/registration limiter | Not implemented | Further protection is needed before unrestricted public use |

Never configure the guest document ID to reference a private user document.
See [guest setup](guest-demo.md) for the allowed routes and verification steps.
Do not put service credentials or normal account tokens in the frontend.

## Remaining work

Before expanding public access, implement atomic storage reservations, bounded
in-flight ingestion, page/text limits, authentication rate limits, and a shared
limiter. Verify failure rollback, concurrent uploads, quota release on deletion,
and isolation between users. These are future work, not active protections.

Monitor hosting, object storage, and model usage separately. Alerts are not a
substitute for application-enforced limits. Deployment or billing changes are
outside this source update.

## CI

The workflow runs backend tests and a PostgreSQL upgrade/downgrade/upgrade using
a disposable service. Frontend checks install the lockfile dependencies, run
tests and lint, then build for production. CI uses dummy credentials and should
not call the live model or production database. A local pass is not proof of a
successful hosted CI run.
