<!-- last_verified: 2026-08-05 -->
# Vercel Delivery Contract (frontend only)

This is the canonical runbook for deploying **the Next.js frontend** to Vercel.
It records the supported topology without linking a local directory, creating a
Vercel project, deploying code, or storing environment values in the repository.
An authorized human performs every external action.

## Why the API is NOT on Vercel

The processing API runs **Open3D**, which depends on native/compiled libraries
(Filament rendering, `libGL`/`libgomp`, and large CPython wheels). Those do not
run in Vercel's serverless Python runtime, and a single point-cloud run far
exceeds a Vercel Function's payload and duration limits. So the API is
**self-hosted** — Railway (see [../railway/README.md](../railway/README.md)),
a Docker container, or a VM — and Vercel hosts only the frontend.

## Topology: one Vercel project (web only)

| Service | Root directory | Framework | Public path | Health check |
| --- | --- | --- | --- | --- |
| `web` | `apps/web` | Next.js | `/` | `/` |

The repo-root `vercel.json` declares only the `web` service. The `web` install
runs from the repo root (`cd ../.. && pnpm install`) so the pnpm workspace
resolves `packages/shared`. The browser talks to the self-hosted API through an
absolute origin — set `NEXT_PUBLIC_API_URL` (below); there is no `/api` rewrite
on Vercel.

## Variables and Public Exposure

Set values in the Vercel Project and environment. Never put values in
`vercel.json`, source code, an issue, PR, terminal transcript, or screenshot.
No B2 credentials belong on the Vercel frontend — they live only on the
self-hosted API.

| Variable | Classification | Notes |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | Public build-time configuration | The self-hosted API origin (e.g. `https://api.example.com`). Next.js inlines it at build time, so it must be set before `pnpm build`; redeploy after changing it. Contains no credential. |

On the API host set `API_CORS_ORIGINS` to the exact Vercel web origin, or the
browser blocks every cross-origin call. Use an exact origin per environment; do
not set a broad production origin to accommodate rotating preview URLs.

## No one-click deploy button

The README intentionally ships **no Vercel deploy button**: a button implies a
whole-app clone, but the Open3D API cannot run on Vercel. Deploy the frontend by
importing the repo as a Vercel project (root `vercel.json`, `web` service) and
point it at your self-hosted API.

## Setup: Human-Approved Only

1. Stand up and verify the self-hosted API first (Railway/Docker/VM). Confirm
   `GET /health` returns `b2_connected: true`.
2. Import the repository into the correct Vercel team. Vercel reads the repo-root
   `vercel.json` and creates the single `web` service project.
3. Set `NEXT_PUBLIC_API_URL` to the API origin for each environment, and set the
   API's `API_CORS_ORIGINS` to the exact Vercel web origin.
4. Deploy a Preview from the approved branch/commit; add a custom domain only
   after a human reviews visibility and CORS. Promote to production only after
   the approved Preview.

Never create a project, preview, domain, production deployment, or environment
variable without the user's explicit approval. A request to edit repository
documentation or configuration is not approval to perform any of those actions.

## Promotion, Verification, and Rollback

1. Confirm the target commit passed `pnpm verify` and review the Vercel config
   and environment target.
2. Verify the self-hosted API's `GET /health` includes `b2_connected: true`
   (HTTP 200 alone can mean `degraded`).
3. Load the web root, exercise the affected flow, and confirm the browser
   reaches the API (CORS + `NEXT_PUBLIC_API_URL`).
4. Record the deployed commit, URLs, health evidence, smoke-test result,
   approver, and skipped checks in the PR or change record.

If verification fails, stop promotion and redeploy the last known-good Vercel
deployment. Treat a B2 outage separately from an application rollback: the API
remains reachable but reports `degraded`.

## References

- [Vercel Services](https://vercel.com/docs/services)
- [Vercel environment variables](https://vercel.com/docs/environment-variables)
- [Railway delivery contract](../railway/README.md) — self-hosted API
