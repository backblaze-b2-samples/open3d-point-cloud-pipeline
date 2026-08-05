"""Isolation semantics of the out-of-process pipeline runner (CAUSE 2).

Proves the containment guarantees: a native crash in the worker surfaces as
PipelineCrashed (never a stuck job / wedged API), a genuine hang is killed at
the timeout as PipelineTimeout, an ordinary exception surfaces as PipelineError,
and a normal run returns its picklable result across the process boundary. Uses
the same 'spawn' start method as production.

Probe functions are module-level so they are picklable *by reference* and
re-importable in a 'spawn' child.
"""

import os
import signal
import time

import pytest

from app.service.pipeline_runner import (
    PipelineCrashed,
    PipelineError,
    PipelineTimeout,
    run_in_process,
    run_pipeline_isolated,
)


def _probe_double(x):
    return x * 2


def _probe_sleep(seconds):
    time.sleep(seconds)
    return "slept"


def _probe_hard_kill():
    # Uncatchable signal death — mimics a native Open3D abort from the parent's
    # point of view (child gone, no result). SIGKILL avoids a macOS crash dialog.
    os.kill(os.getpid(), signal.SIGKILL)


def _probe_raise():
    raise ValueError("boom in the worker")


def test_returns_result_across_process_boundary():
    assert run_in_process(_probe_double, args=(21,), timeout=30) == 42


def test_native_crash_surfaces_as_crashed():
    with pytest.raises(PipelineCrashed):
        run_in_process(_probe_hard_kill, timeout=30)


def test_ordinary_exception_surfaces_as_error():
    with pytest.raises(PipelineError, match="boom in the worker"):
        run_in_process(_probe_raise, timeout=30)


def test_hang_is_killed_at_timeout():
    start = time.monotonic()
    with pytest.raises(PipelineTimeout):
        run_in_process(_probe_sleep, args=(30,), timeout=0.5)
    # Returned promptly (child was killed) rather than waiting out the 30s sleep.
    assert time.monotonic() - start < 10


def test_run_pipeline_isolated_end_to_end():
    """The real pipeline runs in a child and both args and result pickle across
    the boundary — this is the exact path a job takes in production."""
    import tempfile
    from pathlib import Path

    import open3d as o3d

    mesh = o3d.geometry.TriangleMesh.create_torus()
    pcd = mesh.sample_points_poisson_disk(number_of_points=2000)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "torus.ply"
        o3d.io.write_point_cloud(str(path), pcd)
        data = path.read_bytes()

    result = run_pipeline_isolated(
        [("torus.ply", data)],
        voxel_size=0.02,
        meshing_method="poisson",
        register=False,
        timeout=120,
    )
    assert result.processed_ply[:3].lower() == b"ply"
    assert result.mesh_ply[:3].lower() == b"ply"
    assert result.preview_png[:8] == b"\x89PNG\r\n\x1a\n"
    assert result.metrics.mesh_triangles > 0
