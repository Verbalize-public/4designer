"""4designer curate toolbar — Container COMP faces with Text TOP labels.

Button COMP Color paints over `par.top`, and Button has no font face, so neither
PNG Tops nor unicode labels work. Each control is a containerCOMP whose `par.top`
is a Text TOP (ASCII) — same pattern as `ui_orient`. Clicks use panel `lselect`
via `toolbar_execute_callbacks.py` → `FourdesignerExt`.
"""

from __future__ import annotations

# (name, short ASCII label, tooltip, mode)
MODE_BUTTONS = (
	("btn_select", "Sel", "Select", "select"),
	("btn_translate", "Move", "Move", "translate"),
	("btn_rotate", "Rot", "Rotate", "rotate"),
	("btn_scale", "Scl", "Scale", "scale"),
)

ACTION_BUTTONS = (
	("btn_discover", "Reload", "Reload scene"),
	("btn_resetview", "View", "Reset view"),
)

MODE_BY_BUTTON = {name: mode for name, _lab, _tip, mode in MODE_BUTTONS}
BUTTON_BY_MODE = {mode: name for name, _lab, _tip, mode in MODE_BUTTONS}

BTN_W = 44
BTN_H = 28
BTN_GAP = 4
STRIP_H = 36
MARGIN = 6
ACTION_GAP = 12
FIELD_W = 200
RIGHT_GAP = 4
FACE_W = 88
FACE_H = 56

COLOR_IDLE = (0.16, 0.16, 0.18)
COLOR_ACTIVE = (0.28, 0.48, 0.78)
COLOR_ACTION = (0.20, 0.22, 0.16)
COLOR_SNAP_ON = (0.32, 0.55, 0.38)
COLOR_FIELD_BG = (0.12, 0.12, 0.14)
COLOR_TEXT = (0.92, 0.92, 0.94)

NONE_RENDER = "__none__"

_FONT = "C:/Windows/Fonts/segoeui.ttf"


def _set_help(widget, tip):
	try:
		widget.par.help = tip
	except Exception:
		pass


def _face_name(btn_name):
	return "face_" + btn_name.replace("btn_", "")


def _make_face_top(parent, name, label, bg_rgb):
	"""Text TOP used as the visible face of a toolbar container."""
	existing = parent.op(name)
	if existing is not None:
		existing.destroy()
	top = parent.create(textTOP, name)
	top.par.text = label
	try:
		top.par.fontfile = _FONT
	except Exception:
		pass
	try:
		top.par.fontsizex = 20
	except Exception:
		try:
			top.par.fontsize = 20
		except Exception:
			pass
	r, g, b = COLOR_TEXT
	top.par.fontcolorr, top.par.fontcolorg, top.par.fontcolorb = r, g, b
	try:
		top.par.fontalpha = 1.0
	except Exception:
		pass
	br, bg, bb = bg_rgb
	try:
		top.par.bgcolorr, top.par.bgcolorg, top.par.bgcolorb = br, bg, bb
		top.par.bgalpha = 1.0
	except Exception:
		pass
	try:
		top.par.outputresolution = "custom"
		top.par.resolutionw = FACE_W
		top.par.resolutionh = FACE_H
		top.par.alignx = "center"
		top.par.aligny = "center"
	except Exception:
		pass
	try:
		top.par.display = False
	except Exception:
		pass
	return top


def _tint_face(face_top, bg_rgb):
	if face_top is None:
		return
	br, bg, bb = bg_rgb
	try:
		face_top.par.bgcolorr, face_top.par.bgcolorg, face_top.par.bgcolorb = br, bg, bb
	except Exception:
		pass


def _place(widget, x, y, width, height=BTN_H):
	widget.par.hmode = "fixed"
	widget.par.vmode = "fixed"
	widget.par.w = width
	widget.par.h = height
	widget.par.leftanchor = 0.0
	widget.par.rightanchor = 0.0
	widget.par.bottomanchor = 0.0
	widget.par.topanchor = 0.0
	widget.par.horigin = 0.0
	widget.par.vorigin = 0.0
	widget.par.x = int(x)
	widget.par.y = int(y)
	widget.par.layer = 10.0
	widget.par.display = True
	try:
		widget.par.alignallow = "ignore"
	except Exception:
		pass


def _place_right(widget, width, right_offset, y, height=BTN_H):
	widget.par.hmode = "fixed"
	widget.par.vmode = "fixed"
	widget.par.w = width
	widget.par.h = height
	widget.par.leftanchor = 1.0
	widget.par.rightanchor = 1.0
	widget.par.bottomanchor = 0.0
	widget.par.topanchor = 0.0
	widget.par.horigin = 1.0
	widget.par.vorigin = 0.0
	widget.par.x = -int(right_offset + width)
	widget.par.y = int(y)
	widget.par.layer = 10.0
	widget.par.display = True
	try:
		widget.par.alignallow = "ignore"
	except Exception:
		pass


