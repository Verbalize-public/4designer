"""Build the 4designer COMP (drop-in .tox) — one self-contained Container COMP.

Usage (in TD / MCP):
  exec(open(r'.../4designer/td/build_fourdesigner_op.py', encoding='utf-8').read())
  build_fourdesigner_op()   # under /project1 by default
"""

from __future__ import annotations

from pathlib import Path


def _module_dir() -> Path:
	candidates = []
	try:
		candidates.append(Path(__file__).resolve().parent)
	except Exception:
		pass
	try:
		folder = Path(project.folder)
		candidates.append(folder / "4designer" / "td")
		# td-sandbox/toe/_agent_* → walk up looking for sibling 4designer/td
		for parent in folder.parents:
			candidates.append(parent / "4designer" / "td")
			if parent.name.lower() == "projects" or parent.name.lower() == "derivative":
				break
	except Exception:
		pass
	for c in candidates:
		if (c / "fourdesigner_ext.py").exists():
			return c
	raise FileNotFoundError("Could not locate the 4designer td directory")


TODAY = "2026-07-29"


def _td_dir() -> Path:
	"""Resolve the td/ source dir; honor a pre-set MODULE_DIR (exec override)."""
	override = globals().get("MODULE_DIR")
	if override:
		return Path(override)
	return _module_dir()


def _read(name: str) -> str:
	return (_td_dir() / name).read_text(encoding="utf-8")


def _read_version() -> str:
	try:
		text = (_td_dir().parent / "VERSION").read_text(encoding="utf-8").strip()
		if text:
			return text.splitlines()[0].strip()
	except Exception:
		pass
	return "0.1.0"


try:
	VERSION = _read_version()
except Exception:
	VERSION = "0.1.0"

_TD_TYPES = (
	"containerCOMP",
	"geometryCOMP",
	"nullCOMP",
	"cameraCOMP",
	"buttonCOMP",
	"renderTOP",
	"compositeTOP",
	"transformTOP",
	"textTOP",
	"moviefileinTOP",
	"textDAT",
	"panelexecuteDAT",
	"parameterexecuteDAT",
)


def _resolve_td_types(ns: dict | None = None) -> None:
	import sys

	candidates = []
	if ns:
		candidates.append(ns)
	candidates.append(globals())
	candidates.append(sys.modules.get("__main__").__dict__ if "__main__" in sys.modules else {})
	try:
		import inspect
		frame = inspect.currentframe()
		while frame is not None:
			candidates.append(frame.f_globals)
			frame = frame.f_back
	except Exception:
		pass
	for name in _TD_TYPES:
		if name in globals() and globals()[name] is not None:
			continue
		for c in candidates:
			if c and name in c:
				globals()[name] = c[name]
				break
		else:
			try:
				import td as _td
				if hasattr(_td, name):
					globals()[name] = getattr(_td, name)
			except Exception:
				pass


def _menu_page(comp, page_name: str):
	for p in comp.customPages:
		if p.name == page_name:
			return p
	return comp.appendCustomPage(page_name)


def _destroy_custom_pages(comp):
	try:
		for page in list(comp.customPages):
			page.destroy()
	except Exception:
		pass


