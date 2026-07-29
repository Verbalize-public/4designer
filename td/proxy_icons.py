"""4designer proxy icons — pickable Geometry COMPs for lights and cameras.

Polygon-only SOPs (same Render TOP constraint as gizmo_rig): sphere / tube /
cone / box / merge. Icons live under a root `proxies` nullCOMP and mirror the
target Object COMP's tx…rz — they are never parented under the real light/camera.
"""

from __future__ import annotations

ICON_HALF = 0.35  # world AABB half-extent for picking when computeBounds is useless
LIGHT_COLOR = (1.0, 0.85, 0.2)
CAMERA_COLOR = (0.25, 0.85, 0.95)
CAMERA_ALPHA = 0.28  # translucent — opaque cyan fills the frame near the edit cam
# Hide camera glyphs when this close to cam_edit (seeded view sits on the scene cam).
CAMERA_NEAR_HIDE = 1.25


def _sanitize_name(path):
	"""Stable Geometry COMP name from an absolute OP path."""
	safe = path.replace("/", "_").replace(".", "_").lstrip("_")
	if not safe:
		safe = "anon"
	return "proxy_" + safe[:80]


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
	# Blended transparency so low alpha actually composites (not just alphatest).
	try:
		mat.par.blend = True
	except Exception:
		pass
	try:
		mat.par.blending = True
	except Exception:
		pass
	return mat


def _finish_geo(child, merge_or_sop):
	out = child.create(outSOP, "out1")
	out.inputConnectors[0].connect(merge_or_sop)
	try:
		merge_or_sop.display = merge_or_sop.render = False
	except Exception:
		pass
	out.display = out.render = True


def _build_point_light(child):
	"""Sphere bulb + short vertical stem."""
	merge = child.create(mergeSOP, "merge1")
	sphere = child.create(sphereSOP, "bulb")
	sphere.par.radx = sphere.par.rady = sphere.par.radz = 0.18
	sphere.par.tx = sphere.par.ty = sphere.par.tz = 0.0
	sphere.display = sphere.render = False
	stem = child.create(tubeSOP, "stem")
	stem.par.rad1 = stem.par.rad2 = 0.04
	stem.par.height = 0.22
	stem.par.orient = "y"
	stem.par.ty = -0.28
	stem.display = stem.render = False
	merge.inputConnectors[0].connect(sphere)
	merge.inputConnectors[1].connect(stem)
	merge.display = merge.render = False
	_finish_geo(child, merge)


def _build_cone_light(child):
	"""Sphere bulb + tapered tube (cone) along local −Z (TD light look)."""
	merge = child.create(mergeSOP, "merge1")
	sphere = child.create(sphereSOP, "bulb")
	sphere.par.radx = sphere.par.rady = sphere.par.radz = 0.14
	sphere.display = sphere.render = False
	# Tube SOP with one radius 0 == cone (no dedicated coneSOP).
	cone = child.create(tubeSOP, "cone1")
	cone.par.rad1 = 0.0
	cone.par.rad2 = 0.22
	cone.par.height = 0.45
	cone.par.orient = "z"
	cone.par.tz = -0.28
	cone.display = cone.render = False
	merge.inputConnectors[0].connect(sphere)
	merge.inputConnectors[1].connect(cone)
	merge.display = merge.render = False
	_finish_geo(child, merge)


def _build_distant_light(child):
	"""Disc + forward tube arrow along −Z."""
	merge = child.create(mergeSOP, "merge1")
	# Thin box disc in XY (facing −Z)
	disc = child.create(boxSOP, "disc")
	disc.par.sizex = disc.par.sizey = 0.4
	disc.par.sizez = 0.06
	disc.display = disc.render = False
	shaft = child.create(tubeSOP, "shaft")
	shaft.par.rad1 = shaft.par.rad2 = 0.05
	shaft.par.height = 0.5
	shaft.par.orient = "z"
	shaft.par.tz = -0.35
	shaft.display = shaft.render = False
	# Arrow tip as a small box at the front
	tip = child.create(boxSOP, "tip")
	tip.par.sizex = tip.par.sizey = 0.16
	tip.par.sizez = 0.12
	tip.par.tz = -0.65
	tip.display = tip.render = False
	merge.inputConnectors[0].connect(disc)
	merge.inputConnectors[1].connect(shaft)
	merge.inputConnectors[2].connect(tip)
	merge.display = merge.render = False
	_finish_geo(child, merge)


