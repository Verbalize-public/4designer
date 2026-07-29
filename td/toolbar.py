"""4designer curate toolbar — native Button COMPs overlaid on the panel.

Top-docked strip (`ui_toolbar`) with absolute-positioned buttons (align=none).
Mode buttons share a radio group; Discover / Reset View are momentary. Click
dispatch lives in `toolbar_execute_callbacks.py` → `FourdesignerExt`.
"""

from __future__ import annotations

MODE_BUTTONS = (
	("btn_select", "Select", "select"),
	("btn_translate", "Move", "translate"),
	("btn_rotate", "Rotate", "rotate"),
	("btn_scale", "Scale", "scale"),
)

ACTION_BUTTONS = (
	("btn_discover", "Reload"),
	("btn_resetview", "Reset View"),
)

MODE_BY_BUTTON = {name: mode for name, _label, mode in MODE_BUTTONS}
BUTTON_BY_MODE = {mode: name for name, _label, mode in MODE_BUTTONS}

BTN_W = 72
BTN_H = 26
BTN_GAP = 4
STRIP_H = 34
MARGIN = 6
ACTION_GAP = 12  # extra gap before Reload / Reset View

COLOR_IDLE = (0.22, 0.22, 0.24)
COLOR_ACTIVE = (0.30, 0.52, 0.82)
COLOR_ACTION = (0.28, 0.28, 0.22)


def _set_color(btn, rgb):
	r, g, b = rgb
	btn.par.colorr, btn.par.colorg, btn.par.colorb = r, g, b


def _place_button(btn, x, y, width):
	"""Absolute pixel placement inside the toolbar strip (origin = bottom-left)."""
	btn.par.hmode = "fixed"
	btn.par.vmode = "fixed"
	btn.par.w = width
	btn.par.h = BTN_H
	# Clear anchors so x/y are the sole drivers (verified: anchors left x/y at 0).
	btn.par.leftanchor = 0.0
	btn.par.rightanchor = 0.0
	btn.par.bottomanchor = 0.0
	btn.par.topanchor = 0.0
	btn.par.horigin = 0.0
	btn.par.vorigin = 0.0
	btn.par.x = int(x)
	btn.par.y = int(y)
	btn.par.layer = 10.0
	btn.par.display = True
	try:
		btn.par.fontsize = 11
	except Exception:
		pass
	try:
		btn.par.alignallow = "ignore"
	except Exception:
		pass


def build_toolbar(parent, name="ui_toolbar"):
	"""Create (or replace) a top-docked toolbar strip with mode/action buttons.

	Named `ui_toolbar` so it does not collide with the sibling Text DAT module
	`toolbar`.
	"""
	existing = parent.op(name)
	if existing is not None:
		existing.destroy()
	root = parent.create(containerCOMP, name)
	root.par.align = "none"
	try:
		root.par.bgcolorr = root.par.bgcolorg = root.par.bgcolorb = 0.08
		root.par.bgalpha = 0.75
	except Exception:
		pass
	# Dock as a top strip spanning the panel width.
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
	for bname, label, _mode in MODE_BUTTONS:
		btn = root.create(buttonCOMP, bname)
		if btn.name != bname:
			btn.name = bname
		btn.par.label = label
		btn.par.buttontype = "radiodown"
		btn.par.buttongroup = "fourdesigner_mode"
		_place_button(btn, x, y, BTN_W)
		_set_color(btn, COLOR_IDLE)
		x += BTN_W + BTN_GAP

	x += ACTION_GAP
	for bname, label in ACTION_BUTTONS:
		btn = root.create(buttonCOMP, bname)
		if btn.name != bname:
			btn.name = bname
		btn.par.label = label
		btn.par.buttontype = "momentary"
		width = 88 if bname == "btn_resetview" else BTN_W
		_place_button(btn, x, y, width)
		_set_color(btn, COLOR_ACTION)
		x += width + BTN_GAP

	refresh_mode_highlight(root, "translate")
	return root


def refresh_mode_highlight(toolbar_root, active_mode):
	"""Tint the active mode button; sync radio state."""
	if toolbar_root is None:
		return
	active_name = BUTTON_BY_MODE.get(active_mode)
	for bname, _label, mode in MODE_BUTTONS:
		btn = toolbar_root.op(bname)
		if btn is None:
			continue
		is_active = bname == active_name
		_set_color(btn, COLOR_ACTIVE if is_active else COLOR_IDLE)
		try:
			btn.panel.state.val = 1 if is_active else 0
		except Exception:
			pass


def toolbar_button_paths(toolbar_root):
	"""Absolute paths of all toolbar Button COMPs (for panelexecuteDAT)."""
	if toolbar_root is None:
		return []
	paths = []
	for bname, _label, _mode in MODE_BUTTONS:
		btn = toolbar_root.op(bname)
		if btn is not None:
			paths.append(btn.path)
	for bname, _label in ACTION_BUTTONS:
		btn = toolbar_root.op(bname)
		if btn is not None:
			paths.append(btn.path)
	return paths
