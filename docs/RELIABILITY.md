<!-- last_verified: 2026-07-30 -->
# Reliability

Reliability expectations and practices for this project.

## Health Checks

- `GET /health` verifies B2 connectivity and returns `healthy` or `degraded`
- Health endpoint is always available, even when B2 is down

## Error Handling

- HTTP handlers return structured error responses with appropriate status codes
- External service failures (B2) are caught and surfaced as 500/503 responses
- No unhandled exceptions leak stack traces to clients
- Uncaught exceptions are converted to a typed JSON 500 (`{"detail": "Internal server error"}`, modeled by `app.types.ErrorResponse`) by the catch-all in `timing_middleware`
- **Error responses carry CORS headers.** `CORSMiddleware` is registered LAST in `main.py` so it is the outermost middleware and wraps every response — including uncaught-exception 500s produced by the inner catch-all. This is intentional and load-bearing: if a 500 shipped without `Access-Control-Allow-Origin`, the browser would block it and the frontend would surface only an opaque "network error", hiding the real server bug. Regression-guarded by `tests/test_error_handling.py::test_unhandled_exception_500_carries_cors_headers`.

## Logging

- Structured JSON logging via Python stdlib
- Every request gets a `request_id` for tracing
- Log levels: ERROR for failures, WARNING for degraded state, INFO for requests

## Observability

- Request timing middleware logs duration for every request
- `/metrics` endpoint exposes basic Prometheus-format counters
- Upload success/failure counts tracked

## Job Execution — crash & hang isolation

The heavy Open3D compute for a job runs in a **separate process** (`app/service/pipeline_runner.py`, `multiprocessing` `spawn` start method), not in the API worker's own threads. This contains the two failure modes that a native library makes possible:

- **Native crash / segfault.** Open3D's Poisson reconstruction can abort at the C++ level (e.g. the intermittent `PoissonRecon … Failed to close loop` on macOS arm64). Such an abort cannot be caught by an in-process `try/except` and would zombify an in-thread worker — stranding the job `running` forever and taking the single-worker API down. Running it in a child means the crash kills only the child; the parent detects the missing result and marks the job `failed`. `/health` and every route stay responsive. The root-cause crash itself is also eliminated by running Poisson single-threaded (`n_threads=1`), which removes the nondeterministic OpenMP path.
- **Hang / overrun.** A run that exceeds `JOB_RUN_TIMEOUT_SECONDS` (default 600) has its child **killed** (not merely abandoned) and the job marked `failed`. The timeout is enforced by the parent waiting on the child, so a wedged compute can never pin the worker.

Only picklable data crosses the process boundary (source-cloud bytes in, artifact bytes + metrics out); B2 I/O stays in the parent, so the child imports no `boto3`. Regression-guarded by `services/api/tests/test_pipeline_runner.py`.

## Stateful Counters — durability caveats

The download counter and the `/metrics` counters are **in-process, per replica**. Consequences to plan for before scaling:

- **Download counter** (`app/repo/counter.py`) persists to a JSON file at `DOWNLOAD_COUNT_FILE` (default `.data/download_count.json`, resolved from the repo root — deliberately outside `services/api/`, which `uvicorn --reload` watches, so a download never writes into the dev reloader's watch tree). On an ephemeral filesystem (Railway without a mounted volume or Vercel Functions) it **resets to 0 on every redeploy**. With multiple replicas or Function instances each keeps its own file/count. For durable, shared counts: mount a persistent volume or swap the adapter for Redis/DB.
- **`/metrics` counters** live in process memory and reset on restart. Behind a load balancer, each replica reports only its own slice — scrape with an instance label and aggregate, or push to a shared collector.

## Rate Limiting

- Per-IP fixed-window limiter (`app/runtime/ratelimit.py`); `RATE_LIMIT_PER_MINUTE` / `RATE_LIMIT_WRITE_PER_MINUTE` are the budgets. Rejected requests get `429` with a `Retry-After` header.
- Counters are in-process per replica; horizontal scaling needs a shared store (e.g. Redis) for a global limit.

## Graceful Degradation

- File listing returns empty list (not error) when B2 has no objects
- Metadata extraction failures don't block upload (return partial metadata)
- Frontend shows skeleton states while loading, error states on failure — and, for the bucket-listing waits that can run for seconds, on-screen copy that escalates instead of silent skeletons (`lib/loading-progress.ts`)
- A full bucket listing (needed by both `/files` and `/files/stats`) is cached, warmed at startup, and served **stale-while-revalidate**: after the first scan, an expired entry is returned immediately while a background thread refreshes it, so a slow or failing B2 list never turns into a user-visible 8-20s wait. `LIST_CACHE_TTL_SECONDS` (default 300) bounds staleness for changes made outside this app; the app's own uploads and deletes invalidate the cache outright. A failed background refresh keeps serving the previous snapshot and is logged
- `WARM_LIST_CACHE_ON_STARTUP=false` skips the startup scan (offline dev, or when startup must not touch B2)

## Deployment

- The API contracts check `/health`; it confirms process readiness, but the
  response is still HTTP 200 when B2 is degraded. Promotion therefore also
  requires `b2_connected: true` and an affected-flow smoke test.
- Railway uses a persistent service model; Vercel runs the API as a Function.
  On Vercel, set `WARM_LIST_CACHE_ON_STARTUP=false` to avoid a cold-start bucket
  scan, and keep `MAX_FILE_SIZE=4000000`: Vercel rejects request bodies over
  4.5 MB before FastAPI can validate them.
- See [infra/railway/README.md](../infra/railway/README.md) or
  [infra/vercel/README.md](../infra/vercel/README.md) for the selected
  platform's versioned configuration, approval, rollback, and cleanup procedure.
- Environment-specific configuration uses platform variables; no environment
  values are committed to the repository.
