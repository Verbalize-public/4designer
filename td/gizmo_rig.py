"""4designer gizmo rig — one pivot Geometry COMP + per-axis handle children.

`HANDLES` is the single source of truth shared with `fourdesigner_ext.py`'s
hit-test dispatcher: translate and scale reuse the exact same rods/plane-chips
(only the write target differs), rotate gets its own rings. Nesting handle
Geometry COMPs inside the pivot `gizmo1` parents them to it (TD 3D hierarchy
is network nesting — docs.derivative.ca/3D_Parenting), so moving/rotating
`gizmo1` moves the whole rig as one unit.

Gizmo geo is polygon-only (tubeSOP rods, boxSOP chips, merged boxSOP rings):
Line/Circle SOPs do not reliably appear in a Render TOP. Parameter names
(`rad1`/`rad2`, `orient`, `sizex`/`sizey`/`sizez`) were verified live.
"""

from __future__ import annotations


def _gizmo_math():
	return me.parent().op("gizmo_math").module


AXIS_VEC = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
AXIS_COLOR = {"x": (0.85, 0.2, 0.2), "y": (0.25, 0.8, 0.25), "z": (0.25, 0.5, 0.95)}
HIGHLIGHT_COLOR = (1.0, 0.92, 0.15)

ROD_INNER = 0.15
ROD_LENGTH = 1.0
RING_RADIUS = 1.0
# >= half of RING_THICK so the hit annulus matches (or exceeds) the visual ring.
RING_TOLERANCE = 0.12
PLANE_OFFSET = 0.35
PLANE_SIZE = 0.28
# Long enough that, after screen-constant gizmo scale, the guide reads as infinite.
GUIDE_HALF_LENGTH = 2000.0
GUIDE_RADIUS = 0.025

# Snap-plane grid: unit cell in local space; set_plane_grid scales the COMP so
# one local cell maps to the world snap step (after gizmo screen-constant scale).
GRID_HALF_CELLS = 20
GRID_CELL_LOCAL = 1.0
GRID_LINE_RADIUS = 0.02
GRID_LINE_HALF = GRID_HALF_CELLS * GRID_CELL_LOCAL

# (plane name) -> (axis a, axis b, plane normal axis)
_PLANE_DEFS = {"xy": ("x", "y", "z"), "yz": ("y", "z", "x"), "zx": ("z", "x", "y")}


def _build_handles():
	handles = []
	for ax in ("x", "y", "z"):
		handles.append({
			"id": "axis_" + ax,
			"kind": "axis",
			"axis": AXIS_VEC[ax],
			"color": AXIS_COLOR[ax],
			"modes": ("translate", "scale"),
			"write": {"translate": ("t" + ax,), "scale": ("s" + ax,)},
			"geo": "handle_axis_" + ax,
		})
	for pname, (a, b, n) in _PLANE_DEFS.items():
		handles.append({
			"id": "plane_" + pname,
			"kind": "plane",
			"normal": AXIS_VEC[n],
			"axes": (a, b),
			"color": AXIS_COLOR[n],
			"modes": ("translate", "scale"),
			"write": {"translate": ("t" + a, "t" + b), "scale": ("s" + a, "s" + b)},
			"geo": "handle_plane_" + pname,
		})
	for ax in ("x", "y", "z"):
		handles.append({
			"id": "disc_" + ax,
			"kind": "disc",
			"normal": AXIS_VEC[ax],
			"radius": RING_RADIUS,
			"tolerance": RING_TOLERANCE,
			"color": AXIS_COLOR[ax],
			"modes": ("rotate",),
			"write": {"rotate": ("r" + ax,)},
			"geo": "handle_disc_" + ax,
		})
	return handles


HANDLES = _build_handles()
HANDLES_BY_ID = {h["id"]: h for h in HANDLES}


def _scaled(vec, s):
	return vec[0] * s, vec[1] * s, vec[2] * s


