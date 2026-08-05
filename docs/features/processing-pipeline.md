<!-- last_verified: 2026-08-05 -->
# Feature: Open3D Processing Pipeline

## Purpose
Turn one or more raw point clouds into a cleaned cloud, a surface mesh, and a
rendered preview — entirely on-device with Open3D (CPU-only, no GPU, no second
API key) — and write every artifact back to Backblaze B2.

## Used By
- UI: `/jobs/[id]` (run + results), `/jobs/new` (configure)
- API: `POST /jobs/{id}/run` (executes the pipeline in a background thread)

## Core Functions
- `services/api/app/service/pipeline.py` — `run_pipeline()`: orchestrates load → downsample → optional register → mesh → preview and returns artifact bytes + metrics
- `services/api/app/service/pointcloud.py` — geometry ops: `load_cloud()` (PLY/PCD native, LAS/LAZ via laspy), `downsample()` (voxel + statistical outlier removal), `register()` (FPFH + RANSAC global, ICP refine), `build_mesh()` (Poisson / ball-pivoting, normal estimation)
- `services/api/app/service/preview.py` — `render_preview()`: headless PNG (matplotlib primary; Open3D `OffscreenRenderer` optional)

## Canonical Files
- Pipeline orchestration: `services/api/app/service/pipeline.py`
- Geometry: `services/api/app/service/pointcloud.py`

## Inputs
- sources: list of `(filename, bytes)` downloaded from B2 `raw/`
- voxel_size: float; meshing_method: `poisson | ball_pivoting`; register: bool (needs ≥ 2 sources)

## Outputs
- `processed.ply` (cleaned/merged cloud), `mesh.ply` (surface mesh), `preview.png`
- `JobMetrics`: source/downsampled points, mesh vertices/triangles, registered flag, run time, and write-amplification bytes

## Flow
- `run_job` downloads each source from B2 and calls `run_pipeline` inside a `ThreadPoolExecutor` bounded by `JOB_RUN_TIMEOUT_SECONDS`
- Each cloud is voxel-downsampled and outlier-filtered
- With registration on and ≥ 2 sources, clouds are aligned (FPFH+RANSAC then ICP) and merged; otherwise concatenated
- Normals are estimated and the mesh is built (Poisson trims low-density hull artifacts; ball-pivoting uses nearest-neighbour radii)
- A preview PNG is rendered headlessly and all three artifacts are `put_object`ed under `jobs/<id>/`

## Render note (headless robustness)
The preview **never hard-fails** on a headless server. matplotlib (`Agg`,
`mpl_toolkits.mplot3d`) is the primary renderer — a mesh `plot_trisurf` when a
mesh exists, else a height-colored point scatter; it subsamples to ≤ 30k
primitives to bound time. An Open3D `OffscreenRenderer` is attempted only when
`ENABLE_OFFSCREEN_RENDER=true`, inside `try/except`, falling back to matplotlib
if the Filament/GL context is unavailable. A `preview.png` is always written.

## Deployment (local hard rule)
Every op here is CPU-bound Open3D **core geometry** (no CUDA/ML path), so no GPU
is required or auto-selected. Open3D's native libraries do **not** run on Vercel
serverless — the API is local/self-hosted (see [ARCHITECTURE.md](../../ARCHITECTURE.md)).

## Edge Cases
- Unreadable / empty cloud → `ValueError`, the job is marked `failed` with the message
- `.laz` without the `lazrs` backend → clear error, job `failed` (degrades, doesn't crash)
- Too-large voxel or aggressive outlier filter → falls back so a run never yields an empty cloud
- Run exceeds `JOB_RUN_TIMEOUT_SECONDS` → job `failed` (the compute finishes in the background, result discarded)

## Verification
- Test files: `services/api/tests/test_pipeline_smoke.py`, `services/api/tests/test_jobs.py`
- Required cases: load+downsample+mesh a synthetic PLY, preview PNG magic bytes, single-scan run, two-scan registration
- Focused verify command: `pnpm test:api` (or `services/api/.venv/bin/python -m pytest tests/test_pipeline_smoke.py`)
- Default pre-PR verify command: `pnpm verify`
- Pass criteria: the smoke tests produce a real mesh (triangles > 0) and a valid PNG

## Related Docs
- [Jobs](jobs.md)
- [Point-Cloud Ingest](point-cloud-ingest.md)
- [ARCHITECTURE.md](../../ARCHITECTURE.md)
