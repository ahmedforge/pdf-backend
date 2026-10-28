# PDF workspace frontend

React/Vite client for the FastAPI document Q&A service. It provides registration/login, document selection and uploads, and streamed answers.

## Development

Requires Node.js 22 and a running backend (see the [repository setup](../README.md#run-locally)).

```bash
npm ci
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

Open http://localhost:5173. The backend must allow this exact origin through `CORS_ORIGINS`. Tokens are stored in browser localStorage; logging out clears the saved token.

## Checks and production build

```bash
npm run lint
VITE_API_BASE_URL=https://your-api.example.com npm run build
npm run preview
```

Vite writes the build to `dist/`. Configure the public backend URL when building. Never put model keys, database passwords, or Supabase service credentials in `VITE_*` variables. This branch has no frontend automated test script.
