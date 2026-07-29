"""4designer orientation view-cube — 26 clickable zones (faces/edges/corners).

Mirrors `gizmo_rig.py`: declarative `ZONES` shared with `fourdesigner_ext.py`
hit-test. Geometry is polygon-only (boxSOP) so it shows in a Render TOP. The
cube sits at the local origin; `cam_orient` orbits it with the same
yaw/pitch as `cam_edit`.
"""

from __future__ import annotations

import math

# Screen placement — single source of truth for compositor + hit-test rect.
CUBE_VIEWPORT_SIZE = 140
CUBE_MARGIN = 12
CUBE_RENDER_RES = 160

# Local geometry — 6 solid face plates form the visible cube; 26 ZONES still
# drive picking (edge/corner hits use AABBs even when those geos are hidden).
CUBE_HALF = 0.5
FACE_THICK = 0.08
FACE_SIZE = 1.0  # full face — no seam gaps
EDGE_LEN = 0.55
EDGE_THICK = 0.14
CORNER_SIZE = 0.18
# Edge/corner geos stay in the network for optional debug; not drawn by default.
DRAW_EDGE_CORNER = False

HIGHLIGHT_COLOR = (1.0, 0.92, 0.15)
FACE_COLOR = {
	"x": (0.82, 0.22, 0.22),
	"y": (0.22, 0.72, 0.28),
	"z": (0.22, 0.45, 0.90),
}
EDGE_COLOR = (0.50, 0.50, 0.53)
CORNER_COLOR = (0.68, 0.68, 0.70)

# cam_orient distance from cube origin (must clear the cube).
ORIENT_CAM_DIST = 2.4
ORIENT_ORTHO_WIDTH = 1.85


def _v_norm(v):
	x, y, z = v
	length = math.sqrt(x * x + y * y + z * z)
	if length < 1e-9:
		return (0.0, 0.0, 1.0)
	return (x / length, y / length, z / length)


def direction_to_yaw_pitch(direction):
	"""Yaw/pitch (degrees) so the orbit camera sits along `direction` from pivot.

	Same convention as `FourdesignerExt.SeedCamera` / `_apply_orbit_camera`:
	offset = (cos(p)*sin(y), sin(p), cos(p)*cos(y)).
	"""
	d = _v_norm(direction)
	dist = max(math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]), 1e-6)
	yaw = math.degrees(math.atan2(d[0], d[2]))
	pitch = math.degrees(math.asin(max(-1.0, min(1.0, d[1] / dist))))
	# Clamp away from exact poles so yaw stays stable after a Top/Bottom snap.
	pitch = max(-89.0, min(89.0, pitch))
	return yaw, pitch


