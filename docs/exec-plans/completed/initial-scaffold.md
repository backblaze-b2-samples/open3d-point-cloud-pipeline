# Build plan — `open3d-point-cloud-pipeline`

Source of truth for the starter tree: `.claude/scratch/vcsk-ee0757c6-5243-4ae0-b715-fe1eb52300fe/`
(freshly cloned `vibe-coding-starter-kit`). Compute every delta against that tree only.

---

## 1. Purpose

`open3d-point-cloud-pipeline` is a B2-backed 3D point-cloud processing pipeline for 3D-scanning
engineers, AEC/BIM professionals, and robotics/AV perception teams. Users ingest raw LiDAR or
photogrammetry point clouds (PLY / PCD / LAS / LAZ) into Backblaze B2, then run an **Open3D**
pipeline — downsample → optional multi-scan registration → surface meshing → offscreen preview
render — and every artifact (processed cloud, mesh, preview PNG, job manifest) is written back to
B2. It demonstrates B2 as the storage layer for the **largest single artifacts** in a 3D workflow,
where one source cloud fans out into several derived objects — heavy, structured **write-amplification**.
It runs entirely on local OSS: **no second API key, B2 credentials only**. All processing is
on-device (`deployment: local`), CPU by default.

---

## 2. Architecture delta from vibe-coding-starter-kit

### KEEP (as-is or lightly adapted)
- **Monorepo shape:** `apps/web` (Next 15 + shadcn/ui) + `services/api` (FastAPI) + `packages/shared` + `pnpm` workspace. Keep all scripts (`scripts/*.mjs`, `scripts/dev.sh`), CI, pre-commit, tsconfig, eslint, vitest, playwright config.
- **B2 repo layer** `services/api/app/repo/b2_client.py` — single cached boto3 S3 client, list cache, presigned URLs, upload/delete/head. Reuse wholesale; only rename env fields + user-agent (see §6) and add the small artifact/manifest helpers the pipeline needs.
- **Full-bucket explorer** `/files` (`components/files/*`, `runtime/files.py` by-key + path routes). **NON-NEGOTIABLE KEEP** — the bucket-wide browser stays. No tension here; it coexists with the scoped Library (added below).
- **Dashboard shell** (`app/page.tsx`, `components/dashboard/*`, `stats-cards`, `upload-chart`, `recent-uploads-table`) — reused, re-pointed at job/storage metrics.
- **Design system** (`/design`, `components/ui/*`, `components/design/*`, `globals.css`), **Settings** showcase (`/settings`, `settings-form.tsx` — our form exemplar), layout (`app-sidebar`, `header`, `theme-provider`, `command-palette`, `health-banner`), all `lib/*` utilities and tests, `query-client`, `refresh-context`, `upload-queue-context`.
- **Upload internals** — `components/upload/dropzone.tsx`, `upload-form.tsx`, `upload-progress.tsx`, `runtime/upload.py`, `service/upload.py` streaming + size guard. Reused, folded into the Library page (§4) and re-scoped to point-cloud file types.
- **Reliability/security posture** — sync `def` B2 handlers (Starlette threadpool), rate-limit + timing + CORS middleware ordering, structured JSON logging, single-tenant SECURITY stance. Keep, extend to the new routes.

### TRIM (remove from starter)
- **Standalone `/upload` route** (`app/upload/page.tsx`) — ingest is folded into the scoped Library `/scans`; the dropzone/progress *components* are reused there. Remove the sidebar/`pageTitles`/command-palette entries for `/upload`.
- **Image/PDF metadata extraction** — drop `PyPDF2` and the PDF branch in `service/metadata.py`; keep the generic checksum + size detail path (still powers the `/files` explorer detail panel) and keep `Pillow` (used for preview PNG handling). *(Trim is nice-to-have; if it risks breaking `test_file_detail`/`test_metadata_warning`, leave `metadata.py` intact — do not spend loop rounds here.)*
- Starter marketing copy in `README.md`, `PRODUCT.md`, `ARCHITECTURE.md` — rewritten for this sample.

