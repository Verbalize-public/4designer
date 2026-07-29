"""Parameter Execute DAT callbacks — 4designer custom pars."""


def onValueChange(par, prev):
	ext = par.owner.ext.FourdesignerExt
	if par.name == "Rendertop":
		ext.Discover()
	elif par.name == "Mode":
		ext.OnModeChange()


def onPulse(par):
	ext = par.owner.ext.FourdesignerExt
	if par.name == "Discover":
		ext.Discover()
	elif par.name == "Resetview":
		ext.ResetView()
	elif par.name == "Openpanel":
		ext.OpenPanel()
