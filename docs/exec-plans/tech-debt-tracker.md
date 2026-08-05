<!-- last_verified: 2026-08-05 -->
# Tech Debt Tracker

Known tech debt items for **Open3D Point Cloud Pipeline**. Agents update this
when they discover or create tech debt. Items are scoped to the surfaces this
app actually ships: the **Jobs** primary entity, the point-cloud pipeline, the
scoped **Scans** library, the full-bucket **Files** explorer, the dashboard, and
the reused B2 repo layer.

## Open

| Description | Impact | Proposed Resolution | Priority |
|---|---|---|---|
| In-process job run-lock is not durable across restart or replicas | `service/jobs.py` runs the pipeline in a daemon thread guarded by a process-local `threading.Lock` + `_running` set; on a process restart an in-flight job's manifest can stay `running` (the per-run timeout only bounds a live worker), and a second replica would not see the lock, so the same job could run twice. Documented as a single-replica demo caveat in `docs/features/jobs.md` and `docs/RELIABILITY.md` | Persist run-state in the B2 manifest with a lease/heartbeat (reap stale `running` jobs on startup), and move dedup/locking to a shared store (Redis/DB) before running more than one replica | Medium |
| The heavy API is not serverless-deployable | Open3D, `laspy`, and matplotlib depend on native libraries that do not run on Vercel Functions, so the processing API must be run local/self-hosted (Railway/Docker/local). The Next.js frontend can still deploy to Vercel pointing at a self-hosted API. Documented in `README.md`, `ARCHITECTURE.md`, and `infra/vercel/README.md` | Ship a container image (`infra/railway`) as the supported deploy target for the API; keep Vercel scoped to the frontend. Optionally add a `docker-compose.yaml` (see below) as the one-command local run | Medium |
| Download counter & `/metrics` not durable across restart/replicas | Counter resets on redeploy (ephemeral FS); both fragment across replicas | Back the counter with a shared store (Redis/DB); label/aggregate metrics per instance. Lives in `repo/counter.py`, documented in `docs/RELIABILITY.md` | Medium |
| Upload buffers the whole scan in memory | ~3× file size RAM per upload; a large LiDAR/photogrammetry cloud strains the server (the event loop is offloaded, but memory is unbounded). The demo `MAX_FILE_SIZE` cap keeps this safe for the sample; real clouds are far larger | Stream to a temp file, or S3 multipart above a size threshold | Medium |
| `GET /files-by-key/detail` re-downloads the whole object to recompute metadata | Rich metadata for a stored file costs a full download + in-memory hash per preview; large objects are slow/expensive and buffer in API memory | Persist `FileMetadataDetail` at upload (S3 user-metadata, mind the ~2KB cap, or a sidecar object) and serve it without re-downloading; add a size ceiling above which detail is skipped | Medium |
| `get_upload_activity` re-materializes `FileMetadata` for every object just to bucket dates | Wasted O(n) CPU per `/files/stats/activity` (the bucket scan is cached; the materialization is not) | Aggregate from the raw listing dicts like `get_upload_stats` already does | Low |
| `GET /files` has no pagination — the explorer shows only the newest 100 objects | An older object is unreachable from the UI. The browser *states* the truncation (`lib/file-list-limit.ts`) instead of claiming it shows the whole bucket, but there is still no way to page or search to an older key. Note this affects the full-bucket Files explorer, not the scoped Scans library | Add cursor pagination to `GET /files` (pass through S3's `ContinuationToken` rather than slicing a full scan) plus "Load more"/search in the file browser | Medium |
| Only the tree layout exists on `/files`; the Settings "Default file view" List and Grid options are demo placeholders | Settings offers Tree/List/Grid but only the tree renders; the option is labelled a demo field and persists to localStorage only | Build real List/Grid renderers plus a view switcher on `/files`, then honour the stored `defaultView` and drop the "Demo field" label | Low |
| `/settings` profile & preference fields are a labelled demo, not backed by real surfaces | Display name, bio, email-on-upload, quota-warning + threshold, and default view are illustrative placeholders (persist to localStorage, drive nothing) because this is a single-tenant demo with no account system, mailer, quota banner, or activity log. Theme is the only real preference. See `docs/features/settings.md` | Build each backing surface (auth, mailer, quota banner, List/Grid views), then wire the matching field to it and drop its "Demo field" label | Low |
| Single-tenant demo — no auth layer or placeholder | Every consumer designs auth from scratch; unclear where it plugs in. All jobs, scans, and files are shared. Acceptable for a local sample; a hard blocker for any multi-user deployment | Add example middleware (API-key or JWT) + docs for the seam, and scope jobs/scans per principal | Low |
| Frontend has no component/render tests; e2e only checks routing | UI states (loading/error/empty) and the real job journey (create → run → poll → download artifacts → delete) are unverified at the component level | Add jsdom + @testing-library/react render tests; a fixture-driven job-lifecycle e2e | Medium |
| Allowed point-cloud file types hardcoded in `service/upload.py` | Reuse friction — changing the accepted `.ply/.pcd/.las/.laz` set means editing source, and the client mirror in `lib/upload-file-types.ts` must be kept in sync by hand | Make `ALLOWED_TYPES` / `MIME_EXTENSION_MAP` env-configurable and derive the client list from a shared source | Low |
| No `docker-compose.yaml` | Manual venv + dual-process startup slows the first local run, and the API's native deps make a container the natural deploy unit | Add compose with `web` + `api` services and Dockerfiles (also the recommended way to run the native Open3D API) | Low |
| `e2e/**` and `playwright.config.ts` are excluded from `apps/web/tsconfig.json` | Neither `pnpm typecheck` nor `next build` typechecks the E2E specs, and `pnpm test:e2e` is not in CI — type errors there can sit undetected | Add a dedicated `tsconfig.e2e.json` and typecheck it in `pnpm verify:web`, or drop the exclude | Low |
| The `scripts/agent-docs/*` enforcement checks are presence-only in several places | The agent-doc guard asserts that gates *exist*, not that they *run*: an `if: false` job or a `\|\|`-short-circuited verify chain can still satisfy "declares/ runs job X"; `RUN_KEY` matches `run:` at any indentation; and the env-ignore check validates path *shape* rather than that the `.gitignore` is tracked. Several of these are recorded as fixed false-greens in the scripts' own comments — the next regression is silent again | Anchor `run:` to step-level indentation, reject always-false conditions and short-circuit operators on the asserted gates, confirm the ignore source with `git ls-files --error-unmatch`, and add a `node:test` runner over fixture repos wired into `pnpm verify` | Medium |
| The API contract check covers routes only; request/response *shapes* and the hand-written mirrors of the Pydantic models in `packages/shared/src/types.ts` are still hand-synced | Renaming or retyping a response field passes every gate — `docs/api/openapi.json` updates, the route set is unchanged, and the frontend keeps reading the old field as `undefined`. This is the half of "`api-client.ts` hand-synced to FastAPI" that the contract workflow did not close | Generate the shared TS types from `docs/api/openapi.json` (`openapi-typescript` emits types only, no client), or assert the schema of each client-consumed operation against `packages/shared` | Medium |

## Known UI nitpicks

Low-severity polish carried over on the starter surfaces this app keeps
(`globals.css`, the `/files` explorer + preview dialog, the 404 route, the
`/settings` Danger Zone). None blocks a core flow.

- All screens — no `<button>` reports `cursor: pointer` (Tailwind v4 dropped the UA default), so the "this is clickable" signal is weak on the controls the main flows depend on. Fix once via `globals.css`
- `/files` preview + metadata panel — an EXIF `Software` value can carry trailing NUL padding straight into the rendered DOM (invisible on screen, but unsanitised)
- `/files` preview dialog — while the presigned URL is pending, the loading label is screen-reader-only and never escalates, so past ~5s a sighted user sees only an unlabelled shimmer (the dashboard, by contrast, escalates its wait copy)
- 404 route — the breadcrumb title-cases the unknown slug (e.g. "This Route Does Not Exist"), presenting a nonexistent route as a real page name; the rest of the 404 is solid
- `/settings` Danger Zone — the "Empty this bucket" card copy makes an unconditional destructive claim with no on-card qualifier (the confirm dialog does note it is a demo)

## Resolved

| Description | Resolution |
|---|---|
| `api-client.ts` hand-synced to FastAPI (route drift only) | Added deterministic OpenAPI workflow: `docs/api/openapi.json`, `pnpm contract:export`, `pnpm contract:check`, backend freshness coverage in `test_openapi_contract.py`, and frontend route drift coverage in `api-contract.test.ts`. Full codegen remains a future option only if this lightweight check proves insufficient. **Payload/type drift is not covered** — see the open row on `packages/shared/src/types.ts` |
| Byte-exact OpenAPI comparison against floating Python dependencies | Added `services/api/requirements.lock`, a complete Python 3.12 resolution installed by setup and CI. Intentional dependency refreshes now update the lock and `docs/api/openapi.json` together, so routine verification does not absorb upstream schema churn. |
| Blocking boto3 in `async def` handlers froze the single event loop | B2 handlers are sync `def` (Starlette threadpool); upload offloads via `run_in_threadpool` |
| Full-bucket scan on every list/stats/activity request, uncached | Short-TTL, stale-while-revalidate cache in `repo/b2_client`, invalidated on upload/delete |
| No CI — quality gates ran only when a human remembered | `.github/workflows/ci.yml` runs all three `pnpm verify` gates — `check:agent-docs`, `verify:api`, `verify:web` — as parallel jobs on PR and push to `main` |
| SVG stored-XSS; declared MIME trusted; unused `python-magic` dep | Dropped SVG from allow-list; added magic-byte signature check; removed dead `python-magic` |
| No rate limiting → DoS + B2 cost amplification | Per-IP fixed-window limiter (`runtime/ratelimit.py`), read/write budgets |
| Counter persistence lived in the service layer (layering violation) | Moved file I/O to `repo/counter.py` behind `get/increment_download_count` |
| CORS `allow_credentials=True` with no auth + regex escape hatch | Default `allow_credentials=False`; empty origins filtered |
| No security headers on API responses | `X-Content-Type-Options: nosniff` + `Referrer-Policy: no-referrer` on every response |
| Key-addressed ops could target any bucket object | Opt-in `ALLOWED_KEY_PREFIX` confinement (off by default, preserves arbitrary-key routes); job deletes are always prefix-scoped to `jobs/<id>/` |
| Unguarded `int(content-length)`; public `/docs`; uncached `/health` B2 call | Content-Length parse guarded; `ENABLE_DOCS` toggle; connectivity cached ~5s |
| Upload validation sad-paths (413/415) + sanitizer untested | `tests/test_upload_validation.py` covers the rejection matrix, signature, `uploads_total` |
| `NEXT_PUBLIC_API_URL` missing from `.env.example` | Added with guidance |
| `get_upload_stats()` / `list_files()` object listing capped at 1000 | Shared `_list_all_objects()` paginator follows `ContinuationToken` |
| `datetime.utcnow()` deprecated in Python 3.12+ | Replaced with `datetime.now(UTC)` |
| S3 client recreated on every API call | Cached module-level singleton via `lru_cache` |
| Metrics counters not thread-safe | Guarded by `threading.Lock` |
| `_humanize_bytes` duplicated in Python | Extracted to `app/types/formatting.py` |
| `humanizeBytes` / `formatDate` duplicated in TypeScript | Extracted to `lib/utils.ts` (tested) |
| Custom `FileNotFoundError` shadowed the built-in | Renamed to `FileNotFoundServiceError` |
| Dropzone accepted any file type client-side | `accept` allow-list mirroring backend `ALLOWED_TYPES` (tested for drift) |
| No test harness for feature specs | pytest suite across upload, files, activity, errors, validation, rate limit, pagination, and the job lifecycle + pipeline smoke |