def _ensure_pars(comp):
	_destroy_custom_pages(comp)
	page = _menu_page(comp, "4designer")
	page.appendOP("Rendertop", label="Render TOP")
	page.appendMenu("Rendertopchoice", label="Render TOP (toolbar)")
	# Overwrite TD's default name1/Label 1 trio immediately (empty string is invalid).
	try:
		comp.par.Rendertopchoice.menuNames = ["__none__"]
		comp.par.Rendertopchoice.menuLabels = ["(none)"]
	except Exception:
		pass
	comp.par.Rendertopchoice = "__none__"
	page.appendPulse("Refreshrenders", label="Refresh Renders")
	page.appendMenu("Mode", label="Gizmo Mode")
	try:
		comp.par.Mode.menuNames = ["select", "translate", "scale", "rotate"]
		comp.par.Mode.menuLabels = ["Select", "Translate", "Scale", "Rotate"]
	except Exception:
		pass
	comp.par.Mode = "translate"
	page.appendToggle("Snapgrid", label="Snap to Grid")
	comp.par.Snapgrid = False
	page.appendFloat("Snapgridx", label="Snap Grid X")
	page.appendFloat("Snapgridy", label="Snap Grid Y")
	page.appendFloat("Snapgridz", label="Snap Grid Z")
	comp.par.Snapgridx = 0.1
	comp.par.Snapgridy = 0.1
	comp.par.Snapgridz = 0.1
	page.appendPulse("Discover", label="Discover")
	page.appendPulse("Resetview", label="Reset View")
	page.appendPulse("Openpanel", label="Open Panel")
	page.appendStr("Status", label="Status")
	comp.par.Status = "idle"
	try:
		comp.par.Status.readOnly = True
	except Exception:
		pass

	about = _menu_page(comp, "About")
	about.appendStr("Compname", label="Name")
	comp.par.Compname = "fourdesigner"
	about.appendStr("Version", label="Version")
	comp.par.Version = VERSION
	about.appendStr("Created", label="Created")
	comp.par.Created = TODAY
	for p in ("Compname", "Version", "Created"):
		try:
			getattr(comp.par, p).readOnly = True
		except Exception:
			pass


def _load_text(comp, name: str, text: str):
	dat = comp.op(name) or comp.create(textDAT, name)
	dat.text = text
	return dat


