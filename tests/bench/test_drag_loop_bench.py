"""Drag-loop structure benches: math-only vs math+overlay-sync stand-in.

Quantifies finding #1 from docs/PERFORMANCE.md without TouchDesigner:
per-sample overlay/bounds work dominates vs pure handle math.
"""

from __future__ import annotations

import gizmo_math as gm

from tests.mocks.td_stubs import fake_overlay_sync_cost, install_tdu


def _axis_drag_tick(origin, direction, start_t, line_point, line_dir):
	"""One axis-translate sample — mirrors UpdateDrag axis branch math only."""
	t_now = gm.closest_t_on_ray_to_line(origin, direction, line_point, line_dir)
	if t_now is None or start_t is None:
		return None
	delta_scalar = t_now - start_t
	return gm.v_scale(line_dir, delta_scalar)


def test_bench_drag_math_only(benchmark):
	install_tdu()
	line_p = (0.0, 0.0, 0.0)
	line_d = (1.0, 0.0, 0.0)
	start_t = 0.0
	base_o = (0.0, 2.0, -5.0)
	base_d = gm.v_normalize((0.05, -0.15, 1.0))

	def run():
		acc = (0.0, 0.0, 0.0)
		for i in range(120):
			o = (base_o[0] + i * 0.002, base_o[1], base_o[2])
			delta = _axis_drag_tick(o, base_d, start_t, line_p, line_d)
			if delta is not None:
				acc = gm.v_add(acc, delta)
		return acc

	benchmark(run)


def test_bench_drag_with_overlay_sync(benchmark):
	"""Anti-pattern baseline: math + per-tick overlay/bounds stand-in."""
	install_tdu()
	line_p = (0.0, 0.0, 0.0)
	line_d = (1.0, 0.0, 0.0)
	start_t = 0.0
	base_o = (0.0, 2.0, -5.0)
	base_d = gm.v_normalize((0.05, -0.15, 1.0))

	def run():
		acc = (0.0, 0.0, 0.0)
		sync_acc = 0.0
		for i in range(120):
			o = (base_o[0] + i * 0.002, base_o[1], base_o[2])
			delta = _axis_drag_tick(o, base_d, start_t, line_p, line_d)
			if delta is not None:
				acc = gm.v_add(acc, delta)
			# Finding #1: sync on every UV sample (scaled down iters for bench speed).
			sync_acc += fake_overlay_sync_cost(n_objects=32, n_selected=2, iters=40)
		return acc, sync_acc

	benchmark(run)


def test_bench_drag_light_pose(benchmark):
	"""Post-optime tick: math + cheap gizmo tx write stand-in (no overlay)."""
	install_tdu()
	line_p = (0.0, 0.0, 0.0)
	line_d = (1.0, 0.0, 0.0)
	start_t = 0.0
	base_o = (0.0, 2.0, -5.0)
	base_d = gm.v_normalize((0.05, -0.15, 1.0))
	start_gizmo = (0.0, 0.0, 0.0)

	def run():
		acc = (0.0, 0.0, 0.0)
		gx, gy, gz = start_gizmo
		for i in range(120):
			o = (base_o[0] + i * 0.002, base_o[1], base_o[2])
			delta = _axis_drag_tick(o, base_d, start_t, line_p, line_d)
			if delta is not None:
				acc = gm.v_add(acc, delta)
				# Light pose: snapped-style tx write only (no overlay/bounds).
				gx = start_gizmo[0] + delta[0]
				gy = start_gizmo[1] + delta[1]
				gz = start_gizmo[2] + delta[2]
		return acc, (gx, gy, gz)

	benchmark(run)


def test_bench_pick_hits_after_bounds(benchmark):
	"""AABB sort after bounds already cached — cheap half of `_pick_hits_at`."""
	boxes = []
	for i in range(128):
		x = (i % 16) * 2.0
		z = (i // 16) * 2.0
		boxes.append(("p{}".format(i), (x - 0.4, -0.4, z - 0.4), (x + 0.4, 0.4, z + 0.4)))
	origin = (8.0, 0.0, -20.0)
	direction = gm.v_normalize((0.0, 0.0, 1.0))

	from tests.mocks.td_stubs import pick_all_aabbs

	def run():
		# Stand-in for full-scene bounds refresh cost before pick (finding #2).
		fake_overlay_sync_cost(n_objects=128, n_selected=0, iters=8)
		return pick_all_aabbs(gm, origin, direction, boxes)

	benchmark(run)