def _ensure_mat(gizmo, handle):
	name = "mat_" + handle["id"]
	mat = gizmo.op(name)
	if mat is None:
		# constantMAT is unlit — handles stay saturated regardless of scene lights.
		mat = gizmo.create(constantMAT, name)
	r, g, b = handle["color"]
	mat.par.colorr, mat.par.colorg, mat.par.colorb = r, g, b
	return mat


# Polygon-only builders: Line/Circle SOPs do not show in Render TOP without
# special wireframe materials. Tubes + boxes render reliably as solid polys.
# Radii are in gizmo-local units; screen-constant scale is typically ~0.5–0.7,
# so 0.09 local ≈ 0.05–0.06 world — clearly visible at 1280×720.
TUBE_RADIUS = 0.12
TUBE_HEIGHT = ROD_LENGTH - ROD_INNER  # 0.85
PLANE_THICK = 0.08
RING_SEGMENTS = 16
RING_THICK = 0.1


def _build_axis_geo(child, handle):
	"""Cylinder rod along the handle axis (tubeSOP)."""
	ax = next(k for k, v in AXIS_VEC.items() if v == handle["axis"])
	tube = child.create(tubeSOP, "tube1")
	tube.par.rad1 = tube.par.rad2 = TUBE_RADIUS
	tube.par.height = TUBE_HEIGHT
	tube.par.orient = ax
	# Center the tube between ROD_INNER and ROD_LENGTH along the axis.
	mid = (ROD_INNER + ROD_LENGTH) * 0.5
	tube.par.tx, tube.par.ty, tube.par.tz = _scaled(handle["axis"], mid)
	out = child.create(outSOP, "out1")
	out.inputConnectors[0].connect(tube)
	tube.display = tube.render = False
	out.display = out.render = True


def _build_plane_geo(child, handle):
	"""Thin box chip in the plane (boxSOP)."""
	a, b = handle["axes"]
	center = {"x": 0.0, "y": 0.0, "z": 0.0}
	size = {"x": PLANE_THICK, "y": PLANE_THICK, "z": PLANE_THICK}
	for ax in (a, b):
		center[ax] = PLANE_OFFSET
		size[ax] = PLANE_SIZE
	box = child.create(boxSOP, "box1")
	box.par.sizex, box.par.sizey, box.par.sizez = size["x"], size["y"], size["z"]
	box.par.tx, box.par.ty, box.par.tz = center["x"], center["y"], center["z"]
	out = child.create(outSOP, "out1")
	out.inputConnectors[0].connect(box)
	box.display = box.render = False
	out.display = out.render = True


def _build_disc_geo(child, handle):
	"""Ring approximated by merged box segments (boxSOP + mergeSOP)."""
	import math

	normal_axis = next(ax for ax, v in AXIS_VEC.items() if v == handle["normal"])
	plane = {"x": "yz", "y": "xz", "z": "xy"}[normal_axis]
	radius = handle["radius"]
	merge = child.create(mergeSOP, "merge1")
	for i in range(RING_SEGMENTS):
		seg = child.create(boxSOP, "seg" + str(i))
		seg.par.sizex = seg.par.sizey = seg.par.sizez = RING_THICK
		angle = i * (360.0 / RING_SEGMENTS)
		ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))
		if plane == "yz":
			seg.par.ty, seg.par.tz = radius * ca, radius * sa
		elif plane == "xz":
			seg.par.tx, seg.par.tz = radius * ca, radius * sa
		else:
			seg.par.tx, seg.par.ty = radius * ca, radius * sa
		seg.display = seg.render = False
		merge.inputConnectors[i].connect(seg)
	out = child.create(outSOP, "out1")
	out.inputConnectors[0].connect(merge)
	merge.display = merge.render = False
	out.display = out.render = True


_BUILDERS = {"axis": _build_axis_geo, "plane": _build_plane_geo, "disc": _build_disc_geo}


