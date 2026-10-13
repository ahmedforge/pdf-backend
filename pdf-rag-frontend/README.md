# PDF RAG frontend

React 19 + Vite 8, JavaScript/JSX, Tailwind CSS 4, and shadcn/ui components.

## Run locally

Use Node.js 22.12 or newer (or a compatible newer LTS).

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
- PDF preview downloads authenticated blobs through the existing `/download/{id}` route, cleans up object URLs, and uses the browser's native PDF viewer. Mobile rendering depends on browser PDF support; page-aware rendering is a later phase.
- Drag-and-drop upload and three suggested questions. The composer stays anchored below the scrollable chat area.

Phase 2 adds chat history and Markdown rendering below. Page citation chips and page navigation remain out of scope until Phase 3.

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
