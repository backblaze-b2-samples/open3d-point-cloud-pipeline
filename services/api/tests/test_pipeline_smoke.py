"""End-to-end Open3D pipeline smoke test on synthetic clouds (no B2, no network).

Proves the primary feature actually runs on a clean install: load a real PLY,
downsample, estimate normals, build a Poisson mesh, and render a preview PNG —
all CPU-only. This is the pytest form of the build gate in the plan (§7.1).
"""

import numpy as np
import open3d as o3d

from app.service import pointcloud, preview
from app.service.pipeline import run_pipeline


def _sphere_ply_bytes(n_points: int = 1500, seed: int = 0) -> bytes:
    import tempfile
    from pathlib import Path

    mesh = o3d.geometry.TriangleMesh.create_sphere(radius=1.0, resolution=20)
    pcd = mesh.sample_points_poisson_disk(number_of_points=n_points)
    rng = np.random.default_rng(seed)
    noisy = np.asarray(pcd.points) + rng.normal(0, 0.004, size=(len(pcd.points), 3))
    pcd.points = o3d.utility.Vector3dVector(noisy)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sphere.ply"
        o3d.io.write_point_cloud(str(path), pcd)
        return path.read_bytes()


def test_load_downsample_and_mesh():
    data = _sphere_ply_bytes()
    cloud = pointcloud.load_cloud(data, "sphere.ply")
    assert len(cloud.points) > 0

    down = pointcloud.downsample(cloud, voxel_size=0.05)
    assert 0 < len(down.points) <= len(cloud.points)

    mesh = pointcloud.build_mesh(down, "poisson", voxel_size=0.05)
    assert len(mesh.vertices) > 0
    assert len(mesh.triangles) > 0


def test_preview_render_produces_png():
    data = _sphere_ply_bytes()
    cloud = pointcloud.load_cloud(data, "sphere.ply")
    png = preview.render_preview(cloud, None)
    # PNG magic number — proves the headless matplotlib path wrote a real image.
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_run_pipeline_single_scan():
    result = run_pipeline(
        [("sphere.ply", _sphere_ply_bytes())],
        voxel_size=0.05,
        meshing_method="poisson",
        register=False,
    )
    assert result.processed_ply[:3].lower() == b"ply"
    assert result.mesh_ply[:3].lower() == b"ply"
    assert result.preview_png[:8] == b"\x89PNG\r\n\x1a\n"
    assert result.metrics.mesh_triangles > 0
    assert result.metrics.registered is False


def test_run_pipeline_registers_two_scans():
    base = _sphere_ply_bytes(seed=1)
    # A second cloud rigidly offset from the first, to exercise registration.
    pcd = pointcloud.load_cloud(base, "a.ply")
    pcd.translate((0.1, 0.0, 0.0))
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "b.ply"
        o3d.io.write_point_cloud(str(p), pcd)
        second = p.read_bytes()

    result = run_pipeline(
        [("a.ply", base), ("b.ply", second)],
        voxel_size=0.05,
        meshing_method="poisson",
        register=True,
    )
    assert result.metrics.registered is True
    assert result.metrics.mesh_triangles > 0