### ADD (new for `open3d-point-cloud-pipeline`)
- **Open3D pipeline engine** — `services/api/app/service/pipeline.py` (+ helpers): load cloud (PLY/PCD native via Open3D; LAS/LAZ via `laspy` → Open3D), voxel downsample + statistical outlier removal, optional RANSAC(FPFH)+ICP registration of ≥2 clouds, Poisson / ball-pivoting meshing with normal estimation, and a **preview renderer** (see §4 render note).
- **Job domain** — `services/api/app/service/jobs.py` + `app/repo/jobs_store.py`: the primary entity `Job`, persisted as a JSON manifest in B2 at `jobs/<job_id>/job.json`; artifacts at `jobs/<job_id>/{processed.ply,mesh.ply,preview.png}`. CRUD + run.
- **Jobs router** — `services/api/app/runtime/jobs.py`: `GET /jobs`, `POST /jobs`, `GET /jobs/{id}`, `PATCH /jobs/{id}`, `DELETE /jobs/{id}`, `POST /jobs/{id}/run`. Run executes the pipeline in a background thread; manifest status flips `queued→running→done|failed`; frontend polls.
- **Scoped Library** `/scans` — sample-specific asset explorer scoped to the `raw/` prefix (the ingested scans), with a point-cloud-typed upload. Satisfies the "add a scoped explorer alongside the full-bucket explorer" rule.
- **Jobs pages** — `/jobs` (list w/ status + preview thumbnails), `/jobs/new` (create form), `/jobs/[id]` (detail/read + run/edit/delete actions), `/jobs/[id]/edit` (pre-filled edit form).
- **Seed script** — `services/api/scripts/seed_samples.py`: generate small **synthetic** clouds with Open3D (no downloads, license-clean) and upload to B2 `raw/`. Produces at least (a) one full-object cloud (sphere/torus sampled via `sample_points_poisson_disk`, + light Gaussian noise) for the single-scan mesh demo, and (b) an overlapping partial-scan pair (known rigid transform + crop) for the registration demo. Keep each ≤ ~50k points so a run finishes in seconds.
- **B2 layout constants** — `raw/` (ingested scans), `jobs/<id>/` (manifest + artifacts).

---

## 3. B2 surface (S3-compatible only — no b2-native)

| Operation | S3 API | Used by |
|---|---|---|
| Upload raw scan, write processed cloud / mesh / preview / manifest | `put_object` | ingest, pipeline artifact writes, manifest persistence |
| Download source cloud for processing; serve artifacts | `get_object` + `generate_presigned_url` (GET) | pipeline load, job-detail downloads/preview |
| List `raw/`, `jobs/`, whole bucket | `list_objects_v2` (paginated, cached) | Library, jobs list, dashboard stats, `/files` explorer |
| Object metadata | `head_object` | detail panels, existence checks |
| Delete raw scan / job artifacts | `delete_object` | scan delete, job delete (scoped to `jobs/<id>/` prefix) |
| Health | `head_bucket` | `/health` |

All via one boto3 client with `signature_version="s3v4"` and a custom `user_agent_extra` (§6). **No b2-native API anywhere.** Deletes are prefix-scoped to the job's own `jobs/<id>/` — never bucket-wide.

---

## 4. Key features

> **External API provider: NONE.** Open3D runs on-device; the only credentials are `B2_*`.
> Every feature is `deployment: local`. Per `api-provider-selection.md` the local hard rule
> (CPU default, GPU auto-detect CUDA→MPS→CPU) applies — but Open3D **core geometry ops used here
> (voxel downsample, outlier removal, FPFH/RANSAC/ICP, Poisson/ball-pivoting, normal estimation)
> are CPU-bound and need no GPU**; the Open3D CUDA/ML path is not used. No GPU is required and none
> is auto-selected. Est. cost per full demo run: **$0** (local compute + B2 storage/egress only).
> Not routed through Genblaze — the description names no Genblaze/`genblaze-*` stack.

1. **Ingest point clouds to B2** *(local)* — upload PLY / PCD / LAS / LAZ raw scans; scoped Library view of the `raw/` prefix. → `docs/features/point-cloud-ingest.md`
2. **Open3D processing pipeline** *(local, CPU)* — downsample (voxel + statistical outlier removal) → optional multi-scan registration (FPFH+RANSAC global, ICP refine) → surface meshing (Poisson / ball-pivoting) → offscreen preview render. → `docs/features/processing-pipeline.md`
3. **Job lifecycle management** *(local)* — create / read / edit / delete / run processing jobs; job metadata persisted as JSON manifests **in B2** (no database). → `docs/features/jobs.md`
4. **Write-amplified B2 storage** *(local)* — one source cloud → processed cloud + mesh + preview, all written back to B2; the dashboard surfaces total bytes written, artifact count, and the source→artifact **write-amplification ratio**. → covered in `docs/features/dashboard.md`
5. **Rendered previews served from B2** *(local)* — preview PNGs stored in and served from B2 via presigned/public URLs; rendered on the jobs list (thumbnail) and job detail. → part of `processing-pipeline.md`
6. **Full-bucket explorer** *(local)* — the starter's bucket-wide browser retained alongside the scoped Library, for raw storage inspection. → `docs/features/bucket-explorer.md` (renamed from `file-browser.md`)

