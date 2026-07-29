"""Live TD smoke for safe interaction optime.

Run inside TD / MCP:
  exec(open(r'<repo>/tests/live_optime_smoke.py', encoding='utf-8').read())
  # then inspect `result`
"""

fd = op("/project1/fourdesigner1")
ext = fd.extensions[0]
calls = {"overlay": 0, "proxies": 0, "full_sync": 0}
_orig_overlay = ext._sync_selection_overlay
_orig_proxies = ext._sync_selected_proxies
_orig_sync = ext._sync_gizmo_to_selection


def _wrap_overlay():
	calls["overlay"] += 1
	return _orig_overlay()


def _wrap_proxies():
	calls["proxies"] += 1
	return _orig_proxies()


def _wrap_sync():
	calls["full_sync"] += 1
	return _orig_sync()


ext._sync_selection_overlay = _wrap_overlay
ext._sync_selected_proxies = _wrap_proxies
ext._sync_gizmo_to_selection = _wrap_sync

out = {"ok": False, "steps": {}}
try:
	ext.Discover()
	geos = [e["path"] for e in ext.Objects if e.get("kind") == "geo"]
	if not geos:
		raise RuntimeError("no geos discovered")
	primary = geos[0]
	ext.Selected = [primary]
	ext.SetMode("translate")
	try:
		fd.par.Coordspace = "global"
	except Exception:
		pass

	gizmo = ext.gizmo
	handle = ext.rig.HANDLES_BY_ID["axis_x"]
	sel = op(primary)
	start_tx = float(sel.par.tx.eval())
	start_gz = (
		float(gizmo.par.tx.eval()),
		float(gizmo.par.ty.eval()),
		float(gizmo.par.tz.eval()),
	)
	drag = {
		"handle": handle,
		"mode": "translate",
		"geom": ext.rig.handle_world_geometry(gizmo, handle),
		"start_gizmo_pos": start_gz,
		"targets": [
			{
				"path": primary,
				"start_world": sel.worldTransform.copy(),
				"parent_world": ext.gm.object_parent_world(sel),
			}
		],
		"start_t": 0.0,
	}
	ext.Drag = drag
	calls["overlay"] = calls["proxies"] = calls["full_sync"] = 0
	for i in range(8):
		delta = (0.05 * (i + 1), 0.0, 0.0)
		for t_entry in drag["targets"]:
			ext._write_translate(op(t_entry["path"]), t_entry, delta)
		ext._pose_gizmo_during_drag("translate", delta)
	mid_overlay = calls["overlay"]
	mid_proxies = calls["proxies"]
	mid_sync = calls["full_sync"]
	after_tx = float(sel.par.tx.eval())
	gz_tx = float(gizmo.par.tx.eval())
	ext.EndDrag()
	end_had_sync = calls["full_sync"] >= 1

	try:
		fd.par.Coordspace = "local"
	except Exception:
		pass
	ext.Selected = [primary]
	ext.SetMode("rotate")
	_orig_sync()
	handle_r = ext.rig.HANDLES_BY_ID["disc_y"]
	sel = op(primary)
	drag_r = {
		"handle": handle_r,
		"mode": "rotate",
		"geom": ext.rig.handle_world_geometry(gizmo, handle_r),
		"start_gizmo_pos": (
			float(gizmo.par.tx.eval()),
			float(gizmo.par.ty.eval()),
			float(gizmo.par.tz.eval()),
		),
		"targets": [
			{
				"path": primary,
				"start_world": sel.worldTransform.copy(),
				"parent_world": ext.gm.object_parent_world(sel),
			}
		],
		"start_dir": (1.0, 0.0, 0.0),
	}
	ext.Drag = drag_r
	calls["overlay"] = 0
	ext._apply_rotation(sel, drag_r["targets"][0], 25.0, (0.0, 1.0, 0.0))
	ext._pose_gizmo_during_drag("rotate", None)
	local_rot_overlay = calls["overlay"]
	wp = ext.gm.object_world_pose_matrix(sel)
	gp = gizmo.worldTransform
	pose_ok = (
		abs(wp[0, 3] - gp[0, 3]) < 1e-3
		and abs(wp[1, 3] - gp[1, 3]) < 1e-3
		and abs(wp[2, 3] - gp[2, 3]) < 1e-3
	)
	ext.EndDrag()

	# Multi translate light pose
	if len(geos) >= 2:
		ext.Selected = geos[:2]
		ext.SetMode("translate")
		try:
			fd.par.Coordspace = "global"
		except Exception:
			pass
		_orig_sync()
		gizmo = ext.gizmo
		targets = []
		for path in ext.Selected:
			s = op(path)
			targets.append(
				{
					"path": path,
					"start_world": s.worldTransform.copy(),
					"parent_world": ext.gm.object_parent_world(s),
				}
			)
		ext.Drag = {
			"handle": handle,
			"mode": "translate",
			"geom": ext.rig.handle_world_geometry(gizmo, handle),
			"start_gizmo_pos": (
				float(gizmo.par.tx.eval()),
				float(gizmo.par.ty.eval()),
				float(gizmo.par.tz.eval()),
			),
			"targets": targets,
			"start_t": 0.0,
		}
		calls["overlay"] = calls["proxies"] = 0
		delta = (0.1, 0.0, 0.0)
		for t_entry in targets:
			ext._write_translate(op(t_entry["path"]), t_entry, delta)
		ext._pose_gizmo_during_drag("translate", delta)
		multi_mid = calls["overlay"] == 0 and calls["proxies"] == 0
		ext.EndDrag()
	else:
		multi_mid = True

	hits = ext._pick_hits_at(0.5, 0.5)
	pick_ok = isinstance(hits, list)

	ext.Lock()
	any_locked = ext._any_render_locked()
	re = fd.op("render_edit")
	rg = fd.op("render_gizmo")
	if re is not None:
		re.lock = False
	if rg is not None:
		rg.lock = True
	partial = ext._any_render_locked()
	ext.Unlock()
	unlocked = not ext._any_render_locked()

	yaw0 = float(ext.Orbit["yaw"])
	ext.Orbit["yaw"] = yaw0 + 3.0
	ext._apply_orbit_camera(aux=False)
	yaw1 = float(ext.Orbit["yaw"])

	# Fail-open: force light-pose exception → full sync once.
	_snapped = ext._snapped_world_delta

	def _boom_snap(base, delta):
		raise RuntimeError("forced-light-pose")

	ext._snapped_world_delta = _boom_snap
	ext.Drag = {"start_gizmo_pos": (0.0, 0.0, 0.0)}
	calls["full_sync"] = 0
	ext._pose_gizmo_during_drag("translate", (1.0, 0.0, 0.0))
	fail_open_sync = calls["full_sync"] >= 1
	ext._snapped_world_delta = _snapped
	ext.Drag = None

	out["steps"] = {
		"discover": len(ext.Objects),
		"byPath": len(ext.ObjectsByPath),
		"midDragOverlay": mid_overlay,
		"midDragProxies": mid_proxies,
		"midDragFullSync": mid_sync,
		"txMoved": after_tx != start_tx,
		"gizmoTxMoved": abs(gz_tx - start_gz[0]) > 1e-6,
		"endDragHadSync": end_had_sync,
		"localRotOverlayMid": local_rot_overlay,
		"localRotPoseOk": pose_ok,
		"multiMidClean": multi_mid,
		"pickOk": pick_ok,
		"anyLockedAfterLock": any_locked,
		"partialLockDetected": partial,
		"unlockClears": unlocked,
		"orbitYawChanged": yaw1 != yaw0,
		"failOpenSync": fail_open_sync,
	}
	out["ok"] = (
		mid_overlay == 0
		and mid_proxies == 0
		and mid_sync == 0
		and after_tx != start_tx
		and local_rot_overlay == 0
		and pose_ok
		and multi_mid
		and pick_ok
		and any_locked
		and partial
		and unlocked
		and fail_open_sync
		and end_had_sync
	)
finally:
	ext._sync_selection_overlay = _orig_overlay
	ext._sync_selected_proxies = _orig_proxies
	ext._sync_gizmo_to_selection = _orig_sync
	ext.Drag = None

result = out
