"""4designer Extension — discover, select, drag, camera, idle-lock.

Discovery (`_expand_render_par` / `_classify_render_op`) resolves a Render
TOP's geometry/lights/camera parameters into a flat pick table; the world-AABB
technique (`computeBounds(display=True, render=True, recurse=True)` +
`.min`/`.max`) gives each entry a world-space bounding box for ray picking.
Everything downstream of discovery (selection, drag, camera, idle-lock) is
analytic CPU ray math only — no Render Pick DAT, no Multi Touch In DAT, no
external process.

Pick targets: Geometry COMPs (mesh AABB) plus light/camera COMPs via unlit
proxy Geometry icons under `proxies/`. Scale mode is geo-only; lights/cameras
fall back to translate handles.

Multi-select: Ctrl+click toggles an object into/out of `self.Selected` (an
ordered list of paths); a plain click replaces the selection. Alt+click cycles
front→back through AABB overlaps at that pixel (replace); Alt+Ctrl+click
appends the next depth hit if not already selected. With 2+ objects
selected, the gizmo sits at the world-space average of their AABB centers
with identity rotation (world axes), and a drag applies the same world
delta / scale ratio / rotation angle to every selected object independently
(each keeps its own origin -- objects do not orbit the centroid).

Translate/rotate writeback goes through TD's own world matrices, not the
local tx/ty/tz + rx/ry/rz pars directly: `start_world = sel.worldTransform`
is captured at drag start, the world-space delta is applied to a copy of it
(`tdu.Matrix.translate` / `.rotateOnAxis(pivot=...)`), converted back to
that object's local space via its Object-COMP parent's world-inverse
(`gm.object_parent_world`), and written with `sel.setTransform(...)` --
verified live to round-trip exactly for any Object-COMP parent depth *and*
any Rotate Order (`setTransform` respects the target's own `rord`). This is
correct for a parented selection and for any of TD's six Rotate Orders, not
just root-level `xyz`. Scale stays local-par (intrinsically parent- and
order-independent); only the gizmo's own orientation needs the world fix so
its handle axes point the right way under a rotated parent.
"""
from __future__ import annotations

import math

# Visual-only near-pivot hover id — not a real HANDLES entry / not draggable.
CENTER_HOVER_ID = "center"


