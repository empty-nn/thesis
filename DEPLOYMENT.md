# Deployment

The production topology is Vercel (Angular) -> Render (FastAPI) -> Render Postgres.
Vercel proxies `/api` to Render so the signed session cookie remains first-party.

## 1. Push the repository

Commit and push these deployment files to GitHub before connecting either platform.

## 2. Create the Render backend and database

1. In Render, create a **Blueprint** from this repository. Render reads `render.yaml`.
2. Enter `DEEPSEEK_API_KEY` and `GOOGLE_CLIENT_ID` when prompted.
3. Wait for the database migration and API deployment to finish. On the free
   tier, migrations run as part of the service start command because Render does
   not support pre-deploy commands for free web services.
4. Confirm `https://empty-nn-travel-rag-api.onrender.com/api/health` returns `status: ok`.

The Blueprint uses Render's free tiers for an initial thesis/demo deployment.
Free Postgres expires after 30 days, and the free web service can run out of memory
while loading the embedding and reranking models. If that happens, upgrade only the
web service to Standard and keep the database free during the evaluation period.

## 3. Create the Vercel frontend

1. Import the same GitHub repository into Vercel.
2. Set **Root Directory** to `tga-angular-ui`.
3. Deploy. `vercel.json` supplies the build, output, API proxy, and SPA fallback.
4. Add the resulting Vercel origin to the Google OAuth client's authorized
   JavaScript origins.

## 4. Smoke test

Open `/chat`, sign in with Google, send a message, refresh the page, and confirm
the conversation and authentication session persist.

If Render assigns a different hostname, update the API rewrite destination in
`tga-angular-ui/vercel.json` and redeploy the frontend.