def build_fourdesigner_op(parent=None, name: str = "fourdesigner1"):
	"""Create/replace the 4designer COMP. Container = Panel + pivot for the
	whole rig: one node, one drop-in .tox, no separate child panel."""
	_resolve_td_types()
	if parent is None:
		parent = op("/project1")
	existing = parent.op(name)
	if existing is not None:
		existing.destroy()
	comp = parent.create(containerCOMP, name)
	comp.nodeX, comp.nodeY = 0, 0

	_ensure_pars(comp)

	# Sibling Text DAT modules — resolve each other via relative op() lookups.
	gm_dat = _load_text(comp, "gizmo_math", _read("gizmo_math.py"))
	rig_dat = _load_text(comp, "gizmo_rig", _read("gizmo_rig.py"))
	icons_dat = _load_text(comp, "proxy_icons", _read("proxy_icons.py"))
	sel_dat = _load_text(comp, "selection_overlay", _read("selection_overlay.py"))
	toolbar_dat = _load_text(comp, "toolbar", _read("toolbar.py"))
	orient_dat = _load_text(comp, "orient_gizmo", _read("orient_gizmo.py"))
	ext_dat = _load_text(comp, "fourdesigner_ext", _read("fourdesigner_ext.py"))
	gm_dat.nodeX, gm_dat.nodeY = -300, 300
	rig_dat.nodeX, rig_dat.nodeY = -300, 150
	icons_dat.nodeX, icons_dat.nodeY = -300, 75
	sel_dat.nodeX, sel_dat.nodeY = -300, 225
	toolbar_dat.nodeX, toolbar_dat.nodeY = -300, -75
	orient_dat.nodeX, orient_dat.nodeY = -300, -150
	ext_dat.nodeX, ext_dat.nodeY = -300, 0

	try:
		comp.par.ext0object = "op('./fourdesigner_ext').module.FourdesignerExt(me)"
		comp.par.ext0name = "FourdesignerExt"
		comp.par.ext0promote = True
		comp.par.reinitextensions.pulse()
	except Exception:
		pass
	try:
		comp.initializeExtensions()
	except Exception:
		pass

	cam = comp.op("cam_edit") or comp.create(cameraCOMP, "cam_edit")
	cam.nodeX, cam.nodeY = 0, 300
	# `gizmo_screen_scale` assumes `fov` == vertical FOV; TD's own default
	# (viewanglemethod=horzfov) would silently break that formula.
	cam.par.viewanglemethod = "vertfov"
	cam.par.tz = 6.0
	cam.par.near = 0.01
	cam.par.far = 100000

	# Scene pass (opaque) + gizmo pass (transparent clear) → Composite Over.
	rend = comp.op("render_edit") or comp.create(renderTOP, "render_edit")
	rend.nodeX, rend.nodeY = 0, 150
	rend.par.camera = cam.path
	rend.par.outputresolution = "custom"
	rend.par.resolutionw = 1280
	rend.par.resolutionh = 720
	rend.par.bgcolorr = rend.par.bgcolorg = rend.par.bgcolorb = 0.0
	rend.par.bgcolora = 1.0

	rend_g = comp.op("render_gizmo") or comp.create(renderTOP, "render_gizmo")
	rend_g.nodeX, rend_g.nodeY = 200, 150
	rend_g.par.camera = cam.path
	rend_g.par.outputresolution = "custom"
	rend_g.par.resolutionw = 1280
	rend_g.par.resolutionh = 720
	rend_g.par.bgcolorr = rend_g.par.bgcolorg = rend_g.par.bgcolorb = 0.0
	rend_g.par.bgcolora = 0.0

	comp_edit = comp.op("composite_edit") or comp.create(compositeTOP, "composite_edit")
	comp_edit.nodeX, comp_edit.nodeY = 100, 50
	comp_edit.par.operand = "over"
	comp_edit.par.outputresolution = "custom"
	comp_edit.par.resolutionw = 1280
	comp_edit.par.resolutionh = 720
	# First connected = scene, second = gizmo. swaporder puts second on top.
	rend.outputConnectors[0].connect(comp_edit)
	rend_g.outputConnectors[0].connect(comp_edit)
	comp_edit.par.swaporder = True

	rig = rig_dat.module
	rig.build_gizmo_rig(comp, name="gizmo1")
	gizmo = comp.op("gizmo1")
	gizmo.nodeX, gizmo.nodeY = 0, 0

	proxies = icons_dat.module.ensure_proxies_root(comp, "proxies")
	proxies.nodeX, proxies.nodeY = 200, 0

	selection = sel_dat.module.ensure_selection_root(comp, "selection1")
	selection.nodeX, selection.nodeY = 200, -150

	# ---- Orientation view-cube (bottom-right panel overlay) ----
	# Docked child Container (same idea as the toolbar). Transform TOP cannot
	# reliably keep a small render at native pixel size inside a 1280x720 canvas.
	orient_mod = orient_dat.module
	orient_cube = orient_mod.build_orient_cube(comp, name="orient_cube")
	orient_cube.nodeX, orient_cube.nodeY = 400, 0

	cam_o = comp.op("cam_orient") or comp.create(cameraCOMP, "cam_orient")
	cam_o.nodeX, cam_o.nodeY = 400, 300
	cam_o.par.viewanglemethod = "vertfov"
	cam_o.par.projection = "ortho"
	try:
		cam_o.par.orthowidth = orient_mod.ORIENT_ORTHO_WIDTH
	except Exception:
		pass
	cam_o.par.fov = 30.0
	cam_o.par.near = 0.01
	cam_o.par.far = 1000
	cam_o.par.tz = orient_mod.ORIENT_CAM_DIST

	rend_o = comp.op("render_orient") or comp.create(renderTOP, "render_orient")
	rend_o.nodeX, rend_o.nodeY = 400, 150
	rend_o.par.camera = cam_o.path
	orient_mod.wire_orient_render(rend_o, orient_cube)
	rend_o.par.outputresolution = "custom"
	rend_o.par.resolutionw = orient_mod.CUBE_RENDER_RES
	rend_o.par.resolutionh = orient_mod.CUBE_RENDER_RES
	rend_o.par.bgcolorr = rend_o.par.bgcolorg = rend_o.par.bgcolorb = 0.0
	rend_o.par.bgcolora = 0.0

	ui_orient = orient_mod.build_orient_panel(comp, rend_o, name="ui_orient")
	ui_orient.nodeX, ui_orient.nodeY = 600, -150
	# Parent size is applied below; re-dock after w/h are known.
	_orient_panel = ui_orient
	_orient_mod = orient_mod

	# ---- Curate toolbar (native Button COMPs, top strip overlay) ----
	toolbar_mod = toolbar_dat.module
	toolbar = toolbar_mod.build_toolbar(comp, name="ui_toolbar")
	toolbar.nodeX, toolbar.nodeY = 600, 0

	pexec = comp.op("panel_exec") or comp.create(panelexecuteDAT, "panel_exec")
	pexec.nodeX, pexec.nodeY = 300, 0
	pexec.par.panels = comp.path
	pexec.par.panelvalue = "u v lselect rselect mselect wheel rollover rollu rollv ctrl alt"
	pexec.par.valuechange = True
	pexec.par.offtoon = False
	pexec.par.ontooff = False
	pexec.par.whileon = False
	pexec.par.whileoff = False
	pexec.par.active = True
	pexec.text = _read("panel_execute_callbacks.py")

	oexec = comp.op("orient_exec") or comp.create(panelexecuteDAT, "orient_exec")
	oexec.nodeX, oexec.nodeY = 300, -450
	oexec.par.panels = ui_orient.path
	oexec.par.panelvalue = "u v lselect rollover rollu rollv"
	oexec.par.valuechange = True
	oexec.par.offtoon = False
	oexec.par.ontooff = False
	oexec.par.whileon = False
	oexec.par.whileoff = False
	oexec.par.active = True
	oexec.text = _read("orient_execute_callbacks.py")

	texec = comp.op("toolbar_exec") or comp.create(panelexecuteDAT, "toolbar_exec")
	texec.nodeX, texec.nodeY = 300, -300
	toolbar_mod.sync_toolbar_exec(comp, toolbar)
	# Containers use lselect; the Render TOP picker Button COMP uses select.
	# Only Value Change — if Off→On is also on, TD can fire both and toggle
	# buttons (Snapgrid) undo themselves while idempotent actions look fine.
	texec.par.panelvalue = "select lselect"
	texec.par.valuechange = True
	texec.par.offtoon = False
	texec.par.ontooff = False
	texec.par.whileon = False
	texec.par.whileoff = False
	texec.par.active = True
	texec.text = _read("toolbar_execute_callbacks.py")

	# Remove obsolete field_exec if rebuilding an older tox.
	old_fexec = comp.op("field_exec")
	if old_fexec is not None:
		old_fexec.destroy()

	parexec = comp.op("param_exec") or comp.create(parameterexecuteDAT, "param_exec")
	parexec.nodeX, parexec.nodeY = 300, -150
	parexec.par.op = ".."
	parexec.par.pars = (
		"Rendertop Rendertopchoice Refreshrenders Mode Snapgrid "
		"Snapgridx Snapgridy Snapgridz "
		"Discover Resetview Openpanel"
	)
	parexec.par.valuechange = True
	if hasattr(parexec.par, "onpulse"):
		parexec.par.onpulse = True
	parexec.text = _read("param_execute_callbacks.py")

	doc = comp.op("doc_fourdesigner") or comp.create(textDAT, "doc_fourdesigner")
	doc.nodeX, doc.nodeY = -300, 450
	doc.text = (
		"4designer\n"
		"Set Rendertop (toolbar picker or parameter) -> pulse Open Panel.\n"
		"Toolbar left: Select | Move | Rotate | Scale + Reload / View / Grid.\n"
		"Toolbar right: Render TOP picker + List (grouped).\n"
		"Orient cube bottom-right. Self-contained -- no Render Pick DAT.\n"
		"See README.md.\n"
	)

	# Default Viewer = Control Panel Viewer for Panel COMPs.
	comp.par.nodeview = "default"
	comp.par.top = "./composite_edit"
	comp.par.topfill = "best"
	comp.par.align = "none"
	comp.par.w = 1280
	comp.par.h = 720
	comp.par.hmode = "fixed"
	comp.par.vmode = "fixed"
	# Re-dock orient panel now that parent size is final.
	try:
		size = int(_orient_mod.CUBE_VIEWPORT_SIZE)
		margin = int(_orient_mod.CUBE_MARGIN)
		_orient_panel.par.x = 1280 - margin - size
		_orient_panel.par.y = margin
		_orient_panel.par.w = size
		_orient_panel.par.h = size
	except Exception:
		pass
	comp.par.uvbuttonsleft = True
	comp.par.uvbuttonsmiddle = True
	comp.par.uvbuttonsright = True
	comp.par.mousewheel = True
	comp.par.reposition = "off"
	comp.viewer = True

	# Seed the toolbar Render TOP menu from the parent network.
	try:
		comp.ext.FourdesignerExt.RefreshRenderTopList()
	except Exception:
		pass

	print("build_fourdesigner_op:", comp.path)
	return comp


build = build_fourdesigner_op


if __name__ == "__main__":
	build_fourdesigner_op()
