# PDF RAG frontend

React 19 / Vite 8 workspace for the FastAPI document Q&A API. The interface pairs a
virtualized PDF viewer with streamed answers and clickable physical-page citations.

## Run locally

Requires Node.js 22.13 or newer and the backend from the [repository setup](../README.md#run-locally).

```bash
npm ci
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

Open http://localhost:5173. Register/sign in to manage your documents. A guest
session can only read and ask about the configured public sample; local guest
access is disabled until [sample setup](../docs/guest-demo.md) is complete.

The backend must allow the frontend's exact origin in `CORS_ORIGINS`. Copy
`.env.example` to `.env.local` to persist the API URL. Vite variables are public;
never place model keys or storage credentials in them.

## Workspace behavior

- Light/dark themes, collapsible sidebar, resizable desktop panels and mobile PDF/chat tabs.
- Per-document, per-account chat history in localStorage; history is not synced to other devices or stored on the server. Previous turns are not sent as model context.
- Markdown answers, fenced code, Stop/Retry and scroll-follow controls. Raw HTML is ignored and answer images do not load external assets.
- Structured SSE `sources`, `token`, `error` and `done` events; cancellation and partial answers remain visible.
- Citation chips map source chunk indexes to physical PDF pages. Missing legacy page metadata offers a preview without page navigation. Passage matching highlights the text layer when possible, otherwise the page pulses.
- PDF.js worker, fonts, CMaps, WASM and ICC assets are served locally. Virtualization bounds mounted pages; it does not reduce the PDF download size.
- Sequential uploads distinguish transfer progress from server processing. Rename/delete, Retry/Dismiss and response-loss reconciliation are connected to the document API.

## Checks and production build

```bash
npm run test
npm run lint
VITE_API_BASE_URL=https://api.example.com npm run build
npm run preview
```

Replace the example URL with your own HTTPS backend **origin** when deploying;
production builds reject URLs with paths, queries or fragments. No model call is
made by the build itself. Vite writes output to `dist/`; preview normally serves
port 4173 and needs matching backend CORS if used with the API.

Tests cover chat storage/isolation, retries, SSE parsing, citations, upload state,
and guest-token UI detection. Server-side authorization is tested in the backend;
frontend guest detection is not an access-control boundary.

## API and implementation

- [Page citation and SSE contract](../docs/page-citations.md)
- [Document management and migration](../docs/document-management.md)
- [Guest permissions and setup](../docs/guest-demo.md)
- [Latest reconciliation checks](../docs/reconciliation-checks.md)

The responsive layout lives in `src/components/workspace-shell.jsx`; chat/upload
logic is under `src/hooks` and state/stream helpers under `src/lib`. Checked-in UI
components use Tailwind CSS 4 and shadcn/ui-style primitives. The Azure SPA fallback
and PDF asset MIME configuration is in `public/staticwebapp.config.json`.
