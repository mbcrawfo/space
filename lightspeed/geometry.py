"""Circle geometry for the viewer: camera-facing rings and sphere–sphere intersections.

Pure numpy, no VTK. Every function returns plain arrays the viewer pours into one
PolyData whose topology never changes, so a frame only rewrites points.
"""

import numpy as np


def facing_normals(centers: np.ndarray, camera) -> np.ndarray:
    """Unit vectors from each centre toward the camera (a stand-in if the camera sits on one)."""
    towards = np.asarray(camera, dtype=float) - np.asarray(centers, dtype=float)
    lengths = np.linalg.norm(towards, axis=1, keepdims=True)
    towards = np.where(lengths > 0.0, towards, [0.0, 0.0, 1.0])
    return towards / np.maximum(np.linalg.norm(towards, axis=1, keepdims=True), 1e-12)


def circle_points(centers: np.ndarray, radii: np.ndarray, normals: np.ndarray, segments: int) -> np.ndarray:
    """`segments` points around each circle, in the plane perpendicular to its normal; shape (n·segments, 3)."""
    centers = np.asarray(centers, dtype=float)
    normals = np.asarray(normals, dtype=float)
    radii = np.asarray(radii, dtype=float).reshape(-1, 1, 1)
    # A reference axis that is never parallel to the normal, then two in-plane unit vectors.
    reference = np.where(np.abs(normals[:, 2:3]) < 0.9, [[0.0, 0.0, 1.0]], [[1.0, 0.0, 0.0]])
    u = np.cross(normals, reference)
    u /= np.maximum(np.linalg.norm(u, axis=1, keepdims=True), 1e-12)
    v = np.cross(normals, u)
    theta = np.linspace(0.0, 2.0 * np.pi, segments, endpoint=False)
    rim = np.cos(theta)[None, :, None] * u[:, None, :] + np.sin(theta)[None, :, None] * v[:, None, :]
    return (centers[:, None, :] + radii * rim).reshape(-1, 3)


def polyline_cells(circles: int, segments: int) -> np.ndarray:
    """VTK line-cell connectivity closing each circle: [segments+1, i0 … i(n-1), i0] per circle."""
    starts = np.arange(circles)[:, None] * segments
    indices = starts + np.arange(segments)[None, :]
    return np.hstack([np.full((circles, 1), segments + 1), indices, starts]).ravel()


def intersection_circles(center, others: np.ndarray, radius: float):
    """Where the sphere of `radius` about `center` meets the equal spheres about `others`.

    Returns (centres, radii, normals) for one circle per other sphere: the circle lies in
    the plane bisecting the two centres. Spheres that do not yet overlap get a zero-radius
    circle at the midpoint, which draws as nothing — so the topology stays fixed.
    """
    center = np.asarray(center, dtype=float)
    others = np.asarray(others, dtype=float)
    between = others - center
    distances = np.linalg.norm(between, axis=1)
    safe = np.maximum(distances, 1e-12)
    normals = between / safe[:, None]
    radii = np.sqrt(np.maximum(radius**2 - (distances / 2.0) ** 2, 0.0))
    radii[distances >= 2.0 * radius] = 0.0
    centers = center + between / 2.0
    return centers, radii, normals
