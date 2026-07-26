"""MarshalRegistryMixin — object path index, register/proxy, orphan prune."""

import json
import time
import urllib.error
import urllib.request


class MarshalRegistryMixin:
	def PruneOrphans(self):
		"""Unregister SOT objects whose td_path no longer resolves in this project.

		COMP.destroy() does not always fire Execute onExit, and op(path) can briefly
		return None mid-destroy — debounce missing paths (≥0.75s) before pruning.
		"""
		objs = self.State.get('objects') or {}
		if not isinstance(objs, dict):
			return
		suspects = getattr(self, '_orphan_suspects', None)
		if suspects is None:
			self._orphan_suspects = {}
			suspects = self._orphan_suspects
		now = time.time()
		dead = []
		seen = set()
		try:
			from orphan_debounce import orphan_ready_to_prune
		except Exception:
			orphan_ready_to_prune = None
		for oid, obj in objs.items():
			if not isinstance(obj, dict):
				continue
			path = str(obj.get('td_path') or '')
			if not path:
				continue
			oid_s = str(oid)
			seen.add(oid_s)
			try:
				resolved = op(path)
			except Exception:
				resolved = None
			missing = resolved is None
			if orphan_ready_to_prune is not None:
				if orphan_ready_to_prune(suspects, oid_s, missing=missing, now=now, dwell_s=0.75):
					dead.append(oid_s)
				continue
			if not missing:
				suspects.pop(oid_s, None)
				continue
			# Missing — wait and re-verify; only prune after ≥0.75s wall clock.
			first = suspects.get(oid_s)
			if first is None:
				suspects[oid_s] = now
				continue
			if now - first >= 0.75:
				dead.append(oid_s)
		for oid_s in list(suspects.keys()):
			if oid_s not in seen:
				suspects.pop(oid_s, None)
		if not dead:
			return
		try:
			body = json.dumps({'ids': dead}).encode('utf-8')
			req = urllib.request.Request(
				self.BaseUrl + '/api/objects/prune',
				data=body,
				headers={'X-Workspace-Id': self.WorkspaceId, 'Content-Type': 'application/json'},
				method='POST',
			)
			with urllib.request.urlopen(req, timeout=2.0) as r:
				resp = json.loads(r.read().decode())
			removed = resp.get('removed') or dead
			for oid in removed:
				oid_s = str(oid)
				self._forget_path(oid_s)
				suspects.pop(oid_s, None)
			self._status('pruned %d orphans' % len(removed))
		except Exception as e:
			self._status('prune fail: ' + str(e)[:60])

	def ApplyDestroyMarshal(self, msg):
		oid = str(msg.get('id') or '')
		path = str(msg.get('td_path') or self._path_by_id.get(oid) or '')
		if not path:
			self._forget_path(oid)
			return
		comp = op(path)
		if comp is None:
			self._forget_path(oid)
			return
		# Unregister first — COMP.destroy() does not always run Execute onExit.
		try:
			comp.ext.MarshalExt.OnDestroy()
		except Exception:
			pass
		try:
			comp.destroy()
		except Exception:
			pass
		self._forget_path(oid)

	def _forget_path(self, oid):
		oid = str(oid or '')
		if not oid:
			return
		self._path_by_id.pop(oid, None)
		mod = self._shm_mod()
		if mod is not None:
			try:
				self._path_by_hash.pop(mod.id_hash(oid), None)
			except Exception:
				pass

	def _remember_path(self, oid, path):
		oid = str(oid or '')
		path = str(path or '')
		if not oid or not path:
			return
		self._path_by_id[oid] = path
		mod = self._shm_mod()
		if mod is not None:
			try:
				self._path_by_hash[mod.id_hash(oid)] = path
			except Exception:
				pass

	def _rebuild_path_index(self):
		idx = {}
		hidx = {}
		objs = self.State.get('objects') or {}
		mod = self._shm_mod()
		if isinstance(objs, dict):
			for oid, obj in objs.items():
				if isinstance(obj, dict) and obj.get('td_path'):
					oid_s = str(oid)
					path = str(obj['td_path'])
					idx[oid_s] = path
					if mod is not None:
						try:
							hidx[mod.id_hash(oid_s)] = path
						except Exception:
							pass
		self._path_by_id = idx
		# Keep render-seeded hashes; merge marshal paths on top.
		merged = dict(self._path_by_hash or {})
		merged.update(hidx)
		self._path_by_hash = merged

	def ApplySetTrs(self, msg):
		oid = str(msg.get('id') or '')
		trs = msg.get('trs') or {}
		path = str(msg.get('td_path') or self._path_by_id.get(oid) or '')
		if path and oid:
			self._remember_path(oid, path)
		if not path:
			return
		comp = op(path)
		if comp is None:
			return
		chop = comp.op('chop_trs')
		if chop is None:
			return
		t = trs.get('t') or [0, 0, 0]
		r = trs.get('r') or [0, 0, 0]
		s = trs.get('s') or [1, 1, 1]
		# Constant CHOP channel value pars: namevalue0.. or constNname/constNvalue
		self._set_const_channels(chop, {
			'tx': float(t[0]), 'ty': float(t[1]), 'tz': float(t[2]),
			'rx': float(r[0]), 'ry': float(r[1]), 'rz': float(r[2]),
			'sx': float(s[0]), 'sy': float(s[1]), 'sz': float(s[2]),
		})

	def ApplySetLayer(self, msg):
		oid = str(msg.get('id') or '')
		path = str(msg.get('td_path') or self._path_by_id.get(oid) or '')
		if not path:
			return
		comp = op(path)
		if comp is None:
			return
		if hasattr(comp.par, 'Layer'):
			comp.par.Layer = int(msg.get('layer', 0))

	def ApplySetProxyMode(self, msg):
		"""UI → Marshal Proxymode (triggers OnProxyModeChanged → RefreshProxy)."""
		oid = str(msg.get('id') or '')
		path = str(msg.get('td_path') or self._path_by_id.get(oid) or '')
		mode = 'mesh' if str(msg.get('proxy_mode') or '').lower() == 'mesh' else 'mask'
		if not path:
			return
		comp = op(path)
		if comp is None:
			return
		if hasattr(comp.par, 'Proxymode'):
			try:
				cur = str(comp.par.Proxymode.eval() or 'mask').strip().lower()
			except Exception:
				cur = ''
			if cur != mode:
				comp.par.Proxymode = mode
			elif mode == 'mesh':
				# Already mesh — still cook so UI Refresh works.
				try:
					comp.ext.MarshalExt.RefreshProxy()
				except Exception as e:
					self._status('refresh_proxy fail: ' + str(e)[:60])

	def ApplyRefreshProxy(self, msg):
		oid = str(msg.get('id') or '')
		path = str(msg.get('td_path') or self._path_by_id.get(oid) or '')
		if not path:
			return
		comp = op(path)
		if comp is None:
			return
		try:
			if hasattr(comp.par, 'Proxymode'):
				comp.par.Proxymode = 'mesh'
			comp.ext.MarshalExt.RefreshProxy()
		except Exception as e:
			self._status('refresh_proxy fail: ' + str(e)[:60])

	def ProcessPendingProxies(self):
		"""Fallback drain for marshal proxy refresh when SHM is down."""
		self._pending_http_count += 1
		try:
			with self._http('/api/objects/proxies/pending', timeout=1.5) as r:
				data = json.loads(r.read().decode())
		except Exception:
			return
		items = data.get('items') if isinstance(data, dict) else None
		if not isinstance(items, list):
			return
		for item in items:
			if not isinstance(item, dict):
				continue
			if str(item.get('type') or '') == 'refresh_proxy':
				self.ApplyRefreshProxy(item)

	def _set_const_channels(self, chop, values: dict):
		"""Write values into a Constant CHOP by channel name."""
		# Prefer named value pars if present (TD Constant CHOP: const0name/const0value ...)
		name_to_idx = {}
		i = 0
		while True:
			name_par = getattr(chop.par, f'const{i}name', None)
			if name_par is None:
				break
			name_to_idx[str(name_par.eval())] = i
			i += 1
		if name_to_idx:
			for ch, val in values.items():
				if ch in name_to_idx:
					getattr(chop.par, f'const{name_to_idx[ch]}value').val = float(val)
			return
		# Fallback: channel objects
		for ch, val in values.items():
			c = chop[ch]
			if c is not None:
				try:
					c[0] = float(val)
				except Exception:
					pass

	def Register(self, marshalComp):
		"""HTTP register called by Marshal. Returns object id or None."""
		oid = str(marshalComp.par.Objectid.eval() or '')
		if not oid:
			import uuid
			oid = str(uuid.uuid4())
			marshalComp.par.Objectid = oid
		bounds = {
			'min': [-0.5, -0.5, -0.5],
			'max': [0.5, 0.5, 0.5],
		}
		proxy_mode = 'mask'
		try:
			if hasattr(marshalComp.par, 'Proxymode'):
				proxy_mode = str(marshalComp.par.Proxymode.eval() or 'mask').strip().lower()
				if proxy_mode != 'mesh':
					proxy_mode = 'mask'
		except Exception:
			proxy_mode = 'mask'
		try:
			b, _hint = marshalComp.ext.MarshalExt.ProbeBounds()
			if isinstance(b, dict) and 'min' in b and 'max' in b:
				bounds = b
		except Exception:
			pass
		body = {
			'id': oid,
			'name': str(marshalComp.par.Name.eval() or marshalComp.name),
			'layer': int(marshalComp.par.Layer.eval()),
			'td_path': marshalComp.path,
			'bounds': bounds,
			'proxy_mode': proxy_mode,
			'trs': self._read_trs(marshalComp),
		}
		try:
			data = json.dumps(body).encode('utf-8')
			req = urllib.request.Request(
				self.BaseUrl + '/api/objects/register',
				data=data,
				headers={'X-Workspace-Id': self.WorkspaceId, 'Content-Type': 'application/json'},
				method='POST',
			)
			with urllib.request.urlopen(req, timeout=2.0) as r:
				resp = json.loads(r.read().decode())
			self._path_by_id[oid] = marshalComp.path
			marshalComp.par.Status = 'registered'
			return resp.get('id', oid)
		except Exception as e:
			marshalComp.par.Status = 'register_fail'
			self._status('register failed: ' + str(e))
			return None

	def PatchBoundsQuiet(self, marshalComp, bounds):
		oid = str(marshalComp.par.Objectid.eval() or '')
		if not oid:
			return
		body = json.dumps({'bounds': bounds, '_quiet': True}).encode('utf-8')
		req = urllib.request.Request(
			self.BaseUrl + '/api/objects/' + oid,
			data=body,
			headers={'X-Workspace-Id': self.WorkspaceId, 'Content-Type': 'application/json'},
			method='PATCH',
		)
		urllib.request.urlopen(req, timeout=2.0)

	def SetProxyMode(self, marshalComp, mode):
		oid = str(marshalComp.par.Objectid.eval() or '')
		if not oid:
			return
		m = 'mesh' if str(mode).lower() == 'mesh' else 'mask'
		body = json.dumps({'proxy_mode': m, '_quiet': True}).encode('utf-8')
		req = urllib.request.Request(
			self.BaseUrl + '/api/objects/' + oid,
			data=body,
			headers={'X-Workspace-Id': self.WorkspaceId, 'Content-Type': 'application/json'},
			method='PATCH',
		)
		urllib.request.urlopen(req, timeout=2.0)
		if m == 'mask':
			self.DeleteProxy(marshalComp)

	def MaxMeshProxies(self) -> int:
		try:
			if hasattr(self.ownerComp.par, 'Maxmeshproxies'):
				return max(0, int(self.ownerComp.par.Maxmeshproxies.eval()))
		except Exception:
			pass
		return 4096

	def MeshProxyCount(self) -> int:
		try:
			req = urllib.request.Request(self.BaseUrl + '/api/state', headers={'X-Workspace-Id': self.WorkspaceId}, method='GET')
			with urllib.request.urlopen(req, timeout=2.0) as r:
				state = json.loads(r.read().decode())
			n = 0
			for o in (state.get('objects') or {}).values():
				if o.get('proxy_mode') == 'mesh' and o.get('proxy'):
					n += 1
			return n
		except Exception:
			return 0

	def ObjectHasProxy(self, oid: str) -> bool:
		try:
			req = urllib.request.Request(self.BaseUrl + '/api/state', headers={'X-Workspace-Id': self.WorkspaceId}, method='GET')
			with urllib.request.urlopen(req, timeout=2.0) as r:
				state = json.loads(r.read().decode())
			o = (state.get('objects') or {}).get(oid)
			return bool(o and o.get('proxy'))
		except Exception:
			return False

	def UploadProxy(self, marshalComp, glb_bytes, fingerprint='', verts=0, tris=0):
		oid = str(marshalComp.par.Objectid.eval() or '')
		if not oid:
			raise RuntimeError('no object id')
		boundary = '----fdproxy' + str(int(time.time() * 1000))
		parts = []

		def add_field(name, value):
			parts.append(f'--{boundary}\r\n'.encode())
			parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
			parts.append(str(value).encode())
			parts.append(b'\r\n')

		add_field('fingerprint', fingerprint)
		add_field('verts', verts)
		add_field('tris', tris)
		parts.append(f'--{boundary}\r\n'.encode())
		parts.append(
			b'Content-Disposition: form-data; name="file"; filename="proxy.glb"\r\n'
			b'Content-Type: model/gltf-binary\r\n\r\n'
		)
		parts.append(glb_bytes)
		parts.append(b'\r\n')
		parts.append(f'--{boundary}--\r\n'.encode())
		body = b''.join(parts)
		req = urllib.request.Request(
			self.BaseUrl + '/api/objects/' + oid + '/proxy',
			data=body,
			headers={'X-Workspace-Id': self.WorkspaceId, 'Content-Type': f'multipart/form-data; boundary={boundary}'},
			method='PUT',
		)
		with urllib.request.urlopen(req, timeout=10.0) as r:
			return json.loads(r.read().decode())

	def DeleteProxy(self, marshalComp):
		oid = str(marshalComp.par.Objectid.eval() or '')
		if not oid:
			return
		try:
			req = urllib.request.Request(
				self.BaseUrl + '/api/objects/' + oid + '/proxy',
				headers={'X-Workspace-Id': self.WorkspaceId},
				method='DELETE',
			)
			urllib.request.urlopen(req, timeout=2.0)
		except Exception:
			pass

	def Unregister(self, marshalComp):
		oid = str(marshalComp.par.Objectid.eval() or '')
		if not oid:
			return
		try:
			req = urllib.request.Request(
				self.BaseUrl + '/api/objects/' + oid,
				headers={'X-Workspace-Id': self.WorkspaceId},
				method='DELETE',
			)
			with urllib.request.urlopen(req, timeout=2.0) as r:
				r.read()
			self._path_by_id.pop(oid, None)
			try:
				marshalComp.par.Status = 'unregistered'
			except Exception:
				pass
		except urllib.error.HTTPError as e:
			# Idempotent: already gone after UI delete / prior prune.
			if e.code == 404:
				self._path_by_id.pop(oid, None)
				try:
					marshalComp.par.Status = 'unregistered'
				except Exception:
					pass
				return
			try:
				marshalComp.par.Status = 'unregister_fail'
			except Exception:
				pass
			self._status('unregister failed: ' + str(e))
		except Exception as e:
			try:
				marshalComp.par.Status = 'unregister_fail'
			except Exception:
				pass
			self._status('unregister failed: ' + str(e))

	def _read_trs(self, marshalComp):
		chop = marshalComp.op('chop_trs')
		def ch(name, default):
			if chop is None:
				return default
			c = chop[name]
			if c is None:
				return default
			return float(c[0])
		return {
			't': [ch('tx', 0), ch('ty', 0), ch('tz', 0)],
			'r': [ch('rx', 0), ch('ry', 0), ch('rz', 0)],
			's': [ch('sx', 1), ch('sy', 1), ch('sz', 1)],
		}
