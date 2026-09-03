# Deployment

The production topology is Vercel (Angular) -> Google Cloud Run (FastAPI) ->
Render Postgres. Vercel proxies `/api` to Cloud Run so the signed session cookie
remains first-party.

## 1. Push the repository

Commit and push these deployment files to GitHub before connecting either platform.

## 2. Create the Render database

Keep the existing `travel-rag-postgres` database. Copy its external connection
URL into Cloud Run as `DATABASE_URL`; do not commit it.

The Render database free tier expires after 30 days.

## 3. Deploy the backend to Google Cloud Run

Build from `be/Dockerfile` and configure the service with one CPU, 2 GiB RAM,
request-based billing, minimum instances 0, maximum instances 1, and concurrency
1. The container uses CPU-only PyTorch, caches both models during its build, runs
database migrations on startup, and enables the cross-encoder reranker.

Configure these runtime variables in Cloud Run:

- `DATABASE_URL`
- `AUTH_SESSION_SECRET`
- `DEEPSEEK_API_KEY`
- `GOOGLE_CLIENT_ID`
- `COOKIE_SECURE=true`
- `USER_TIMEZONE=Asia/Ho_Chi_Minh`
- `RERANKER_ENABLED=true`
- `CORS_ORIGINS=https://thesis-wheat-one.vercel.app`

Allow unauthenticated invocation because application authentication is handled
by the API session. The deployed API is
`https://travel-rag-api-636198143323.asia-southeast1.run.app`. Confirm its
`/api/health` endpoint returns
`{"status":"ok","service":"travel-rag-api"}`.

## 4. Create the Vercel frontend

1. Import the same GitHub repository into Vercel.
2. Set **Root Directory** to `tga-angular-ui`.
3. Deploy. `vercel.json` supplies the build, output, API proxy, and SPA fallback.
4. Add the resulting Vercel origin to the Google OAuth client's authorized
   JavaScript origins.

## 4. Smoke test

Open `/chat`, sign in with Google, send a message, refresh the page, and confirm
the conversation and authentication session persist.

Update the API rewrite destination in `tga-angular-ui/vercel.json` to the Cloud
Run service hostname and redeploy the frontend.