class FourdesignerExt:
	def __init__(self, ownerComp):
		self.ownerComp = ownerComp
		# Pick table: {path, kind, min, max} — kind is geo | light | camera.
		self.Objects = []
		# Ordered list of selected paths; last entry is the "primary" for
		# Status/kind display when exactly one object is selected.
		self.Selected = []
		self.Drag = None
		self.Hovered = None
		self.Orbit = {"yaw": -25.0, "pitch": 20.0, "dist": 6.0, "pivot": (0.0, 0.0, 0.0)}
		self.CamSeeded = False
		self._orbit_last = None
		self._pan_last = None
		self._lsel_prev = 0
		self._rsel_prev = 0
		self._msel_prev = 0
		# Panel u/v often lag the button-down edge; arm after the first sample
		# while held so pick/orbit/pan never fire on a stale UV.
		self._lmb_armed = False
		self._orbit_armed = False
		self._pan_armed = False
		# Latched on LMB edge — Alt/Ctrl panel vals can clear before UV arms.
		self._lmb_ctrl = False
		self._lmb_alt = False
		self.OrientHovered = None
		# Guard against Rendertop <-> Rendertopchoice sync feedback loops.
		self._rendertop_syncing = False
		# Last Alt depth-cycle index (optional; advance is selection-based).
		self._pick_cycle = None

	_PANEL_EXEC_VALUES = (
		"u v lselect rselect mselect wheel rollover rollu rollv ctrl alt"
	)

	# ---- module / node access ----
	@property
	def gm(self):
		return self.ownerComp.op("gizmo_math").module

	@property
	def rig(self):
		return self.ownerComp.op("gizmo_rig").module

	@property
	def icons(self):
		return self.ownerComp.op("proxy_icons").module

	@property
	def overlay(self):
		dat = self.ownerComp.op("selection_overlay")
		return dat.module if dat is not None else None

	@property
	def toolbar_mod(self):
		dat = self.ownerComp.op("toolbar")
		return dat.module if dat is not None else None

	@property
	def orient(self):
		dat = self.ownerComp.op("orient_gizmo")
		return dat.module if dat is not None else None

	@property
	def cam(self):
		return self.ownerComp.op("cam_edit")

	@property
	def cam_orient(self):
		return self.ownerComp.op("cam_orient")

	@property
	def render_edit(self):
		return self.ownerComp.op("render_edit")

	@property
	def render_gizmo(self):
		return self.ownerComp.op("render_gizmo")

	@property
	def render_orient(self):
		return self.ownerComp.op("render_orient")

	@property
	def gizmo(self):
		return self.ownerComp.op("gizmo1")

	@property
	def orient_cube(self):
		return self.ownerComp.op("orient_cube")

	@property
	def proxies(self):
		return self.ownerComp.op("proxies")

	@property
	def selection_root(self):
		return self.ownerComp.op("selection1")

	@property
	def toolbar(self):
		return self.ownerComp.op("ui_toolbar")

	@property
	def ui_orient(self):
		return self.ownerComp.op("ui_orient")

	@property
	def panel(self):
		"""The owner COMP is itself the interactive Container/Panel -- one
		node, one drop-in tox, no separate child panel to keep in sync."""
		return self.ownerComp

	# Back-compat for any external reader that still expects Geos.
	@property
	def Geos(self):
		return [e for e in self.Objects if e.get("kind") == "geo"]

	def _status(self, msg):
		try:
			self.ownerComp.par.Status = str(msg)[:120]
		except Exception:
			pass

	def _current_mode(self):
		try:
			return self.ownerComp.par.Mode.eval()
		except Exception:
			return "translate"

	# ---- G2 Discover ----
	def _expand_render_par(self, par):
		"""Resolve a Render TOP OP/list parameter into a list of OPs."""
		if par is None:
			return []
		try:
			val = par.eval()
		except Exception:
			return []
		if val is None:
			return []
		if isinstance(val, (list, tuple)):
			return [x for x in val if x is not None]
		if hasattr(val, "path"):
			return [val]
		return []

	def _classify_render_op(self, o):
		try:
			if isinstance(o, cameraCOMP):
				return "camera"
			if isinstance(o, geometryCOMP):
				return "geo"
			if isinstance(o, lightCOMP):
				return "light"
		except Exception:
			pass
		opt = (getattr(o, "OPType", "") or type(o).__name__ or "").lower()
		if "camera" in opt:
			return "camera"
		if "light" in opt:
			return "light"
		if "geometry" in opt or opt.endswith("geo"):
			return "geo"
		return None

	def _compute_world_bounds(self, geo):
		"""World-space AABB via `computeBounds`, kept in world space since
		the ray test below operates in world space too.
		"""
		try:
			b = geo.computeBounds(display=True, render=True, recurse=True)
			mn, mx = b.min, b.max
			return (float(mn.x), float(mn.y), float(mn.z)), (float(mx.x), float(mx.y), float(mx.z))
		except Exception:
			p = self.gm.object_world_position(geo)
			return (p[0] - 0.5, p[1] - 0.5, p[2] - 0.5), (p[0] + 0.5, p[1] + 0.5, p[2] + 0.5)

	def _icon_world_bounds(self, obj):
		"""Fixed-radius AABB around an Object COMP origin (lights / cameras)."""
		half = self.icons.ICON_HALF
		p = self.gm.object_world_position(obj)
		return (
			(p[0] - half, p[1] - half, p[2] - half),
			(p[0] + half, p[1] + half, p[2] + half),
		)

	def _object_bounds(self, obj, kind):
		if kind == "geo":
			return self._compute_world_bounds(obj)
		return self._icon_world_bounds(obj)

	def _object_entry(self, path):
		for entry in self.Objects:
			if entry["path"] == path:
				return entry
		return None

	def _has_selection(self):
		return bool(self.Selected)

	def _primary_path(self):
		"""Last selected/toggled path — used for single-selection kind/Status."""
		return self.Selected[-1] if self.Selected else None

	def _selected_kind(self):
		entry = self._object_entry(self._primary_path())
		return entry["kind"] if entry else None

	def _selected_kinds(self):
		"""Distinct kinds across the whole selection (for mode-gating multi-select)."""
		kinds = set()
		for path in self.Selected:
			entry = self._object_entry(path)
			if entry:
				kinds.add(entry["kind"])
		return kinds

	def _effective_mode(self):
		"""Gizmo mode for the current selection — scale is geo-only."""
		mode = self._current_mode()
		if mode == "scale" and (self._selected_kinds() & {"light", "camera"}):
			return "translate"
		return mode

	def Discover(self):
		rt_par = getattr(self.ownerComp.par, "Rendertop", None)
		rt = rt_par.eval() if rt_par is not None else None
		if rt is None:
			self._status("Discover: no Rendertop set")
			self.Objects = []
			self._pick_cycle = None
			self._rebuild_proxies([], [])
			return []
		geos, lights, cams = [], [], []
		for par_name in ("geometry", "lights", "camera"):
			p = getattr(rt.par, par_name, None)
			for o in self._expand_render_par(p):
				kind = self._classify_render_op(o)
				if kind == "geo":
					geos.append(o)
				elif kind == "light":
					lights.append(o)
				elif kind == "camera":
					cams.append(o)
		table = []
		for g in geos:
			bmin, bmax = self._object_bounds(g, "geo")
			table.append({"path": g.path, "kind": "geo", "min": bmin, "max": bmax})
		for lit in lights:
			bmin, bmax = self._object_bounds(lit, "light")
			table.append({"path": lit.path, "kind": "light", "min": bmin, "max": bmax})
		for cam in cams:
			bmin, bmax = self._object_bounds(cam, "camera")
			table.append({"path": cam.path, "kind": "camera", "min": bmin, "max": bmax})
		self.Objects = table
		valid_paths = {e["path"] for e in table}
		self.Selected = [p for p in self.Selected if p in valid_paths]
		self._rebuild_proxies(lights, cams)
		self._wire_edit_render(geos, lights)
		if not self.CamSeeded and cams:
			self.SeedCamera(cams[0])
		self._pick_cycle = None
		self._sync_gizmo_to_selection()
		self._status(
			"Discover: {} geo / {} light / {} cam".format(len(geos), len(lights), len(cams))
		)
		self._sync_toolbar_exec()
		self._sync_panel_exec()
		return table

	def _rebuild_proxies(self, lights, cams):
		icons = self.icons
		root = icons.ensure_proxies_root(self.ownerComp, "proxies")
		icons.clear_proxies(root)
		for lit in lights:
			try:
				icons.build_light_proxy(root, lit)
			except Exception as e:
				self._status("proxy light fail: " + str(e)[:50])
		for cam in cams:
			try:
				icons.build_camera_proxy(root, cam)
			except Exception as e:
				self._status("proxy cam fail: " + str(e)[:50])
		self._refresh_camera_proxy_visibility()

	def _refresh_camera_proxy_visibility(self):
		"""Hide translucent camera glyphs when they sit on the edit camera."""
		try:
			self.icons.update_camera_proxy_visibility(self.proxies, self.cam, self.gm)
		except Exception:
			pass

	def _sync_all_proxies(self):
		root = self.proxies
		if root is None:
			return
		icons = self.icons
		for entry in self.Objects:
			if entry["kind"] not in ("light", "camera"):
				continue
			target = op(entry["path"])
			proxy = icons.find_proxy_for(root, entry["path"])
			if target is not None and proxy is not None:
				icons.sync_proxy_transform(proxy, target)
		self._refresh_camera_proxy_visibility()

	@staticmethod
	def _is_gizmo_geo_name(name):
		return (
			name.startswith("handle_")
			or name.startswith("guide_")
			or name.startswith("grid_")
		)

	def _gizmo_geometry_paths(self):
		"""Explicit paths for the gizmo pass — nested handle/guide/grid Geometry
		COMPs must be listed individually; parent nullCOMP path alone is not
		enough and must NOT be included (Render TOP geometry rejects it)."""
		gizmo = self.gizmo
		if gizmo is None:
			return []
		paths = []
		for child in gizmo.children:
			try:
				if child.family == "COMP" and child.OPType == "geometryCOMP" and (
					self._is_gizmo_geo_name(child.name)
				):
					paths.append(child.path)
			except Exception:
				pass
		return paths

	def _selection_geometry_paths(self):
		overlay = self.overlay
		root = self.selection_root
		if overlay is None or root is None:
			return []
		try:
			return list(overlay.selection_geometry_paths(root))
		except Exception:
			return []

	def _wire_gizmo_render(self):
		"""Assign handle + selection-cage Geometry COMPs to render_gizmo.

		TD's Render TOP `geometry` par silently drops COMPs whose `.render` is
		False (and rejects nullCOMPs). Force-render on → assign → restore mode
		visibility so inactive handles stay in the list and can be toggled later.
		"""
		rend_g = self.render_gizmo
		gizmo = self.gizmo
		if rend_g is None or gizmo is None:
			return
		paths = self._gizmo_geometry_paths()
		paths.extend(self._selection_geometry_paths())
		if not paths:
			return
		# Remember current render flags, force on, assign, restore.
		prev = {}
		for child in gizmo.children:
			try:
				if self._is_gizmo_geo_name(child.name):
					prev[child.path] = bool(child.render)
					child.render = True
			except Exception:
				pass
		sel_root = self.selection_root
		if sel_root is not None:
			for child in sel_root.children:
				try:
					if child.name.startswith("sel_"):
						prev[child.path] = bool(child.render)
						child.render = True
				except Exception:
					pass
		try:
			rend_g.par.geometry = " ".join(paths)
		except Exception as e:
			self._status("wire gizmo fail: " + str(e)[:60])
		for path, flag in prev.items():
			node = op(path)
			if node is not None:
				try:
					node.render = flag
				except Exception:
					pass
		# Re-apply mode so visibility matches current Mode/selection.
		if self.Selected and self._current_mode() != "select":
			self.rig.set_gizmo_mode(gizmo, self._effective_mode())
		elif self._current_mode() == "select" or not self.Selected:
			self.rig.set_gizmo_mode(gizmo, None)

	def _wire_edit_render(self, geos, lights):
		# Scene pass: Geos + light/camera proxy icons. Real lights still light
		# the scene. Gizmo pass: handles only, composited Over.
		rend = self.render_edit
		rend_g = self.render_gizmo
		light_paths = " ".join(l.path for l in lights)
		geo_paths = [g.path for g in geos]
		geo_paths.extend(self.icons.proxy_paths(self.proxies))
		if rend is not None:
			try:
				rend.par.geometry = " ".join(geo_paths)
			except Exception as e:
				self._status("wire geometry fail: " + str(e)[:60])
			try:
				rend.par.lights = light_paths
			except Exception as e:
				self._status("wire lights fail: " + str(e)[:60])
		if rend_g is not None:
			try:
				rend_g.par.lights = light_paths
			except Exception:
				pass
			self._wire_gizmo_render()
		self.Unlock()

	# ---- G3 Select (analytic) ----
	def _render_res_w(self):
		try:
			return float(self.render_edit.par.resolutionw.eval())
		except Exception:
			return 1280.0

	def _render_res_h(self):
		try:
			return float(self.render_edit.par.resolutionh.eval())
		except Exception:
			return 720.0

	def _panel_size(self):
		p = self.ownerComp
		try:
			w = float(p.width)
			h = float(p.height)
			if w > 1.0 and h > 1.0:
				return w, h
		except Exception:
			pass
		return self._render_res_w(), self._render_res_h()

	def _ray_from_panel(self, u, v):
		# Remap panel u/v through topfill=best letterbox so rays match pixels.
		res_w, res_h = self._render_res_w(), self._render_res_h()
		panel_w, panel_h = self._panel_size()
		u_c, v_c = self.gm.panel_uv_to_content(u, v, panel_w, panel_h, res_w, res_h)
		return self.gm.unproject_ray(self.cam, u_c, v_c, res_w, res_h)

	def _refresh_object_bounds(self, path=None):
		"""Recompute cached world AABBs after transforms (Discover caches once)."""
		for entry in self.Objects:
			if path is not None and entry["path"] != path:
				continue
			obj = op(entry["path"])
			if obj is None:
				continue
			bmin, bmax = self._object_bounds(obj, entry["kind"])
			entry["min"], entry["max"] = bmin, bmax

	def _pick_hits_at(self, u, v):
		"""All AABB ray hits at panel u/v, front-to-back (ascending t)."""
		self._refresh_object_bounds()
		origin, direction = self._ray_from_panel(u, v)
		hits = []
		for entry in self.Objects:
			t = self.gm.ray_vs_aabb(origin, direction, entry["min"], entry["max"])
			if t is not None:
				hits.append((t, entry["path"]))
		hits.sort(key=lambda h: h[0])
		return [path for _t, path in hits]

	def _advance_pick_cycle(self, paths):
		"""Pick next depth hit after the deepest currently-selected path in `paths`.

		Selection-relative (not UV-keyed) so small mouse drift between Alt clicks
		still advances the stack. Returns (path_or_None, index, n).
		"""
		if not paths:
			self._pick_cycle = None
			return None, 0, 0
		start = -1
		for i, path in enumerate(paths):
			if path in self.Selected:
				start = i
		index = (start + 1) % len(paths)
		self._pick_cycle = {"paths": list(paths), "index": index}
		return paths[index], index, len(paths)

	def SelectAt(self, u, v, additive=False, cycle=False):
		"""Pick at panel u/v.

		`additive` (Ctrl): toggle closest hit (no Alt), or append cycled hit (with Alt).
		`cycle` (Alt): walk front→back AABB overlaps at this pixel; wrap at end.
		Without Alt, a miss clears (replace) or leaves selection alone (additive).
		"""
		paths = self._pick_hits_at(u, v)
		if cycle:
			chosen, index, n = self._advance_pick_cycle(paths)
			if chosen is None:
				if not additive:
					self.Selected = []
			elif additive:
				# Alt+Ctrl: append next depth hit if not already selected (no toggle-off).
				if chosen not in self.Selected:
					self.Selected = self.Selected + [chosen]
			else:
				self.Selected = [chosen]
			self._sync_gizmo_to_selection()
			self._status_selection(depth=(index + 1, n) if n > 1 else None)
			return chosen

		self._pick_cycle = None
		best_path = paths[0] if paths else None
		if additive:
			if best_path is None:
				pass
			elif best_path in self.Selected:
				self.Selected = [p for p in self.Selected if p != best_path]
			else:
				self.Selected = self.Selected + [best_path]
		else:
			self.Selected = [best_path] if best_path is not None else []
		self._sync_gizmo_to_selection()
		self._status_selection()
		return best_path

	def _status_selection(self, depth=None):
		n = len(self.Selected)
		scale_blocked = self._current_mode() == "scale" and bool(self._selected_kinds() & {"light", "camera"})
		depth_suffix = ""
		if depth is not None:
			di, dn = depth
			if dn > 1:
				depth_suffix = " — depth {}/{}".format(di, dn)
		if n == 0:
			self._status("Selected: none" + depth_suffix)
		elif n == 1:
			kind = self._selected_kind() or "none"
			if scale_blocked:
				self._status(
					"Selected: {} ({}) — Scale N/A{}".format(self.Selected[0], kind, depth_suffix)
				)
			else:
				self._status(
					"Selected: {} ({}){}".format(self.Selected[0], kind, depth_suffix)
				)
		else:
			if scale_blocked:
				self._status("Selected: {} objects — Scale N/A{}".format(n, depth_suffix))
			else:
				self._status("Selected: {} objects{}".format(n, depth_suffix))

	def _distance_to_gizmo_center(self, u, v):
		"""Closest-approach distance of the panel ray to the gizmo pivot, or None."""
		gizmo = self.gizmo
		if gizmo is None:
			return None
		origin, direction = self._ray_from_panel(u, v)
		center = self.gm.object_world_position(gizmo)
		to_c = self.gm.v_sub(center, origin)
		t = self.gm.v_dot(to_c, direction)
		if t < 0:
			return None
		closest = self.gm.v_add(origin, self.gm.v_scale(direction, t))
		return self.gm.v_length(self.gm.v_sub(closest, center))

	def _ray_near_gizmo(self, u, v, radius_scale=1.25):
		"""True if the panel ray passes near the gizmo pivot (handle near-miss zone)."""
		gizmo = self.gizmo
		if gizmo is None:
			return False
		dist = self._distance_to_gizmo_center(u, v)
		if dist is None:
			return False
		scale = max(self.rig.gizmo_uniform_scale(gizmo), 1e-4)
		return dist <= self.rig.RING_RADIUS * scale * radius_scale

	def _near_center(self, u, v):
		"""True if the ray passes through the small gap around the pivot (pre-rod)."""
		gizmo = self.gizmo
		if gizmo is None:
			return False
		dist = self._distance_to_gizmo_center(u, v)
		if dist is None:
			return False
		scale = max(self.rig.gizmo_uniform_scale(gizmo), 1e-4)
		return dist <= self.rig.ROD_INNER * scale * 1.4

	def _selection_centroid(self):
		"""Average of selected objects' world AABB centers (multi-select pivot)."""
		cx = cy = cz = 0.0
		n = 0
		for path in self.Selected:
			entry = self._object_entry(path)
			if entry is None:
				continue
			mn, mx = entry["min"], entry["max"]
			cx += 0.5 * (mn[0] + mx[0])
			cy += 0.5 * (mn[1] + mx[1])
			cz += 0.5 * (mn[2] + mx[2])
			n += 1
		if n < 1:
			return None
		return (cx / n, cy / n, cz / n)

	def _sync_selected_proxies(self):
		"""Keep proxy icons stuck to every selected light/camera."""
		for path in self.Selected:
			entry = self._object_entry(path)
			if entry is None or entry["kind"] not in ("light", "camera"):
				continue
			target = op(path)
			proxy = self.icons.find_proxy_for(self.proxies, path)
			if target is not None:
				self.icons.sync_proxy_transform(proxy, target)

	def _sync_selection_overlay(self):
		"""Pose AABB cages + tint light/camera proxies for `self.Selected`."""
		overlay = self.overlay
		if overlay is None:
			return
		root = overlay.ensure_selection_root(self.ownerComp, "selection1")
		selected = set(self.Selected)
		# Refresh bounds for selected paths so cages track after transforms.
		for path in self.Selected:
			self._refresh_object_bounds(path)
		entries = []
		for path in self.Selected:
			entry = self._object_entry(path)
			if entry is None:
				continue
			entries.append({
				"path": entry["path"],
				"min": entry["min"],
				"max": entry["max"],
			})
		prev_names = set()
		for child in root.children:
			try:
				if child.name.startswith("sel_"):
					prev_names.add(child.name)
			except Exception:
				pass
		overlay.sync_selection_overlays(root, entries)
		# Tint proxies: selected → highlight; others → default.
		icons = self.icons
		proxies = self.proxies
		if proxies is not None:
			for child in proxies.children:
				try:
					if not child.name.startswith("proxy_"):
						continue
					# Match via find: storage path isn't on the child; invert sanitize.
					is_sel = False
					for path in selected:
						if icons.find_proxy_for(proxies, path) is child:
							is_sel = True
							break
					overlay.set_proxy_selected(child, is_sel, icons_mod=icons)
				except Exception:
					pass
		# New cages need to be listed on render_gizmo.geometry.
		new_names = set()
		for child in root.children:
			try:
				if child.name.startswith("sel_"):
					new_names.add(child.name)
			except Exception:
				pass
		if new_names != prev_names:
			self._wire_gizmo_render()

	def _sync_gizmo_to_selection(self):
		gizmo = self.gizmo
		if gizmo is None:
			return
		self.Hovered = None
		if not self.Selected:
			self.rig.set_gizmo_mode(gizmo, None)
			self._refresh_gizmo_feedback()
			self._sync_selection_overlay()
			return
		if len(self.Selected) == 1:
			sel = op(self.Selected[0])
			if sel is None:
				self.rig.set_gizmo_mode(gizmo, None)
				self._refresh_gizmo_feedback()
				self._sync_selection_overlay()
				return
			# World pose, not local rx/ty/rz -- correct under any Object-COMP parent.
			gizmo.setTransform(self.gm.object_world_pose_matrix(sel))
		else:
			# Multi-select: world-aligned gizmo at the AABB-center average.
			centroid = self._selection_centroid()
			if centroid is None:
				self.rig.set_gizmo_mode(gizmo, None)
				self._refresh_gizmo_feedback()
				self._sync_selection_overlay()
				return
			gizmo.par.tx, gizmo.par.ty, gizmo.par.tz = centroid
			gizmo.par.rx = gizmo.par.ry = gizmo.par.rz = 0.0
		if self._current_mode() == "select":
			self.rig.set_gizmo_mode(gizmo, None)
		else:
			self.rig.set_gizmo_mode(gizmo, self._effective_mode())
		self._rescale_gizmo()
		self._refresh_gizmo_feedback()
		self._sync_selected_proxies()
		self._sync_selection_overlay()

	def OnModeChange(self):
		mode = self._current_mode()
		tb = self.toolbar_mod
		if tb is not None:
			tb.refresh_mode_highlight(self.toolbar, mode)
		gizmo = self.gizmo
		if gizmo is not None and self.Selected:
			eff = self._effective_mode()
			if mode == "scale" and (self._selected_kinds() & {"light", "camera"}):
				self._status("Scale N/A for light/camera")
			elif mode == "select":
				self.rig.set_gizmo_mode(gizmo, None)
			else:
				self.rig.set_gizmo_mode(gizmo, eff)
			self._refresh_gizmo_feedback()
		elif gizmo is not None and mode == "select":
			self.rig.set_gizmo_mode(gizmo, None)
			self._refresh_gizmo_feedback()

	def SetMode(self, mode):
		"""Set gizmo Mode from the toolbar (or script)."""
		if mode not in ("select", "translate", "scale", "rotate"):
			return
		try:
			self.ownerComp.par.Mode = mode
		except Exception as e:
			self._status("SetMode fail: " + str(e)[:60])
			return
		# Parexec may not fire when set from script in some builds — sync directly.
		self.OnModeChange()
		self._status("Mode: " + mode)

	def OnSnapGridChange(self):
		"""Sync snap toggle highlight + plane grid when Snapgrid par changes."""
		enabled = self._snap_enabled()
		tb = self.toolbar_mod
		if tb is not None:
			tb.refresh_snap_highlight(self.toolbar, enabled)
		self._refresh_gizmo_feedback()
		self._status("Snap: " + ("on" if enabled else "off"))

	def _sync_toolbar_exec(self):
		"""Ensure toolbar_exec watches every clickable toolbar control."""
		tb = self.toolbar_mod
		if tb is None:
			return
		try:
			tb.sync_toolbar_exec(self.ownerComp, self.toolbar)
		except Exception:
			pass

	def _sync_panel_exec(self):
		"""Ensure panel_exec monitors ctrl+alt (and the rest of the pick surface)."""
		pexec = self.ownerComp.op("panel_exec")
		if pexec is None:
			return
		try:
			pexec.par.panelvalue = self._PANEL_EXEC_VALUES
		except Exception:
			pass

	def OnToolbarButton(self, button_name):
		"""Dispatch a toolbar Button COMP click by node name."""
		tb = self.toolbar_mod
		if tb is not None and button_name in tb.MODE_BY_BUTTON:
			self.SetMode(tb.MODE_BY_BUTTON[button_name])
			return
		if button_name == "btn_discover":
			self.Discover()
			return
		if button_name == "btn_resetview":
			self.ResetView()
			return
		if button_name == "btn_refreshrenders":
			self.RefreshRenderTopList()
			return
		if button_name == "btn_rendertop":
			self.OpenRenderTopMenu()
			return
		if button_name == "btn_snapgrid":
			# Debounce: select can report more than once per physical click.
			try:
				frame = absTime.frame
			except Exception:
				frame = None
			if frame is not None and getattr(self, "_snap_btn_frame", None) == frame:
				return
			self._snap_btn_frame = frame
			try:
				cur = bool(self.ownerComp.par.Snapgrid.eval())
			except Exception:
				cur = False
			try:
				self.ownerComp.par.Snapgrid = not cur
			except Exception:
				pass
			self.OnSnapGridChange()
			return

	# ---- Render TOP picker (parent-network scan) ----
	# Empty string is an invalid custom Menu name in TD (defaults stick as name1/Label 1).
	NONE_RENDER = "__none__"

	def _set_rendertop_menu(self, names, labels):
		"""Hard-replace Rendertopchoice menu entries; retry once if ghosts remain."""
		par = self.ownerComp.par.Rendertopchoice
		par.menuNames = list(names)
		par.menuLabels = list(labels)
		got = list(par.menuNames)
		allowed = set(names)
		if any(n not in allowed for n in got):
			par.menuNames = list(names)
			par.menuLabels = list(labels)

	def _is_valid_render_choice(self, path):
		"""True for NONE_RENDER or a live renderTOP path."""
		if path == self.NONE_RENDER or path is None:
			return True
		if not path or not str(path).startswith("/"):
			return False
		try:
			node = op(path)
		except Exception:
			return False
		if node is None:
			return False
		try:
			return isinstance(node, renderTOP) or (getattr(node, "OPType", "") or "") == "renderTOP"
		except Exception:
			return (getattr(node, "OPType", "") or "") == "renderTOP"

	def RefreshRenderTopList(self):
		"""Rebuild Rendertopchoice + toolbar field from renderTOPs in the parent network."""
		parent = self.ownerComp.parent()
		tops = []
		if parent is not None:
			try:
				tops = list(parent.findChildren(type=renderTOP, maxDepth=1))
			except Exception:
				tops = []
			# Exclude our own internal render passes if they somehow appear as siblings.
			own = {self.render_edit, self.render_gizmo, self.render_orient}
			tops = [t for t in tops if t not in own]
			tops.sort(key=lambda t: t.name.lower())

		paths = [self.NONE_RENDER] + [t.path for t in tops]
		labels = ["(none)"] + [t.name for t in tops]
		try:
			self._set_rendertop_menu(paths, labels)
		except Exception as e:
			self._status("Refresh renders fail: " + str(e)[:60])
			return

		# Preserve current Rendertop if still listed; else clear to (none).
		current_path = ""
		try:
			rt = self.ownerComp.par.Rendertop.eval()
			if rt is not None:
				current_path = rt.path
		except Exception:
			pass
		if current_path in paths:
			choice = current_path
		else:
			choice = self.NONE_RENDER

		self._rendertop_syncing = True
		try:
			self.ownerComp.par.Rendertopchoice = choice
			self._apply_rendertop_path(choice, discover=False)
		finally:
			self._rendertop_syncing = False

		tb = self.toolbar_mod
		if tb is not None:
			tb.sync_rendertop_field(self.toolbar, choice, labels, paths)
		self._status("Renders: {} in parent".format(len(tops)))
		return paths

	def _apply_rendertop_path(self, path, discover=True):
		"""Set the Rendertop OP par from an absolute path (or clear)."""
		if path == self.NONE_RENDER or path is None or path == "":
			path = ""
		elif not self._is_valid_render_choice(path):
			self._status("Ignore non-render choice: " + str(path)[:40])
			return
		try:
			if path:
				self.ownerComp.par.Rendertop = path
			else:
				self.ownerComp.par.Rendertop = ""
		except Exception as e:
			self._status("Set Rendertop fail: " + str(e)[:60])
			return
		if discover:
			self.Discover()

	def _sync_rendertop_from_choice(self, discover=True):
		"""Rendertopchoice → Rendertop OP par."""
		if self._rendertop_syncing:
			return
		self._rendertop_syncing = True
		try:
			choice = str(self.ownerComp.par.Rendertopchoice.eval() or self.NONE_RENDER)
			if not self._is_valid_render_choice(choice):
				choice = self.NONE_RENDER
				self.ownerComp.par.Rendertopchoice = choice
			self._apply_rendertop_path(choice, discover=discover)
			tb = self.toolbar_mod
			if tb is not None:
				try:
					names = list(self.ownerComp.par.Rendertopchoice.menuNames)
					labels = list(self.ownerComp.par.Rendertopchoice.menuLabels)
				except Exception:
					names, labels = [self.NONE_RENDER], ["(none)"]
				tb.sync_rendertop_field(self.toolbar, choice, labels, names)
		finally:
			self._rendertop_syncing = False

	def _sync_choice_from_rendertop(self):
		"""Rendertop OP par → Rendertopchoice (+ toolbar field). Never append to menu."""
		if self._rendertop_syncing:
			return
		path = ""
		try:
			rt = self.ownerComp.par.Rendertop.eval()
			if rt is not None:
				path = rt.path
		except Exception:
			pass
		try:
			names = list(self.ownerComp.par.Rendertopchoice.menuNames)
		except Exception:
			names = []
		# Rebuild the full list if path is missing or ghosts are present.
		needs_refresh = False
		if path and path not in names:
			needs_refresh = True
		if any(n != self.NONE_RENDER and not str(n).startswith("/") for n in names):
			needs_refresh = True
		if needs_refresh:
			self.RefreshRenderTopList()
			return

		choice = path if path else self.NONE_RENDER
		self._rendertop_syncing = True
		try:
			try:
				labels = list(self.ownerComp.par.Rendertopchoice.menuLabels)
				names = list(self.ownerComp.par.Rendertopchoice.menuNames)
			except Exception:
				names, labels = [self.NONE_RENDER], ["(none)"]
			if choice in names:
				self.ownerComp.par.Rendertopchoice = choice
			tb = self.toolbar_mod
			if tb is not None:
				tb.sync_rendertop_field(self.toolbar, choice, labels, names)
		finally:
			self._rendertop_syncing = False

	def OnRenderTopParChange(self):
		"""Parameter dialog Rendertop changed → sync choice + Discover."""
		if self._rendertop_syncing:
			return
		self._sync_choice_from_rendertop()
		self.Discover()

	def OnRenderTopChoiceChange(self):
		"""Rendertopchoice menu changed → sync OP + Discover."""
		if self._rendertop_syncing:
			return
		self._sync_rendertop_from_choice(discover=True)

	def OnRenderTopFieldChange(self, value):
		"""Toolbar picker selected a value → set Rendertopchoice."""
		if self._rendertop_syncing:
			return
		val = self.NONE_RENDER if value is None else str(value)
		if not self._is_valid_render_choice(val):
			self._status("Ignore non-render choice: " + val[:40])
			return
		try:
			cur = str(self.ownerComp.par.Rendertopchoice.eval() or self.NONE_RENDER)
		except Exception:
			cur = self.NONE_RENDER
		if val == cur:
			self._sync_rendertop_from_choice(discover=True)
			return
		self._rendertop_syncing = True
		try:
			self.ownerComp.par.Rendertopchoice = val
		finally:
			self._rendertop_syncing = False
		self._sync_rendertop_from_choice(discover=True)

	def OpenRenderTopMenu(self):
		"""Open the system PopMenu listing parent-network Render TOPs."""
		# Always refresh so the list matches the parent network (no stale ghosts).
		self.RefreshRenderTopList()
		try:
			names = list(self.ownerComp.par.Rendertopchoice.menuNames)
			labels = list(self.ownerComp.par.Rendertopchoice.menuLabels)
		except Exception:
			names, labels = [self.NONE_RENDER], ["(none)"]
		# Defense: drop any non-sentinel / non-path leftovers.
		filtered = [
			(n, lab)
			for n, lab in zip(names, labels)
			if n == self.NONE_RENDER or (str(n).startswith("/") and self._is_valid_render_choice(n))
		]
		if not filtered:
			filtered = [(self.NONE_RENDER, "(none)")]
		names = [n for n, _ in filtered]
		labels = [lab for _, lab in filtered]

		try:
			cur = str(self.ownerComp.par.Rendertopchoice.eval() or self.NONE_RENDER)
		except Exception:
			cur = self.NONE_RENDER
		checked = []
		try:
			idx = names.index(cur)
			checked = [labels[idx]]
		except Exception:
			pass

		def _on_select(info):
			try:
				i = int(info.get("index", -1))
			except Exception:
				i = -1
			if i < 0 or i >= len(names):
				return
			self.OnRenderTopFieldChange(names[i])

		try:
			# Prefer the documented PopMenu shortcut; fall back to the child OP.
			try:
				pop = op.TDResources.PopMenu
			except Exception:
				pop = op.TDResources.op("popMenu")
			pop.Open(
				items=list(labels),
				callback=_on_select,
				checkedItems=checked,
			)
		except Exception as e:
			self._status("Render menu fail: " + str(e)[:60])

	# ---- Snap-to-grid (translate only) ----
	def _snap_enabled(self):
		try:
			return bool(self.ownerComp.par.Snapgrid.eval())
		except Exception:
			return False

	def _snap_steps(self):
		try:
			return (
				float(self.ownerComp.par.Snapgridx.eval()),
				float(self.ownerComp.par.Snapgridy.eval()),
				float(self.ownerComp.par.Snapgridz.eval()),
			)
		except Exception:
			return (0.1, 0.1, 0.1)

	@staticmethod
	def _snap_scalar(v, step):
		if step is None or step <= 0:
			return v
		return round(v / step) * step

	def _snap_world_pos(self, pos):
		sx, sy, sz = self._snap_steps()
		return (
			self._snap_scalar(pos[0], sx),
			self._snap_scalar(pos[1], sy),
			self._snap_scalar(pos[2], sz),
		)

	def _snapped_world_delta(self, start_pos, world_delta):
		"""Snap (start + delta) to the grid and return the effective delta."""
		if not self._snap_enabled() or start_pos is None or world_delta is None:
			return world_delta
		new_pos = (
			start_pos[0] + world_delta[0],
			start_pos[1] + world_delta[1],
			start_pos[2] + world_delta[2],
		)
		snapped = self._snap_world_pos(new_pos)
		return (
			snapped[0] - start_pos[0],
			snapped[1] - start_pos[1],
			snapped[2] - start_pos[2],
		)

	GIZMO_DESIRED_PX = 90.0

	def _rescale_gizmo(self):
		gizmo, cam = self.gizmo, self.cam
		if gizmo is None or cam is None:
			return
		cam_pos = self.gm.object_world_position(cam)
		gizmo_pos = self.gm.object_world_position(gizmo)
		try:
			fov_y = float(cam.par.fov.eval())
		except Exception:
			fov_y = 45.0
		scale = self.gm.gizmo_screen_scale(cam_pos, gizmo_pos, fov_y, self._render_res_h(), self.GIZMO_DESIRED_PX)
		gizmo.par.sx = gizmo.par.sy = gizmo.par.sz = max(scale, 1e-4)
		# Snap grid cell spacing is in gizmo-local units — refresh when scale changes.
		self._refresh_gizmo_feedback()

	# ---- Hover highlight + guide lines ----
	def UpdateHover(self, u, v):
		"""Pick the hovered handle (or center zone) from rollu/rollv."""
		if self.Drag is not None:
			return
		if self.gizmo is None or not self.Selected or self._current_mode() == "select":
			self._apply_hover(None)
			return
		handle_id = self._pick_handle(u, v)
		if handle_id is None and self._near_center(u, v):
			handle_id = CENTER_HOVER_ID
		self._apply_hover(handle_id)

	def _apply_hover(self, handle_id):
		if handle_id == self.Hovered:
			return
		self.Hovered = handle_id
		self._refresh_gizmo_feedback()

	def _refresh_gizmo_feedback(self):
		"""Resolve active highlight + guide lines + snap plane grid from Drag/Hovered."""
		gizmo = self.gizmo
		if gizmo is None:
			return
		active = None
		if self.Drag is not None:
			active = self.Drag["handle"]["id"]
		elif self.Hovered is not None:
			active = self.Hovered

		highlight_ids = set()
		guide_axes = set()
		mode = self._effective_mode()
		if active == CENTER_HOVER_ID:
			for handle in self.rig.HANDLES:
				if mode in handle["modes"] and handle["kind"] == "axis":
					highlight_ids.add(handle["id"])
			guide_axes = {"x", "y", "z"}
		elif active is not None and active in self.rig.HANDLES_BY_ID:
			highlight_ids = {active}
			guide_axes = self.rig.handle_axes_for_highlight(self.rig.HANDLES_BY_ID[active])

		self.rig.set_gizmo_highlight(gizmo, highlight_ids)
		self.rig.set_guide_lines(gizmo, guide_axes)

		plane_grid_id = None
		if self._snap_enabled() and mode == "translate":
			if active is not None and active in self.rig.HANDLES_BY_ID:
				h = self.rig.HANDLES_BY_ID[active]
				if h["kind"] == "plane":
					plane_grid_id = h["id"]
		self.rig.set_plane_grid(
			gizmo,
			plane_grid_id,
			plane_grid_id is not None,
			self._snap_steps(),
			self.rig.gizmo_uniform_scale(gizmo),
		)

	# ---- G4/G4b/G5 handle hit-test + drag ----
	def _hit_test(self, origin, direction, geom):
		gm = self.gm
		if geom["kind"] == "axis":
			dist = gm.ray_line_distance(origin, direction, geom["point"], geom["direction"])
			scale = self.rig.gizmo_uniform_scale(self.gizmo)
			if dist > max(self.rig.TUBE_RADIUS * scale, 1e-4):
				return None
			t_line = gm.closest_t_on_ray_to_line(origin, direction, geom["point"], geom["direction"])
			# Keep rods from stealing center clicks meant for plane chips.
			if t_line is None or not (geom["t_min"] * 0.85 <= t_line <= geom["t_max"] * 1.15):
				return None
			hit = gm.v_add(geom["point"], gm.v_scale(geom["direction"], t_line))
			return gm.v_length(gm.v_sub(hit, origin))
		if geom["kind"] == "plane":
			hit = gm.ray_vs_plane(origin, direction, geom["point"], geom["normal"])
			if hit is None:
				return None
			rel = gm.v_sub(hit, geom["point"])
			da, db = gm.v_dot(rel, geom["a_dir"]), gm.v_dot(rel, geom["b_dir"])
			if abs(da) > geom["half"] or abs(db) > geom["half"]:
				return None
			return gm.v_length(gm.v_sub(hit, origin))
		hit = gm.ray_vs_disc(origin, direction, geom["center"], geom["normal"], geom["radius"], geom["tolerance"])
		if hit is None:
			return None
		return gm.v_length(gm.v_sub(hit, origin))

	def _pick_handle(self, u, v):
		gizmo = self.gizmo
		if gizmo is None or not self.Selected:
			return None
		origin, direction = self._ray_from_panel(u, v)
		mode = self._effective_mode()
		best_id, best_t = None, None
		for handle in self.rig.HANDLES:
			if mode not in handle["modes"]:
				continue
			geom = self.rig.handle_world_geometry(gizmo, handle)
			t = self._hit_test(origin, direction, geom)
			if t is not None and (best_t is None or t < best_t):
				best_t, best_id = t, handle["id"]
		return best_id

	def BeginDrag(self, u, v):
		if not self.Selected or self.gizmo is None:
			return False
		handle_id = self._pick_handle(u, v)
		if handle_id is None:
			return False
		targets = [(path, op(path)) for path in self.Selected]
		if any(sel is None for _, sel in targets):
			return False
		mode = self._effective_mode()
		handle = self.rig.HANDLES_BY_ID[handle_id]
		write_names = handle["write"].get(mode)
		if not write_names:
			return False
		origin, direction = self._ray_from_panel(u, v)
		geom = self.rig.handle_world_geometry(self.gizmo, handle)
		gizmo = self.gizmo
		drag = {
			"handle": handle,
			"mode": mode,
			"geom": geom,
			"start_gizmo_pos": (
				float(gizmo.par.tx.eval()), float(gizmo.par.ty.eval()), float(gizmo.par.tz.eval()),
			),
			"targets": [],
		}
		for path, sel in targets:
			t_entry = {"path": path}
			if mode == "scale":
				t_entry["start_values"] = {n: float(getattr(sel.par, n).eval()) for n in write_names}
			else:
				# translate + rotate write back through world matrices so an
				# Object-COMP parent (any depth) and any Rotate Order both
				# just work -- see `_write_translate` / `_apply_rotation`.
				t_entry["start_world"] = sel.worldTransform.copy()
				t_entry["parent_world"] = self.gm.object_parent_world(sel)
			drag["targets"].append(t_entry)
		if handle["kind"] == "axis":
			drag["start_t"] = self.gm.closest_t_on_ray_to_line(origin, direction, geom["point"], geom["direction"])
		elif handle["kind"] == "plane":
			drag["start_hit"] = self.gm.ray_vs_plane(origin, direction, geom["point"], geom["normal"])
		else:
			hit = self.gm.ray_vs_plane(origin, direction, geom["center"], geom["normal"])
			drag["start_dir"] = self.gm.v_sub(hit, geom["center"]) if hit else (1.0, 0.0, 0.0)
		self.Drag = drag
		self._status("Drag begin: " + handle_id)
		self._refresh_gizmo_feedback()
		return True

	def _write_translate(self, sel, t_entry, world_delta):
		"""Apply a world-space delta to `sel`'s world pose, then convert back
		to local pars through its Object-COMP parent's world-inverse
		(identity when unparented) -- correct at any nesting depth.

		When Snapgrid is on, the final world position is quantized per axis
		before writeback (translate only).
		"""
		gm = self.gm
		start_pos = gm.matrix_col(t_entry["start_world"], 3)
		delta = self._snapped_world_delta(start_pos, world_delta)
		new_world = t_entry["start_world"].copy()
		new_world.translate(delta[0], delta[1], delta[2])
		parent_inv = t_entry["parent_world"].getInverse()
		sel.setTransform(parent_inv * new_world)

	def _apply_rotation(self, sel, t_entry, angle_delta_deg, world_normal):
		"""Rotate `sel`'s world pose about its OWN world position by a
		world-axis angle delta, then convert back to local pars. Exact for
		any Object-COMP parent depth and any Rotate Order -- `setTransform`
		round-trips through the target's own `rord` (verified live), so no
		hand-rolled euler/order table is needed here."""
		gm = self.gm
		start_world = t_entry["start_world"]
		pivot = list(gm.matrix_col(start_world, 3))
		new_world = start_world.copy()
		new_world.rotateOnAxis(list(world_normal), angle_delta_deg, pivot=pivot)
		parent_inv = t_entry["parent_world"].getInverse()
		sel.setTransform(parent_inv * new_world)

	def _update_gizmo_during_multi_drag(self, mode, translate_delta):
		"""Keep the multi-select gizmo under the cursor without re-deriving
		its pose from (possibly stale, un-refreshed) per-object AABB centers.
		Translate moves the rig by the same world delta as the objects;
		rotate/scale act in place on each object so the rig pose is static."""
		gizmo = self.gizmo
		if gizmo is None or self.Drag is None:
			return
		if mode == "translate" and translate_delta is not None:
			base = self.Drag.get("start_gizmo_pos")
			if base is not None:
				delta = self._snapped_world_delta(base, translate_delta)
				gizmo.par.tx = base[0] + delta[0]
				gizmo.par.ty = base[1] + delta[1]
				gizmo.par.tz = base[2] + delta[2]
		self._rescale_gizmo()
		self._refresh_gizmo_feedback()
		self._sync_selected_proxies()
		self._sync_selection_overlay()

	def UpdateDrag(self, u, v):
		drag = self.Drag
		if drag is None:
			return False
		targets = drag.get("targets") or []
		live = [(t, op(t["path"])) for t in targets]
		if not live or any(sel is None for _, sel in live):
			self.Drag = None
			return False
		gm = self.gm
		origin, direction = self._ray_from_panel(u, v)
		handle, geom, mode = drag["handle"], drag["geom"], drag["mode"]
		write_names = handle["write"][mode]
		translate_delta = None

		if handle["kind"] == "axis":
			t_now = gm.closest_t_on_ray_to_line(origin, direction, geom["point"], geom["direction"])
			if t_now is None or drag.get("start_t") is None:
				return True
			delta_scalar = t_now - drag["start_t"]
			if mode == "translate":
				translate_delta = gm.v_scale(geom["direction"], delta_scalar)
				for t_entry, sel in live:
					self._write_translate(sel, t_entry, translate_delta)
			else:
				ref = max(self.rig.gizmo_uniform_scale(self.gizmo), 1e-4) * self.rig.ROD_LENGTH
				name = write_names[0]
				ratio = 1.0 + delta_scalar / ref
				for t_entry, sel in live:
					start = t_entry["start_values"][name]
					setattr(sel.par, name, max(start * ratio, 1e-4))

		elif handle["kind"] == "plane":
			hit = gm.ray_vs_plane(origin, direction, geom["point"], geom["normal"])
			if hit is None or drag.get("start_hit") is None:
				return True
			world_delta = gm.v_sub(hit, drag["start_hit"])
			if mode == "translate":
				translate_delta = world_delta
				for t_entry, sel in live:
					self._write_translate(sel, t_entry, world_delta)
			else:
				ref = max(self.rig.gizmo_uniform_scale(self.gizmo), 1e-4) * self.rig.ROD_LENGTH
				delta_a, delta_b = gm.v_dot(world_delta, geom["a_dir"]), gm.v_dot(world_delta, geom["b_dir"])
				name_a, name_b = write_names
				ratio_a, ratio_b = 1.0 + delta_a / ref, 1.0 + delta_b / ref
				for t_entry, sel in live:
					start_a, start_b = t_entry["start_values"][name_a], t_entry["start_values"][name_b]
					setattr(sel.par, name_a, max(start_a * ratio_a, 1e-4))
					setattr(sel.par, name_b, max(start_b * ratio_b, 1e-4))

		else:  # disc / rotate
			hit = gm.ray_vs_plane(origin, direction, geom["center"], geom["normal"])
			if hit is None:
				return True
			cur_dir = gm.v_sub(hit, geom["center"])
			angle = gm.signed_angle_in_plane(drag["start_dir"], cur_dir, geom["normal"])
			for t_entry, sel in live:
				self._apply_rotation(sel, t_entry, angle, geom["normal"])

		# Keep the rig stuck to the selection; drag hit math still uses BeginDrag geom.
		if len(self.Selected) > 1:
			self._update_gizmo_during_multi_drag(mode, translate_delta)
		else:
			self._sync_gizmo_to_selection()
		return True

	def EndDrag(self):
		self.Drag = None
		self._refresh_object_bounds()
		self._sync_all_proxies()
		self._sync_gizmo_to_selection()
		self._status("Drag end")
		# _sync clears Hovered; next rollover sample restores highlight.

	# ---- Private edit camera: orbit / pan / dolly, seeded once ----
	def _geo_bounds_centroid(self):
		geos = [e for e in self.Objects if e.get("kind") == "geo"]
		if not geos:
			# Fall back to any discovered object (light/camera icons).
			geos = self.Objects
		if not geos:
			return None
		cx = cy = cz = 0.0
		n = 0
		for entry in geos:
			mn, mx = entry["min"], entry["max"]
			cx += 0.5 * (mn[0] + mx[0])
			cy += 0.5 * (mn[1] + mx[1])
			cz += 0.5 * (mn[2] + mx[2])
			n += 1
		if n < 1:
			return None
		return (cx / n, cy / n, cz / n)

	def _scene_cam_lookat_pivot(self, scene_cam):
		"""Best-effort look-at pivot from a scene camera; None if unavailable."""
		try:
			# lookat COMP path (common TD camera setup)
			look = scene_cam.par.lookat.eval()
			if look is not None:
				return self.gm.object_world_position(look)
		except Exception:
			pass
		try:
			# Some builds expose pivot via px/py/pz when using pivot-style look
			px = float(scene_cam.par.px.eval())
			py = float(scene_cam.par.py.eval())
			pz = float(scene_cam.par.pz.eval())
			if abs(px) + abs(py) + abs(pz) > 1e-6:
				# Pivot pars are often local; convert via worldTransform when possible.
				try:
					wp = scene_cam.worldTransform * tdu.Position(px, py, pz)
					return (float(wp.x), float(wp.y), float(wp.z))
				except Exception:
					pos = self.gm.object_world_position(scene_cam)
					return (pos[0] + px, pos[1] + py, pos[2] + pz)
		except Exception:
			pass
		return None

	def SeedCamera(self, scene_cam):
		pos = self.gm.object_world_position(scene_cam)
		_, _, fwd = self.gm.camera_basis(scene_cam)
		pivot = self._scene_cam_lookat_pivot(scene_cam)
		if pivot is None:
			pivot = self._geo_bounds_centroid()
		if pivot is None:
			pivot = self.gm.v_add(pos, self.gm.v_scale(fwd, 5.0))
		to_cam = self.gm.v_sub(pos, pivot)
		dist = max(self.gm.v_length(to_cam), 0.1)
		# If look-at was missing and we fell back to a centroid behind the cam,
		# keep a forward pivot so the orbit frame stays usable.
		if self.gm.v_dot(to_cam, fwd) < 0 and self._scene_cam_lookat_pivot(scene_cam) is None:
			pivot = self.gm.v_add(pos, self.gm.v_scale(fwd, dist))
			to_cam = self.gm.v_sub(pos, pivot)
		yaw = math.degrees(math.atan2(to_cam[0], to_cam[2]))
		pitch = math.degrees(math.asin(max(-1.0, min(1.0, to_cam[1] / dist))))
		self.Orbit = {"yaw": yaw, "pitch": pitch, "dist": dist, "pivot": pivot}
		self._apply_orbit_camera()
		self.CamSeeded = True
		self._status("Camera seeded from " + scene_cam.path)

	def ResetView(self):
		self.CamSeeded = False
		self.Discover()

	def _apply_orbit_camera(self):
		cam = self.cam
		if cam is None:
			return
		yaw, pitch = math.radians(self.Orbit["yaw"]), math.radians(self.Orbit["pitch"])
		dist, pivot = self.Orbit["dist"], self.Orbit["pivot"]
		offset = (math.cos(pitch) * math.sin(yaw), math.sin(pitch), math.cos(pitch) * math.cos(yaw))
		cam.par.tx = pivot[0] + dist * offset[0]
		cam.par.ty = pivot[1] + dist * offset[1]
		cam.par.tz = pivot[2] + dist * offset[2]
		cam.par.ry = math.degrees(yaw)
		cam.par.rx = -math.degrees(pitch)
		cam.par.rz = 0.0
		self._mirror_orient_camera(offset)
		self._rescale_gizmo()
		self._refresh_camera_proxy_visibility()

	def _mirror_orient_camera(self, offset=None):
		"""Keep cam_orient orbiting the view-cube with the same yaw/pitch."""
		cam_o = self.cam_orient
		og = self.orient
		if cam_o is None or og is None:
			return
		yaw, pitch = math.radians(self.Orbit["yaw"]), math.radians(self.Orbit["pitch"])
		if offset is None:
			offset = (
				math.cos(pitch) * math.sin(yaw),
				math.sin(pitch),
				math.cos(pitch) * math.cos(yaw),
			)
		d = og.ORIENT_CAM_DIST
		cam_o.par.tx = d * offset[0]
		cam_o.par.ty = d * offset[1]
		cam_o.par.tz = d * offset[2]
		cam_o.par.ry = math.degrees(yaw)
		cam_o.par.rx = -math.degrees(pitch)
		cam_o.par.rz = 0.0

	# ---- Orientation view-cube (ui_orient panel) ----
	def _pick_orient_zone_uv(self, u, v):
		"""Ray-pick an orient zone using u/v in the ui_orient panel (0..1)."""
		og = self.orient
		cam_o = self.cam_orient
		if og is None or cam_o is None:
			return None
		res = float(og.CUBE_RENDER_RES)
		origin, direction = self.gm.unproject_ray(cam_o, u, v, res, res)
		best_id, best_t = None, None
		for zone in og.ZONES:
			t = self.gm.ray_vs_aabb(origin, direction, zone["aabb_min"], zone["aabb_max"])
			if t is not None and (best_t is None or t < best_t):
				best_t, best_id = t, zone["id"]
		return best_id

	def _apply_orient_hover(self, zone_id):
		if zone_id == self.OrientHovered:
			return
		self.OrientHovered = zone_id
		og = self.orient
		if og is not None:
			og.set_orient_highlight(self.orient_cube, zone_id)

	def SnapView(self, direction):
		"""Instant-snap edit camera yaw/pitch to look from `direction` (pivot/dist kept)."""
		og = self.orient
		if og is None:
			return
		yaw, pitch = og.direction_to_yaw_pitch(direction)
		self.Orbit["yaw"] = yaw
		self.Orbit["pitch"] = pitch
		self._apply_orbit_camera()
		self.Unlock()
		self._status("Snap view")

	def OnOrientPanelValueChange(self, panelValue):
		"""Handle clicks/hover on the ui_orient view-cube panel."""
		ui = self.ui_orient
		if ui is None:
			return
		try:
			u, v = float(ui.panel.u.val), float(ui.panel.v.val)
			lsel = int(ui.panel.lselect.val)
		except Exception:
			return
		rollover = 0
		rollu = rollv = 0.0
		try:
			rollover = int(ui.panel.rollover.val)
			rollu = float(ui.panel.rollu.val)
			rollv = float(ui.panel.rollv.val)
		except Exception:
			pass

		self.Unlock()
		lsel_edge = bool(lsel) and not bool(getattr(self, "_orient_lsel_prev", 0))
		if lsel and not lsel_edge:
			# Armed sample (skip stale edge UV), same pattern as main panel LMB.
			if not getattr(self, "_orient_lmb_armed", False):
				self._orient_lmb_armed = True
				zone_id = self._pick_orient_zone_uv(u, v)
				zone = self.orient.ZONES_BY_ID.get(zone_id) if self.orient and zone_id else None
				if zone is not None:
					self.SnapView(zone["direction"])
		elif not lsel:
			self._orient_lmb_armed = False
		self._orient_lsel_prev = lsel

		if rollover:
			self._apply_orient_hover(self._pick_orient_zone_uv(rollu, rollv))
		else:
			self._apply_orient_hover(None)
		if not lsel:
			self.Lock()

	def _orbit_update(self, u, v):
		if self._orbit_last is None:
			self._orbit_last = (u, v)
			return
		du, dv = u - self._orbit_last[0], v - self._orbit_last[1]
		self._orbit_last = (u, v)
		self.Orbit["yaw"] += du * 220.0
		# Grab / Blender turntable: drag up lowers camera elevation.
		self.Orbit["pitch"] = max(-89.0, min(89.0, self.Orbit["pitch"] - dv * 220.0))
		self._apply_orbit_camera()

	def _pan_update(self, u, v):
		if self._pan_last is None:
			self._pan_last = (u, v)
			return
		du, dv = u - self._pan_last[0], v - self._pan_last[1]
		self._pan_last = (u, v)
		right, up, _ = self.gm.camera_basis(self.cam)
		speed = self.Orbit["dist"] * 1.2
		# Grab-pan: content follows the mouse.
		pivot = self.gm.v_sub(self.Orbit["pivot"], self.gm.v_scale(right, du * speed))
		pivot = self.gm.v_sub(pivot, self.gm.v_scale(up, dv * speed))
		self.Orbit["pivot"] = pivot
		self._apply_orbit_camera()

	def _dolly(self, wheel):
		self.Orbit["dist"] = max(0.25, self.Orbit["dist"] * (0.9 if wheel > 0 else 1.1))
		self._apply_orbit_camera()

	def _lmb_press(self, u, v, additive=False, cycle=False):
		"""Handle a single LMB press once UV is armed (not on the button edge).
		`additive` (Ctrl) / `cycle` (Alt) are forwarded to SelectAt.
		Alt (cycle) always selects — never starts a gizmo drag — so overlaps
		under the rig remain reachable in transform modes."""
		if not cycle:
			if self._current_mode() != "select" and self.Selected and self._pick_handle(u, v) is not None:
				self.BeginDrag(u, v)
				return
			if self._current_mode() != "select" and self.Selected and self._ray_near_gizmo(u, v):
				# Near-miss on the rig: ignore so we don't clear selection.
				self._status("Gizmo near-miss")
				return
		self.SelectAt(u, v, additive=additive, cycle=cycle)

	# ---- Idle-cook control (verified mechanism: op.lock, not a script early-out) ----
	_LOCK_NODES = (
		"render_edit",
		"render_gizmo",
		"composite_edit",
		"render_orient",
	)

	def Lock(self):
		for name in self._LOCK_NODES:
			node = self.ownerComp.op(name)
			if node is not None:
				node.lock = True

	def Unlock(self):
		for name in self._LOCK_NODES:
			node = self.ownerComp.op(name)
			if node is not None:
				node.lock = False

	def OpenPanel(self):
		p = self.panel
		if p is None:
			return
		try:
			# Keep the picker / snap tint current when the panel opens.
			self.RefreshRenderTopList()
			self._sync_toolbar_exec()
			self._sync_panel_exec()
			tb = self.toolbar_mod
			if tb is not None:
				tb.refresh_snap_highlight(self.toolbar, self._snap_enabled())
			p.openViewer()
		except Exception as e:
			self._status("OpenPanel fail: " + str(e)[:60])

	# ---- Panel Execute DAT entry point (fires only on value change — idle-cheap) ----
	def OnPanelValueChange(self, panelValue):
		p = self.panel
		if p is None:
			return
		try:
			u, v = float(p.panel.u.val), float(p.panel.v.val)
			lsel, rsel, msel = int(p.panel.lselect.val), int(p.panel.rselect.val), int(p.panel.mselect.val)
		except Exception:
			return
		ctrl = 0
		try:
			ctrl = int(p.panel.ctrl.val)
		except Exception:
			pass
		alt = 0
		try:
			alt = int(p.panel.alt.val)
		except Exception:
			pass
		wheel = 0.0
		try:
			wheel = float(p.panel.wheel.val)
		except Exception:
			pass

		# Hover UV (rollu/rollv) updates without a button held; plain u/v do not.
		rollover = 0
		rollu = rollv = 0.0
		try:
			rollover = int(p.panel.rollover.val)
			rollu = float(p.panel.rollu.val)
			rollv = float(p.panel.rollv.val)
		except Exception:
			pass

		active = bool(lsel or rsel or msel or wheel)
		# Unlock for button interaction OR hover feedback updates.
		if active or rollover:
			self.Unlock()

		lsel_edge = bool(lsel) and not bool(self._lsel_prev)
		rsel_edge = bool(rsel) and not bool(self._rsel_prev)
		msel_edge = bool(msel) and not bool(self._msel_prev)

		# LMB: never pick on the button-down edge (u/v often still stale).
		# Latch Ctrl/Alt on the edge — TD sets them at click time and they may
		# clear before the first non-edge UV sample that arms the pick.
		# First non-edge event while held arms + picks once; then drag.
		if lsel:
			if lsel_edge:
				self._lmb_armed = False
				self._lmb_ctrl = bool(ctrl)
				self._lmb_alt = bool(alt)
			if self.Drag is not None:
				self.UpdateDrag(u, v)
			elif not lsel_edge and not self._lmb_armed:
				self._lmb_armed = True
				additive = bool(ctrl) or bool(self._lmb_ctrl)
				cycle = bool(alt) or bool(self._lmb_alt)
				self._lmb_press(u, v, additive=additive, cycle=cycle)
		else:
			if self.Drag is not None:
				self.EndDrag()
			self._lmb_armed = False
			self._lmb_ctrl = False
			self._lmb_alt = False
		self._lsel_prev = lsel

		# RMB orbit: skip edge; seed last UV on first follow-up sample (no delta).
		if rsel:
			if rsel_edge:
				self._orbit_armed = False
				self._orbit_last = None
			elif not self._orbit_armed:
				self._orbit_last = (u, v)
				self._orbit_armed = True
			else:
				self._orbit_update(u, v)
		else:
			self._orbit_last = None
			self._orbit_armed = False
		self._rsel_prev = rsel

		if msel:
			if msel_edge:
				self._pan_armed = False
				self._pan_last = None
			elif not self._pan_armed:
				self._pan_last = (u, v)
				self._pan_armed = True
			else:
				self._pan_update(u, v)
		else:
			self._pan_last = None
			self._pan_armed = False
		self._msel_prev = msel

		if wheel:
			self._dolly(wheel)

		# Hover highlight / guide lines — skip while mid-drag (Drag owns feedback).
		if not rollover:
			self._apply_hover(None)
		elif self.Drag is None:
			self.UpdateHover(rollu, rollv)

		# Re-lock when no button interaction (hover frame is frozen in the TOP).
		if not active:
			self.Lock()
