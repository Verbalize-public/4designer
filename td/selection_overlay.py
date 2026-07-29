"""4designer selection overlay — AABB edge cages + proxy select tint.

Selected objects get a yellow wire box on the transparent `render_gizmo` pass
so selection stays visible in Select mode (gizmo handles hidden) and with
multiselect. Polygon-only tubes (same Render TOP constraint as gizmo_rig).
"""

from __future__ import annotations

# Softer than gizmo-handle hover so cages read as outline, not solid rods.
HIGHLIGHT_COLOR = (1.0, 0.92, 0.15)
HIGHLIGHT_ALPHA = 0.65
# Local radius on the unit (±0.5) cage; keep thin after non-uniform AABB scale.
EDGE_RADIUS = 0.006
EDGE_LENGTH = 1.0  # unit cube edge length


def _sanitize_name(path):
	safe = path.replace("/", "_").replace(".", "_").lstrip("_")
	if not safe:
		safe = "anon"
	return "sel_" + safe[:80]


def _clear_children(comp):
	for c in list(comp.children):
		try:
			c.destroy()
		except Exception:
			pass


def _ensure_mat(parent, name, color, alpha=1.0):
	mat = parent.op(name)
	if mat is None:
		mat = parent.create(constantMAT, name)
	r, g, b = color
	mat.par.colorr, mat.par.colorg, mat.par.colorb = r, g, b
	try:
		mat.par.alpha = float(alpha)
	except Exception:
		pass
	try:
		mat.par.blend = True
	except Exception:
		pass
	try:
		mat.par.blending = True
	except Exception:
		pass
	return mat


def _edge_tube(child, name, orient, center):
	"""Unit-length tube along `orient` ('x'|'y'|'z') centered at local `center`."""
	tube = child.create(tubeSOP, name)
	tube.par.rad1 = tube.par.rad2 = EDGE_RADIUS
	tube.par.height = EDGE_LENGTH
	tube.par.orient = orient
	tube.par.tx, tube.par.ty, tube.par.tz = center
	tube.display = tube.render = False
	return tube


def build_aabb_cage(child):
	"""Unit AABB wire box (±0.5) as 12 tubeSOP edges + merge + out."""
	_clear_children(child)
	merge = child.create(mergeSOP, "merge1")
	# 4 edges along X (y,z = ±0.5), 4 along Y, 4 along Z.
	edges = []
	for y in (-0.5, 0.5):
		for z in (-0.5, 0.5):
			edges.append(("x", (0.0, y, z)))
	for x in (-0.5, 0.5):
		for z in (-0.5, 0.5):
			edges.append(("y", (x, 0.0, z)))
	for x in (-0.5, 0.5):
		for y in (-0.5, 0.5):
			edges.append(("z", (x, y, 0.0)))
	for i, (orient, center) in enumerate(edges):
		tube = _edge_tube(child, "e" + str(i), orient, center)
		merge.inputConnectors[i].connect(tube)
	out = child.create(outSOP, "out1")
	out.inputConnectors[0].connect(merge)
	merge.display = merge.render = False
	out.display = out.render = True


def ensure_selection_root(parent, name="selection1"):
	"""Create (or return) the nullCOMP that holds selection cage Geometry children."""
	root = parent.op(name)
	if root is None:
		root = parent.create(nullCOMP, name)
	root.pickable = False
	_ensure_mat(root, "mat_selection", HIGHLIGHT_COLOR, alpha=HIGHLIGHT_ALPHA)
	return root


def clear_selection_overlays(root):
	if root is None:
		return
	_clear_children(root)


def _ensure_cage(root, path):
	name = _sanitize_name(path)
	child = root.op(name)
	if child is None:
		child = root.create(geometryCOMP, name)
		build_aabb_cage(child)
		mat = root.op("mat_selection")
		if mat is None:
			mat = _ensure_mat(root, "mat_selection", HIGHLIGHT_COLOR, alpha=HIGHLIGHT_ALPHA)
		child.par.material = mat.path
		child.pickable = False
	return child


