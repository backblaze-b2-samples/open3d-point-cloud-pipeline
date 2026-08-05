<!-- last_verified: 2026-07-28 -->
# App Workflows

User journeys inside the application.

## Ingest Scans

- User navigates to `/scans` (the scoped Library over the `raw/` prefix)
- Drops or selects point-cloud files (PLY / PCD / LAS / LAZ) in the dropzone
- Client filters by extension and size (max 500MB); the API re-validates the extension and the leading bytes (`ply` / `LASF` / PCD header), then stores the scan at `raw/{name}`
- A determinate bar tracks the bytes leaving the browser; once sent, the row switches to "Storing in B2..." with an indeterminate sweeping bar for the server-side phase
- On success the scan appears in the `raw/` list below, with a delete action and a "Create job" shortcut
- The upload queue lives in an app-wide provider, so navigating away keeps it running and the header shows an "Uploading N files" indicator
- No scans yet? Run `services/api/scripts/seed_samples.py` to add synthetic sample clouds
- See: [Point-Cloud Ingest](features/point-cloud-ingest.md)

## Create and Run a Processing Job

- User navigates to `/jobs/new`
- Fills the form: a name, a multi-select of source scans (a selector over the `raw/` set — registration needs ≥ 2), a meshing-method `Select` (Poisson default), a Register switch (enabled only with ≥ 2 scans), and a voxel size (with a safe-default hint)
- Submitting creates the job (`POST /jobs`, status `queued`) and lands on its detail page
- Pressing **Run** starts the Open3D pipeline in the background; the manifest flips `running` and the page polls
- When it finishes, the detail page shows the rendered preview, run metrics (points, mesh triangles, run time), the **write-amplification** ratio, and download links for the processed cloud, mesh, and preview — all served from B2
- **Edit** opens the form pre-filled with the job's real values; **Delete** removes only that job's `jobs/<id>/` prefix after a confirmation; **Re-run** reprocesses
- A failed run shows the error inline instead of hanging
- See: [Jobs](features/jobs.md), [Processing Pipeline](features/processing-pipeline.md)

## Browse and Manage Files

- User navigates to `/files`
- Page loads the 100 most recent objects from the API (sorted most recent first). While it loads, the page says so on screen and escalates the wording if the wait runs long — a full bucket listing measured 2.8s-21s cold
- If that limit was hit, a notice states how many objects the bucket actually holds — the page never claims to show everything
- Files displayed in tree view with folders and type-specific icons
- Folders auto-expand on load until the *majority* of the listed files are reachable without clicking, so the page's own "click a file" instruction is always actionable. Stopping at the first visible file was not enough: one stray top-level object left the other 99 sealed in collapsed folders while the page claimed to show 100
- Clicking a file row opens its preview; the per-row actions menu (preview / download / delete) is always visible, on every viewport
- Arriving at `/files?preview=<key>` expands that file's folders and opens its preview directly. This is how the ⌘K palette and the dashboard's recent-uploads rows hand off a *specific* file; the param is consumed on arrival so it doesn't re-fire later
- **Preview**: opens dialog with image/PDF preview + metadata panel, and the file's Download / Delete actions — the advertised "click a file" path offers everything the row menu does. The loading state holds until the media paints; a failure offers "Open in a new tab". The preview URL is signed with `Content-Disposition: inline` so PDFs render in place
- **Download**: shows a pending state on the row plus a toast while the presigned URL is fetched, then starts the download via an anchor click (which, unlike a popup, still works if the click's user activation expired during a slow presign). Failures are reported; the click can never silently do nothing
- **Delete**: the confirmation dialog stays open showing "Deleting..." until the request settles, then the row disappears with the toast (optimistic cache update) and the list reconciles with the server. The dialog is held deliberately — Radix closes on action click by default, which dismissed the only pending state and left the row looking untouched while the delete was still in flight
- Empty bucket shows a "No files found" message pointing to the Scans library
- This is the bucket-wide view (`raw/` scans and `jobs/` artifacts); for just the source scans, use the Scans library
- See: [Bucket Explorer](features/bucket-explorer.md)

## View Dashboard

- User navigates to `/` (home)
- Parallel queries load: job stats, recent jobs, and bucket activity — job queries poll while any job is active
- While stats load, the page states it in words above the cards rather than showing silent skeletons
- Stat cards show: processing jobs, source data (raw/), artifacts on B2, and the write-amplification multiplier
- The Bucket Activity chart shows objects written to B2 per day (last 7)
- The Recent Jobs table lists the latest jobs with status; each links to its detail page
- Empty state: "No jobs yet" / "No activity yet"
- See: [Dashboard](features/dashboard.md)

## Change Preferences

- User navigates to `/settings`
- A banner at the top states that the page is mostly a demonstration: only Theme is wired up for real, the rest showcases what a settings page can look like when you adapt the kit
- **Theme** (real): editing it and saving applies it immediately and persists it (`next-themes`), and the header's theme toggle drives the same state
- **Profile and preference fields** (demo): Display name, Bio, Default file view (Tree/List/Grid), Email me on every upload, Warn me when approaching quota + threshold. Each is labelled "Demo field", persists to `localStorage` only, and drives no behaviour — there is no account system, mailer, quota banner, activity log, or List/Grid view behind them yet
- Saving reports honestly: a success toast that separates the real theme change from the locally-stored demo values, or a warning toast if the browser blocked storage (theme still changes). It never claims a save that did not happen — the original page toasted "Settings saved" for fields that changed nothing
- Danger Zone actions are a demo — no real delete runs
- See: [Settings](features/settings.md)