def _build_guide_line(child, axis_letter):
	"""Thin tube centered on the origin, spanning ±GUIDE_HALF_LENGTH along axis."""
	tube = child.create(tubeSOP, "tube1")
	tube.par.rad1 = tube.par.rad2 = GUIDE_RADIUS
	tube.par.height = GUIDE_HALF_LENGTH * 2.0
	tube.par.orient = axis_letter
	tube.par.tx = tube.par.ty = tube.par.tz = 0.0
	out = child.create(outSOP, "out1")
	out.inputConnectors[0].connect(tube)
	tube.display = tube.render = False
	out.display = out.render = True


def _ensure_guide_mat(gizmo, axis_letter):
	name = "mat_guide_" + axis_letter
	mat = gizmo.op(name)
	if mat is None:
		mat = gizmo.create(constantMAT, name)
	r, g, b = AXIS_COLOR[axis_letter]
	mat.par.colorr, mat.par.colorg, mat.par.colorb = r, g, b
	return mat


def _ensure_grid_mat(gizmo, plane_name):
	"""Dim axis-tinted material for the snap plane grid (normal-axis color)."""
	name = "mat_grid_" + plane_name
	mat = gizmo.op(name)
	if mat is None:
		mat = gizmo.create(constantMAT, name)
	_a, _b, n = _PLANE_DEFS[plane_name]
	r, g, b = AXIS_COLOR[n]
	# Dim so the grid reads as overlay, not solid rods.
	mat.par.colorr, mat.par.colorg, mat.par.colorb = r * 0.55, g * 0.55, b * 0.55
	try:
		mat.par.alpha = 0.55
	except Exception:
		pass
	return mat


def _tube_along(child, name, orient_axis, length, center):
	"""Thin tubeSOP along orient_axis, centered at `center` dict {x,y,z}."""
	tube = child.create(tubeSOP, name)
	tube.par.rad1 = tube.par.rad2 = GRID_LINE_RADIUS
	tube.par.height = length
	tube.par.orient = orient_axis
	tube.par.tx, tube.par.ty, tube.par.tz = center["x"], center["y"], center["z"]
	tube.display = tube.render = False
	return tube


def _build_plane_grid_geo(child, plane_name):
	"""Polygon grid of thin tubes on a unit-cell lattice in the named plane.

	Coverage is ±GRID_HALF_CELLS cells of size GRID_CELL_LOCAL. `set_plane_grid`
	scales the Geometry COMP so one local cell equals the world snap step.
	"""
	a, b, _n = _PLANE_DEFS[plane_name]
	merge = child.create(mergeSOP, "merge1")
	idx = 0
	span = GRID_LINE_HALF * 2.0
	# Lines parallel to axis a (vary along b).
	for i in range(-GRID_HALF_CELLS, GRID_HALF_CELLS + 1):
		center = {"x": 0.0, "y": 0.0, "z": 0.0}
		center[b] = i * GRID_CELL_LOCAL
		tube = _tube_along(child, "a" + str(i + GRID_HALF_CELLS), a, span, center)
		merge.inputConnectors[idx].connect(tube)
		idx += 1
	# Lines parallel to axis b (vary along a).
	for i in range(-GRID_HALF_CELLS, GRID_HALF_CELLS + 1):
		center = {"x": 0.0, "y": 0.0, "z": 0.0}
		center[a] = i * GRID_CELL_LOCAL
		tube = _tube_along(child, "b" + str(i + GRID_HALF_CELLS), b, span, center)
		merge.inputConnectors[idx].connect(tube)
		idx += 1
	out = child.create(outSOP, "out1")
	out.inputConnectors[0].connect(merge)
	merge.display = merge.render = False
	out.display = out.render = True


