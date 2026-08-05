"""End-to-end Open3D pipeline: source cloud bytes -> derived artifact bytes.

Pure compute. Takes the raw source clouds (already downloaded from B2 by
``service/jobs.py``) and returns the processed cloud, the surface mesh, and the
preview PNG as bytes, plus the run metrics. B2 I/O and manifest persistence stay
in ``service/jobs.py``; this module never touches storage. CPU-only — no GPU.
"""

import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import open3d as o3d

from app.service import pointcloud, preview
from app.types.jobs import JobMetrics


@dataclass
class PipelineResult:
    processed_ply: bytes
    mesh_ply: bytes
    preview_png: bytes
    metrics: JobMetrics


def _to_ply_bytes(geometry) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "out.ply"
        if isinstance(geometry, o3d.geometry.TriangleMesh):
            o3d.io.write_triangle_mesh(str(path), geometry)
        else:
            o3d.io.write_point_cloud(str(path), geometry)
        return path.read_bytes()


def run_pipeline(
    sources: list[tuple[str, bytes]],
    *,
    voxel_size: float,
    meshing_method: str,
    register: bool,
) -> PipelineResult:
    """Run the full pipeline over one or more source clouds.

    downsample -> optional multi-scan registration -> surface meshing ->
    preview render. ``sources`` is a list of ``(filename, raw_bytes)``.
    """
    start = time.monotonic()

    clouds = [pointcloud.load_cloud(data, name) for name, data in sources]
    source_points = sum(len(c.points) for c in clouds)

    downsampled = [pointcloud.downsample(c, voxel_size) for c in clouds]

    did_register = False
    if register and len(downsampled) >= 2:
        merged = pointcloud.register(downsampled, voxel_size)
        did_register = True
    else:
        merged = o3d.geometry.PointCloud(downsampled[0])
        for extra in downsampled[1:]:
            merged += extra

    mesh = pointcloud.build_mesh(merged, meshing_method, voxel_size)

    processed_ply = _to_ply_bytes(merged)
    mesh_ply = _to_ply_bytes(mesh)
    preview_png = preview.render_preview(merged, mesh)

    metrics = JobMetrics(
        source_points=source_points,
        downsampled_points=len(merged.points),
        mesh_vertices=len(mesh.vertices),
        mesh_triangles=len(mesh.triangles),
        registered=did_register,
        duration_seconds=round(time.monotonic() - start, 2),
    )
    return PipelineResult(processed_ply, mesh_ply, preview_png, metrics)
