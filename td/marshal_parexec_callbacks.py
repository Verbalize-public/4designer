"""Parameter Execute callbacks for Marshal COMP."""


def onPulse(par):
	if par.name == 'Refreshproxy':
		par.owner.ext.MarshalExt.RefreshProxy()


def onValueChange(par, prev):
	if par.name == 'Active':
		par.owner.ext.MarshalExt.OnActiveChanged()
	elif par.name == 'Proxymode':
		par.owner.ext.MarshalExt.OnProxyModeChanged()
	elif par.name == 'Autoproxy':
		if bool(par.eval()):
			par.owner.ext.MarshalExt.MaybeAutoProxy()
	elif par.name in ('Layer', 'Name'):
		# Re-register to push metadata (idempotent).
		if bool(par.owner.par.Active.eval()):
			par.owner.ext.MarshalExt.Register()