def _pose_cage(child, bmin, bmax):
	sx = max(float(bmax[0]) - float(bmin[0]), 1e-4)
	sy = max(float(bmax[1]) - float(bmin[1]), 1e-4)
	sz = max(float(bmax[2]) - float(bmin[2]), 1e-4)
	child.par.tx = 0.5 * (float(bmin[0]) + float(bmax[0]))
	child.par.ty = 0.5 * (float(bmin[1]) + float(bmax[1]))
	child.par.tz = 0.5 * (float(bmin[2]) + float(bmax[2]))
	child.par.rx = child.par.ry = child.par.rz = 0.0
	child.par.sx, child.par.sy, child.par.sz = sx, sy, sz
	child.render = True
	try:
		child.display = True
	except Exception:
		pass


def sync_selection_overlays(root, entries):
	"""Pose one AABB cage per entry; hide cages not in the active set.

	`entries` is a list of dicts with keys `path`, `min`, `max` (world AABB).
	"""
	if root is None:
		return
	active = set()
	for entry in entries or ():
		path = entry.get("path")
		bmin, bmax = entry.get("min"), entry.get("max")
		if not path or bmin is None or bmax is None:
			continue
		child = _ensure_cage(root, path)
		_pose_cage(child, bmin, bmax)
		active.add(child.name)
	for child in root.children:
		try:
			if child.family != "COMP" or not child.name.startswith("sel_"):
				continue
			if child.name not in active:
				child.render = False
		except Exception:
			pass


def selection_geometry_paths(root):
	"""Absolute paths of selection cage Geometry COMPs (for Render TOP geometry)."""
	if root is None:
		return []
	paths = []
	for child in root.children:
		try:
			if child.family == "COMP" and child.name.startswith("sel_"):
				paths.append(child.path)
		except Exception:
			pass
	return paths


def set_proxy_selected(proxy, selected, icons_mod=None):
	"""Tint a light/camera proxy yellow when selected; restore default otherwise.

	Proxies share root materials (`mat_light` / `mat_camera`); selection assigns
	a dedicated `mat_selection` on the proxies root so unselected peers stay
	untouched.
	"""
	if proxy is None:
		return
	# TD: `.parent` is a ParentShortcut — must call it to get the COMP.
	try:
		parent = proxy.parent()
	except Exception:
		parent = None
	if parent is None:
		return
	kind = None
	try:
		kind = proxy.storage.get("proxy_kind")
	except Exception:
		kind = None
	if selected:
		mat = parent.op("mat_selection")
		if mat is None:
			mat = _ensure_mat(parent, "mat_selection", HIGHLIGHT_COLOR, alpha=HIGHLIGHT_ALPHA)
		else:
			r, g, b = HIGHLIGHT_COLOR
			mat.par.colorr, mat.par.colorg, mat.par.colorb = r, g, b
			try:
				mat.par.alpha = float(HIGHLIGHT_ALPHA)
			except Exception:
				pass
		proxy.par.material = mat.path
		return
	# Restore default tint from proxy_icons constants when available.
	if icons_mod is not None:
		if kind == "camera":
			color = icons_mod.CAMERA_COLOR
			alpha = icons_mod.CAMERA_ALPHA
			mat = parent.op("mat_camera")
			if mat is None:
				mat = _ensure_mat(parent, "mat_camera", color, alpha=alpha)
			else:
				r, g, b = color
				mat.par.colorr, mat.par.colorg, mat.par.colorb = r, g, b
				try:
					mat.par.alpha = float(alpha)
				except Exception:
					pass
			proxy.par.material = mat.path
			return
		color = icons_mod.LIGHT_COLOR
		mat = parent.op("mat_light")
		if mat is None:
			mat = _ensure_mat(parent, "mat_light", color)
		else:
			r, g, b = color
			mat.par.colorr, mat.par.colorg, mat.par.colorb = r, g, b
		proxy.par.material = mat.path
		return
	# Fallback without icons module: restore shared mats if present.
	if kind == "camera":
		mat = parent.op("mat_camera")
		if mat is not None:
			proxy.par.material = mat.path
	else:
		mat = parent.op("mat_light")
		if mat is not None:
			proxy.par.material = mat.path
