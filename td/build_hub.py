"""Build the 4designer hub COMP (Global OP Shortcut: 4designer).

Usage (in TD / MCP):
  exec(open(r'.../4designer/td/build_hub.py', encoding='utf-8').read())
  build_hub()   # under /project1 by default
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
		candidates.append(Path(project.folder) / "4designer" / "td")
	except Exception:
		pass
	for c in candidates:
		if (c / "fourdesigner_ext.py").exists():
			return c
	raise FileNotFoundError("Could not locate the 4designer td directory")


MODULE_DIR = _module_dir()
TODAY = "2026-07-26"
def _read_version() -> str:
	"""Read the repository VERSION file."""
	candidates = [MODULE_DIR.parent / "VERSION"]
	try:
		candidates.append(Path(__file__).resolve().parent.parent / "VERSION")
	except NameError:
		pass
	for candidate in candidates:
		try:
			text = candidate.read_text(encoding="utf-8").strip()
			if text:
				return text.splitlines()[0].strip()
		except OSError:
			pass
	return "1.0.0"


VERSION = _read_version()

_TD_TYPES = (
	"baseCOMP",
	"websocketDAT",
	"textDAT",
	"executeDAT",
	"parameterexecuteDAT",
	"annotateCOMP",
	"textCOMP",
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


def _read(name: str) -> str:
	return (_module_dir() / name).read_text(encoding="utf-8")


def _read_shm_buf() -> str:
	"""Embed the shared SHM SoT, not the thin td/ re-export."""
	shared = _module_dir().parent / "shm" / "fourdesigner_shm" / "shm_buf.py"
	if shared.is_file():
		return shared.read_text(encoding="utf-8")
	return _read("shm_buf.py")


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
	page.appendStr("Daemonurl", label="Daemon URL")
	comp.par.Daemonurl = "http://127.0.0.1:9983"
	page.appendStr("Workspaceid", label="Workspace Id")
	comp.par.Workspaceid = ""
	page.appendStr("Daemondir", label="Daemon Dir")
	comp.par.Daemondir = str(MODULE_DIR.parent / "daemon")
	page.appendStr("Status", label="Status")
	comp.par.Status = "idle"
	try:
		comp.par.Status.readOnly = True
	except Exception:
		pass
	page.appendPulse("Ensuredaemon", label="Ensure Daemon")
	page.appendPulse("Openui", label="Open UI")

	# Create Marshal — clones embedded templates/marshal (no disk .py at pulse time).
	page.appendStr("Marshalname", label="Marshal Name")
	comp.par.Marshalname = "marshal1"
	page.appendOP("Marshalparent", label="Place In")
	# Empty → hub's parent network
	page.appendToggle("Demobox", label="Demo Box")
	comp.par.Demobox = True
	page.appendMenu("Defaultproxymode", label="Default Proxy Mode")
	try:
		comp.par.Defaultproxymode.menuNames = ["mask", "mesh"]
		comp.par.Defaultproxymode.menuLabels = ["Mask (AABB)", "Mesh (GLB)"]
	except Exception:
		pass
	comp.par.Defaultproxymode = "mask"
	page.appendInt("Maxmeshproxies", label="Max Mesh Proxies")
	comp.par.Maxmeshproxies = 4096
	page.appendPulse("Createmarshal", label="Create Marshal")

	about = _menu_page(comp, "About")
	about.appendStr("Compname", label="Name")
	comp.par.Compname = "4designer"
	about.appendStr("Version", label="Version")
	comp.par.Version = VERSION
	about.appendStr("Created", label="Created")
	comp.par.Created = TODAY
	about.appendStr("Lastupdate", label="Last Update")
	comp.par.Lastupdate = TODAY
	for p in ("Compname", "Version", "Created", "Lastupdate"):
		try:
			getattr(comp.par, p).readOnly = True
		except Exception:
			pass


def _load_text(comp, name: str, text: str):
	dat = comp.op(name) or comp.create(textDAT, name)
	dat.text = text
	return dat


def _embed_marshal_template(hub):
	"""Build dormant templates/marshal inside hub for clone-based Create."""
	templates = hub.op("templates") or hub.create(baseCOMP, "templates")
	templates.nodeX = -400
	templates.nodeY = 0
	templates.allowCooking = False
	try:
		templates.expose = False
	except Exception:
		pass
	# Load build_marshal.py from the same td/ folder (build-time only).
	ns = dict(globals())
	code = (_module_dir() / "build_marshal.py").read_text(encoding="utf-8")
	exec(code, ns)
	tpl = ns["build_marshal"](parent=templates, name="marshal", demo_box=False, active=False)
	tpl.nodeX = 0
	tpl.nodeY = 0
	tpl.allowCooking = False
	try:
		tpl.expose = False
	except Exception:
		pass
	tpl.par.Status = "template"
	tpl.par.Objectid = ""
	doc = templates.op("doc_templates") or templates.create(textDAT, "doc_templates")
	doc.nodeX = -200
	doc.nodeY = 0
	doc.text = (
		"Internal marshal template.\n"
		"Create Marshal on the hub clones this COMP into Place In (or hub parent).\n"
		"Do not enable Active here — clones start Active and register via op.fourdesigner.\n"
	)
	return tpl


def build_hub(parent=None, name: str = "4designer"):
	"""Create/replace hub COMP. Sets Global OP Shortcut `fourdesigner`."""
	_resolve_td_types()
	if parent is None:
		parent = op("/project1")
	existing = parent.op(name)
	if existing is not None:
		existing.destroy()
	comp = parent.create(baseCOMP, name)
	comp.nodeX = 0
	comp.nodeY = 0

	# Global OP Shortcut — discovery API for Marshals.
	# TD requires a valid Python identifier (leading digit forbidden), so
	# shortcut is `fourdesigner` → op.fourdesigner (plan wrote op.4designer).
	try:
		comp.par.opshortcut = "fourdesigner"
	except Exception:
		pass

	_ensure_pars(comp)

	ext_dat = _load_text(comp, "fourdesigner_ext", _read("fourdesigner_ext.py"))
	# Mixins (disk modules under td/ext/) — also available as sibling Text DATs.
	for mixin in ("hub_lifecycle", "render_snapshot", "shm_drain", "marshal_registry"):
		src = _module_dir() / "ext" / f"{mixin}.py"
		if src.is_file():
			_load_text(comp, mixin, src.read_text(encoding="utf-8"))
	orphan = _module_dir() / "orphan_debounce.py"
	if orphan.is_file():
		_load_text(comp, "orphan_debounce", orphan.read_text(encoding="utf-8"))
	_load_text(comp, "shm_buf", _read_shm_buf())
	ws_cb = _load_text(comp, "websocket_callbacks", _read("websocket_callbacks.py"))

	# Extension — same pattern as Stagepad: module class(me)
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

	ws = comp.op("websocket1") or comp.create(websocketDAT, "websocket1")
	ws.nodeX = 200
	ws.nodeY = 0
	ws.par.callbacks = ws_cb
	ws.par.active = False
	ws.par.netaddress = "127.0.0.1/ws"
	ws.par.port = 9983

	# Execute / Param Execute carry callbacks inline
	ex = comp.op("execute1") or comp.create(executeDAT, "execute1")
	ex.nodeX = 200
	ex.nodeY = -150
	ex.text = _read("execute_callbacks.py")
	ex.par.start = True
	ex.par.framestart = True

	pe = comp.op("parexec1") or comp.create(parameterexecuteDAT, "parexec1")
	pe.nodeX = 200
	pe.nodeY = -300
	pe.text = _read("parexec_callbacks.py")
	pe.par.op = ".."
	pe.par.pars = "*"
	pe.par.valuechange = False
	if hasattr(pe.par, "onpulse"):
		pe.par.onpulse = True

	doc = comp.op("doc_hub") or comp.create(textDAT, "doc_hub")
	doc.nodeX = -200
	doc.nodeY = 0
	doc.text = (
		"4designer hub\n"
		"- Global OP Shortcut: fourdesigner (op.fourdesigner)\n"
		"- Ensure Daemon / Open UI / Create Marshal pulses\n"
		"- Create Marshal clones templates/marshal (no disk .py at pulse time)\n"
		"- WS receives set_trs → writes Marshal chop_trs\n"
		"- Marshals register via HTTP through this hub\n"
	)

	ann = comp.op("annotate_hub") or comp.create(annotateCOMP, "annotate_hub")
	ann.nodeX = -200
	ann.nodeY = 200
	try:
		ann.par.text = "Hub: daemon + WS + Create Marshal"
	except Exception:
		pass

	# Layout
	ext_dat.nodeX = 0
	ext_dat.nodeY = -150
	ws_cb.nodeX = 0
	ws_cb.nodeY = -300

	_embed_marshal_template(comp)

	print("build_hub:", comp.path, "shortcut=", getattr(comp.par, "opshortcut", None))
	return comp


# Alias used in cheat sheet
build = build_hub


if __name__ == "__main__":
	build_hub()
