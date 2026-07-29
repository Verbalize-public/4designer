"""Panel Execute DAT callbacks — 4designer.

Fires only when a monitored panel value changes (u/v/lselect/rselect/mselect/
wheel) — idle-cheap by construction, not a per-frame poll. Dispatches
straight into the Extension; see the idle-cook note in fourdesigner_ext.py
for why the Render TOP lock/unlock still matters separately from this.

Important: if Off→On is also enabled alongside Value Change, TD routes the
0→1 edge to onOffToOn and skips onValueChange for that edge. Keep offton
off in the builder, and still dispatch every callback here as a backstop.
"""


def _dispatch(panelValue):
	try:
		me.parent().ext.FourdesignerExt.OnPanelValueChange(panelValue)
	except Exception as e:
		try:
			me.parent().par.Status = "panel err: " + str(e)[:100]
		except Exception:
			pass


def onValueChange(panelValue):
	_dispatch(panelValue)


def onOffToOn(panelValue):
	_dispatch(panelValue)


def onOnToOff(panelValue):
	_dispatch(panelValue)


def whileOn(panelValue):
	return


def whileOff(panelValue):
	return


def onValuesChanged(channels):
	return
