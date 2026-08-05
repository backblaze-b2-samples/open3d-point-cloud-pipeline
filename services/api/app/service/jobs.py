"""Job lifecycle: create / read / update / delete / run.

A Job's system of record is a JSON manifest in B2 (``jobs/<id>/job.json``) — no
database. Running orchestrates from a background daemon thread and flips the
manifest ``queued -> running -> done|failed``; the frontend polls. The heavy
Open3D compute itself runs in a SEPARATE process (``service/pipeline_runner.py``)
so a native crash/segfault or a hang is contained to that child — it can never
zombify the worker or wedge the whole API, and both are turned into a ``failed``
manifest. All B2 access goes through ``repo/`` (``repo.artifacts`` for
manifests/artifacts); the pipeline compute lives in ``service/pipeline.py``.
"""

import logging
import threading
import uuid
from datetime import UTC, datetime

from app.config import settings
from app.repo import artifacts
from app.service.pipeline_runner import (
    PipelineCrashed,
    PipelineTimeout,
    run_pipeline_isolated,
)
from app.types.formatting import humanize_bytes
from app.types.jobs import Job, JobArtifact, JobCreate, JobStats, JobUpdate

logger = logging.getLogger(__name__)

_JOBS_PREFIX = "jobs/"
_MANIFEST_NAME = "job.json"

# In-process guard so two concurrent POST /run requests can't both launch the
# same job. Single-replica demo stance (documented in docs/RELIABILITY.md).
_run_lock = threading.Lock()
_running: set[str] = set()


class JobNotFoundError(Exception):
    def __init__(self, detail: str = "Job not found"):
        self.detail = detail
        super().__init__(detail)


class JobConflictError(Exception):
    def __init__(self, detail: str = "Job is already running"):
        self.detail = detail
        super().__init__(detail)


class JobValidationError(Exception):
    def __init__(self, detail: str = "Invalid job"):
        self.detail = detail
        super().__init__(detail)


def _manifest_key(job_id: str) -> str:
    return f"{_JOBS_PREFIX}{job_id}/{_MANIFEST_NAME}"


def _artifact_prefix(job_id: str) -> str:
    return f"{_JOBS_PREFIX}{job_id}/"


def _now() -> datetime:
    return datetime.now(UTC)


def _save(job: Job) -> None:
    artifacts.put_bytes(
        _manifest_key(job.id),
        job.model_dump_json().encode("utf-8"),
        "application/json",
    )


def _load(job_id: str) -> Job | None:
    data = artifacts.get_bytes(_manifest_key(job_id))
    if data is None:
        return None
    return Job.model_validate_json(data)


def list_jobs() -> list[Job]:
    """Every job, newest first. Reads each manifest under jobs/."""
    jobs: list[Job] = []
    for obj in artifacts.list_under(_JOBS_PREFIX):
        if not obj["Key"].endswith(_MANIFEST_NAME):
            continue
        data = artifacts.get_bytes(obj["Key"])
        if data is None:
            continue
        try:
            jobs.append(Job.model_validate_json(data))
        except ValueError:
            logger.warning("Skipping unreadable job manifest: %s", obj["Key"])
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    return jobs


def get_job(job_id: str) -> Job:
    job = _load(job_id)
    if job is None:
        raise JobNotFoundError()
    return job


def create_job(payload: JobCreate) -> Job:
    now = _now()
    job = Job(
        id=uuid.uuid4().hex,
        status="queued",
        created_at=now,
        updated_at=now,
        **payload.model_dump(),
    )
    _save(job)
    logger.info("Job created: id=%s name=%s", job.id, job.name)
    return job


def update_job(job_id: str, payload: JobUpdate) -> Job:
    job = get_job(job_id)
    if job.status == "running":
        raise JobConflictError("Cannot edit a job while it is running")
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return job
    updated = job.model_copy(update={**updates, "updated_at": _now()})
    _save(updated)
    logger.info("Job updated: id=%s fields=%s", job_id, sorted(updates))
    return updated


def delete_job(job_id: str) -> None:
    # Confirm existence first so a missing id is a clean 404, then delete only
    # this job's own prefix — never bucket-wide.
    get_job(job_id)
    artifacts.delete_under(_artifact_prefix(job_id))
    logger.info("Job deleted: id=%s", job_id)


def run_job(job_id: str) -> Job:
    """Mark a job running and launch the pipeline in a background thread."""
    job = get_job(job_id)
    if not job.source_keys:
        raise JobValidationError("Job has no source scans to process")
    with _run_lock:
        if job.status == "running" or job_id in _running:
            raise JobConflictError()
        _running.add(job_id)
    started = job.model_copy(
        update={"status": "running", "error": None, "updated_at": _now()}
    )
    _save(started)
    threading.Thread(target=_execute, args=(job_id,), daemon=True).start()
    logger.info("Job run started: id=%s", job_id)
    return started


