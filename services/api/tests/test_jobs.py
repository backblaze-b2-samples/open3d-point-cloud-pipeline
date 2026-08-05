"""Job lifecycle tests with an in-memory stand-in for B2 object storage.

The Open3D pipeline itself is faked here (a fast stub) so these stay unit-fast;
the real geometry pipeline is exercised end-to-end in test_pipeline_smoke.py.
"""

import time

import pytest

from app.repo import artifacts
from app.service import jobs as jobs_service
from app.service.jobs import (
    JobConflictError,
    JobNotFoundError,
)
from app.service.pipeline import PipelineResult
from app.types import JobCreate, JobUpdate
from app.types.jobs import JobMetrics


@pytest.fixture
def mem_store(monkeypatch):
    store: dict[str, bytes] = {}

    def put_bytes(key, data, content_type):
        store[key] = data
        return len(data)

    def get_bytes(key):
        return store.get(key)

    def list_under(prefix):
        return [
            {"Key": k, "Size": len(v)} for k, v in store.items() if k.startswith(prefix)
        ]

    def delete_under(prefix):
        keys = [k for k in store if k.startswith(prefix)]
        for k in keys:
            del store[k]
        return len(keys)

    monkeypatch.setattr(artifacts, "put_bytes", put_bytes)
    monkeypatch.setattr(artifacts, "get_bytes", get_bytes)
    monkeypatch.setattr(artifacts, "list_under", list_under)
    monkeypatch.setattr(artifacts, "delete_under", delete_under)
    return store


def _fake_pipeline_result():
    return PipelineResult(
        processed_ply=b"PROCESSED",
        mesh_ply=b"MESH-BYTES",
        preview_png=b"PNGDATA",
        metrics=JobMetrics(
            source_points=100,
            downsampled_points=90,
            mesh_vertices=10,
            mesh_triangles=20,
        ),
    )


def _wait_for_status(job_id, status, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = jobs_service.get_job(job_id)
        if job.status == status:
            return job
        time.sleep(0.02)
    return jobs_service.get_job(job_id)


def test_create_read_list(mem_store):
    job = jobs_service.create_job(
        JobCreate(name="East wing", source_keys=["raw/a.ply"], voxel_size=0.05)
    )
    assert job.status == "queued"
    assert jobs_service.get_job(job.id).name == "East wing"
    assert any(j.id == job.id for j in jobs_service.list_jobs())


def test_update_job(mem_store):
    job = jobs_service.create_job(
        JobCreate(name="Draft", source_keys=["raw/a.ply"])
    )
    updated = jobs_service.update_job(
        job.id, JobUpdate(name="Final", meshing_method="ball_pivoting")
    )
    assert updated.name == "Final"
    assert updated.meshing_method == "ball_pivoting"
    # Untouched fields are preserved.
    assert updated.source_keys == ["raw/a.ply"]


def test_delete_job(mem_store):
    job = jobs_service.create_job(JobCreate(name="Temp", source_keys=["raw/a.ply"]))
    jobs_service.delete_job(job.id)
    with pytest.raises(JobNotFoundError):
        jobs_service.get_job(job.id)


def test_missing_job_raises(mem_store):
    with pytest.raises(JobNotFoundError):
        jobs_service.get_job("does-not-exist")


def test_run_writes_artifacts_and_amplification(mem_store, monkeypatch):
    mem_store["raw/a.ply"] = b"x" * 40  # 40-byte source scan
    monkeypatch.setattr(
        jobs_service, "run_pipeline_isolated", lambda *a, **k: _fake_pipeline_result()
    )

    job = jobs_service.create_job(JobCreate(name="Run me", source_keys=["raw/a.ply"]))
    started = jobs_service.run_job(job.id)
    assert started.status == "running"

    done = _wait_for_status(job.id, "done")
    assert done.status == "done"
    assert done.preview_key == f"jobs/{job.id}/preview.png"
    # Three artifacts written back to B2.
    assert {a.name for a in done.artifacts} == {"processed_cloud", "mesh", "preview"}
    assert f"jobs/{job.id}/mesh.ply" in mem_store
    # Write amplification = artifact_bytes / source_bytes, both > 0.
    assert done.metrics.source_bytes == 40
    assert done.metrics.artifact_bytes > 0
    assert done.metrics.write_amplification > 0


def test_run_with_missing_source_fails(mem_store, monkeypatch):
    monkeypatch.setattr(
        jobs_service, "run_pipeline_isolated", lambda *a, **k: _fake_pipeline_result()
    )
    job = jobs_service.create_job(JobCreate(name="Broken", source_keys=["raw/gone.ply"]))
    jobs_service.run_job(job.id)
    failed = _wait_for_status(job.id, "failed")
    assert failed.status == "failed"
    assert failed.error


def test_run_rejects_second_concurrent_run(mem_store, monkeypatch):
    mem_store["raw/a.ply"] = b"x" * 40

    def slow_pipeline(*a, **k):
        time.sleep(0.3)
        return _fake_pipeline_result()

    monkeypatch.setattr(jobs_service, "run_pipeline_isolated", slow_pipeline)
    job = jobs_service.create_job(JobCreate(name="Once", source_keys=["raw/a.ply"]))
    jobs_service.run_job(job.id)
    with pytest.raises(JobConflictError):
        jobs_service.run_job(job.id)
    _wait_for_status(job.id, "done")


def test_job_stats(mem_store, monkeypatch):
    mem_store["raw/a.ply"] = b"x" * 100
    monkeypatch.setattr(
        jobs_service, "run_pipeline_isolated", lambda *a, **k: _fake_pipeline_result()
    )
    job = jobs_service.create_job(JobCreate(name="S", source_keys=["raw/a.ply"]))
    jobs_service.run_job(job.id)
    _wait_for_status(job.id, "done")

    stats = jobs_service.get_job_stats()
    assert stats.total_jobs == 1
    assert stats.done == 1
    assert stats.source_bytes == 100
    assert stats.artifact_count == 3
    assert stats.write_amplification > 0