def _make_control(parent, name, label, tip, bg_rgb, x=None, y=None, width=BTN_W, right_offset=None):
	"""Container face + Text TOP. Returns (container, face_top)."""
	comp = parent.create(containerCOMP, name)
	if comp.name != name:
		comp.name = name
	face = _make_face_top(parent, _face_name(name), label, bg_rgb)
	comp.par.top = face.path
	comp.par.topfill = "best"
	try:
		comp.par.bgalpha = 0.0
	except Exception:
		pass
	comp.par.align = "none"
	comp.par.uvbuttonsleft = True
	try:
		comp.par.reposition = "off"
	except Exception:
		pass
	if right_offset is not None:
		_place_right(comp, width, right_offset, y)
	else:
		_place(comp, x, y, width)
	_set_help(comp, tip)
	return comp, face


def build_toolbar(parent, name="ui_toolbar"):
	existing = parent.op(name)
	if existing is not None:
		existing.destroy()
	root = parent.create(containerCOMP, name)
	root.par.align = "none"
	try:
		root.par.bgcolorr = root.par.bgcolorg = root.par.bgcolorb = 0.06
		root.par.bgalpha = 0.88
	except Exception:
		pass
	root.par.hmode = "fill"
	root.par.vmode = "fixed"
	root.par.h = STRIP_H
	root.par.leftanchor = 0.0
	root.par.rightanchor = 1.0
	root.par.topanchor = 1.0
	root.par.bottomanchor = 1.0
	root.par.horigin = 0.0
	root.par.vorigin = 1.0
	root.par.topoffset = -STRIP_H
	root.par.leftoffset = 0.0
	root.par.rightoffset = 0.0
	root.par.layer = 5.0
	root.par.display = True

	y = max((STRIP_H - BTN_H) // 2, 2)
	x = MARGIN
	for bname, label, tip, _mode in MODE_BUTTONS:
		_make_control(root, bname, label, tip, COLOR_IDLE, x=x, y=y, width=BTN_W)
		x += BTN_W + BTN_GAP

	x += ACTION_GAP
	for bname, label, tip in ACTION_BUTTONS:
		width = 52 if bname == "btn_discover" else BTN_W
		_make_control(root, bname, label, tip, COLOR_ACTION, x=x, y=y, width=width)
		x += width + BTN_GAP

	right = MARGIN
	_make_control(
		root, "btn_refreshrenders", "List", "Refresh render list", COLOR_ACTION,
		y=y, width=BTN_W, right_offset=right,
	)
	right += BTN_W + RIGHT_GAP

	# Picker stays a Button COMP (variable text label, no icon needed).
	picker = root.create(buttonCOMP, "btn_rendertop")
	if picker.name != "btn_rendertop":
		picker.name = "btn_rendertop"
	picker.par.buttontype = "momentary"
	picker.par.label = "(none)"
	try:
		picker.par.fontsize = 11
	except Exception:
		pass
	picker.par.colorr, picker.par.colorg, picker.par.colorb = COLOR_FIELD_BG
	_place_right(picker, FIELD_W, right, y)
	_set_help(picker, "Render TOP")
	right += FIELD_W + RIGHT_GAP

	_make_control(
		root, "btn_snapgrid", "Snap", "Snap to grid", COLOR_IDLE,
		y=y, width=BTN_W, right_offset=right,
	)

	refresh_mode_highlight(root, "translate")
	refresh_snap_highlight(root, False)
	sync_rendertop_field(root, NONE_RENDER, ["(none)"], [NONE_RENDER])
	return root


def refresh_mode_highlight(toolbar_root, active_mode):
	if toolbar_root is None:
		return
	active_name = BUTTON_BY_MODE.get(active_mode)
	for bname, _lab, _tip, mode in MODE_BUTTONS:
		face = toolbar_root.op(_face_name(bname))
		_tint_face(face, COLOR_ACTIVE if bname == active_name else COLOR_IDLE)


def refresh_snap_highlight(toolbar_root, enabled):
	if toolbar_root is None:
		return
	face = toolbar_root.op(_face_name("btn_snapgrid"))
	_tint_face(face, COLOR_SNAP_ON if enabled else COLOR_IDLE)


def sync_rendertop_field(toolbar_root, menu_value, labels, names=None):
	if toolbar_root is None:
		return
	picker = toolbar_root.op("btn_rendertop")
	if picker is None:
		return
	if names is None:
		names = list(labels)
	value = menu_value if menu_value is not None else NONE_RENDER
	if value == "" or value is None:
		value = NONE_RENDER
	label = "(none)"
	try:
		idx = list(names).index(value)
		label = list(labels)[idx]
	except Exception:
		if value and value != NONE_RENDER:
			try:
				o = op(value)
				label = o.name if o is not None else str(value)
			except Exception:
				label = str(value)
	picker.par.label = label
	picker.par.colorr, picker.par.colorg, picker.par.colorb = COLOR_FIELD_BG
	try:
		picker.par.fontsize = 11
	except Exception:
		pass


def toolbar_button_paths(toolbar_root):
	"""Paths of clickable toolbar controls for panelexecuteDAT."""
	if toolbar_root is None:
		return []
	paths = []
	for bname, _lab, _tip, _mode in MODE_BUTTONS:
		comp = toolbar_root.op(bname)
		if comp is not None:
			paths.append(comp.path)
	for bname, _lab, _tip in ACTION_BUTTONS:
		comp = toolbar_root.op(bname)
		if comp is not None:
			paths.append(comp.path)
	for bname in ("btn_snapgrid", "btn_rendertop", "btn_refreshrenders"):
		comp = toolbar_root.op(bname)
		if comp is not None:
			paths.append(comp.path)
	return paths
