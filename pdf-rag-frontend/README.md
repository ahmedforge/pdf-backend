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

This phase does not add conversation history, markdown rendering, or page citation chips. Those belong to subsequent phases. Page citation navigation requires a page-aware PDF renderer and citation metadata; it is not inferred from plain answer text.

## UI components and styling

`src/index.css` defines light/dark semantic tokens and the Tailwind theme. `components.json` enables shadcn's JavaScript output; `jsconfig.json` and Vite both map `@/` to `src/`.

Button, Tabs and Resizable are checked-in shadcn/ui source. The shadcn CSS helpers are inlined using its official eject command, so the CLI is not an application dependency. To add a component:

```bash
npx shadcn@latest add input
```

Existing API state and handlers live in `src/App.jsx`; `src/components/workspace-shell.jsx` supplies the responsive workspace. `src/components/theme-toggle.jsx` supplies the shared theme control. No backend code is part of this phase.
