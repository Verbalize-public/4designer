"""Panel Execute DAT callbacks — 4designer orientation view-cube panel.

Watches u/v/lselect/rollover on `ui_orient`. Dispatches into FourdesignerExt
orient-panel handlers (pick zone → SnapView / hover highlight).
"""


def _dispatch(panelValue):
	try:
		me.parent().ext.FourdesignerExt.OnOrientPanelValueChange(panelValue)
	except Exception as e:
		try:
			me.parent().par.Status = "orient err: " + str(e)[:100]
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
