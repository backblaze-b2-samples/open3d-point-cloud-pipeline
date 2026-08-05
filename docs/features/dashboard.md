<!-- last_verified: 2026-08-05 -->
# Feature: Dashboard

## Purpose
Give an at-a-glance view of point-cloud processing and the write-amplified B2
storage it produces — how many jobs ran, how much source data was ingested, how
many artifacts were written, and the source→artifact write-amplification ratio.

## Used By
- UI: `/` page (dashboard home)
- API: `GET /jobs/stats`, `GET /jobs`, `GET /files/stats/activity`

## Core Functions
- `apps/web/src/components/dashboard/stats-cards.tsx` — 4 stat cards (Processing Jobs, Source Data, Artifacts on B2, Write Amplification)
- `apps/web/src/components/dashboard/recent-jobs-table.tsx` — most recent jobs with status
- `apps/web/src/components/dashboard/upload-chart.tsx` — objects written to B2 per day
- `apps/web/src/lib/queries.ts` — `useJobStats()`, `useJobs()`, `useUploadActivity()`
- `services/api/app/service/jobs.py` — `get_job_stats()` (counts jobs, sums `raw/` vs `jobs/` bytes, computes amplification)
- `services/api/app/repo/artifacts.py` — `list_under()` for the `raw/` and `jobs/` prefixes

## Canonical Files
- Dashboard aggregation: `services/api/app/service/jobs.py` (`get_job_stats`)
- Stat cards: `apps/web/src/components/dashboard/stats-cards.tsx`

## Inputs
- None (loads automatically)

## Outputs
- `GET /jobs/stats` → `JobStats` (total_jobs, per-status counts, source_bytes, artifact_bytes, artifact_count, write_amplification)
- `GET /jobs` → `Job[]` for the recent-jobs table
- `GET /files/stats/activity?days=7` → `DailyUploadCount[]` for the bar chart (all objects, server-aggregated)

## Flow
- Page loads → parallel queries for job stats, recent jobs, and bucket activity
- Stat cards show the job count, ingested source size, artifact count, and the write-amplification multiplier (artifact bytes ÷ source bytes)
- The "Bucket Activity" chart shows objects written to B2 per day (last 7)
- The "Recent Jobs" table links each job to its detail page; job queries poll while any job is active so a finished run appears without a manual refresh

## Edge Cases
- API unavailable → inline error state with retry (never a false "0 jobs")
- No jobs / no scans → empty states on cards, chart, and table
- Numbers derive from listing the `raw/` and `jobs/` prefixes; the app's own writes invalidate the shared listing cache, so its own changes are never stale

## UX States
- Loading: a "Loading pipeline metrics…" notice above skeleton cards
- Empty: "No jobs yet" / "No activity yet"
- Loaded: populated cards, chart, and recent-jobs table

## Verification
- Test files: `services/api/tests/test_jobs.py` (`test_job_stats`), `apps/web/src/lib/api-contract.test.ts`
- Required cases: job stats with a completed run (amplification > 0), empty bucket, API error fallback
- Focused verify command: `pnpm test:api`
- Default pre-PR verify command: `pnpm verify`
- Pass criteria: focused tests and `pnpm verify` green

## Related Docs
- [Jobs](jobs.md)
- [ARCHITECTURE.md](../../ARCHITECTURE.md)
- [App Workflows](../app-workflows.md)
