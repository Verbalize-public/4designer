"""Callbacks for the websocket1 DAT inside the 4designer hub COMP."""


def _ext(dat):
	return dat.parent().ext.FourdesignerExt


def onConnect(dat):
	_ext(dat).OnWsConnect()


def onDisconnect(dat):
	_ext(dat).OnWsDisconnect()


def onReceiveText(dat, rowIndex, message):
	_ext(dat).OnWsReceive(message)


def onReceiveBinary(dat, contents):
	pass


def onReceivePing(dat, contents):
	dat.sendPong(contents)


def onReceivePong(dat, contents):
	pass


def onMonitorMessage(dat, message):
	pass
