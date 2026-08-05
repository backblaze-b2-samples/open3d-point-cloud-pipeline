"""Unit + integration tests for point-cloud upload validation."""

import pytest

from app.service import upload as upload_service
from app.service.upload import (
    POINT_CLOUD_EXTENSIONS,
    UploadError,
    file_extension,
    is_allowed_extension,
    matches_point_cloud_signature,
    process_upload,
    sanitize_filename,
)
from app.types import FileUploadResponse

# --- sanitize_filename ------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd", "passwd"),  # path components stripped
        ("a\x00b.ply", "ab.ply"),  # null byte removed
        ("my scan.ply", "my_scan.ply"),  # unsafe char substituted
        ("...hidden", "_hidden"),  # dot run collapses to _ before dot-strip
        ("", "unnamed"),  # empty → placeholder
        ("/", "unnamed"),  # only a path separator → placeholder
    ],
)
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "a" * 300 + ".ply",  # long name with extension
        "a" * 300,  # long name, NO extension
        "a" * 300 + "." + "b" * 250,  # absurdly long extension
    ],
)
def test_sanitize_filename_truncates_long_names(raw):
    result = sanitize_filename(raw)
    assert len(result) <= 200
    assert not result.startswith(".")


# --- extension gate ---------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("scan.ply", "ply"),
        ("cloud.PCD", "pcd"),
        ("lidar.las", "las"),
        ("lidar.laz", "laz"),
        ("noext", ""),
    ],
)
def test_file_extension(filename, expected):
    assert file_extension(filename) == expected


def test_allowed_extensions_cover_the_point_cloud_set():
    assert set(POINT_CLOUD_EXTENSIONS) == {"ply", "pcd", "las", "laz"}
    for ext in POINT_CLOUD_EXTENSIONS:
        assert is_allowed_extension(ext)
    assert not is_allowed_extension("png")
    assert not is_allowed_extension("txt")


# --- magic-byte signatures --------------------------------------------------

_PLY = b"ply\nformat binary_little_endian 1.0\n"
_LAS = b"LASF" + b"\x00" * 20
_PCD = b"# .PCD v0.7 - Point Cloud Data file format\nVERSION 0.7\n"


@pytest.mark.parametrize(
    ("data", "ext", "expected"),
    [
        (_PLY, "ply", True),
        (b"<html>not a ply", "ply", False),
        (_LAS, "las", True),
        (_LAS, "laz", True),  # LAZ keeps the LASF header
        (b"nope", "las", False),
        (_PCD, "pcd", True),
        (b"random bytes with no header", "pcd", False),
    ],
)
def test_matches_point_cloud_signature(data, ext, expected):
    assert matches_point_cloud_signature(data, ext) is expected


# --- process_upload rejection matrix ----------------------------------------


def test_rejects_oversized_content_length(monkeypatch):
    monkeypatch.setattr(upload_service.settings, "max_file_size", 10)
    with pytest.raises(UploadError) as exc:
        process_upload(_PLY, "scan.ply", "application/octet-stream", content_length=999)
    assert exc.value.status_code == 413


def test_rejects_disallowed_extension():
    with pytest.raises(UploadError) as exc:
        process_upload(b"data", "notes.txt", "text/plain", content_length=4)
    assert exc.value.status_code == 415


def test_rejects_signature_mismatch():
    # .ply name and octet-stream, but the bytes are not a PLY.
    with pytest.raises(UploadError) as exc:
        process_upload(b"not a real ply", "scan.ply", "application/octet-stream", content_length=14)
    assert exc.value.status_code == 415


def test_rejects_empty_file():
    with pytest.raises(UploadError):
        process_upload(b"", "scan.ply", "application/octet-stream", content_length=0)


def test_accepts_valid_point_cloud(monkeypatch):
    monkeypatch.setattr(
        upload_service,
        "upload_file",
        lambda file_data, key, content_type: FileUploadResponse(
            key=key,
            filename="scan.ply",
            size_bytes=len(file_data),
            size_human="35 B",
            content_type=content_type,
            uploaded_at="2026-02-14T00:00:00Z",
            url=None,
            metadata=None,
        ),
    )
    monkeypatch.setattr(
        upload_service,
        "extract_metadata",
        lambda file_data, filename, content_type, uploaded_at=None: None,
    )
    result = process_upload(_PLY, "scan.ply", "application/octet-stream", content_length=len(_PLY))
    assert result.key == "raw/scan.ply"
    assert result.content_type == "application/octet-stream"


# --- uploads_total metric increments ----------------------------------------


@pytest.mark.asyncio
async def test_successful_upload_increments_uploads_metric(client, monkeypatch):
    from app.runtime import metrics

    monkeypatch.setattr(metrics, "_upload_count", 0)
    monkeypatch.setattr(
        upload_service,
        "upload_file",
        lambda file_data, key, content_type: FileUploadResponse(
            key=key,
            filename="scan.ply",
            size_bytes=len(file_data),
            size_human="35 B",
            content_type=content_type,
            uploaded_at="2026-02-14T00:00:00Z",
            url=None,
            metadata=None,
        ),
    )
    monkeypatch.setattr(
        upload_service,
        "extract_metadata",
        lambda file_data, filename, content_type, uploaded_at=None: None,
    )

    resp = await client.post(
        "/upload", files={"file": ("scan.ply", _PLY, "application/octet-stream")}
    )
    assert resp.status_code == 200

    metrics_resp = await client.get("/metrics")
    assert "uploads_total 1" in metrics_resp.text
