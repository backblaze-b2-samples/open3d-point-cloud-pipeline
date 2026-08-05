import logging

# Sync `def` handlers on purpose: the whole chain is blocking boto3, so
# Starlette runs these in its threadpool instead of stalling the event loop
# (see runtime/files.py for the full rationale).
from fastapi import APIRouter, HTTPException

from app.service.jobs import (
    JobConflictError,
    JobNotFoundError,
    JobValidationError,
    create_job,
    delete_job,
    get_job,
    get_job_stats,
    list_jobs,
    run_job,
    update_job,
)
from app.types import Job, JobCreate, JobStats, JobUpdate

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/jobs", response_model=list[Job])
def list_jobs_endpoint():
    return list_jobs()


# Declared before /jobs/{job_id} so "stats" is not swallowed by the id param.
@router.get("/jobs/stats", response_model=JobStats)
def job_stats_endpoint():
    return get_job_stats()


@router.post("/jobs", response_model=Job, status_code=201)
def create_job_endpoint(payload: JobCreate):
    return create_job(payload)


@router.get("/jobs/{job_id}", response_model=Job)
def get_job_endpoint(job_id: str):
    try:
        return get_job(job_id)
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.detail) from None


@router.patch("/jobs/{job_id}", response_model=Job)
def update_job_endpoint(job_id: str, payload: JobUpdate):
    try:
        return update_job(job_id, payload)
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.detail) from None
    except JobConflictError as e:
        raise HTTPException(status_code=409, detail=e.detail) from None


@router.delete("/jobs/{job_id}")
def delete_job_endpoint(job_id: str) -> dict[str, bool | str]:
    try:
        delete_job(job_id)
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.detail) from None
    except RuntimeError:
        raise HTTPException(status_code=502, detail="Failed to delete job from storage") from None
    return {"deleted": True, "id": job_id}


@router.post("/jobs/{job_id}/run", response_model=Job)
def run_job_endpoint(job_id: str):
    try:
        return run_job(job_id)
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.detail) from None
    except JobConflictError as e:
        raise HTTPException(status_code=409, detail=e.detail) from None
    except JobValidationError as e:
        raise HTTPException(status_code=400, detail=e.detail) from None
