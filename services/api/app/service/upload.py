import re

from app.config import settings
from app.repo import upload_file
from app.service.metadata import extract_metadata
from app.types import FileUploadResponse
from app.types.formatting import humanize_bytes

# Point-cloud ingest. Browsers send `application/octet-stream` for these binary
# formats (no registered MIME type), so the declared content type is untrusted
# and we gate on the file EXTENSION plus a light per-format magic-byte check.
# Keep this set in lockstep with the frontend dropzone allow-list in
# apps/web/src/lib/upload-file-types.ts (a test on each side enforces the mirror).
POINT_CLOUD_EXTENSIONS: tuple[str, ...] = ("ply", "pcd", "las", "laz")

# Canonical stored content type: these formats have no standard MIME type and
# the client value is untrusted, so every ingested scan is stored as a generic
# binary object. Downloads still work; the extension carries the real format.
POINT_CLOUD_CONTENT_TYPE = "application/octet-stream"

# Raw scans land under this prefix — the scoped Library (/scans) is this prefix.
RAW_PREFIX = "raw/"


def file_extension(filename: str) -> str:
    """Lower-cased extension without the dot, or '' when there is none."""
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def is_allowed_extension(ext: str) -> bool:
    return ext in POINT_CLOUD_EXTENSIONS


def matches_point_cloud_signature(data: bytes, ext: str) -> bool:
    """Light magic-byte check that ``data`` looks like a ``ext`` point cloud.

    PLY files begin with ``ply``; LAS/LAZ begin with the ``LASF`` magic (LAZ is
    laszip-compressed LAS and keeps the same header). PCD has an ASCII header
    but no single-byte magic, so it is checked leniently. An unknown extension
    returns True (the extension gate already rejected non-point-cloud files).
    """
    if ext == "ply":
        return data[:3].lower() == b"ply"
    if ext in ("las", "laz"):
        return data[:4] == b"LASF"
    if ext == "pcd":
        head = data[:200]
        return (
            head[:1] == b"#"
            or head[:7] == b"VERSION"
            or b".PCD" in head
            or b"FIELDS" in head
        )
    return True


_SAFE_FILENAME_RE = re.compile(r"[^\w\-.]")


def sanitize_filename(filename: str) -> str:
    """Sanitize filename: strip path components, remove unsafe chars, limit length."""
    name = filename.replace("\\", "/").split("/")[-1]
    name = name.replace("\x00", "")
    name = _SAFE_FILENAME_RE.sub("_", name)
    name = re.sub(r"[_.]{2,}", "_", name)
    name = name.lstrip(".").strip()
    if len(name) > 200:
        base, sep, ext = name.rpartition(".")
        # Preserve the extension only when there is one that still fits;
        # otherwise (no dot, or an absurdly long "extension") hard-truncate.
        # `rpartition` returns ("", "", name) when there is no dot, so guard on
        # `sep`, not `ext` — else an extensionless name keeps its whole body.
        name = (
            base[: 200 - len(ext) - 1] + "." + ext
            if sep and len(ext) < 200
            else name[:200]
        )
    return name or "unnamed"


class UploadError(Exception):
    """Raised when upload validation fails."""

    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def process_upload(
    file_data: bytes,
    filename: str,
    content_type: str,
    content_length: int | None = None,
) -> FileUploadResponse:
    """Validate and store a point-cloud upload as a raw scan. Raises UploadError."""
    if not filename:
        raise UploadError("No filename provided")

    if content_length and content_length > settings.max_file_size:
        raise UploadError(
            f"File too large. Max size: {humanize_bytes(settings.max_file_size)}",
            status_code=413,
        )

    safe_name = sanitize_filename(filename)
    ext = file_extension(safe_name)
    if not is_allowed_extension(ext):
        raise UploadError(
            "Unsupported file type. Upload a point cloud: "
            f"{', '.join('.' + e for e in POINT_CLOUD_EXTENSIONS)}",
            status_code=415,
        )

    if len(file_data) == 0:
        raise UploadError("Empty file")

    if not matches_point_cloud_signature(file_data, ext):
        raise UploadError(
            f"File contents do not look like a valid .{ext} point cloud",
            status_code=415,
        )

    if len(file_data) > settings.max_file_size:
        raise UploadError(
            f"File too large. Max size: {humanize_bytes(settings.max_file_size)}",
            status_code=413,
        )

    # B2 buckets are always versioned — re-uploading the same key adds a new
    # version automatically, so no duplicate rejection is needed.
    key = f"{RAW_PREFIX}{safe_name}"
    result = upload_file(file_data, key, POINT_CLOUD_CONTENT_TYPE)
    metadata = extract_metadata(
        file_data, safe_name, POINT_CLOUD_CONTENT_TYPE, result.uploaded_at
    )

    return FileUploadResponse(
        key=result.key,
        filename=result.filename,
        size_bytes=result.size_bytes,
        size_human=result.size_human,
        content_type=POINT_CLOUD_CONTENT_TYPE,
        uploaded_at=result.uploaded_at,
        url=result.url,
        metadata=metadata,
    )
