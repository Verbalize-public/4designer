"""Build a Marshal COMP: In POP → transformPOP ← chop_trs → Out POP.

Usage (in TD / MCP):
  exec(open(r'.../4designer/td/build_marshal.py', encoding='utf-8').read())
  build_marshal()                 # under /project1
  build_marshal(demo_box=True)    # also create boxPOP wired to In
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
		if (c / "marshal_ext.py").exists():
			return c
	raise FileNotFoundError("Could not locate the 4designer td directory")


MODULE_DIR = None  # resolved at call time via _module_dir()
TODAY = "2026-07-26"


def _read_version() -> str:
	"""Read the repository VERSION file."""
	md = _module_dir()
	for candidate in (md.parent / "VERSION",):
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
	"inPOP",
	"outPOP",
	"nullPOP",
	"transformPOP",
	"boxPOP",
	"constantCHOP",
	"textDAT",
	"executeDAT",
	"parameterexecuteDAT",
	"annotateCOMP",
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


def _ensure_pars(comp, name: str):
	_destroy_custom_pages(comp)
	page = _menu_page(comp, "Marshal")
	page.appendToggle("Active", label="Active")
	# Caller sets Active after create (template builds pass active=False).
	comp.par.Active = False
	page.appendStr("Name", label="Name")
	comp.par.Name = name
	page.appendInt("Layer", label="Layer")
	comp.par.Layer = 0
	page.appendMenu("Proxymode", label="Proxy Mode")
	try:
		comp.par.Proxymode.menuNames = ["mask", "mesh"]
		comp.par.Proxymode.menuLabels = ["Mask (AABB)", "Mesh (GLB)"]
	except Exception:
		pass
	comp.par.Proxymode = "mask"
	page.appendPulse("Refreshproxy", label="Refresh Proxy")
	page.appendToggle("Autoproxy", label="Auto Proxy")
	comp.par.Autoproxy = False
	page.appendStr("Proxystatus", label="Proxy Status")
	comp.par.Proxystatus = "idle"
	try:
		comp.par.Proxystatus.readOnly = True
	except Exception:
		pass
	page.appendStr("Objectid", label="Object Id")
	comp.par.Objectid = ""
	try:
		comp.par.Objectid.readOnly = True
	except Exception:
		pass
	page.appendStr("Status", label="Status")
	comp.par.Status = "idle"
	try:
		comp.par.Status.readOnly = True
	except Exception:
		pass
	page.appendOP("Hub", label="Hub Override")
	# leave empty — primary discovery is op.fourdesigner

	about = _menu_page(comp, "About")
	about.appendStr("Compname", label="Name")
	comp.par.Compname = "marshal"
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


def _setup_const_chop(chop):
	"""Configure Constant CHOP with tx..sz channels."""
	channels = [
		("tx", 0.0), ("ty", 0.0), ("tz", 0.0),
		("rx", 0.0), ("ry", 0.0), ("rz", 0.0),
		("sx", 1.0), ("sy", 1.0), ("sz", 1.0),
	]
	# Ensure enough const slots
	try:
		if hasattr(chop.par, "constsize"):
			chop.par.constsize = len(channels)
		elif hasattr(chop.par, "size"):
			chop.par.size = len(channels)
	except Exception:
		pass
	for i, (nm, val) in enumerate(channels):
		name_par = getattr(chop.par, f"const{i}name", None)
		val_par = getattr(chop.par, f"const{i}value", None)
		if name_par is not None and val_par is not None:
			name_par.val = nm
			val_par.val = float(val)
			continue
		# Older naming: name0 / value0
		name_par = getattr(chop.par, f"name{i}", None)
		val_par = getattr(chop.par, f"value{i}", None)
		if name_par is not None and val_par is not None:
			name_par.val = nm
			val_par.val = float(val)


def _bind_transform_to_chop(xform, chop_name: str = "chop_trs"):
	"""Express transformPOP TRS from local Constant CHOP (relative)."""
	expr = "op('{}')['{}']".format
	pairs = (
		("tx", "tx"), ("ty", "ty"), ("tz", "tz"),
		("rx", "rx"), ("ry", "ry"), ("rz", "rz"),
		("sx", "sx"), ("sy", "sy"), ("sz", "sz"),
	)
	for par_name, ch in pairs:
		par = getattr(xform.par, par_name, None)
		if par is None:
			continue
		try:
			par.expr = expr(chop_name, ch)
		except Exception:
			try:
				par.mode = ParMode.EXPRESSION
				par.expr = expr(chop_name, ch)
			except Exception:
				pass


def build_marshal(
	parent=None,
	name: str = "marshal1",
	demo_box: bool = False,
	active: bool = True,
):
	"""Create/replace Marshal COMP. Discovers hub via op.fourdesigner only.

	Pass active=False when embedding a dormant template (e.g. hub templates/marshal).
	"""
	_resolve_td_types()
	if parent is None:
		parent = op("/project1")
	existing = parent.op(name)
	if existing is not None:
		existing.destroy()
	comp = parent.create(baseCOMP, name)
	comp.nodeX = 400
	comp.nodeY = 0
	_ensure_pars(comp, name)
	comp.par.Active = bool(active)

	ext_dat = comp.op("marshal_ext") or comp.create(textDAT, "marshal_ext")
	ext_dat.text = _read("marshal_ext.py")
	ext_dat.nodeX = 0
	ext_dat.nodeY = -200

	pm_dat = comp.op("proxy_mesh") or comp.create(textDAT, "proxy_mesh")
	pm_dat.text = _read("proxy_mesh.py")
	pm_dat.nodeX = 0
	pm_dat.nodeY = -350

	try:
		comp.par.ext0object = "op('./marshal_ext').module.MarshalExt(me)"
		comp.par.ext0name = "MarshalExt"
		comp.par.ext0promote = True
		comp.par.reinitextensions.pulse()
	except Exception:
		pass
	try:
		comp.initializeExtensions()
	except Exception:
		pass

	inp = comp.create(inPOP, "in1")
	inp.nodeX = 0
	inp.nodeY = 0

	null_rest = comp.create(nullPOP, "null_rest")
	null_rest.nodeX = 150
	null_rest.nodeY = 0
	null_rest.inputConnectors[0].connect(inp)

	chop = comp.create(constantCHOP, "chop_trs")
	chop.nodeX = 0
	chop.nodeY = 150
	_setup_const_chop(chop)

	xform = comp.create(transformPOP, "transform1")
	xform.nodeX = 300
	xform.nodeY = 0
	xform.inputConnectors[0].connect(null_rest)
	_bind_transform_to_chop(xform, "chop_trs")

	null_out = comp.create(nullPOP, "null_out")
	null_out.nodeX = 500
	null_out.nodeY = 0
	null_out.inputConnectors[0].connect(xform)

	outp = comp.create(outPOP, "out1")
	outp.nodeX = 700
	outp.nodeY = 0
	outp.inputConnectors[0].connect(null_out)

	pe = comp.create(parameterexecuteDAT, "parexec1")
	pe.nodeX = 200
	pe.nodeY = -200
	pe.text = _read("marshal_parexec_callbacks.py")
	pe.par.op = ".."
	pe.par.pars = "Active Layer Name Proxymode Autoproxy Refreshproxy"
	pe.par.valuechange = True
	if hasattr(pe.par, "onpulse"):
		pe.par.onpulse = True

	ex = comp.create(executeDAT, "execute1")
	ex.nodeX = 200
	ex.nodeY = -500
	ex.text = _read("marshal_execute_callbacks.py")
	# Dormant templates must not register on hub cook.
	ex.par.start = bool(active)
	ex.par.exit = bool(active)

	doc = comp.create(textDAT, "doc_marshal")
	doc.nodeX = -200
	doc.nodeY = 0
	doc.text = (
		"Marshal\n"
		"In → null_rest → transformPOP ← chop_trs → Out\n"
		"Proxymode: mask (AABB only) | mesh (decimated GLB)\n"
		"Hub: op.fourdesigner — Refresh Proxy pulses bounds (+ GLB if mesh).\n"
	)

	# Optional demo geometry outside the COMP for wiring
	box = None
	if demo_box:
		box = parent.op(f"{name}_box") or parent.create(boxPOP, f"{name}_box")
		box.nodeX = comp.nodeX - 200
		box.nodeY = comp.nodeY
		try:
			inp.inputConnectors[0].connect(box)
		except Exception:
			# In POP connects from outside
			pass
		# Wire from outside: box → marshal
		try:
			comp.inputConnectors[0].connect(box)
		except Exception:
			pass

	print("build_marshal:", comp.path)
	return comp


build = build_marshal


if __name__ == "__main__":
	build_marshal(demo_box=True)
