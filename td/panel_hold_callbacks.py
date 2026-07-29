"""Panel Execute DAT — while-held poller for RMB orbit / MMB pan.

Value Change alone is not enough: with some viewer/focus setups, `u`/`v` stop
emitting change events while `rselect`/`mselect` is held, so orbit arms once
and never updates. This DAT watches only the button channels and fires
`whileOn` every frame into the slim `OnPanelHoldTick` path (not the full
panel handler — that would double-apply deltas and thrash gizmo rescale).
"""


def _dispatch(panelValue):
	try:
		me.parent().ext.FourdesignerExt.OnPanelHoldTick(panelValue)
	except Exception as e:
		try:
			me.parent().par.Status = "hold err: " + str(e)[:100]
		except Exception:
			pass


def onValueChange(panelValue):
	_dispatch(panelValue)


def onOffToOn(panelValue):
	_dispatch(panelValue)


def onOnToOff(panelValue):
	# Release edges are handled by the main panel_exec valuechange path.
	return


def whileOn(panelValue):
	_dispatch(panelValue)


def whileOff(panelValue):
	return


def onValuesChanged(channels):
	return
