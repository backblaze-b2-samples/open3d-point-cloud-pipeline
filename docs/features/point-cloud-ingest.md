<!-- last_verified: 2026-08-05 -->
# Feature: Point-Cloud Ingest

## Purpose
Upload raw LiDAR / photogrammetry point clouds (PLY, PCD, LAS, LAZ) from the
browser into Backblaze B2 under the `raw/` prefix, so they can be processed into
meshes and previews.

## Used By
- UI: `/scans` page (scoped Library) — ingest form + `raw/` object list
- API: `POST /upload`, `GET /files?prefix=raw/`, `DELETE /files-by-key`

## Core Functions
- `apps/web/src/components/scans/scans-library.tsx` — the scoped Library: reuses the upload form and lists the `raw/` prefix with per-scan delete
- `apps/web/src/components/upload/*` — dropzone / form / progress (reused from the starter, re-scoped to point-cloud types)
- `apps/web/src/lib/upload-file-types.ts` — `POINT_CLOUD_EXTENSIONS`, dropzone allow-list (mirrors the backend)
- `services/api/app/service/upload.py` — `process_upload()`, extension + magic-byte validation, stores under `raw/`
- `services/api/app/repo/b2_client.py` — `upload_file()` via boto3 `put_object`

## Canonical Files
- Service orchestration: `services/api/app/service/upload.py`
- Scoped Library: `apps/web/src/components/scans/scans-library.tsx`

## Inputs
- file: `File` (browser multipart) — a `.ply` / `.pcd` / `.las` / `.laz` cloud

## Outputs
- `FileUploadResponse`: key, filename, size, content_type, uploaded_at, url, metadata
- Side effect: object stored in B2 at `raw/{sanitized_filename}` as `application/octet-stream`

## Flow
- User drops or selects point-cloud files in the dropzone on `/scans`
- Client filters by extension (`.ply/.pcd/.las/.laz`) and 500 MB size; rejected files stay in the queue with a reason
- XHR sends a multipart `POST /upload`; the API rejects oversized bodies early via `Content-Length`
- API sanitizes the filename, validates the **extension** against the point-cloud set, checks the leading bytes (`ply` / `LASF` / PCD header), then `put_object`s to `raw/{name}`
- The Library re-lists `raw/` and the new scan appears

## Edge Cases
- Non-point-cloud extension (e.g. `.txt`, `.png`) → 415
- Bytes don't match the extension (e.g. HTML sent as `.ply`) → 415
- Empty file → 400; oversized (> `MAX_FILE_SIZE`, default 500 MB) → 413
- Duplicate name → B2 versions it (buckets are always versioned)
- Real LiDAR scans are often multi-GB; B2 handles far larger objects. The 500 MB cap only bounds the in-memory API path and is configurable via `MAX_FILE_SIZE`

## UX States
- Empty: dropzone + "No scans ingested yet" (hint to upload or run the seed script)
- Loading: per-file progress, then an indeterminate "Storing in B2..." phase
- Error: per-file reason + retry; Complete: scan appears in the `raw/` list

## Verification
- Test files: `services/api/tests/test_upload_validation.py`, `services/api/tests/test_upload_conflict.py`, `apps/web/src/lib/upload-file-types.test.ts`
- Required cases: valid `.ply` stored under `raw/`, disallowed extension (415), signature mismatch (415), empty (400), oversized (413), frontend/back-end extension mirror
- Focused verify command: `pnpm test:api`
- Default pre-PR verify command: `pnpm verify`
- Pass criteria: focused tests + `pnpm verify` green

## Related Docs
- [Processing Pipeline](processing-pipeline.md)
- [Jobs](jobs.md)
- [Bucket Explorer](bucket-explorer.md)
- [App Workflows](../app-workflows.md)
