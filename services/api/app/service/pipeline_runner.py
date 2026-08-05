"""Run the CPU-heavy Open3D pipeline in an isolated 'spawn' worker process.

A native abort/segfault inside Open3D (e.g. the intermittent Poisson "Failed to
close loop" on macOS arm64) CANNOT be caught by an in-process ``try/except`` and
CANNOT be reclaimed by a thread-level timeout — it kills/zombifies the worker.
In the single-worker API that would (a) strand the job "running" forever and
(b) take the whole API down with it. Running the compute in a separate process
contains both failure modes: a native crash kills only the child, and a genuine
hang is bounded by killing the child on timeout.

Only picklable data crosses the process boundary: the pipeline's ``sources``
(``list[(name, bytes)]``) go in and a ``PipelineResult`` (bytes + a Pydantic
metrics model) comes back. B2 I/O stays in the PARENT (``service/jobs.py``), so
the child imports no ``boto3`` — it only computes geometry.
"""

import logging
import multiprocessing as mp
from collections.abc import Callable
from typing import Any

from app.service.pipeline import PipelineResult, run_pipeline

logger = logging.getLogger(__name__)

# Grace period to reap a child after it has produced a result / been killed.
_JOIN_GRACE_SECONDS = 5.0


class PipelineTimeout(Exception):
    """The pipeline exceeded its per-run time budget; the worker was killed."""


class PipelineCrashed(Exception):
    """The worker process died (native crash/segfault) without a result."""


class PipelineError(Exception):
    """The pipeline raised an ordinary Python exception inside the worker."""


def _worker(conn, fn: Callable, args: tuple, kwargs: dict) -> None:
    """Child entrypoint: run ``fn`` and ship a tagged result back over ``conn``.

    Runs in the spawned process. Any ordinary exception is serialized as a
    string (the traceback object is not reliably picklable); a native
    crash/segfault never reaches this handler and instead closes ``conn``,
    which the parent reads as EOF.
    """
    try:
        result = fn(*args, **kwargs)
        conn.send(("ok", result))
    except Exception as exc:  # ordinary failure -> report cleanly to the parent
        conn.send(("error", f"{type(exc).__name__}: {exc}"))
    finally:
        conn.close()


def _reap(proc: mp.Process) -> None:
    """Kill the child if it is still alive, then join so it is never a zombie."""
    if proc.is_alive():
        proc.kill()
    proc.join(_JOIN_GRACE_SECONDS)


def run_in_process(
    fn: Callable[..., Any],
    *,
    args: tuple = (),
    kwargs: dict | None = None,
    timeout: float,
) -> Any:
    """Run ``fn(*args, **kwargs)`` in a separate 'spawn' process, bounded by
    ``timeout`` seconds.

    Returns ``fn``'s (picklable) return value. Raises :class:`PipelineTimeout`
    if the deadline passes (the child is killed first), :class:`PipelineCrashed`
    if the child dies without a result, or :class:`PipelineError` if ``fn``
    raised an ordinary exception inside the child.
    """
    ctx = mp.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(
        target=_worker,
        args=(child_conn, fn, args, kwargs or {}),
        daemon=True,
    )
    proc.start()
    # Only the child writes; closing our copy lets recv see EOF if it dies.
    child_conn.close()

    status: str | None = None
    payload: Any = None
    try:
        if not parent_conn.poll(timeout):
            raise PipelineTimeout("Processing exceeded the per-run time limit")
        try:
            status, payload = parent_conn.recv()
        except EOFError:  # child died mid-/pre-send (native crash)
            status = None
    finally:
        parent_conn.close()
        _reap(proc)

    if status == "ok":
        return payload
    if status == "error":
        raise PipelineError(str(payload))
    raise PipelineCrashed(
        f"Processing worker exited unexpectedly (exit code {proc.exitcode})"
    )


def run_pipeline_isolated(
    sources: list[tuple[str, bytes]],
    *,
    voxel_size: float,
    meshing_method: str,
    register: bool,
    timeout: float,
) -> PipelineResult:
    """Run :func:`app.service.pipeline.run_pipeline` in an isolated worker."""
    return run_in_process(
        run_pipeline,
        args=(sources,),
        kwargs={
            "voxel_size": voxel_size,
            "meshing_method": meshing_method,
            "register": register,
        },
        timeout=timeout,
    )