**Render note (build-critical robustness).** The preview render must NEVER hard-fail headless.
**Primary renderer = matplotlib** (`mpl_toolkits.mplot3d`): mesh `plot_trisurf` when a mesh exists,
else a point-cloud scatter colored by height/depth — pure CPU, deterministic, always produces a PNG.
Subsample to ≤ ~30k points/faces before rendering to bound time. **Optional higher-fidelity path:**
`o3d.visualization.rendering.OffscreenRenderer`, attempted inside `try/except` and falling back to
matplotlib if the Filament/GL context fails to initialize. A `preview.png` is always written to B2.

### Primary-entity lifecycle — entity: **Job**
DEFAULT: the UI exposes ALL lifecycle verbs, and Phase 2 builds them.

| Verb | UI surface | Built? |
|---|---|---|
| create | `/jobs/new` form → `POST /jobs` | ✅ |
| read | `/jobs` list + `/jobs/[id]` detail | ✅ |
| edit | `/jobs/[id]/edit` (pre-filled) → `PATCH /jobs/{id}` | ✅ |
| delete | button on detail + list → `DELETE /jobs/{id}` (prefix-scoped) | ✅ |
| run | run / re-run button → `POST /jobs/{id}/run` | ✅ |

All five verbs are built → `omitted_ui_verbs` is empty. The raw **scan** is a *secondary* entity
(create=upload, read=Library/preview, delete=remove); it has no edit/run because a raw scan is an
immutable source file — no justification entry needed since it is not the primary entity.

### Form UX conventions
Create-job form (`/jobs/new`):
- **name** — free text; placeholder hint e.g. `"e.g. Warehouse scan — east wing"`.
- **source scans** — selector over the finite set of `raw/` clouds (multi-select checkbox list / combobox), never free text. Registration needs ≥2; single selection runs the single-scan path.
- **meshing method** — `Select` (`poisson` | `ball_pivoting`), default `poisson`. Finite → selector.
- **register** — `Switch`/`RadioGroup` (on/off), default off; only effective with ≥2 sources (disable/hint otherwise). Finite → selector.
- **voxel size** — number input; safe default surfaced via `FormDescription` (e.g. `"0.02 — leave the default for the sample scans"`). Guidance only, **no autofill button**.

Edit form (`/jobs/[id]/edit`) opens **pre-filled** with the job's real values; same selector rules,
no default hints. Model both on `apps/web/src/components/settings/settings-form.tsx`.

---

## 5. Doc transforms

- **Rewrite:** `docs/features/dashboard.md` (job + storage/write-amplification metrics); `docs/features/file-browser.md` → **rename** `bucket-explorer.md`.
- **Repurpose:** `docs/features/file-upload.md` → `point-cloud-ingest.md`.
- **Delete or rewrite:** `docs/features/metadata-extraction.md` — delete if the metadata trim (§2) is done; otherwise leave a short generic-metadata note. Don't loop on it.
- **New stubs (from `docs/features/_template.md`):** `processing-pipeline.md`, `jobs.md`.
- **Top-level:** rewrite `README.md`, `PRODUCT.md`, `ARCHITECTURE.md`, `docs/app-workflows.md` for the point-cloud pipeline. **README ordering (humans first):** title + one-line what-it-is → quick start (install, fill `.env`, `seed_samples.py`, run demo) → screenshots placeholder → features → B2 role / write-amplification → architecture → a **FAQ / When-to-use** block (keep question-shaped content). Note the local/self-hosted API caveat (see §7).

---

## 6. Rename table

| Kind | From (starter) | To |
|---|---|---|
| Repo / dir | `vibe-coding-starter-kit` | `open3d-point-cloud-pipeline` |
| `APP_NAME` (`lib/app-config.ts`) | `"OSS Starter Kit"` | `"Open3D Point Cloud Pipeline"` |
| `APP_DESCRIPTION` | `"File management dashboard powered by Backblaze B2"` | `"Process LiDAR & photogrammetry point clouds with Open3D, stored on Backblaze B2"` |
| FastAPI `title` (`main.py`) | `"OSS Starter Kit API"` | `"Open3D Point Cloud Pipeline API"` |
| `user_agent_extra` (`b2_client.py`) | `"b2ai-oss-start"` | `"open3d-point-cloud-pipeline"` |
| UTM `utm_content` (`app-sidebar.tsx` footer) | `b2ai-oss-start` | `open3d-point-cloud-pipeline` |
| `package.json` `name` (root, `apps/web`, `packages/shared`) | `*starter-kit*` | `open3d-point-cloud-pipeline` (+ `-web`, `-shared`) |
| Header `pageTitles` map + sidebar `navItems` | Upload/Files entries | Scans, Jobs, Files (drop Upload) |
| CI / railway / vercel names, image tags | `*starter*` | `open3d-point-cloud-pipeline` |

