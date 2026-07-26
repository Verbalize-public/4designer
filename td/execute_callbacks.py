"""Execute DAT callbacks: ensure daemon on project load; drain SHM each frame."""


def onStart():
	comp = me.parent()
	run("args[0].ext.FourdesignerExt.EnsureDaemon()", comp, delayFrames=120)


def onFrameStart(frame):
	try:
		me.parent().ext.FourdesignerExt.DrainShm()
	except Exception:
		pass
