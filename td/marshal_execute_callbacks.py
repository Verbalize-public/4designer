"""Execute DAT: register on create when Active; always unregister on exit.

Objectid is stored on this DAT during Register (`fd_oid`) because onExit may
run after the parent COMP is already gone — `me.parent()` then fails.
"""

import json
import urllib.request
import urllib.error


def onStart():
	comp = me.parent()
	run("args[0].ext.MarshalExt.OnActiveChanged()", comp, delayFrames=30)


def _daemon_base():
	hub = getattr(op, 'fourdesigner', None)
	base = 'http://127.0.0.1:9983'
	try:
		if hub is not None and hasattr(hub.par, 'Daemonurl'):
			base = str(hub.par.Daemonurl.eval() or base).rstrip('/')
	except Exception:
		pass
	return base


def _http_unregister(oid: str):
	if not oid:
		return
	try:
		req = urllib.request.Request(_daemon_base() + '/api/objects/' + oid, method='DELETE')
		with urllib.request.urlopen(req, timeout=2.0) as r:
			r.read()
	except urllib.error.HTTPError:
		pass
	except Exception:
		pass


def onExit():
	oid = ''
	try:
		oid = str(me.fetch('fd_oid', '') or '')
	except Exception:
		pass
	if not oid:
		try:
			comp = me.parent()
			oid = str(comp.par.Objectid.eval() or '')
		except Exception:
			pass
	try:
		comp = me.parent()
		comp.ext.MarshalExt.OnDestroy()
		return
	except Exception:
		pass
	_http_unregister(oid)
