"""Open3D geometry operations for the processing pipeline.

Pure, in-memory compute: bytes in, Open3D geometry out. No B2 access (that stays
in ``repo/``) and no job/manifest concerns (those live in ``service/pipeline.py``
and ``service/jobs.py``). Every operation here is CPU-bound Open3D **core
geometry** — voxel downsample, statistical outlier removal, FPFH/RANSAC/ICP
registration, Poisson / ball-pivoting meshing, normal estimation. None of it
uses the Open3D CUDA/ML path, so no GPU is required or selected.
"""

import tempfile
from pathlib import Path

import numpy as np
import open3d as o3d

# File formats Open3D reads natively (from a temp file); LAS/LAZ go via laspy.
_NATIVE_EXTENSIONS = {"ply", "pcd", "xyz", "xyzn", "xyzrgb", "pts"}


def _extension(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def load_cloud(data: bytes, filename: str) -> o3d.geometry.PointCloud:
    """Load a point cloud from raw bytes by file extension.

    PLY/PCD (and other Open3D-native formats) are read directly; LAS/LAZ go
    through laspy (LAZ needs the ``lazrs`` backend). Raises ValueError for an
    empty or unreadable cloud.
    """
    ext = _extension(filename)
    if ext in ("las", "laz"):
        return _load_las(data, ext)
    return _load_native(data, ext if ext in _NATIVE_EXTENSIONS else "ply")


def _load_native(data: bytes, ext: str) -> o3d.geometry.PointCloud:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"cloud.{ext}"
        path.write_bytes(data)
        pcd = o3d.io.read_point_cloud(str(path))
    if len(pcd.points) == 0:
        raise ValueError("Point cloud is empty or could not be read")
    return pcd


def _load_las(data: bytes, ext: str) -> o3d.geometry.PointCloud:
    import laspy

    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"cloud.{ext}"
            path.write_bytes(data)
            las = laspy.read(str(path))
    except Exception as exc:  # laspy surfaces many error types; degrade cleanly.
        raise ValueError(
            f"Could not read {ext.upper()} cloud (is the lazrs backend "
            f"installed for .laz?): {exc}"
        ) from exc

    xyz = np.vstack([las.x, las.y, las.z]).T.astype(np.float64)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(xyz)

    dims = set(las.point_format.dimension_names)
    if {"red", "green", "blue"} <= dims:
        rgb = np.vstack([las.red, las.green, las.blue]).T.astype(np.float64)
        peak = float(rgb.max()) if rgb.size else 0.0
        if peak > 255:
            rgb /= 65535.0
        elif peak > 1:
            rgb /= 255.0
        pcd.colors = o3d.utility.Vector3dVector(np.clip(rgb, 0.0, 1.0))

    if len(pcd.points) == 0:
        raise ValueError("LAS/LAZ cloud has no points")
    return pcd


def downsample(pcd: o3d.geometry.PointCloud, voxel_size: float) -> o3d.geometry.PointCloud:
    """Voxel-downsample then remove statistical outliers.

    Falls back to the input if a too-large voxel or an aggressive outlier filter
    would otherwise leave nothing, so a run never yields an empty cloud.
    """
    down = pcd.voxel_down_sample(voxel_size=voxel_size) if voxel_size > 0 else pcd
    if len(down.points) == 0:
        down = pcd
    clean, _ = down.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
    return clean if len(clean.points) > 0 else down


def _nn_scale(pcd: o3d.geometry.PointCloud, fallback: float = 0.05) -> float:
    """Mean nearest-neighbour distance — a scale for normals / BPA radii."""
    dists = np.asarray(pcd.compute_nearest_neighbor_distance())
    return float(dists.mean()) if dists.size else fallback


def ensure_normals(pcd: o3d.geometry.PointCloud, voxel_size: float) -> None:
    """Estimate + orient normals in place if absent (meshing needs them)."""
    if pcd.has_normals():
        return
    radius = max(voxel_size * 2, _nn_scale(pcd) * 3)
    pcd.estimate_normals(
        o3d.geometry.KDTreeSearchParamHybrid(radius=radius, max_nn=30)
    )
    pcd.orient_normals_consistent_tangent_plane(10)


def _feature(pcd: o3d.geometry.PointCloud, voxel_size: float):
    pcd.estimate_normals(
        o3d.geometry.KDTreeSearchParamHybrid(radius=voxel_size * 2, max_nn=30)
    )
    return o3d.pipelines.registration.compute_fpfh_feature(
        pcd,
        o3d.geometry.KDTreeSearchParamHybrid(radius=voxel_size * 5, max_nn=100),
    )


def register(
    clouds: list[o3d.geometry.PointCloud], voxel_size: float
) -> o3d.geometry.PointCloud:
    """Register 2+ clouds onto the first (FPFH+RANSAC global, ICP refine).

    Returns a single merged cloud. Each additional cloud is aligned pairwise to
    the base; a failed alignment still contributes its ICP-refined position.
    """
    reg = o3d.pipelines.registration
    base = clouds[0]
    base_fpfh = _feature(base, voxel_size)
    threshold = voxel_size * 1.5
    merged = o3d.geometry.PointCloud(base)

    for other in clouds[1:]:
        other_fpfh = _feature(other, voxel_size)
        result = reg.registration_ransac_based_on_feature_matching(
            other,
            base,
            other_fpfh,
            base_fpfh,
            True,
            threshold,
            reg.TransformationEstimationPointToPoint(False),
            3,
            [
                reg.CorrespondenceCheckerBasedOnEdgeLength(0.9),
                reg.CorrespondenceCheckerBasedOnDistance(threshold),
            ],
            reg.RANSACConvergenceCriteria(100000, 0.999),
        )
        icp = reg.registration_icp(
            other,
            base,
            threshold,
            result.transformation,
            reg.TransformationEstimationPointToPlane(),
        )
        merged += o3d.geometry.PointCloud(other).transform(icp.transformation)

    return merged


def build_mesh(
    pcd: o3d.geometry.PointCloud, method: str, voxel_size: float
) -> o3d.geometry.TriangleMesh:
    """Surface-mesh a cloud with Poisson (default) or ball-pivoting."""
    ensure_normals(pcd, voxel_size)
    if method == "ball_pivoting":
        avg = _nn_scale(pcd, fallback=voxel_size or 0.02)
        radii = o3d.utility.DoubleVector([avg, avg * 2, avg * 4])
        mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_ball_pivoting(
            pcd, radii
        )
    else:
        # n_threads=1: Poisson's OpenMP-parallel isosurface extraction is the
        # source of a non-deterministic native abort on macOS arm64
        # ("PoissonRecon ... Failed to close loop"). Single-threaded is
        # deterministic and eliminates that crash; the seed clouds are small so
        # the serial path is not a meaningful slowdown.
        mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            pcd, depth=8, n_threads=1
        )
        # Trim low-density balloon artifacts that Poisson leaves around the hull.
        density = np.asarray(densities)
        if density.size:
            mesh.remove_vertices_by_mask(density < np.quantile(density, 0.02))
    mesh.compute_vertex_normals()
    return mesh
