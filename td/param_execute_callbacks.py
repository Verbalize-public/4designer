"""Parameter Execute DAT callbacks — 4designer custom pars."""


def onValueChange(par, prev):
	ext = par.owner.ext.FourdesignerExt
	if par.name == "Rendertop":
		ext.OnRenderTopParChange()
	elif par.name == "Rendertopchoice":
		ext.OnRenderTopChoiceChange()
	elif par.name == "Mode":
		ext.OnModeChange()
	elif par.name == "Snapgrid":
		ext.OnSnapGridChange()
	elif par.name == "Coordspace":
		ext.OnCoordSpaceChange()
	elif par.name in ("Snapgridx", "Snapgridy", "Snapgridz"):
		# Respace the visible snap plane grid without toggling the highlight.
		ext._refresh_gizmo_feedback()


def onPulse(par):
	ext = par.owner.ext.FourdesignerExt
	if par.name == "Discover":
		ext.Discover()
	elif par.name == "Resetview":
		ext.ResetView()
	elif par.name == "Openpanel":
		ext.OpenPanel()
	elif par.name == "Refreshrenders":
		ext.RefreshRenderTopList()
