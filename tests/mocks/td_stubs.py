"""Minimal TD-shaped stubs for offline gizmo_math / drag-loop benches.

Enough for `matrix_col`, `camera_basis`, `unproject_ray`, and a fake drag
sync cost — not a full TouchDesigner runtime.
"""

from __future__ import annotations

import math


class FakePosition:
	__slots__ = ("x", "y", "z")

	def __init__(self, x=0.0, y=0.0, z=0.0):
		self.x = float(x)
		self.y = float(y)
		self.z = float(z)


class FakeMatrix:
	"""Column-major 4x4 matching TD's `M * v` / `m[row, col]` access."""

	__slots__ = ("_m",)

	def __init__(self, rows=None):
		if rows is None:
			self._m = [
				[1.0, 0.0, 0.0, 0.0],
				[0.0, 1.0, 0.0, 0.0],
				[0.0, 0.0, 1.0, 0.0],
				[0.0, 0.0, 0.0, 1.0],
			]
		else:
			# rows is four length-4 sequences in row-major storage of columns?
			# tdu.Matrix constructor takes four column vectors as 4-tuples in
			# object_world_pose_matrix: [right..., up..., fwd..., pos...]
			# each argument is a column (x,y,z,w).
			cols = [list(c) for c in rows]
			self._m = [[cols[c][r] for c in range(4)] for r in range(4)]

	def __getitem__(self, key):
		row, col = key
		return self._m[row][col]

	def __setitem__(self, key, value):
		row, col = key
		self._m[row][col] = float(value)

	def copy(self):
		out = FakeMatrix()
		out._m = [row[:] for row in self._m]
		return out

	def __mul__(self, other):
		if isinstance(other, FakePosition):
			x, y, z = other.x, other.y, other.z
			w = 1.0
			rx = self._m[0][0] * x + self._m[0][1] * y + self._m[0][2] * z + self._m[0][3] * w
			ry = self._m[1][0] * x + self._m[1][1] * y + self._m[1][2] * z + self._m[1][3] * w
			rz = self._m[2][0] * x + self._m[2][1] * y + self._m[2][2] * z + self._m[2][3] * w
			rw = self._m[3][0] * x + self._m[3][1] * y + self._m[3][2] * z + self._m[3][3] * w
			if abs(rw) > 1e-12:
				rx, ry, rz = rx / rw, ry / rw, rz / rw
			return FakePosition(rx, ry, rz)
		raise TypeError("FakeMatrix only multiplies FakePosition")


class FakePar:
	def __init__(self, value):
		self._value = value

	def eval(self):
		return self._value


class FakePars:
	def __init__(self, **kwargs):
		self._vals = dict(kwargs)

	def __getattr__(self, name):
		if name.startswith("_"):
			raise AttributeError(name)
		return FakePar(self._vals.get(name, 0.0))


class FakeCamera:
	"""Orthographic-ish stub: identity world, simple projection inverse."""

	def __init__(self, tx=0.0, ty=0.0, tz=6.0, fov=45.0):
		self.worldTransform = FakeMatrix()
		self.worldTransform[0, 3] = tx
		self.worldTransform[1, 3] = ty
		self.worldTransform[2, 3] = tz
		self.par = FakePars(fov=fov)

	def projectionInverse(self, res_w, res_h):
		# Map NDC (x,y,1) to a camera-space point on a plane at z=-1.
		# Enough for direction variety in benches; not a real TD frustum.
		aspect = float(res_w) / max(float(res_h), 1.0)
		m = FakeMatrix()
		m[0, 0] = aspect
		m[1, 1] = 1.0
		m[2, 2] = -1.0
		m[2, 3] = -1.0
		return m


def install_tdu(module_globals=None):
	"""Inject a tiny `tdu` namespace into gizmo_math's expectations."""
	import types
	import sys

	tdu = types.SimpleNamespace(Matrix=FakeMatrix, Position=FakePosition)
	sys.modules["tdu"] = tdu
	# gizmo_math references bare `tdu` at call time — also bind on the module.
	import gizmo_math as gm

	gm.tdu = tdu
	if module_globals is not None:
		module_globals["tdu"] = tdu
	return tdu


def fake_overlay_sync_cost(n_objects=8, n_selected=1, iters=200):
	"""CPU stand-in for overlay + bounds work on a drag tick.

	Not equal to TD `computeBounds`, but scales with selection/scene size so
	benches can compare drag-with-sync vs drag-math-only.
	"""
	acc = 0.0
	for _ in range(iters):
		for i in range(n_objects):
			# Cheap but non-trivial float work mimicking bounds + cage pose.
			x = float(i) * 0.37
			acc += math.sin(x) * math.cos(x + n_selected)
		for j in range(n_selected):
			acc += (j + 1) * 0.001
	return acc


def pick_all_aabbs(gm, origin, direction, boxes):
	"""Front-to-back AABB hits — mirrors `_pick_hits_at` math after bounds exist."""
	hits = []
	for path, bmin, bmax in boxes:
		t = gm.ray_vs_aabb(origin, direction, bmin, bmax)
		if t is not None:
			hits.append((t, path))
	hits.sort(key=lambda h: h[0])
	return [p for _t, p in hits]