def _build_zones():
	zones = []
	# 6 faces — outward normals are camera-from directions.
	faces = (
		("face_px", (1.0, 0.0, 0.0), "x"),
		("face_nx", (-1.0, 0.0, 0.0), "x"),
		("face_py", (0.0, 1.0, 0.0), "y"),
		("face_ny", (0.0, -1.0, 0.0), "y"),
		("face_pz", (0.0, 0.0, 1.0), "z"),
		("face_nz", (0.0, 0.0, -1.0), "z"),
	)
	for zid, normal, axis in faces:
		n = _v_norm(normal)
		center = (n[0] * CUBE_HALF, n[1] * CUBE_HALF, n[2] * CUBE_HALF)
		# Thin plate: full size on the two tangential axes, FACE_THICK along normal.
		size = [FACE_SIZE, FACE_SIZE, FACE_SIZE]
		ax = 0 if abs(n[0]) > 0.5 else (1 if abs(n[1]) > 0.5 else 2)
		size[ax] = FACE_THICK
		half = (size[0] * 0.5, size[1] * 0.5, size[2] * 0.5)
		zones.append({
			"id": zid,
			"kind": "face",
			"direction": n,
			"center": center,
			"size": tuple(size),
			"aabb_min": (center[0] - half[0], center[1] - half[1], center[2] - half[2]),
			"aabb_max": (center[0] + half[0], center[1] + half[1], center[2] + half[2]),
			"color": FACE_COLOR[axis],
			"geo": "zone_" + zid,
		})

	# 12 edges — average of two face normals.
	edge_axes = (
		("edge_px_py", (1.0, 1.0, 0.0)),
		("edge_px_ny", (1.0, -1.0, 0.0)),
		("edge_nx_py", (-1.0, 1.0, 0.0)),
		("edge_nx_ny", (-1.0, -1.0, 0.0)),
		("edge_px_pz", (1.0, 0.0, 1.0)),
		("edge_px_nz", (1.0, 0.0, -1.0)),
		("edge_nx_pz", (-1.0, 0.0, 1.0)),
		("edge_nx_nz", (-1.0, 0.0, -1.0)),
		("edge_py_pz", (0.0, 1.0, 1.0)),
		("edge_py_nz", (0.0, 1.0, -1.0)),
		("edge_ny_pz", (0.0, -1.0, 1.0)),
		("edge_ny_nz", (0.0, -1.0, -1.0)),
	)
	for zid, raw in edge_axes:
		n = _v_norm(raw)
		center = (n[0] * CUBE_HALF, n[1] * CUBE_HALF, n[2] * CUBE_HALF)
		# Elongate along the axis that is ~0 in the edge normal (the edge tangent).
		size = [EDGE_THICK, EDGE_THICK, EDGE_THICK]
		zero_axis = min(range(3), key=lambda i: abs(raw[i]))
		size[zero_axis] = EDGE_LEN
		half = (size[0] * 0.5, size[1] * 0.5, size[2] * 0.5)
		zones.append({
			"id": zid,
			"kind": "edge",
			"direction": n,
			"center": center,
			"size": tuple(size),
			"aabb_min": (center[0] - half[0], center[1] - half[1], center[2] - half[2]),
			"aabb_max": (center[0] + half[0], center[1] + half[1], center[2] + half[2]),
			"color": EDGE_COLOR,
			"geo": "zone_" + zid,
		})

	# 8 corners — diagonals.
	for ix in (-1.0, 1.0):
		for iy in (-1.0, 1.0):
			for iz in (-1.0, 1.0):
				raw = (ix, iy, iz)
				n = _v_norm(raw)
				sid = "corner_{}_{}_{}".format(
					"p" if ix > 0 else "n",
					"p" if iy > 0 else "n",
					"p" if iz > 0 else "n",
				)
				center = (n[0] * CUBE_HALF, n[1] * CUBE_HALF, n[2] * CUBE_HALF)
				s = CORNER_SIZE
				half = s * 0.5
				zones.append({
					"id": sid,
					"kind": "corner",
					"direction": n,
					"center": center,
					"size": (s, s, s),
					"aabb_min": (center[0] - half, center[1] - half, center[2] - half),
					"aabb_max": (center[0] + half, center[1] + half, center[2] + half),
					"color": CORNER_COLOR,
					"geo": "zone_" + sid,
				})
	return zones


ZONES = _build_zones()
ZONES_BY_ID = {z["id"]: z for z in ZONES}


def _ensure_mat(parent, zone):
	name = "mat_" + zone["id"]
	mat = parent.op(name)
	if mat is None:
		mat = parent.create(constantMAT, name)
	r, g, b = zone["color"]
	mat.par.colorr, mat.par.colorg, mat.par.colorb = r, g, b
	return mat


def _build_zone_geo(child, zone):
	box = child.create(boxSOP, "box1")
	sx, sy, sz = zone["size"]
	cx, cy, cz = zone["center"]
	box.par.sizex, box.par.sizey, box.par.sizez = sx, sy, sz
	box.par.tx, box.par.ty, box.par.tz = cx, cy, cz
	out = child.create(outSOP, "out1")
	out.inputConnectors[0].connect(box)
	box.display = box.render = False
	out.display = out.render = True


