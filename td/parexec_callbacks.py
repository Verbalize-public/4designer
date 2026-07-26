"""Parameter Execute callbacks for the 4designer hub COMP."""


def onPulse(par):
	ext = par.owner.ext.FourdesignerExt
	if par.name == 'Ensuredaemon':
		ext.EnsureDaemon()
	elif par.name == 'Openui':
		ext.OpenUI()
	elif par.name == 'Createmarshal':
		ext.CreateMarshal()


def onValueChange(par, prev):
	return
