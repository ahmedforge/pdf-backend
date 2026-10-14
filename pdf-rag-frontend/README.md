# PDF RAG frontend

React 19 + Vite 8, JavaScript/JSX, Tailwind CSS 4, and shadcn/ui components.

## Run locally

Use Node.js 22.13 or newer (or a compatible newer LTS).

```bash
npm ci
VITE_API_BASE_URL=https://pdf-rag-backend.lemontree-0d2266d5.centralindia.azurecontainerapps.io npm run dev
```

Open http://localhost:5173. The Azure backend currently allows this localhost origin. A different hostname/port needs a matching backend CORS configuration. Sign in with an existing account or register through the app.

To persist configuration, copy `.env.example` to `.env.local` and set `VITE_API_BASE_URL`. This is a public backend URL; never put private keys in Vite environment variables.

```bash
npm run lint
VITE_API_BASE_URL=https://pdf-rag-backend.lemontree-0d2266d5.centralindia.azurecontainerapps.io npm run build
npm run preview
```

The preview server normally uses port 4173; authenticated browser API calls require that origin to be allowed by backend CORS. The production build requires an HTTPS backend origin.

## Phase 1: design system and layout shell

- Inter Variable is bundled locally, with no Google Fonts request.
- Neutral surfaces with one indigo accent, rounded-xl surfaces, subtle borders/shadows, and 180ms fades that respect reduced motion.
- Theme toggle starts with the OS preference and persists an explicit light/dark choice under `pdf-rag-theme` in localStorage.
- Collapsible document sidebar, resizable desktop PDF/chat panels, and mobile PDF/chat tabs.
- Existing register/login, upload and streaming answer flows remain connected to FastAPI.
- PDF preview downloads authenticated blobs through the existing `/download/{id}` route, cleans up object URLs, and now uses the virtualized PDF.js viewer introduced in Phase 3.
- Drag-and-drop upload and three suggested questions. The composer stays anchored below the scrollable chat area.

Phase 2 adds chat history and Markdown rendering below. Page citation chips and page navigation are implemented in Phase 3 below.

## UI components and styling

`src/index.css` defines light/dark semantic tokens and the Tailwind theme. `components.json` enables shadcn's JavaScript output; `jsconfig.json` and Vite both map `@/` to `src/`.

Button, Tabs and Resizable are checked-in shadcn/ui source. The shadcn CSS helpers are inlined using its official eject command, so the CLI is not an application dependency. To add a component:

```bash
npx shadcn@latest add input
```

Existing API state and handlers live in `src/App.jsx`; `src/components/workspace-shell.jsx` supplies the responsive workspace. `src/components/theme-toggle.jsx` supplies the shared theme control. No backend code is part of this phase.

## Phase 2: chat interface

- Each document has its own messages and draft. History persists in localStorage under `pdf-rag-chat:v1:<account-subject>:<document-id>`. It survives refresh and sign-out; Clear chat removes only the current document's conversation. This is browser-local history, not server-side chat storage or multi-device sync.
- Storage parsing/access/quota failures show a warning and leave the live conversation usable in memory. An unfinished saved answer restores as stopped with Retry.
- User bubbles align right; AI answers use react-markdown and remark-gfm for headings, lists, tables, code, and copyable code blocks. Raw HTML is ignored; answer images do not load remote assets.
- The composer grows to approximately six lines, stays anchored at the bottom, and is disabled while waiting. Enter sends; Shift+Enter inserts a newline; IME composition is respected.
- Searching document appears immediately. Streamed chunks render as received; a response delivered as one chunk uses a short progressive text reveal. Stop preserves a partial answer; errors show Retry, which replaces the failed attempt without duplicating the user's question.
- The view follows new content unless you scroll up; Latest message restores following. Switching documents stops an active answer and retains its partial content.
- API contracts are unchanged: the streaming request still posts `{question, top_k: 3}` to `/files/{id}/ask/stream` with a Bearer token. Prior conversation messages are not sent as additional backend context.
- No citations or backend code changes are included.

### Verify phase 2

```bash
npm run test
npm run lint
VITE_API_BASE_URL=https://pdf-rag-backend.lemontree-0d2266d5.centralindia.azurecontainerapps.io npm run build
VITE_API_BASE_URL=https://pdf-rag-backend.lemontree-0d2266d5.centralindia.azurecontainerapps.io npm run dev
```

In the app, ask questions on two PDFs, switch between them, and reload to verify separate histories. Clear one chat and verify the other remains. Try Shift+Enter, copy a code block, scroll up during a response, and use Stop/Retry. Check light/dark themes and mobile PDF/chat tabs. Automated tests cover storage isolation/failures, retry races, UTF-8 chunk boundaries, full-response reveal, empty streams, and cancellation. Browser QA uses an isolated local API fixture to exercise controlled failures without touching production data.

