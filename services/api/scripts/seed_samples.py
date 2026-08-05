"""Seed the B2 bucket with small SYNTHETIC point clouds (no downloads).

Generates license-clean sample scans with Open3D and uploads them to the
``raw/`` prefix so a fresh clone has something to process immediately:

  * ``raw/object-torus.ply`` — a full-object cloud (torus sampled with Poisson
    disk + light Gaussian noise) for the single-scan mesh demo.
  * ``raw/scan-pair-a.ply`` / ``raw/scan-pair-b.ply`` — two overlapping partial
    scans of one sphere; ``b`` is offset by a known rigid transform so the
    registration demo has something real to recover.

Each cloud is kept to a few tens of thousands of points so a run finishes in
seconds. Run after filling in ``.env``:

    services/api/.venv/bin/python services/api/scripts/seed_samples.py
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np
import open3d as o3d
from dotenv import load_dotenv

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[1]

# Load B2 credentials from the repo-root .env before importing the repo layer.
load_dotenv(REPO_ROOT / ".env")
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.repo import artifacts  # noqa: E402
from app.service.upload import RAW_PREFIX  # noqa: E402

_RNG = np.random.default_rng(7)


def _to_ply_bytes(pcd: o3d.geometry.PointCloud) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "cloud.ply"
        o3d.io.write_point_cloud(str(path), pcd)
        return path.read_bytes()


def _jitter(pcd: o3d.geometry.PointCloud, sigma: float) -> o3d.geometry.PointCloud:
    pts = np.asarray(pcd.points)
    pcd.points = o3d.utility.Vector3dVector(pts + _RNG.normal(0, sigma, size=pts.shape))
    return pcd


def make_object_cloud(n_points: int = 20000) -> o3d.geometry.PointCloud:
    """A full-object torus cloud for the single-scan mesh demo."""
    mesh = o3d.geometry.TriangleMesh.create_torus(
        torus_radius=1.0, tube_radius=0.35, radial_resolution=60, tubular_resolution=40
    )
    pcd = mesh.sample_points_poisson_disk(number_of_points=n_points)
    return _jitter(pcd, sigma=0.004)


def make_scan_pair(
    n_points: int = 24000,
) -> tuple[o3d.geometry.PointCloud, o3d.geometry.PointCloud]:
    """Two overlapping partial scans of one sphere with a known offset on ``b``."""
    mesh = o3d.geometry.TriangleMesh.create_sphere(radius=1.0, resolution=40)
    full = _jitter(mesh.sample_points_poisson_disk(number_of_points=n_points), 0.004)
    pts = np.asarray(full.points)

    # Two overlapping crops along X (overlap band -0.3 < x < 0.3).
    scan_a = full.select_by_index(np.where(pts[:, 0] < 0.3)[0])
    scan_b = full.select_by_index(np.where(pts[:, 0] > -0.3)[0])

    # Displace scan B by a known rigid transform for registration to recover.
    transform = np.eye(4)
    angle = np.deg2rad(18.0)
    transform[:3, :3] = o3d.geometry.get_rotation_matrix_from_xyz((0.0, angle, 0.0))
    transform[:3, 3] = (0.15, 0.05, 0.10)
    scan_b.transform(transform)
    return scan_a, scan_b


def _upload(name: str, pcd: o3d.geometry.PointCloud, prefix: str) -> None:
    key = f"{prefix}{name}"
    data = _to_ply_bytes(pcd)
    artifacts.put_bytes(key, data, "application/octet-stream")
    sys.stdout.write(f"  uploaded {key}  ({len(pcd.points):,} points, {len(data):,} bytes)\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prefix",
        default=RAW_PREFIX,
        help=f"B2 key prefix for seeded scans (default: {RAW_PREFIX})",
    )
    args = parser.parse_args()
    prefix = args.prefix if args.prefix.endswith("/") else args.prefix + "/"

    sys.stdout.write("Generating synthetic point clouds and uploading to B2...\n")
    _upload("object-torus.ply", make_object_cloud(), prefix)
    scan_a, scan_b = make_scan_pair()
    _upload("scan-pair-a.ply", scan_a, prefix)
    _upload("scan-pair-b.ply", scan_b, prefix)
    sys.stdout.write(
        "Done. Create a job at /jobs/new — pick the torus for a single-scan mesh, "
        "or both scan-pair clouds with registration ON.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
