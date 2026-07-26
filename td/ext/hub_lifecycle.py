"""HubLifecycleMixin — daemon lifecycle, WS fan-in, prune loop helpers."""

import json
import os
import subprocess
import time
import urllib.request
import webbrowser

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000


class HubLifecycleMixin:
	def _hello_payload(self):
		return {
			'type': 'hello',
			'role': 'td',
			'workspace_id': self.WorkspaceId,
			'project_name': str(getattr(project, 'name', '') or ''),
			'project_folder': str(getattr(project, 'folder', '') or ''),
		}

	def _http(self, path, *, data=None, method=None, headers=None, timeout=2.0):
		"""HTTP to daemon with required X-Workspace-Id (not for /health)."""
		url = path if str(path).startswith('http') else (self.BaseUrl + path)
		hdrs = {'X-Workspace-Id': self.WorkspaceId}
		if headers:
			hdrs.update(headers)
		req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
		return urllib.request.urlopen(req, timeout=timeout)

	def ProbeHealth(self, timeout=0.8):
		"""Return 'ok' | 'wrong_app' | 'refused'."""
		try:
			with urllib.request.urlopen(self.BaseUrl + '/health', timeout=timeout) as r:
				data = json.loads(r.read().decode())
			if data.get('app') == '4designer':
				return 'ok'
			return 'wrong_app'
		except Exception:
			return 'refused'

	def HealthCheck(self, timeout=0.8):
		return self.ProbeHealth(timeout=timeout) == 'ok'

	def EnsureDaemon(self):
		status = self.ProbeHealth()
		if status == 'ok':
			self._status('daemon running')
			self._connect_ws()
			run("args[0]._recover_ws_hello()", self, delayFrames=15)
			return True
		if status == 'wrong_app':
			self._status('port busy (not 4designer)')
			return False
		if not self.SpawnDaemon():
			return False
		run("args[0]._connect_ws()", self, delayFrames=90)
		run("args[0]._recover_ws_hello()", self, delayFrames=120)
		return True

	def SpawnDaemon(self):
		d = self.DaemonDir
		python = os.path.join(d, '.venv', 'Scripts', 'python.exe')
		if not os.path.exists(python):
			# POSIX fallback
			python = os.path.join(d, '.venv', 'bin', 'python')
		if not os.path.exists(python):
			self._status('venv python not found: ' + python)
			return False
		flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
		try:
			kwargs = dict(
				args=[python, '-m', 'fourdesigner_daemon'],
				cwd=d,
				stdin=subprocess.DEVNULL,
				stdout=subprocess.DEVNULL,
				stderr=subprocess.DEVNULL,
				close_fds=True,
			)
			if os.name == 'nt':
				kwargs['creationflags'] = flags
			subprocess.Popen(**kwargs)
		except Exception as e:
			self._status('spawn failed: ' + str(e))
			return False
		self._status('daemon spawned')
		return True

	def OpenUI(self):
		wid = self.WorkspaceId
		url = self.BaseUrl + '/'
		if wid:
			url = url + '?workspace=' + wid
		webbrowser.open(url)

	def CreateMarshal(self):
		"""Clone embedded templates/marshal into Place In (or hub parent).

		Fallbacks (documented): load tox/marshal.tox, then
		exec build_marshal.py from disk — only if the embedded template is missing.
		"""
		hub = self.ownerComp
		parent = self._resolve_marshal_parent()
		if parent is None:
			self._status('create fail: no parent')
			return None
		base = str(hub.par.Marshalname.eval() or 'marshal1').strip() or 'marshal1'
		name = self._unique_child_name(parent, base)
		demo = bool(hub.par.Demobox.eval()) if hasattr(hub.par, 'Demobox') else False

		clone = self._clone_from_template(parent, name)
		if clone is None:
			clone = self._load_marshal_tox(parent, name)
		if clone is None:
			clone = self._build_marshal_from_disk(parent, name, demo_box=False)
		if clone is None:
			self._status('create fail: no template/tox/builder')
			return None

		self._activate_marshal(clone, name)
		clone.nodeX = hub.nodeX + 400
		clone.nodeY = hub.nodeY
		if demo:
			self._wire_demo_box(parent, clone)
		self._status('created ' + clone.path)
		return clone

	def _resolve_marshal_parent(self):
		hub = self.ownerComp
		raw = ''
		if hasattr(hub.par, 'Marshalparent'):
			try:
				raw = str(hub.par.Marshalparent.eval() or '')
			except Exception:
				raw = ''
		if raw:
			try:
				p = op(raw)
			except Exception:
				p = None
			if p is None:
				self._status('create fail: bad Place In')
				return None
			return p
		return hub.parent()

	def _unique_child_name(self, parent, base):
		if parent.op(base) is None:
			return base
		n = 1
		while parent.op(f'{base}_{n}') is not None:
			n += 1
		return f'{base}_{n}'

	def _clone_from_template(self, parent, name):
		tpl = self.ownerComp.op('templates/marshal')
		if tpl is None:
			return None
		try:
			return parent.copy(tpl, name=name)
		except Exception as e:
			self._status('clone fail: ' + str(e)[:80])
			return None

	def _tools_dir(self):
		# Prefer project-relative; keep portable (no absolute /project1 in COMP).
		candidates = [
			os.path.join(project.folder, 'tools', '4designer'),
			os.path.join(self.DaemonDir, '..'),
		]
		for c in candidates:
			c = os.path.normpath(c)
			if os.path.isdir(os.path.join(c, 'td')):
				return c
		return candidates[0]

	def _load_marshal_tox(self, parent, name):
		tox = os.path.join(self._tools_dir(), 'tox', 'marshal.tox')
		if not os.path.isfile(tox):
			return None
		try:
			loaded = parent.loadTox(tox, unwired=True, pattern=name)
		except Exception as e:
			self._status('tox load fail: ' + str(e)[:80])
			return None
		# loadTox may return the COMP or a container; normalize name.
		comp = loaded
		if comp is not None and comp.name != name:
			try:
				comp.name = name
			except Exception:
				pass
		return comp

	def _build_marshal_from_disk(self, parent, name, demo_box=False):
		path = os.path.join(self._tools_dir(), 'td', 'build_marshal.py')
		if not os.path.isfile(path):
			return None
		try:
			ns = {}
			with open(path, encoding='utf-8') as f:
				exec(f.read(), ns)
			return ns['build_marshal'](
				parent=parent, name=name, demo_box=demo_box, active=True
			)
		except Exception as e:
			self._status('build_marshal fail: ' + str(e)[:80])
			return None

	def _activate_marshal(self, clone, name):
		clone.allowCooking = True
		try:
			clone.expose = True
		except Exception:
			pass
		if hasattr(clone.par, 'Name'):
			clone.par.Name = name
		if hasattr(clone.par, 'Objectid'):
			clone.par.Objectid = ''
		if hasattr(clone.par, 'Status'):
			clone.par.Status = 'idle'
		if hasattr(clone.par, 'Proxymode') and hasattr(self.ownerComp.par, 'Defaultproxymode'):
			try:
				clone.par.Proxymode = str(self.ownerComp.par.Defaultproxymode.eval() or 'mask')
			except Exception:
				clone.par.Proxymode = 'mask'
		if hasattr(clone.par, 'Autoproxy'):
			clone.par.Autoproxy = False
		# Enable lifecycle callbacks on clones of dormant templates.
		ex = clone.op('execute1')
		if ex is not None:
			ex.par.start = True
			ex.par.exit = True
		try:
			clone.par.reinitextensions.pulse()
		except Exception:
			pass
		try:
			clone.initializeExtensions()
		except Exception:
			pass
		if hasattr(clone.par, 'Active'):
			clone.par.Active = True
		# ParamExec may miss scripted Active flips; match marshal execute delay.
		run(
			'args[0].ext.MarshalExt.OnActiveChanged()',
			clone,
			delayFrames=2,
		)

	def _wire_demo_box(self, parent, marshal_comp):
		box_name = marshal_comp.name + '_box'
		box = parent.op(box_name)
		if box is None:
			try:
				box = parent.create(boxPOP, box_name)
			except Exception:
				try:
					import td
					box = parent.create(td.boxPOP, box_name)
				except Exception as e:
					self._status('demo box fail: ' + str(e)[:60])
					return
		box.nodeX = marshal_comp.nodeX - 200
		box.nodeY = marshal_comp.nodeY
		try:
			marshal_comp.inputConnectors[0].connect(box)
		except Exception:
			pass

	def _connect_ws(self):
		ws = self.ownerComp.op('websocket1')
		if ws is None:
			return
		url = self.BaseUrl
		hostport = url.split('://', 1)[-1]
		host, _, port = hostport.partition(':')
		want_addr = host + '/ws'
		want_port = int(port or 80)
		# Already live on the right endpoint — do not bounce (avoids prune-run stacks).
		try:
			if (
				self.Connected
				and bool(ws.par.active)
				and str(ws.par.netaddress) == want_addr
				and int(ws.par.port) == want_port
			):
				return
		except Exception:
			pass
		ws.par.active = False
		ws.par.netaddress = want_addr
		ws.par.port = want_port
		# Toggle off→on same frame often fails; reactivate next frames.
		run("args[0].par.active = True", ws, delayFrames=1)
		run("args[0].par.active = True", ws, delayFrames=30)

	def _recover_ws_hello(self):
		"""Reassert TD role after ext reinit / missed onConnect / daemon restart.

		Websocket DAT can remain peer-connected while ``Connected`` was reset to
		False in ``__init__``, which blocks ``_ws_send`` and stalls the UI hero.
		"""
		ws = self.ownerComp.op('websocket1')
		if ws is None:
			return
		if self.Connected:
			self._ws_send(self._hello_payload())
			return
		if not bool(ws.par.active):
			if self.HealthCheck(timeout=0.4):
				self._connect_ws()
			return
		# Stale flag: DAT is active — try hello directly, then fall back to bounce.
		try:
			ws.sendText(json.dumps(self._hello_payload()))
			self.Connected = True
			self._status('connected (reassert)')
			self._schedule_prune_loop(delayFrames=120)
		except Exception:
			self.Connected = False
			if self.HealthCheck(timeout=0.4):
				self._connect_ws()

	def OnWsConnect(self):
		self.Connected = True
		self._status('connected')
		self._ws_send(self._hello_payload())
		# State usually arrives on accept before hello; delay prune one-shot.
		run('args[0].PruneOrphans()', self, delayFrames=15)
		run('args[0].ListRenderTops()', self, delayFrames=20)
		# Single orphan/fallback sweep — kills any stacked stale prune runs first.
		self._schedule_prune_loop(delayFrames=120)

	def _kill_prune_runs(self, *, include_due=True):
		"""Drop delayed _prune_loop runs (incl. ones bound to dead ext instances)."""
		try:
			for _ in range(4):
				left = 0
				for r in list(runs):
					try:
						src = str(r.source)
						rem = float(r.remainingFrames)
					except Exception:
						continue
					if '_prune_loop' not in src:
						continue
					if not include_due and rem <= 0:
						continue
					left += 1
					try:
						r.kill()
					except Exception:
						pass
				if left == 0:
					break
		except Exception:
			pass

	def _count_prune_runs(self):
		n = 0
		try:
			for r in list(runs):
				try:
					if '_prune_loop' in str(r.source):
						n += 1
				except Exception:
					pass
		except Exception:
			pass
		return n

	def _schedule_prune_loop(self, delayFrames=None):
		self._kill_prune_runs()
		if delayFrames is None:
			delayFrames = (
				self.PRUNE_PERIOD_SHM_DOWN
				if not self._shm_ok()
				else self.PRUNE_PERIOD_FRAMES
			)
		run(
			'args[0]._prune_loop()',
			self,
			delayFrames=int(delayFrames),
			group=self.PRUNE_GROUP,
		)

	def _prune_alive(self):
		"""False for delayed runs still holding a pre-reinit extension instance."""
		try:
			return self.ownerComp.ext.FourdesignerExt is self
		except Exception:
			return False

	def _prune_loop(self):
		# Stale ext instance from before reinit/hot-reload: do not reschedule.
		if not self._prune_alive():
			return
		self._prune_ticks += 1
		if self.Connected:
			# HTTP pending only when SHM unavailable (fallback).
			if not self._shm_ok():
				try:
					self.ProcessPendingDestroys()
				except Exception:
					pass
				try:
					self.ProcessPendingRender()
				except Exception:
					pass
				try:
					self.ProcessPendingProxies()
				except Exception:
					pass
			try:
				self.PruneOrphans()
			except Exception:
				pass
		# Ensure single-flight: drop any *pending* siblings then schedule exactly one.
		self._kill_prune_runs(include_due=False)
		period = (
			self.PRUNE_PERIOD_SHM_DOWN
			if not self._shm_ok()
			else self.PRUNE_PERIOD_FRAMES
		)
		run(
			'args[0]._prune_loop()',
			self,
			delayFrames=int(period),
			group=self.PRUNE_GROUP,
		)

	def ProcessPendingDestroys(self):
		"""Drain daemon queue of UI deletes (fallback when SHM down)."""
		self._pending_http_count += 1
		try:
			with self._http('/api/pending_destroys', timeout=1.5) as r:
				data = json.loads(r.read().decode())
		except Exception:
			return
		items = data.get('items') if isinstance(data, dict) else None
		if not isinstance(items, list):
			return
		for item in items:
			if not isinstance(item, dict):
				continue
			self.ApplyDestroyMarshal(item)

	def OnWsDisconnect(self):
		self.Connected = False
		self._status('disconnected')
		self._retry_fails = 0
		run("args[0]._retry()", self, delayFrames=180)

	def _retry(self):
		if self.Connected:
			return
		if self.HealthCheck(timeout=0.4):
			self._connect_ws()
			return
		self._retry_fails += 1
		if self._retry_fails >= 3 and time.time() - self._last_spawn > self.SPAWN_COOLDOWN_S:
			self._last_spawn = time.time()
			self.SpawnDaemon()
		run("args[0]._retry()", self, delayFrames=180)

	def _ws_send(self, msg: dict):
		ws = self.ownerComp.op('websocket1')
		if ws is not None and self.Connected:
			ws.sendText(json.dumps(msg))

	def _msg_for_us(self, msg):
		wid = msg.get('workspace_id')
		if wid is None or wid == '':
			return True
		return str(wid) == self.WorkspaceId

	def OnWsReceive(self, text):
		try:
			msg = json.loads(text)
		except Exception:
			return
		mtype = msg.get('type')
		if mtype == 'workspace_rekey':
			new_id = str(msg.get('workspace_id') or '').strip()
			if not new_id:
				return
			par = getattr(self.ownerComp.par, 'Workspaceid', None)
			if par is not None:
				par.val = new_id
			self._status('workspace rekey')
			# Re-open SHM under new id; re-hello.
			try:
				if self._shm is not None:
					self._shm.close(unlink=False)
			except Exception:
				pass
			self._shm = None
			self._shm_slug = ''
			self._ws_send(self._hello_payload())
			return
		if mtype == 'workspace_list':
			return
		if mtype == 'state':
			if not self._msg_for_us(msg):
				return
			self.State = msg
			self._rebuild_path_index()
			return
		if mtype == 'project_patch':
			if not self._msg_for_us(msg):
				return
			# Merge shallow keys we care about
			if 'objects' in msg and isinstance(msg['objects'], dict):
				objs = dict(self.State.get('objects') or {})
				# full replace if schema present, else merge
				if 'schema_version' in msg:
					objs = msg['objects']
				else:
					objs.update(msg['objects'])
				self.State['objects'] = objs
				self._rebuild_path_index()
			for k in ('layers', 'selection', 'td_connected', 'slug', 'workspace_id'):
				if k in msg:
					self.State[k] = msg[k]
			return
		if mtype == 'set_trs':
			self.ApplySetTrs(msg)
			return
		if mtype == 'set_layer':
			self.ApplySetLayer(msg)
			return
		if mtype == 'set_proxy_mode':
			self.ApplySetProxyMode(msg)
			return
		if mtype == 'refresh_proxy':
			self.ApplyRefreshProxy(msg)
			return
		if mtype == 'destroy_marshal':
			self.ApplyDestroyMarshal(msg)
			return
		if mtype == 'list_render_tops':
			self.ListRenderTops()
			return
		if mtype == 'render_snapshot':
			self.SnapshotRender(str(msg.get('path') or ''))
			return
		if mtype == 'render_preview':
			self.CaptureRenderPreview(str(msg.get('path') or ''))
			return
		if mtype == 'set_object_trs':
			self.ApplySetObjectTrs(msg)
			return
		if mtype == 'render_cook_proxies':
			ids = msg.get('ids')
			self.CookRenderProxiesBatch(ids if isinstance(ids, list) else None)
			return

	def _status(self, msg):
		try:
			self.ownerComp.par.Status = str(msg)[:120]
		except Exception:
			pass
