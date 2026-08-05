<!-- last_verified: 2026-08-05 -->
# Feature: Jobs (primary entity)

## Purpose
Create, read, edit, delete, and run point-cloud processing jobs. A job is the
primary entity; its system of record is a JSON manifest in B2 — there is no
database.

## Used By
- UI: `/jobs` (list), `/jobs/new` (create), `/jobs/[id]` (read + run/edit/delete), `/jobs/[id]/edit` (pre-filled edit)
- API: `GET /jobs`, `POST /jobs`, `GET /jobs/{id}`, `PATCH /jobs/{id}`, `DELETE /jobs/{id}`, `POST /jobs/{id}/run`, `GET /jobs/stats`

## Core Functions
- `services/api/app/service/jobs.py` — lifecycle: `create_job`, `get_job`, `list_jobs`, `update_job`, `delete_job`, `run_job` (+ background `_execute`), `get_job_stats`
- `services/api/app/repo/artifacts.py` — B2 manifest/artifact I/O (`put_bytes`, `get_bytes`, `list_under`, prefix-scoped `delete_under`)
- `services/api/app/types/jobs.py` — `Job`, `JobCreate`, `JobUpdate`, `JobMetrics`, `JobArtifact`, `JobStats`
- `apps/web/src/components/jobs/*` — `jobs-list`, `job-form` (create + edit), `job-detail`, `job-preview`, `job-status-badge`
- `apps/web/src/lib/queries.ts` — `useJobs`, `useJob`, `useJobStats`, `useCreateJob`, `useUpdateJob`, `useDeleteJob`, `useRunJob`

## Canonical Files
- Lifecycle service: `services/api/app/service/jobs.py`
- Form exemplar: `apps/web/src/components/jobs/job-form.tsx` (modeled on `settings-form.tsx`)

## Inputs
- name: string; source_keys: string[] (selector over `raw/`, ≥ 1); meshing_method: `poisson | ball_pivoting`; register_scans: bool; voxel_size: number (> 0, ≤ 10)

## Outputs
- `Job` record persisted at `jobs/<id>/job.json`; on a completed run: `artifacts[]`, `metrics`, `preview_key`
- Manifest status transitions: `queued → running → done | failed`

## Persistence (no database)
Manifests and artifacts live under `jobs/<id>/` in B2. `list_jobs` reads every
`job.json`; `run_job` marks the manifest `running` and orchestrates from a
daemon thread, then rewrites the manifest `done` (with artifacts + metrics) or
`failed` (with the error). The heavy Open3D compute runs in a **separate
process** (`service/pipeline_runner.py`, `spawn` start method), so a native
crash/segfault or a hang is confined to that child and turned into a `failed`
manifest instead of stranding the job or wedging the API; B2 I/O stays in the
parent. Deletes are prefix-scoped to the job's own `jobs/<id>/` — never
bucket-wide.

## Form UX conventions
- **name** — free text; create form shows a placeholder hint, edit form does not
- **source scans** — multi-select checkbox list over the finite `raw/` set (a selector, never free text); ≥ 2 required for registration
- **meshing method** — `Select` (`poisson` default)
- **register** — `Switch`, default off, disabled until ≥ 2 scans are selected
- **voxel size** — number input; create form surfaces a safe default via `FormDescription` (`0.02`), no autofill button; edit form omits the hint

## Edge Cases
- Missing id → 404; editing a `running` job → 409; running an already-running job → 409
- A source key missing in B2 at run time → job `failed` with a clear message
- A native crash/segfault in the compute child → job `failed` (worker crashed), never stuck `running`; the API stays responsive
- A run that overruns `JOB_RUN_TIMEOUT_SECONDS` → the compute child is killed and the job is `failed` (exceeded the time limit)
- On a process restart, an in-flight job's manifest can stay `running` (single-replica demo caveat; the per-run timeout + out-of-process isolation still bound a live worker) — see [RELIABILITY.md](../RELIABILITY.md)

## UX States
- List empty → "No processing jobs yet" + New job CTA; loading → skeleton cards
- Detail → status badge, preview, config, metrics, artifact downloads; polls every 2s while active
- Failed → destructive alert with the error

## Verification
- Test files: `services/api/tests/test_jobs.py`, `services/api/tests/test_pipeline_runner.py`, `services/api/tests/test_pipeline_smoke.py`, `apps/web/src/lib/api-contract.test.ts`
- Required cases: create/read/list, update, delete, run→done with artifacts + write-amplification, run with a missing source → failed, concurrent-run conflict, job stats; out-of-process isolation: result round-trips the process boundary, a worker crash → `PipelineCrashed`, a hang → killed at timeout (`PipelineTimeout`), an ordinary pipeline error → `PipelineError`
- Focused verify command: `pnpm test:api`
- Default pre-PR verify command: `pnpm verify`
- Pass criteria: lifecycle tests green; the OpenAPI contract includes every `/jobs` operation

## Related Docs
- [Processing Pipeline](processing-pipeline.md)
- [Dashboard](dashboard.md)
- [ARCHITECTURE.md](../../ARCHITECTURE.md)
