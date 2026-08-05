"""Headless preview rendering for a processed cloud / mesh.

The render must NEVER hard-fail on a headless server. ``matplotlib`` (Agg
backend) is the primary, always-works renderer — pure CPU, deterministic, no GL
context. An Open3D ``OffscreenRenderer`` is an OPTIONAL higher-fidelity path,
attempted only when explicitly enabled and always inside ``try/except`` so a
missing Filament/GL context falls back to matplotlib. A ``preview.png`` is
always produced.
"""

import io
import logging

import matplotlib

matplotlib.use("Agg")  # headless: never tries to open a window
import matplotlib.pyplot as plt
import numpy as np
import open3d as o3d

from app.config import settings

logger = logging.getLogger(__name__)

# Bound render time: subsample above this many points/triangles.
_MAX_RENDER_PRIMS = 30000
_RNG = np.random.default_rng(0)  # deterministic subsampling


def render_preview(
    pcd: o3d.geometry.PointCloud,
    mesh: o3d.geometry.TriangleMesh | None = None,
) -> bytes:
    """Return PNG bytes for a preview. Never raises."""
    if settings.enable_offscreen_render:
        png = _try_offscreen(pcd, mesh)
        if png is not None:
            return png
    try:
        return _matplotlib_preview(pcd, mesh)
    except Exception:
        logger.warning("matplotlib preview failed; writing placeholder", exc_info=True)
        return _placeholder_png()


def _subsample_rows(arr: np.ndarray, limit: int) -> np.ndarray:
    if len(arr) <= limit:
        return arr
    idx = _RNG.choice(len(arr), size=limit, replace=False)
    return arr[idx]


def _matplotlib_preview(
    pcd: o3d.geometry.PointCloud, mesh: o3d.geometry.TriangleMesh | None
) -> bytes:
    fig = plt.figure(figsize=(6, 6), facecolor="#0b0f17")
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor("#0b0f17")
    ax.set_axis_off()

    if mesh is not None and len(mesh.triangles) > 0:
        verts = np.asarray(mesh.vertices)
        tris = _subsample_rows(np.asarray(mesh.triangles), _MAX_RENDER_PRIMS)
        ax.plot_trisurf(
            verts[:, 0],
            verts[:, 1],
            tris,
            verts[:, 2],
            cmap="viridis",
            linewidth=0,
            antialiased=False,
        )
        pts = verts
    else:
        pts = _subsample_rows(np.asarray(pcd.points), _MAX_RENDER_PRIMS)
        ax.scatter(
            pts[:, 0], pts[:, 1], pts[:, 2], c=pts[:, 2], cmap="viridis", s=1, linewidths=0
        )

    _equal_aspect(ax, pts)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return buf.getvalue()


def _equal_aspect(ax, pts: np.ndarray) -> None:
    """Make the three axes share one scale so the shape isn't distorted."""
    if pts.size == 0:
        return
    mins = pts.min(axis=0)
    maxs = pts.max(axis=0)
    center = (mins + maxs) / 2
    radius = float((maxs - mins).max()) / 2 or 1.0
    ax.set_xlim(center[0] - radius, center[0] + radius)
    ax.set_ylim(center[1] - radius, center[1] + radius)
    ax.set_zlim(center[2] - radius, center[2] + radius)


def _placeholder_png() -> bytes:
    fig = plt.figure(figsize=(6, 6), facecolor="#0b0f17")
    ax = fig.add_subplot(111)
    ax.set_axis_off()
    ax.text(
        0.5,
        0.5,
        "preview unavailable",
        ha="center",
        va="center",
        color="#94a3b8",
        transform=ax.transAxes,
    )
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    return buf.getvalue()


def _try_offscreen(
    pcd: o3d.geometry.PointCloud, mesh: o3d.geometry.TriangleMesh | None
) -> bytes | None:
    """Optional Open3D OffscreenRenderer path. Returns None on any failure."""
    try:
        import tempfile
        from pathlib import Path

        renderer = o3d.visualization.rendering.OffscreenRenderer(768, 768)
        material = o3d.visualization.rendering.MaterialRecord()
        geometry = mesh if (mesh is not None and len(mesh.triangles) > 0) else pcd
        material.shader = "defaultLit" if geometry is mesh else "defaultUnlit"
        renderer.scene.add_geometry("geom", geometry, material)
        renderer.scene.set_background([0.043, 0.059, 0.09, 1.0])
        image = renderer.render_to_image()
        # Open3D writes an image to a path, so round-trip through a temp file.
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "preview.png"
            o3d.io.write_image(str(out), image)
            return out.read_bytes()
    except Exception:
        logger.info("OffscreenRenderer unavailable; using matplotlib", exc_info=True)
        return None