## Phase 3: citation sources and PDF navigation

- Chat now posts the existing JSON body with `fetch` to `/files/{id}/ask/stream?format=sse`, using `VITE_API_BASE_URL` and Bearer authentication. A ReadableStream parser handles `sources`, `token`, `error`, and `done` events, split JSON/UTF-8/CRLF reads, incomplete streams, and cancellation. SSE errors preserve partial answers and show Retry. The backend contract is documented in `../docs/page-citations.md`.
- Each turn persists its normalized source array in the existing localStorage history format. Source-less Phase 2 messages remain valid and their `[Chunk N]` text stays plain.
- Citation chips match `chunk_index`, show a page/snippet tooltip, and navigate only when the source has a positive page. NULL-page chips show the preview without navigation; unmatched markers remain plain. Markers in code blocks/inline code/links are not converted to chips.
- Sources rows list unique physical pages actually cited in that answer, not every retrieved source.
- A shared current-page state connects chat and the PDF toolbar. Citation clicks select the PDF tab on mobile. The toolbar provides page input, previous/next, zoom and fit width.
- PDF bytes are downloaded through the existing authenticated API helper. React-PDF/PDF.js uses a Vite-bundled local worker and locally served/copied font, CMap, WASM and ICC assets. No native browser PDF toolbar or CDN worker is used.
- TanStack Virtual mounts only nearby pages (overscan 2). Page heights are measured as they render; distant jumps use estimates then correct their alignment. The full authenticated PDF is still downloaded; virtualization limits page/canvas rendering, not download size.
- Cited passages are matched against normalized text-layer spans (Unicode and whitespace normalization). Matching spans highlight briefly. Missing/extraction-mismatched text falls back to a page pulse. Fade animations are 180ms and reduced-motion preferences are respected.

### Check this phase

```bash
npm ci
npm run test
npm run lint
VITE_API_BASE_URL=https://YOUR-SSE-ENABLED-BACKEND npm run build
# For an approved Step 1 backend running locally:
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

At http://localhost:5173, upload a multi-page text PDF, ask a question, click a numbered citation and compare the physical page with the source. Try toolbar navigation/zoom/fit width, tooltips, and mobile tabs. Reload and verify the chips still work. For legacy documents with NULL pages, verify preview-only chips. Older history without sources should still display its original marker text.

Tests cover one-byte SSE boundaries, server error events, missing done, cancellation, citation mapping/deduplication, old/new localStorage records and text normalization. Browser verification uses a local test service and a 1,002-page synthetic PDF to check bounded rendering, physical pages 7/999/1002, text-layer highlighting, page pulse fallback, error/retry and mobile navigation.

The Azure backend now advertises the structured SSE contract and the deployed frontend uses it. The production frontend is hosted at https://white-grass-09deb0b00.1.azurestaticapps.net.

### Citation storage and streaming safety

Saved source metadata contains only `chunk_index`, `page`, `similarity`, and a
maximum 300-character `text` snippet. Citation metadata has a shared 64 KiB budget
per account; oldest messages lose their sources first, while question/answer text
is retained. If browser storage reports a quota error, source metadata is removed
from this account's stored histories in oldest-first order and the save is retried
once. If messages still do not fit, chat continues in memory and shows a storage
warning. Corrupt records restore as an empty history for that PDF. Other accounts,
auth tokens, and theme preferences are not evicted.

Chat requires the structured SSE endpoint and never falls back to plain-text
streaming. HTTP 404/422, a non-SSE content type, missing sources/done events, and
server error events enter the existing error/Retry flow. Sources must arrive
within 30 seconds after the response starts, meaningful events must arrive at
least every 30 seconds, and streams have a 180-second total limit. Keep-alive
comments do not extend these deadlines. Error events fail immediately, even if
the server never sends `done`.

Run `npm run test`, `npm run lint`, and `npm run build` to check the quota recovery,
corrupt/blocked storage, fragmented SSE, incompatible responses, and deadlines.

## Phase 4A upload and document management

XHR uploads report real bytes sent, then Processing until the synchronous API
response. Multiple files run one at a time. Cancellation is offered only while
Uploading; Processing remains visible. Network/timeout failures after sending
are reconciled with GET /files. A 409 caused by a browser's automatic retry is
also reconciled against the pre-upload IDs; normal duplicate errors remain 409.

The sidebar uses display_name, with inline rename/rollback and confirmed delete.
Deleting removes the document's local history and memory draft and stops its chat.
Drafts are memory-only; there is no separate saved draft record. Upload state is
separate from login/chat, and new uploads preserve the current document selection.
Queues are isolated to the active account.

Tests cover upload validation, string/array error details, queue transitions,
XHR progress/abort and response reconciliation. Local fault injection forwards to
the real backend and tests dropped responses, throttling and rename errors. No
production endpoint is stubbed. Physical phone verification remains pending.
