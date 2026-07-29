"""Panel Execute DAT callbacks — 4designer toolbar controls.

Watches `select` (Button COMP picker) and `lselect` (Container faces).
Off→On edge dispatches into FourdesignerExt.
"""


def _ext():
	return me.parent().ext.FourdesignerExt


def _dispatch(panelValue):
	try:
		ext = _ext()
	except Exception as e:
		try:
			me.parent().par.Status = "toolbar err: " + str(e)[:100]
		except Exception:
			pass
		return
	try:
		name = panelValue.owner.name
	except Exception:
		return
	try:
		ext.OnToolbarButton(name)
	except Exception as e:
		try:
			me.parent().par.Status = "toolbar err: " + str(e)[:100]
		except Exception:
			pass


def onOffToOn(panelValue):
	_dispatch(panelValue)


def onValueChange(panelValue):
	try:
		if int(panelValue.val) == 1:
			_dispatch(panelValue)
	except Exception:
		pass


def onOnToOff(panelValue):
	return


def whileOn(panelValue):
	return


def whileOff(panelValue):
	return


def onValuesChanged(channels):
	return
