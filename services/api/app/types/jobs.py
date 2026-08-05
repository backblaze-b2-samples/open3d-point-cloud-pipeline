"""Pydantic models for the primary entity: a point-cloud processing Job.

A Job is persisted as a JSON manifest in B2 at ``jobs/<id>/job.json`` — there is
no database. Its derived artifacts live alongside it under ``jobs/<id>/``.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# Finite option sets — surfaced as selectors (not free text) in the create/edit
# forms, and validated at the API boundary here.
MeshingMethod = Literal["poisson", "ball_pivoting"]
MESHING_METHODS: tuple[MeshingMethod, ...] = ("poisson", "ball_pivoting")

JobStatus = Literal["queued", "running", "done", "failed"]

# Safe default voxel size for the seed clouds (see /jobs/new FormDescription).
DEFAULT_VOXEL_SIZE = 0.02


class JobArtifact(BaseModel):
    """One derived object written back to B2 by a completed run."""

    name: str  # "processed_cloud" | "mesh" | "preview"
    kind: str  # "cloud" | "mesh" | "image"
    key: str
    size_bytes: int
    size_human: str


class JobMetrics(BaseModel):
    """Numbers the run produced — drive the dashboard's write-amplification view."""

    source_points: int = 0
    downsampled_points: int = 0
    mesh_vertices: int = 0
    mesh_triangles: int = 0
    registered: bool = False
    source_bytes: int = 0
    artifact_bytes: int = 0
    write_amplification: float = 0.0
    duration_seconds: float = 0.0


class JobConfig(BaseModel):
    """The tunable inputs shared by create, edit, and the persisted manifest."""

    name: str = Field(min_length=1, max_length=120)
    # Object keys under raw/ — chosen from a selector, never free text.
    source_keys: list[str] = Field(min_length=1)
    meshing_method: MeshingMethod = "poisson"
    # Multi-scan registration. Only effective with >= 2 sources; ignored for a
    # single-scan run. (Named `register_scans`, not `register`, to avoid
    # shadowing ABCMeta.register on Pydantic's model metaclass.)
    register_scans: bool = False
    voxel_size: float = Field(default=DEFAULT_VOXEL_SIZE, gt=0, le=10.0)


class JobCreate(JobConfig):
    """POST /jobs body."""


class JobUpdate(BaseModel):
    """PATCH /jobs/{id} body — every field optional (partial update)."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    source_keys: list[str] | None = Field(default=None, min_length=1)
    meshing_method: MeshingMethod | None = None
    register_scans: bool | None = None
    voxel_size: float | None = Field(default=None, gt=0, le=10.0)


class Job(JobConfig):
    """Full Job record as persisted and returned to the frontend."""

    id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    error: str | None = None
    metrics: JobMetrics = Field(default_factory=JobMetrics)
    artifacts: list[JobArtifact] = Field(default_factory=list)
    preview_key: str | None = None


class JobStats(BaseModel):
    """Aggregate job + write-amplification metrics for the dashboard."""

    total_jobs: int
    queued: int
    running: int
    done: int
    failed: int
    source_bytes: int
    source_bytes_human: str
    artifact_bytes: int
    artifact_bytes_human: str
    artifact_count: int
    write_amplification: float