def build_gizmo_rig(parent, name="gizmo1"):
	"""Create (or replace) the pivot Null COMP + per-axis handle Geometry children.

	Pivot must be a nullCOMP (transform-only). Nesting Geometry COMPs under
	another Geometry COMP does not reliably render when children are listed in
	a Render TOP — verified live. nullCOMP parenting preserves world TRS.
	"""
	existing = parent.op(name)
	if existing is not None:
		existing.destroy()
	gizmo = parent.create(nullCOMP, name)
	gizmo.pickable = False
	for old in list(gizmo.children):
		old.destroy()

	for i, handle in enumerate(HANDLES):
		child = gizmo.create(geometryCOMP, handle["geo"])
		child.nodeX = (i % 3) * 160
		child.nodeY = -(i // 3) * 160
		for default_child in list(child.children):
			default_child.destroy()
		_BUILDERS[handle["kind"]](child, handle)
		mat = _ensure_mat(gizmo, handle)
		child.par.material = mat.path
		child.pickable = False

	for i, ax in enumerate(("x", "y", "z")):
		child = gizmo.create(geometryCOMP, "guide_" + ax)
		child.nodeX = (i % 3) * 160
		child.nodeY = -640
		for default_child in list(child.children):
			default_child.destroy()
		_build_guide_line(child, ax)
		mat = _ensure_guide_mat(gizmo, ax)
		child.par.material = mat.path
		child.pickable = False
		child.render = False

	for i, pname in enumerate(("xy", "yz", "zx")):
		child = gizmo.create(geometryCOMP, "grid_" + pname)
		child.nodeX = (i % 3) * 160
		child.nodeY = -800
		for default_child in list(child.children):
			default_child.destroy()
		_build_plane_grid_geo(child, pname)
		mat = _ensure_grid_mat(gizmo, pname)
		child.par.material = mat.path
		child.pickable = False
		child.render = False

	set_gizmo_mode(gizmo, "translate")
	set_guide_lines(gizmo, ())
	set_plane_grid(gizmo, None, False, (0.1, 0.1, 0.1), 1.0)
	return gizmo


def set_gizmo_mode(gizmo, mode):
	"""Show only the handles valid for `mode` ('translate' | 'scale' | 'rotate')."""
	for handle in HANDLES:
		child = gizmo.op(handle["geo"])
		if child is not None:
			child.render = mode in handle["modes"]


def set_gizmo_highlight(gizmo, active_ids):
	"""Tint handle materials yellow when their id is in `active_ids`, else restore."""
	active = set(active_ids) if active_ids else set()
	for handle in HANDLES:
		mat = gizmo.op("mat_" + handle["id"])
		if mat is None:
			continue
		r, g, b = HIGHLIGHT_COLOR if handle["id"] in active else handle["color"]
		mat.par.colorr, mat.par.colorg, mat.par.colorb = r, g, b


def set_guide_lines(gizmo, axes):
	"""Show only the guide tubes whose axis letter is in `axes`."""
	wanted = set(axes) if axes else set()
	for ax in ("x", "y", "z"):
		child = gizmo.op("guide_" + ax)
		if child is not None:
			child.render = ax in wanted


def _plane_name_from_handle_id(plane_id):
	"""'plane_xy' → 'xy'; bare 'xy' also accepted."""
	if not plane_id:
		return None
	if plane_id.startswith("plane_"):
		return plane_id[6:]
	if plane_id in _PLANE_DEFS:
		return plane_id
	return None


def set_plane_grid(gizmo, plane_id, visible, steps, gizmo_scale):
	"""Show snap grid on one translate plane; hide others.

	`steps` is (sx, sy, sz) world snap sizes. `gizmo_scale` is the gizmo's
	uniform screen-constant scale so tube spacing maps to world steps.
	Tubes are re-spaced in-place (no COMP scale) so line thickness stays readable.
	"""
	wanted = _plane_name_from_handle_id(plane_id) if visible else None
	scale = max(float(gizmo_scale) if gizmo_scale else 1.0, 1e-4)
	sx, sy, sz = steps if steps is not None else (0.1, 0.1, 0.1)
	step_by_axis = {"x": float(sx), "y": float(sy), "z": float(sz)}
	for pname, (a, b, _n) in _PLANE_DEFS.items():
		child = gizmo.op("grid_" + pname)
		if child is None:
			continue
		show = wanted == pname
		child.render = show
		if not show:
			continue
		# Keep COMP scale identity — spacing is written onto tube SOPs directly.
		child.par.sx = child.par.sy = child.par.sz = 1.0
		local_a = max(step_by_axis[a], 1e-6) / scale
		local_b = max(step_by_axis[b], 1e-6) / scale
		span_a = GRID_HALF_CELLS * local_a * 2.0
		span_b = GRID_HALF_CELLS * local_b * 2.0
		# Lines parallel to axis a (vary along b).
		for i in range(-GRID_HALF_CELLS, GRID_HALF_CELLS + 1):
			tube = child.op("a" + str(i + GRID_HALF_CELLS))
			if tube is None:
				continue
			tube.par.height = span_a
			center = {"x": 0.0, "y": 0.0, "z": 0.0}
			center[b] = i * local_b
			tube.par.tx, tube.par.ty, tube.par.tz = center["x"], center["y"], center["z"]
		# Lines parallel to axis b (vary along a).
		for i in range(-GRID_HALF_CELLS, GRID_HALF_CELLS + 1):
			tube = child.op("b" + str(i + GRID_HALF_CELLS))
			if tube is None:
				continue
			tube.par.height = span_b
			center = {"x": 0.0, "y": 0.0, "z": 0.0}
			center[a] = i * local_a
			tube.par.tx, tube.par.ty, tube.par.tz = center["x"], center["y"], center["z"]


def handle_axes_for_highlight(handle):
	"""Axis letters whose guide lines accompany a hovered/active handle."""
	if handle["kind"] == "axis":
		ax = next(k for k, v in AXIS_VEC.items() if v == handle["axis"])
		return {ax}
	if handle["kind"] == "plane":
		return set(handle["axes"])
	ax = next(k for k, v in AXIS_VEC.items() if v == handle["normal"])
	return {ax}


def gizmo_uniform_scale(gizmo):
	"""Gizmo's own current display scale (driven per-frame by `gizmo_screen_scale`)."""
	try:
		return float(gizmo.par.sx.eval())
	except Exception:
		return 1.0


def handle_world_geometry(gizmo, handle):
	"""World-space geometry for hit-testing one handle, given the gizmo's current pose.

	Values are pre-scaled by the gizmo's current screen-constant scale so
	`fourdesigner_ext.py`'s hit-test/drag math never has to re-derive rig
	constants — this module owns the rig's own geometric shape, the ext owns
	dispatch + parameter writes.
	"""
	gm = _gizmo_math()
	origin = gm.object_world_position(gizmo)
	scale = gizmo_uniform_scale(gizmo)
	if handle["kind"] == "axis":
		direction = gm.object_axis_world(gizmo, handle["axis"])
		return {
			"kind": "axis",
			"point": origin,
			"direction": direction,
			"t_min": ROD_INNER * scale,
			"t_max": ROD_LENGTH * scale,
		}
	if handle["kind"] == "plane":
		normal = gm.object_axis_world(gizmo, handle["normal"])
		a_dir = gm.object_axis_world(gizmo, AXIS_VEC[handle["axes"][0]])
		b_dir = gm.object_axis_world(gizmo, AXIS_VEC[handle["axes"][1]])
		center = gm.v_add(origin, gm.v_scale(gm.v_add(a_dir, b_dir), PLANE_OFFSET * scale))
		return {
			"kind": "plane",
			"point": center,
			"normal": normal,
			"a_dir": a_dir,
			"b_dir": b_dir,
			# True half-extent of the chip + small slack for easier picking.
			"half": (PLANE_SIZE * scale) * 0.5 * 1.15,
		}
	normal = gm.object_axis_world(gizmo, handle["normal"])
	return {
		"kind": "disc",
		"center": origin,
		"normal": normal,
		"radius": handle["radius"] * scale,
		"tolerance": handle["tolerance"] * scale,
	}
