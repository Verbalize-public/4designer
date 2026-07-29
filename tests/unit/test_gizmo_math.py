"""Correctness tests for pure gizmo_math (no TouchDesigner)."""

from __future__ import annotations

import math

import gizmo_math as gm


def test_v_normalize_unit():
	n = gm.v_normalize((3.0, 0.0, 4.0))
	assert abs(gm.v_length(n) - 1.0) < 1e-9
	assert abs(n[0] - 0.6) < 1e-9
	assert abs(n[2] - 0.8) < 1e-9


def test_ray_vs_aabb_hit_front():
	origin = (0.0, 0.0, -5.0)
	direction = (0.0, 0.0, 1.0)
	t = gm.ray_vs_aabb(origin, direction, (-1.0, -1.0, -1.0), (1.0, 1.0, 1.0))
	assert t is not None
	assert abs(t - 4.0) < 1e-6


def test_ray_vs_aabb_miss():
	origin = (0.0, 0.0, -5.0)
	direction = (0.0, 0.0, 1.0)
	t = gm.ray_vs_aabb(origin, direction, (2.0, 2.0, -1.0), (3.0, 3.0, 1.0))
	assert t is None


def test_ray_vs_aabb_parallel_outside():
	origin = (2.0, 0.0, 0.0)
	direction = (0.0, 0.0, 1.0)
	assert gm.ray_vs_aabb(origin, direction, (-1.0, -1.0, -1.0), (1.0, 1.0, 1.0)) is None


def test_ray_vs_plane_hit():
	hit = gm.ray_vs_plane((0.0, 0.0, -2.0), (0.0, 0.0, 1.0), (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
	assert hit is not None
	assert abs(hit[2]) < 1e-9


def test_ray_vs_plane_behind():
	hit = gm.ray_vs_plane((0.0, 0.0, 2.0), (0.0, 0.0, 1.0), (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
	assert hit is None


def test_closest_t_on_ray_to_line():
	# Horizontal X handle at origin; ray from (0,2,-2) toward (0,0,1) direction-ish
	# Use ray looking at origin from +Y.
	t = gm.closest_t_on_ray_to_line(
		(0.0, 2.0, 0.0),
		(0.0, -1.0, 0.0),
		(0.0, 0.0, 0.0),
		(1.0, 0.0, 0.0),
	)
	assert t is not None
	assert abs(t) < 1e-6


def test_ray_line_distance_parallel():
	d = gm.ray_line_distance((0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
	assert abs(d - 1.0) < 1e-6


def test_ray_vs_disc_annulus():
	hit = gm.ray_vs_disc(
		(0.0, 0.0, -2.0),
		(0.0, 0.0, 1.0),
		(0.0, 0.0, 0.0),
		(0.0, 0.0, 1.0),
		radius=1.0,
		tolerance=0.15,
	)
	# Hit at origin center — distance 0 from center, not on ring.
	assert hit is None
	hit2 = gm.ray_vs_disc(
		(1.0, 0.0, -2.0),
		(0.0, 0.0, 1.0),
		(0.0, 0.0, 0.0),
		(0.0, 0.0, 1.0),
		radius=1.0,
		tolerance=0.15,
	)
	assert hit2 is not None


def test_signed_angle_in_plane_quarter_turn():
	ang = gm.signed_angle_in_plane((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
	assert abs(ang - 90.0) < 1e-4


def test_panel_uv_to_content_centered():
	# Panel 1280x720, content 1280x720 — identity.
	u_c, v_c = gm.panel_uv_to_content(0.5, 0.5, 1280, 720, 1280, 720)
	assert abs(u_c - 0.5) < 1e-6
	assert abs(v_c - 0.5) < 1e-6


def test_gizmo_screen_scale_increases_with_distance():
	near = gm.gizmo_screen_scale((0.0, 0.0, 0.0), (0.0, 0.0, 2.0), 45.0, 720, 90.0)
	far = gm.gizmo_screen_scale((0.0, 0.0, 0.0), (0.0, 0.0, 8.0), 45.0, 720, 90.0)
	assert far > near * 3.5


def test_snap_scalar_matches_ext_helper():
	# Mirror FourdesignerExt._snap_scalar without importing the extension (TD).
	def snap_scalar(v, step):
		if step is None or step <= 0:
			return v
		return round(v / step) * step

	assert snap_scalar(0.14, 0.1) == 0.1
	assert snap_scalar(0.16, 0.1) == 0.2
	assert snap_scalar(1.0, 0.0) == 1.0
