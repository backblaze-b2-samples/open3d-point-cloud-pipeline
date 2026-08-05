from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Backblaze B2 (S3-compatible). Env var names follow the standardized B2_*
    # contract: B2_APPLICATION_KEY_ID / B2_APPLICATION_KEY / B2_BUCKET_NAME /
    # B2_REGION / B2_PUBLIC_URL_BASE.
    b2_application_key_id: str = ""
    b2_application_key: str = ""
    b2_bucket_name: str = ""
    # Region selects the S3 endpoint. B2's S3 endpoint is
    # https://s3.<region>.backblazeb2.com — derived via the endpoint_url
    # property below, so no region string is hardcoded here. Required at runtime;
    # set B2_REGION in .env (see .env.example, e.g. us-west-004 / us-east-005).
    b2_region: str = ""
    # Advanced override: set B2_ENDPOINT only to target a non-standard or
    # S3-proxy endpoint. Empty by default so the endpoint is derived from
    # b2_region.
    b2_endpoint: str = ""
    # Optional public base URL for public buckets — builds direct object URLs
    # (e.g. preview PNGs). The app runs fine without it (falls back to presigned
    # URLs), so it is functionally optional.
    b2_public_url_base: str = ""

    api_port: int = 8000
    # Interactive API docs (/docs, /redoc, /openapi.json). On by default for
    # local dev and starter-kit exploration; set false to hide the full API
    # surface in production.
    enable_docs: bool = True
    # Explicit allowlist by default — covers Next on :3000 and the
    # fallback :3001 it picks if 3000 is busy. Production deploys should
    # override with the exact frontend origin.
    api_cors_origins: str = "http://localhost:3000,http://localhost:3001"
    # Optional dev-only escape hatch: a regex that matches additional
    # allowed origins. Empty by default — set this to e.g.
    # `^http://localhost:\d+$` to accept any localhost port without
    # listing each one. NEVER ship this to production.
    api_cors_origin_regex: str = ""

    # Upload limits. Real LiDAR / photogrammetry clouds are routinely multi-GB
    # and B2 handles objects far larger than this — the cap only bounds what the
    # in-memory API upload path buffers. Raise MAX_FILE_SIZE for bigger source
    # scans; the seed clouds stay small (a few MB).
    max_file_size: int = 500 * 1024 * 1024  # 500MB

    # Hard per-run ceiling for a processing job (seconds). A job that exceeds it
    # is marked failed rather than pinning a worker thread forever. Generous for
    # the small seed clouds; raise it for very large real-world scans.
    job_run_timeout_seconds: float = 600.0

    # Preview rendering. matplotlib (Agg) is always the primary, headless-safe
    # renderer. Set true to ALSO attempt an Open3D OffscreenRenderer first for a
    # higher-fidelity thumbnail — it needs a working Filament/GL context and
    # falls back to matplotlib automatically when one is unavailable (e.g. a
    # headless server), so leaving it off is the safe default.
    enable_offscreen_render: bool = False

    # Optional confinement for key-addressed reads/deletes. Empty by default so
    # the by-key routes accept any key shape (they deliberately support nested
    # folders and reserved-word segments). Point a fork at a bucket shared with
    # other data? Set to e.g. "uploads/" to restrict all key ops to app uploads.
    allowed_key_prefix: str = ""

    # Full-bucket listing cache (repo/list_cache.py). Both /files and
    # /files/stats need every object, and paginating a 16k-object bucket takes
    # ~8-20s, so one scan is shared. Entries older than the TTL are still
    # served *immediately* while a background thread refreshes them
    # (stale-while-revalidate), so only the very first scan can make a user
    # wait. Uploads and deletes invalidate the cache outright, so the app's own
    # writes are never served stale — only bucket changes made elsewhere can lag
    # by up to this TTL.
    list_cache_ttl_seconds: float = 300.0
    # Scan the bucket once at startup so the first page view doesn't pay for the
    # cold scan. Set false for offline dev or when startup must not touch B2.
    warm_list_cache_on_startup: bool = True

    # Rate limiting (per client IP, per 60s window). In-process per replica —
    # documented in docs/RELIABILITY.md; horizontal scaling needs a shared
    # store (e.g. Redis). Writes/downloads get the tighter cap.
    rate_limit_per_minute: int = 120
    # Covers uploads, deletes, downloads and previews — kept generous enough
    # that a normal browsing/upload session doesn't trip it.
    rate_limit_write_per_minute: int = 60

    # Small durable counters (downloads, etc). Relative paths resolve against
    # the repo root (see repo/counter.py). Point at a persistent volume in
    # production if you care about surviving restarts.
    #
    # It must stay OUTSIDE services/api/: that is the directory `uvicorn
    # --reload` watches in dev, so a counter file there means every download
    # writes into the reloader's watch tree. Today uvicorn only restarts for
    # `*.py`, so the writes surface as misleading "N changes detected" log noise
    # on every download — but a single added `--reload-include` would turn a
    # normal user action into an API restart that drops in-flight requests.
    download_count_file: str = ".data/download_count.json"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def endpoint_url(self) -> str:
        """S3 endpoint for the configured region.

        Derives ``https://s3.<region>.backblazeb2.com`` from ``b2_region`` so no
        region string is hardcoded. ``b2_endpoint`` (empty by default) is an
        advanced override for non-standard endpoints.
        """
        return self.b2_endpoint or f"https://s3.{self.b2_region}.backblazeb2.com"

    @property
    def cors_origins(self) -> list[str]:
        # Drop empties so a trailing comma or API_CORS_ORIGINS="" doesn't yield
        # a stray "" origin.
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]


settings = Settings()
