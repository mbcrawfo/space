import math

import numpy as np
import pytest

from lightspeed import geometry


def test_facing_normals_point_from_each_centre_to_the_camera():
    centers = np.array([[0.0, 0.0, 0.0], [3.0, 0.0, 0.0]])
    normals = geometry.facing_normals(centers, camera=(0.0, 0.0, 10.0))
    assert normals[0] == pytest.approx([0.0, 0.0, 1.0])
    assert normals[1] == pytest.approx(np.array([-3.0, 0.0, 10.0]) / math.sqrt(109.0))
    assert np.linalg.norm(normals, axis=1) == pytest.approx([1.0, 1.0])


def test_facing_normals_survive_the_camera_sitting_on_a_centre():
    normals = geometry.facing_normals(np.array([[1.0, 2.0, 3.0]]), camera=(1.0, 2.0, 3.0))
    assert np.isfinite(normals).all()
    assert np.linalg.norm(normals[0]) == pytest.approx(1.0)


def test_circle_points_lie_on_the_circle_in_the_plane_of_the_normal():
    centers = np.array([[0.0, 0.0, 0.0], [5.0, 5.0, 5.0]])
    radii = np.array([2.0, 0.5])
    normals = np.array([[0.0, 0.0, 1.0], [1.0, 0.0, 0.0]])
    points = geometry.circle_points(centers, radii, normals, segments=8)
    assert points.shape == (16, 3)
    first, second = points[:8], points[8:]
    assert np.linalg.norm(first - centers[0], axis=1) == pytest.approx(np.full(8, 2.0))
    assert first[:, 2] == pytest.approx(np.zeros(8))  # in the plane perpendicular to z
    assert np.linalg.norm(second - centers[1], axis=1) == pytest.approx(np.full(8, 0.5))
    assert second[:, 0] == pytest.approx(np.full(8, 5.0))  # in the plane perpendicular to x


def test_circle_points_handles_a_normal_along_the_reference_axis():
    points = geometry.circle_points(np.zeros((1, 3)), np.array([1.0]), np.array([[0.0, 0.0, 1.0]]), segments=12)
    assert np.isfinite(points).all()
    assert np.linalg.norm(points, axis=1) == pytest.approx(np.ones(12))


def test_polyline_cells_close_each_circle():
    cells = geometry.polyline_cells(circles=2, segments=4)
    assert cells.tolist() == [5, 0, 1, 2, 3, 0, 5, 4, 5, 6, 7, 4]


def test_intersection_circles_of_equal_spheres():
    center = np.array([0.0, 0.0, 0.0])
    others = np.array([[6.0, 0.0, 0.0], [0.0, 20.0, 0.0]])
    centers, radii, normals = geometry.intersection_circles(center, others, radius=5.0)
    # two spheres of radius 5 with centres 6 apart meet in a circle of radius 4 about the midpoint
    assert centers[0] == pytest.approx([3.0, 0.0, 0.0])
    assert radii[0] == pytest.approx(4.0)
    assert normals[0] == pytest.approx([1.0, 0.0, 0.0])
    # 20 apart they do not meet yet: a zero-radius circle (invisible) at the midpoint
    assert radii[1] == 0.0
    assert centers[1] == pytest.approx([0.0, 10.0, 0.0])
    assert np.isfinite(normals).all()


def test_intersection_circle_at_the_moment_of_first_contact_is_a_point():
    _, radii, _ = geometry.intersection_circles(np.zeros(3), np.array([[8.0, 0.0, 0.0]]), radius=4.0)
    assert radii[0] == 0.0
