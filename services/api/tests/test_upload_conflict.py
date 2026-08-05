"""Unit tests for upload filename handling (point-cloud ingest)."""

from app.service import upload as upload_service
from app.types import FileUploadResponse

# A minimal ASCII PLY header — enough to pass the point-cloud signature check.
_PLY = b"ply\nformat ascii 1.0\nelement vertex 0\nend_header\n"


def _echo_upload(file_data, key, content_type):
    return FileUploadResponse(
        key=key,
        filename="scan.ply",
        size_bytes=len(file_data),
        size_human="48 B",
        content_type=content_type,
        uploaded_at="2026-02-14T00:00:00Z",
        url=None,
        metadata=None,
    )


def test_upload_allows_duplicate_filename(monkeypatch):
    """B2 is always versioned — re-uploading the same name creates a new version."""
    monkeypatch.setattr(upload_service, "upload_file", _echo_upload)
    monkeypatch.setattr(
        upload_service,
        "extract_metadata",
        lambda file_data, filename, content_type, uploaded_at=None: None,
    )

    result = upload_service.process_upload(
        file_data=_PLY,
        filename="scan.ply",
        content_type="application/octet-stream",
        content_length=len(_PLY),
    )

    assert result.key == "raw/scan.ply"


def test_upload_stores_raw_scan_under_raw_prefix(monkeypatch):
    monkeypatch.setattr(upload_service, "upload_file", _echo_upload)
    monkeypatch.setattr(
        upload_service,
        "extract_metadata",
        lambda file_data, filename, content_type, uploaded_at=None: None,
    )

    result = upload_service.process_upload(
        file_data=_PLY,
        filename="warehouse-east.ply",
        content_type="application/octet-stream",
        content_length=len(_PLY),
    )

    assert result.key == "raw/warehouse-east.ply"