def build_orient_cube(parent, name="orient_cube"):
	"""Create (or replace) the pivot nullCOMP + per-zone Geometry children.

	Faces are always drawn. Edge/corner geos are built for hit-AABB parity but
	hidden unless DRAW_EDGE_CORNER is True — keeps the cube looking solid.
	"""
	existing = parent.op(name)
	if existing is not None:
		existing.destroy()
	root = parent.create(nullCOMP, name)
	root.pickable = False
	for old in list(root.children):
		old.destroy()

	for i, zone in enumerate(ZONES):
		child = root.create(geometryCOMP, zone["geo"])
		child.nodeX = (i % 6) * 140
		child.nodeY = -(i // 6) * 140
		for default_child in list(child.children):
			default_child.destroy()
		_build_zone_geo(child, zone)
		mat = _ensure_mat(root, zone)
		child.par.material = mat.path
		child.pickable = False
		if zone["kind"] == "face":
			child.render = True
		else:
			child.render = bool(DRAW_EDGE_CORNER)

	set_orient_highlight(root, None)
	return root


def orient_geometry_paths(root):
	"""Visible Geometry COMP paths for the orient Render TOP (faces by default)."""
	if root is None:
		return []
	paths = []
	for zone in ZONES:
		if zone["kind"] != "face" and not DRAW_EDGE_CORNER:
			continue
		child = root.op(zone["geo"])
		if child is not None:
			paths.append(child.path)
	return paths


def wire_orient_render(rend, root):
	"""Assign visible orient zone geos to a Render TOP as an OP list."""
	if rend is None or root is None:
		return
	ops = []
	for zone in ZONES:
		if zone["kind"] != "face" and not DRAW_EDGE_CORNER:
			continue
		child = root.op(zone["geo"])
		if child is not None:
			child.render = True
			ops.append(child)
	if not ops:
		return
	try:
		rend.par.geometry = ops
	except Exception:
		try:
			rend.par.geometry = " ".join(o.path for o in ops)
		except Exception:
			pass


def set_orient_highlight(root, active_id):
	"""Yellow-tint one zone material; restore others."""
	if root is None:
		return
	for zone in ZONES:
		mat = root.op("mat_" + zone["id"])
		if mat is None:
			continue
		r, g, b = HIGHLIGHT_COLOR if zone["id"] == active_id else zone["color"]
		mat.par.colorr, mat.par.colorg, mat.par.colorb = r, g, b


def screen_rect(res_w, res_h, size=None, margin=None):
	"""Bottom-right pixel rect (x0,y0,x1,y1) in content/image space, y-up.

	Kept for docs/compat; live picking now uses the `ui_orient` panel's own u/v.
	"""
	size = CUBE_VIEWPORT_SIZE if size is None else size
	margin = CUBE_MARGIN if margin is None else margin
	x1 = float(res_w) - margin
	x0 = x1 - size
	y0 = float(margin)
	y1 = y0 + size
	return x0, y0, x1, y1


def build_orient_panel(parent, render_top, name="ui_orient"):
	"""Dock a small Container showing `render_top` in the parent's bottom-right."""
	existing = parent.op(name)
	if existing is not None:
		existing.destroy()
	size = int(CUBE_VIEWPORT_SIZE)
	margin = int(CUBE_MARGIN)
	root = parent.create(containerCOMP, name)
	root.par.align = "none"
	root.par.hmode = "fixed"
	root.par.vmode = "fixed"
	root.par.w = size
	root.par.h = size
	# Absolute bottom-right inside parent (origin = bottom-left).
	root.par.leftanchor = 0.0
	root.par.rightanchor = 0.0
	root.par.bottomanchor = 0.0
	root.par.topanchor = 0.0
	root.par.horigin = 0.0
	root.par.vorigin = 0.0
	root.par.x = int(parent.par.w.eval()) - margin - size
	root.par.y = margin
	root.par.layer = 6.0
	root.par.display = True
	try:
		root.par.bgalpha = 0.0
	except Exception:
		pass
	root.par.top = render_top.path
	root.par.topfill = "best"
	root.par.uvbuttonsleft = True
	root.par.mousewheel = False
	try:
		root.par.reposition = "off"
	except Exception:
		pass
	return root