**Env var rename → parent CLAUDE.md Standard #3** (the starter deviates; b2-doctor is stale on the starter). Rename across `settings.py`, `main.py` (REQUIRED_B2_SETTINGS + PLACEHOLDER_VALUES), `.env.example`, `tests/conftest.py`, `scripts/doctor.mjs`, `scripts/setup.mjs`, README/docs — grep the whole tree for each old name:

| Old (starter) | New (Standard #3) |
|---|---|
| `B2_KEY_ID` / `b2_key_id` | `B2_APPLICATION_KEY_ID` / `b2_application_key_id` |
| `B2_APPLICATION_KEY` | `B2_APPLICATION_KEY` (unchanged) |
| `B2_BUCKET_NAME` | `B2_BUCKET_NAME` (unchanged) |
| `B2_ENDPOINT` / `b2_endpoint` | `B2_REGION` / `b2_region` (default `us-west-004`); endpoint **derived** `https://s3.{region}.backblazeb2.com` via a `Settings.endpoint_url` property. Keep an optional, empty-by-default `B2_ENDPOINT` advanced override. |
| `B2_PUBLIC_URL` / `b2_public_url` | `B2_PUBLIC_URL_BASE` / `b2_public_url_base` |

---

## 7. Build-critical constraints & known gotchas (heed these)

1. **Python is 3.12 (`services/api/.python-version`).** Open3D 0.18 has **no cp312 wheel** → pin **`open3d>=0.19.0`** (0.19 ships macOS-arm64 + cp312 wheels and supports numpy 2). If 0.19 fails to import on the local arm64/py3.12 env, fall back to pinning `.python-version` = `3.11` + `open3d>=0.18,<0.19`. **Verify a clean install actually imports and runs** (unpinned/ill-matched ML deps are a classic false-green): after install, run a smoke that does `import open3d; read a tiny ply; voxel_down_sample; estimate_normals; create_from_point_cloud_poisson; matplotlib render → PNG`.
2. **Requirements** (`services/api/requirements.txt`, lower-bound `>=` pins; then regenerate `requirements.lock` per `docs/dev-workflows.md`): add `open3d>=0.19.0`, `laspy[lazrs]>=2.5.0` (LAZ needs the `lazrs` backend; degrade gracefully if a `.laz` can't be read), `matplotlib>=3.8.0`, `numpy` (let Open3D resolve; do **not** hard-cap unless a conflict forces it). Keep `Pillow`. Remove `PyPDF2` only if the metadata trim is done.
3. **`test_dependency_lock.py`** enforces `requirements.txt` ⊆ lock and `>=`-only pins — keep both in sync or that test fails.
4. **Header branding leak is already fixed** in this starter (`header.tsx` uses `APP_NAME` + `pageTitles` + `deriveTitleFromPath`; `app-config.ts` centralizes identity). Just update `APP_NAME`/`APP_DESCRIPTION`, the `pageTitles` map, and sidebar `navItems`.
5. **Point-cloud file types** — update `apps/web/src/lib/upload-file-types.ts` and backend `ALLOWED_TYPES`/`MIME_EXTENSION_MAP` in `service/upload.py` to `.ply/.pcd/.las/.laz` (mostly `application/octet-stream`; validate by extension server-side). Keep both in sync (a test/comment enforces the mirror).
6. **Upload size** — bump `Settings.max_file_size` default (e.g. 500 MB) and document that real LiDAR clouds are far larger and that B2 handles multi-GB objects; the demo cap is configurable. Seed clouds stay small.
7. **Deploy honesty** — Open3D (native libs) will **not** run on Vercel serverless. Treat the API as **local/self-hosted** (like other native-ML samples here); the Next frontend may still deploy to Vercel pointing at a self-hosted API. Don't claim the heavy API deploys to Vercel; adjust `infra/` + README accordingly, keep it honest.
8. **Job durability** — in-process background-thread execution: on process restart an in-flight job's manifest could stay `running`. Acceptable for a demo (document it, like the starter documents its in-process rate-limit). Add a hard per-run timeout guard so a job can't hang forever.
9. **Finish order (avoid build-timeout leaving tail phases undone):** (1) backend pipeline + jobs + B2 wiring + env rename; (2) frontend — all pages functional end-to-end; (3) docs/theming/README. Before returning, **`pnpm lint`, `pnpm build`, and `pytest` must all pass**, and the Open3D smoke (constraint 1) must succeed.

---

## 8. Success = reviewer-clean

No `❌` from `sample-reviewer` against this plan + `../CLAUDE.md` (S3-only default, custom user-agent
on every client, standardized `B2_*` names), primary-entity CRUD+run all present, both the full-bucket
explorer and the scoped Library present, forms follow the selector + default-hint conventions, and a
clean install passes lint/build/pytest + the Open3D smoke.