def _execute(job_id: str) -> None:
    try:
        job = _load(job_id)
        if job is None:  # deleted between run_job() and here
            return
        sources: list[tuple[str, bytes]] = []
        for key in job.source_keys:
            data = artifacts.get_bytes(key)
            if data is None:
                raise JobValidationError(f"Source scan not found in B2: {key}")
            sources.append((key.rsplit("/", 1)[-1], data))
        source_bytes = sum(len(d) for _, d in sources)

        # Heavy Open3D compute runs in a SEPARATE process (see
        # service/pipeline_runner.py): a native crash/segfault kills only that
        # child, and a genuine hang is bounded — the child is killed on timeout
        # — so one bad run can never zombify the worker or wedge the whole API.
        # B2 I/O stays here in the parent, below.
        result = run_pipeline_isolated(
            sources,
            voxel_size=job.voxel_size,
            meshing_method=job.meshing_method,
            register=job.register_scans,
            timeout=settings.job_run_timeout_seconds,
        )

        written = _write_artifacts(job_id, result)
        metrics = result.metrics.model_copy(
            update={
                "source_bytes": source_bytes,
                "artifact_bytes": written["bytes"],
                "write_amplification": round(written["bytes"] / source_bytes, 2)
                if source_bytes
                else 0.0,
            }
        )
        done = _load(job_id)
        if done is None:  # deleted mid-run
            return
        _save(
            done.model_copy(
                update={
                    "status": "done",
                    "updated_at": _now(),
                    "metrics": metrics,
                    "artifacts": written["artifacts"],
                    "preview_key": written["preview_key"],
                }
            )
        )
        logger.info("Job done: id=%s amp=%sx", job_id, metrics.write_amplification)
    except PipelineTimeout:
        _mark_failed(job_id, "Processing exceeded the per-run time limit")
    except PipelineCrashed as exc:
        logger.warning("Job worker crashed: id=%s err=%s", job_id, exc)
        _mark_failed(job_id, "Processing failed unexpectedly (worker crashed)")
    except Exception as exc:
        logger.warning("Job failed: id=%s err=%s", job_id, exc)
        _mark_failed(job_id, str(exc))
    finally:
        with _run_lock:
            _running.discard(job_id)


def _write_artifacts(job_id: str, result) -> dict:
    prefix = _artifact_prefix(job_id)
    plan = [
        ("processed_cloud", "cloud", "processed.ply", result.processed_ply, "application/octet-stream"),
        ("mesh", "mesh", "mesh.ply", result.mesh_ply, "application/octet-stream"),
        ("preview", "image", "preview.png", result.preview_png, "image/png"),
    ]
    out: list[JobArtifact] = []
    total = 0
    preview_key = None
    for name, kind, filename, data, content_type in plan:
        key = f"{prefix}{filename}"
        size = artifacts.put_bytes(key, data, content_type)
        total += size
        out.append(
            JobArtifact(
                name=name, kind=kind, key=key, size_bytes=size, size_human=humanize_bytes(size)
            )
        )
        if name == "preview":
            preview_key = key
    return {"artifacts": out, "bytes": total, "preview_key": preview_key}


def _mark_failed(job_id: str, detail: str) -> None:
    job = _load(job_id)
    if job is None:
        return
    _save(job.model_copy(update={"status": "failed", "error": detail, "updated_at": _now()}))


def get_job_stats() -> JobStats:
    """Aggregate job + write-amplification metrics for the dashboard."""
    jobs = list_jobs()
    by_status = {"queued": 0, "running": 0, "done": 0, "failed": 0}
    for job in jobs:
        by_status[job.status] = by_status.get(job.status, 0) + 1

    source_bytes = sum(o["Size"] for o in artifacts.list_under("raw/"))
    artifact_objs = [
        o for o in artifacts.list_under(_JOBS_PREFIX) if not o["Key"].endswith(_MANIFEST_NAME)
    ]
    artifact_bytes = sum(o["Size"] for o in artifact_objs)

    return JobStats(
        total_jobs=len(jobs),
        queued=by_status["queued"],
        running=by_status["running"],
        done=by_status["done"],
        failed=by_status["failed"],
        source_bytes=source_bytes,
        source_bytes_human=humanize_bytes(source_bytes),
        artifact_bytes=artifact_bytes,
        artifact_bytes_human=humanize_bytes(artifact_bytes),
        artifact_count=len(artifact_objs),
        write_amplification=round(artifact_bytes / source_bytes, 2) if source_bytes else 0.0,
    )