def _build_camera(child):
	"""Tiny translucent camera glyph (body + lens). No frustum."""
	merge = child.create(mergeSOP, "merge1")
	body = child.create(boxSOP, "body")
	body.par.sizex = 0.12
	body.par.sizey = 0.09
	body.par.sizez = 0.08
	body.par.tz = 0.01
	body.display = body.render = False
	lens = child.create(tubeSOP, "lens")
	lens.par.rad1 = lens.par.rad2 = 0.035
	lens.par.height = 0.07
	lens.par.orient = "z"
	lens.par.tz = -0.07
	lens.display = lens.render = False
	merge.inputConnectors[0].connect(body)
	merge.inputConnectors[1].connect(lens)
	merge.display = merge.render = False
	_finish_geo(child, merge)


def _light_type(light_op):
	p = getattr(light_op.par, "lighttype", None)
	if p is None:
		return "point"
	try:
		lt = str(p.eval() or "point").strip().lower()
	except Exception:
		return "point"
	if lt not in ("point", "cone", "distant"):
		return "point"
	return lt


def ensure_proxies_root(parent, name="proxies"):
	"""Create (or return) the nullCOMP that holds proxy Geometry children."""
	root = parent.op(name)
	if root is None:
		root = parent.create(nullCOMP, name)
	root.pickable = False
	return root


def clear_proxies(root):
	if root is None:
		return
	_clear_children(root)


def sync_proxy_transform(proxy, target):
	"""Copy Object COMP local TRS channels used by the gizmo onto the proxy."""
	if proxy is None or target is None:
		return
	for n in ("tx", "ty", "tz", "rx", "ry", "rz"):
		try:
			setattr(proxy.par, n, float(getattr(target.par, n).eval()))
		except Exception:
			pass
	# Icons stay unit-scale; never copy target sx/sy/sz.
	try:
		proxy.par.sx = proxy.par.sy = proxy.par.sz = 1.0
	except Exception:
		pass


def build_light_proxy(root, light_op):
	"""Create one Geometry COMP icon for `light_op` under `root`. Returns the child."""
	name = _sanitize_name(light_op.path)
	existing = root.op(name)
	if existing is not None:
		existing.destroy()
	child = root.create(geometryCOMP, name)
	_clear_children(child)
	lt = _light_type(light_op)
	if lt == "cone":
		_build_cone_light(child)
	elif lt == "distant":
		_build_distant_light(child)
	else:
		_build_point_light(child)
	mat = _ensure_mat(root, "mat_light", LIGHT_COLOR, alpha=1.0)
	child.par.material = mat.path
	child.pickable = False
	try:
		child.storage["proxy_kind"] = "light"
	except Exception:
		pass
	sync_proxy_transform(child, light_op)
	return child


def build_camera_proxy(root, cam_op):
	"""Create one Geometry COMP icon for `cam_op` under `root`. Returns the child."""
	name = _sanitize_name(cam_op.path)
	existing = root.op(name)
	if existing is not None:
		existing.destroy()
	child = root.create(geometryCOMP, name)
	_clear_children(child)
	_build_camera(child)
	mat = _ensure_mat(root, "mat_camera", CAMERA_COLOR, alpha=CAMERA_ALPHA)
	child.par.material = mat.path
	child.pickable = False
	try:
		child.storage["proxy_kind"] = "camera"
	except Exception:
		pass
	sync_proxy_transform(child, cam_op)
	return child


def update_camera_proxy_visibility(root, edit_cam, gm_module, min_dist=None):
	"""Hide camera glyphs that sit on top of the edit camera (seeded view).

	Picking still uses the Objects AABB table — only Render is toggled.
	"""
	if root is None or edit_cam is None or gm_module is None:
		return
	if min_dist is None:
		min_dist = CAMERA_NEAR_HIDE
	try:
		cam_pos = gm_module.object_world_position(edit_cam)
	except Exception:
		return
	for child in root.children:
		try:
			if child.family != "COMP" or not child.name.startswith("proxy_"):
				continue
			kind = None
			try:
				kind = child.storage.get("proxy_kind")
			except Exception:
				kind = None
			if kind != "camera":
				continue
			pos = gm_module.object_world_position(child)
			d = gm_module.v_length(gm_module.v_sub(pos, cam_pos))
			child.render = d >= min_dist
		except Exception:
			pass


def proxy_paths(root):
	"""Absolute paths of all proxy Geometry COMPs under `root`."""
	if root is None:
		return []
	paths = []
	for child in root.children:
		try:
			if child.family == "COMP" and child.name.startswith("proxy_"):
				paths.append(child.path)
		except Exception:
			pass
	return paths


def find_proxy_for(root, target_path):
	if root is None or not target_path:
		return None
	return root.op(_sanitize_name(target_path))
