"""Throughput benches for pure gizmo_math pick loops."""

from __future__ import annotations

import gizmo_math as gm

from tests.mocks.td_stubs import pick_all_aabbs


def _make_grid_boxes(n=64, spacing=3.0, half=0.5):
	boxes = []
	side = int(math_ceil_sqrt(n))
	i = 0
	for z in range(side):
		for x in range(side):
			if i >= n:
				break
			cx = (x - side * 0.5) * spacing
			cz = (z - side * 0.5) * spacing
			bmin = (cx - half, -half, cz - half)
			bmax = (cx + half, half, cz + half)
			boxes.append(("obj_{}".format(i), bmin, bmax))
			i += 1
		if i >= n:
			break
	return boxes


def math_ceil_sqrt(n):
	s = int(n ** 0.5)
	return s if s * s >= n else s + 1


def test_bench_ray_vs_aabb_64(benchmark):
	boxes = _make_grid_boxes(64)
	origin = (0.0, 0.0, -20.0)
	direction = gm.v_normalize((0.15, 0.05, 1.0))

	def run():
		return pick_all_aabbs(gm, origin, direction, boxes)

	hits = benchmark(run)
	assert isinstance(hits, list)


def test_bench_ray_vs_aabb_256(benchmark):
	boxes = _make_grid_boxes(256)
	origin = (0.0, 0.0, -40.0)
	direction = gm.v_normalize((0.1, -0.05, 1.0))

	def run():
		return pick_all_aabbs(gm, origin, direction, boxes)

	benchmark(run)


def test_bench_closest_t_and_plane(benchmark):
	origin = (0.0, 2.0, -4.0)
	direction = gm.v_normalize((0.1, -0.2, 1.0))
	line_p = (0.0, 0.0, 0.0)
	line_d = (1.0, 0.0, 0.0)
	plane_p = (0.0, 0.0, 0.0)
	plane_n = (0.0, 1.0, 0.0)

	def run():
		acc = 0.0
		for i in range(200):
			o = (origin[0] + i * 0.001, origin[1], origin[2])
			t = gm.closest_t_on_ray_to_line(o, direction, line_p, line_d)
			hit = gm.ray_vs_plane(o, direction, plane_p, plane_n)
			if t is not None:
				acc += t
			if hit is not None:
				acc += hit[0]
		return acc

	benchmark(run)


def test_bench_gizmo_screen_scale(benchmark):
	cam = (0.0, 1.5, 6.0)

	def run():
		s = 0.0
		for i in range(500):
			g = (i * 0.01, 0.0, 0.0)
			s += gm.gizmo_screen_scale(cam, g, 45.0, 720.0, 90.0)
		return s

	benchmark(run)
