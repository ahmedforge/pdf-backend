# Guest demo

`POST /auth/guest` issues a 20-minute, signed, sample-only bearer token. No visitor
account is created. Set `GUEST_DEMO_DOCUMENT_ID` to one explicitly public sample
owned by a dedicated demo account; unset it to disable new and existing guest access.
Never point it at a user's private PDF. Restart/redeploy after changing this setting.

Guest sessions can list only that sample, download it, and ask questions through
the existing JSON/plain-text/SSE endpoints. All other authenticated routes,
including uploads, rename, deletion, other documents and semantic search, are
blocked server-side. Both token owner and document claims must match the configured
sample. Guest tokens cannot be promoted to normal tokens through the guest API.
The demo account has an undisclosed random password; no login credentials appear
in the frontend. No migration is needed. Normal users retain existing behavior.

All guest model calls share the existing 10-requests/minute owner limiter, so
minting another guest token does not reset the allowance. This is process-local
protection for a low-traffic resume demo, not a durable multi-replica abuse system.
Guest history is stored only in the visitor's browser, never shared through the
server. After expiry, requests are rejected; reload returns to the entry screen, where the demo can be restarted.

The public sample explains how the app works and supports real model responses,
streaming, citations and PDF text highlighting. Answers are not canned. Guests
cannot upload or modify documents; sign-in is offered for the full workspace.

To enable locally, upload the sample using a dedicated test account, set its id
in `GUEST_DEMO_DOCUMENT_ID`, and restart the API. Click “Try the demo — no signup”.
Verify chat and citations, then check that direct upload/PATCH/DELETE requests
with the guest token return 403. Never publish a normal demo-account bearer token.
