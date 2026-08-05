<!-- last_verified: 2026-07-30 -->
# Architecture

## Components

- **apps/web/** — Next.js 16 frontend (App Router, Tailwind v4, shadcn/ui)
  - Dashboard with job + storage write-amplification metrics
  - Scans library — point-cloud ingest, scoped to the `raw/` prefix
  - Jobs (primary entity) — create/read/edit/delete/run, with preview thumbnails
  - Full-bucket file explorer with preview, download, delete
  - Dark mode via `next-themes`
- **services/api/** — FastAPI backend (layered architecture)
  - REST API for scan ingest, job lifecycle, and the full-bucket explorer
  - Open3D processing pipeline (downsample → optional registration → mesh → preview), CPU-only, run in a background thread
  - B2 S3 integration via boto3 (raw scans, job manifests, and artifacts)
  - Health check endpoint with B2 connectivity verification
  - Structured JSON logging, Prometheus-format `/metrics`
- **packages/shared/** — TypeScript type definitions
  - Mirrors Pydantic models from the API (files + Job types)
  - Consumed by `apps/web/` as workspace dependency

## Backend Layering

The API follows a strict layered architecture:

```
types/     Pydantic models — no logic, no imports from other layers
  |
config/    Settings (pydantic-settings) — depends only on types
  |
repo/      Data access (boto3 B2 client) — no business logic
  |
service/   Business logic — calls repo, returns types
  |
runtime/   FastAPI routes — calls service, never repo directly
```

### Layering Rules

1. Dependencies flow downward only: `types` -> `config` -> `repo` -> `service` -> `runtime`
2. No backward imports (e.g., service must not import from runtime)
3. `boto3` only allowed in `repo/` layer
4. All boundary data uses Pydantic models (no raw dicts across layers)
5. Each file stays under 300 lines

### Directory Structure

```
services/api/
  main.py                  App entrypoint, middleware, router registration
  app/
    types/                 Pydantic models (FileMetadata, UploadStats, Job, ...)
    config/                Settings loaded from environment (endpoint_url derived from B2_REGION)
    repo/                  B2 S3 client + artifacts.py (manifest/artifact I/O) — the only boto3 code
    service/               Business logic: upload, files, metadata, jobs, pipeline, pointcloud, preview
    runtime/               FastAPI route handlers (files, jobs, upload, health, metrics)
  scripts/seed_samples.py  Generate synthetic clouds and upload to raw/
  tests/                   pytest tests (structural + integration + Open3D smoke)
```

## Boundary Invariants

- **No external SDK leakage**: `boto3` is only imported in `app/repo/`. All other layers interact with B2 through the repo interface.
- **No raw dicts at boundaries**: All data crossing layer boundaries uses typed Pydantic models.
- **No cross-layer mutable state**: Configuration is read-only after init, and no mutable state is shared *between* layers. Intra-layer caches/counters (the listing cache in `repo/list_cache.py`, the B2 connectivity cache in `repo/b2_client.py`, the download counter in `repo/counter.py`, the rate-limit and metrics state in `runtime/`) are module-local and guarded by a `threading.Lock`. The listing cache also owns the only background thread in the app: a stale entry is served immediately while that thread re-scans (stale-while-revalidate), and `main.lifespan` warms it once at startup so no user pays for the cold full-bucket scan.
- **Validated inputs**: All HTTP inputs validated by FastAPI/Pydantic. File keys reject empty and path-traversal patterns; optional prefix confinement via `ALLOWED_KEY_PREFIX` (off by default).

## Deployment

- **Local dev** — `pnpm dev` runs both services via `concurrently`
  - Web: `localhost:3000`
  - API: `localhost:8000`
- **Railway** — two services from the same repository: `web` builds from the
  repository root because it consumes `packages/shared`; `api` builds from
  `services/api`. The versioned per-service configs and the human-approved
  staging/production contract live in [infra/railway/README.md](infra/railway/README.md).
- **Self-hosted API (required for Open3D).** Open3D's native libraries do **not**
  run on Vercel's serverless runtime, so the processing API is self-hosted:
  locally, in a Docker container, or on Railway (two services; the versioned
  configs and human-approved delivery contract live in
  [infra/railway/README.md](infra/railway/README.md)). Point-cloud ops are
  CPU-only — no GPU is required. `services/api/index.py` is a generic ASGI
  wrapper that strips an `/api` prefix, useful behind any single-origin reverse
  proxy.
- **Vercel — frontend only.** The Next.js app can deploy to Vercel (root
  `vercel.json` declares the single `web` service) pointing at the self-hosted
  API via `NEXT_PUBLIC_API_URL`. There is intentionally **no Vercel deploy
  button** because the API cannot run there. See
  [infra/vercel/README.md](infra/vercel/README.md).

External provisioning and deployment remain explicit user-approved actions.

## Data Stores

- **Backblaze B2** — object storage (S3-compatible API), the **sole** data store (no database)
  - `raw/` — ingested source scans
  - `jobs/<id>/job.json` — the Job manifest (system of record for the primary entity)
  - `jobs/<id>/{processed.ply,mesh.ply,preview.png}` — derived artifacts
  - Listing/metadata via S3 `list_objects_v2` / `head_object`; a single-flight, stale-while-revalidate cache is shared across `/files`, the Library, and the dashboard

## External Services

- **Backblaze B2 S3 API** — file storage, retrieval, deletion, presigned URLs

## Trust Boundaries

See [docs/SECURITY.md](docs/SECURITY.md) for full security documentation.

- **Frontend -> API** — CORS-restricted to configured origins. `CORSMiddleware` is registered LAST in `main.py` (outermost) so it wraps **every** response, including uncaught-exception 500s — otherwise the browser would block error responses and the UI would only see an opaque "network error". See [docs/RELIABILITY.md](docs/RELIABILITY.md#error-handling). A per-IP rate-limit middleware sits inner to CORS; see [docs/SECURITY.md](docs/SECURITY.md#rate-limiting).
- **API -> B2** — authenticated via application keys, signature v4
- **Client -> B2** — presigned URLs for download (10-min expiry, forced attachment)

## Data Flows

- **Ingest**: Browser -> `POST /upload` (multipart) -> API validates extension + magic bytes -> repo writes to B2 `raw/{name}` -> response
- **Create job**: Browser -> `POST /jobs` -> service writes the manifest to `jobs/<id>/job.json` (status `queued`)
- **Run job**: Browser -> `POST /jobs/{id}/run` -> manifest flips `running` -> background thread downloads sources from B2, runs the Open3D pipeline (`service/pipeline.py`), writes `processed.ply` + `mesh.ply` + `preview.png` to `jobs/<id>/`, then rewrites the manifest `done` (or `failed`) -> frontend polls
- **List / Download / Delete**: `GET /files` / `GET /files-by-key/download` (presigned) / prefix-scoped `DELETE /jobs/{id}` (removes only `jobs/<id>/`)

## Observability

- Structured JSON logging on all requests with `request_id`
- Request timing middleware (logs duration per request; also the catch-all that converts uncaught exceptions to a typed JSON 500)
- `/metrics` endpoint (Prometheus format: request count, latency, upload count)
- `/health` endpoint (B2 connectivity check)

## API Contract

- Checked-in OpenAPI artifact: `docs/api/openapi.json`
- Export/check command: `pnpm contract:export` / `pnpm contract:check`
- FastAPI freshness test: `services/api/tests/test_openapi_contract.py`
- Frontend route drift test: `apps/web/src/lib/api-contract.test.ts`

The frontend client keeps a small `API_CLIENT_ROUTES` registry in
`apps/web/src/lib/api-client.ts`. Tests compare that registry to the checked-in
OpenAPI artifact so route changes fail loudly before the hand-written client can
silently drift from FastAPI. `GET /metrics` is intentionally server-only.

## Canonical Files

- Primary-entity lifecycle (service): `services/api/app/service/jobs.py`
- Pipeline compute: `services/api/app/service/pipeline.py`, `pointcloud.py`, `preview.py`
- Jobs routes: `services/api/app/runtime/jobs.py`
- B2 data access (repo layer): `services/api/app/repo/b2_client.py`, `repo/artifacts.py`
- Pydantic models: `services/api/app/types/` (`files.py`, `jobs.py`, `upload.py`, `stats.py`)
- Config (pydantic-settings): `services/api/app/config/settings.py`
- Structural tests: `services/api/tests/test_structure.py`; Open3D smoke: `tests/test_pipeline_smoke.py`
- OpenAPI contract: `docs/api/openapi.json` (exporter: `services/api/scripts/export_openapi.py`)
- Frontend API client / hooks: `apps/web/src/lib/api-client.ts`, `apps/web/src/lib/queries.ts`
- Shared TypeScript types: `packages/shared/src/types.ts`

## Core Features

- [Point-Cloud Ingest](docs/features/point-cloud-ingest.md)
- [Processing Pipeline](docs/features/processing-pipeline.md)
- [Jobs](docs/features/jobs.md)
- [Dashboard](docs/features/dashboard.md)
- [Bucket Explorer](docs/features/bucket-explorer.md)

## References

- [docs/SECURITY.md](docs/SECURITY.md) — security principles and implementation
- [docs/RELIABILITY.md](docs/RELIABILITY.md) — reliability expectations
- [AGENTS.md](AGENTS.md) — architectural invariants and agent instructions
