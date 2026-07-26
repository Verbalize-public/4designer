"""RenderSnapshotMixin — render TOP list/preview/snapshot/proxy cook."""

import json
import os
import time
import urllib.request


class RenderSnapshotMixin:
	PREVIEW_MAX_SIZE = 320
	# Sibling of hub (not inside): TD cannot wire external TOPs into COMP children
	# without an In TOP — hub-local preview_res stayed unconnected → black JPEG.
	PREVIEW_RES_NAME = 'fd_preview_res'

	def ProcessPendingRender(self):
		"""Drain daemon queue for render list/snapshot (fallback when SHM down)."""
		self._pending_http_count += 1
		try:
			with self._http('/api/render/pending', timeout=1.5) as r:
				data = json.loads(r.read().decode())
		except Exception:
			return
		items = data.get('items') if isinstance(data, dict) else None
		if not isinstance(items, list):
			return
		for item in items:
			if not isinstance(item, dict):
				continue
			cmd = str(item.get('type') or '')
			if cmd == 'list_render_tops':
				self.ListRenderTops()
			elif cmd == 'render_snapshot':
				self.SnapshotRender(str(item.get('path') or ''))
			elif cmd == 'render_preview':
				self.CaptureRenderPreview(str(item.get('path') or ''))
			elif cmd == 'render_cook_proxies':
				ids = item.get('ids')
				self.CookRenderProxiesBatch(ids if isinstance(ids, list) else None)

	def ListRenderTops(self):
		"""POST first-level renderTOPs under /project1 to the daemon."""
		tops = []
		try:
			root = op('/project1')
			if root is not None:
				for c in root.findChildren(type=renderTOP, maxDepth=1):
					tops.append({'path': c.path, 'name': c.name})
		except Exception as e:
			self._status('list_render_tops fail: ' + str(e)[:60])
			return
		try:
			body = json.dumps({'tops': tops}).encode('utf-8')
			req = urllib.request.Request(
				self.BaseUrl + '/api/render/tops',
				data=body,
				headers={'X-Workspace-Id': self.WorkspaceId, 'Content-Type': 'application/json'},
				method='PUT',
			)
			with urllib.request.urlopen(req, timeout=2.0) as r:
				r.read()
			self._status('render tops: %d' % len(tops))
		except Exception as e:
			self._status('render tops put fail: ' + str(e)[:60])

	def _ensure_preview_res(self):
		"""Persistent resolutionTOP beside the hub for low-rate preview (no create/destroy churn)."""
		parent = self.ownerComp.parent()
		if parent is None:
			parent = self.ownerComp
		name = self.PREVIEW_RES_NAME
		top = parent.op(name)
		# Migrate away from legacy hub-internal preview_res (cannot take external wires).
		legacy = self.ownerComp.op('preview_res')
		if legacy is not None:
			try:
				legacy.destroy()
			except Exception:
				pass
		if top is not None:
			return top
		try:
			import td
			top = parent.create(td.resolutionTOP, name)
		except Exception:
			try:
				top = parent.create(resolutionTOP, name)
			except Exception as e:
				self._status('preview_res create fail: ' + str(e)[:50])
				return None
		try:
			top.nodeX = self.ownerComp.nodeX - 200
			top.nodeY = self.ownerComp.nodeY - 200
			top.viewer = False
			top.display = False
			top.render = False
		except Exception:
			pass
		return top

	def _connect_preview_input(self, pres, rtop):
		"""Wire rtop → pres; return True if input is actually connected."""
		try:
			cur = pres.inputs[0] if pres.inputs else None
			if cur is not None and getattr(cur, 'path', None) == rtop.path:
				return True
			if cur is not None:
				pres.inputConnectors[0].disconnect()
			pres.inputConnectors[0].connect(rtop)
		except Exception:
			try:
				pres.inputConnectors[0].connect(rtop)
			except Exception as e:
				self._status('preview connect fail: ' + str(e)[:50])
				return False
		cur = pres.inputs[0] if pres.inputs else None
		if cur is None or getattr(cur, 'path', None) != rtop.path:
			self._status('preview connect fail: no wire into ' + pres.path[:40])
			return False
		return True

	def CaptureRenderPreview(self, path):
		"""Downscale Render TOP → JPEG → PUT /api/render/preview (feedback only)."""
		path = str(path or '').strip()
		if not path:
			self._status('preview: empty path')
			return
		rtop = op(path)
		if rtop is None:
			self._status('preview: missing ' + path[:50])
			return
		try:
			if getattr(rtop, 'family', None) != 'TOP':
				self._status('preview: not a TOP ' + path[:40])
				return
		except Exception:
			pass
		pres = self._ensure_preview_res()
		if pres is None:
			return
		max_size = int(self.PREVIEW_MAX_SIZE)
		try:
			width = int(rtop.width or 1)
			height = int(rtop.height or 1)
		except Exception:
			width, height = 1, 1
		longest = max(width, height, 1)
		if width >= height:
			new_w = min(max_size, width) if longest > max_size else width
			new_h = max(1, round(height * new_w / width)) if width else 1
		else:
			new_h = min(max_size, height) if longest > max_size else height
			new_w = max(1, round(width * new_h / height)) if height else 1
		try:
			if not self._connect_preview_input(pres, rtop):
				return
			pres.par.outputresolution = 'custom'
			pres.par.resolutionw = int(new_w)
			pres.par.resolutionh = int(new_h)
			byte_array = pres.saveByteArray('.jpg')
			if not byte_array:
				self._status('preview: empty jpeg')
				return
			jpeg = bytes(byte_array)
		except Exception as e:
			self._status('preview cook fail: ' + str(e)[:60])
			return
		try:
			req = urllib.request.Request(
				self.BaseUrl + '/api/render/preview',
				data=jpeg,
				headers={
					'X-Workspace-Id': self.WorkspaceId,
					'Content-Type': 'image/jpeg',
					'X-Render-Path': path,
				},
				method='PUT',
			)
			with urllib.request.urlopen(req, timeout=3.0) as r:
				r.read()
			self._status('preview: %dx%d %dB' % (new_w, new_h, len(jpeg)))
		except Exception as e:
			self._status('preview put fail: ' + str(e)[:60])

	def SnapshotRender(self, path):
		"""One-shot snapshot of a Render TOP's geos / lights / cameras → daemon."""
		path = str(path or '').strip()
		if not path:
			self._status('render snapshot: empty path')
			return
		rtop = op(path)
		if rtop is None:
			self._status('render snapshot: missing ' + path[:50])
			return
		objects = []
		seen = set()

		def add_op(o, kind_hint=None):
			if o is None:
				return
			p = getattr(o, 'path', None)
			if not p or p in seen:
				return
			seen.add(p)
			kind = kind_hint or self._classify_render_op(o)
			if not kind:
				return
			entry = {
				'td_path': p,
				'name': getattr(o, 'name', p.rsplit('/', 1)[-1]),
				'kind': kind,
				'op_type': getattr(o, 'OPType', '') or type(o).__name__,
				'layer': 0,
				'visible': True,
				'trs': self._read_object_trs(o),
				'proxy_mode': 'mask',
			}
			if kind in ('light', 'env_light'):
				lt, ang = self._read_light_cue(o, kind)
				entry['light_type'] = lt
				entry['cone_angle'] = ang
			if kind == 'geo':
				entry['bounds'] = self._compute_geo_bounds(o)
			else:
				entry['bounds'] = {
					'min': [-0.25, -0.25, -0.25],
					'max': [0.25, 0.25, 0.25],
				}
			objects.append(entry)
			# Seed SHM path map with the same stable id the daemon will assign.
			try:
				import uuid as _uuid
				oid = str(_uuid.uuid5(_uuid.NAMESPACE_URL, '4designer-render:' + p))
				self._remember_path(oid, p)
			except Exception:
				pass

		for o in self._expand_render_par(getattr(rtop.par, 'geometry', None)):
			add_op(o, 'geo')
		for o in self._expand_render_par(getattr(rtop.par, 'lights', None)):
			add_op(o, None)
		for o in self._expand_render_par(getattr(rtop.par, 'camera', None)):
			add_op(o, 'camera')

		payload = {
			'render_path': path,
			'objects': objects,
		}
		try:
			body = json.dumps(payload).encode('utf-8')
			req = urllib.request.Request(
				self.BaseUrl + '/api/render/scene',
				data=body,
				headers={'X-Workspace-Id': self.WorkspaceId, 'Content-Type': 'application/json'},
				method='PUT',
			)
			with urllib.request.urlopen(req, timeout=4.0) as r:
				resp = json.loads(r.read().decode())
			status = (resp or {}).get('status') or ('%d objects' % len(objects))
			self._status('snapshot: ' + str(status)[:80])
		except Exception as e:
			self._status('snapshot put fail: ' + str(e)[:60])

	def ApplySetObjectTrs(self, msg):
		"""Write Object COMP tx…sz directly (geo / light / camera) — no chop_trs."""
		oid = str(msg.get('id') or '')
		path = str(msg.get('td_path') or '')
		trs = msg.get('trs') or {}
		if path and oid:
			self._remember_path(oid, path)
		if not path:
			return
		comp = op(path)
		if comp is None:
			return
		t = trs.get('t') or [0, 0, 0]
		r = trs.get('r') or [0, 0, 0]
		s = trs.get('s') or [1, 1, 1]
		try:
			if hasattr(comp.par, 'tx'):
				comp.par.tx = float(t[0])
				comp.par.ty = float(t[1])
				comp.par.tz = float(t[2])
			if hasattr(comp.par, 'rx'):
				comp.par.rx = float(r[0])
				comp.par.ry = float(r[1])
				comp.par.rz = float(r[2])
			if hasattr(comp.par, 'sx'):
				comp.par.sx = float(s[0])
				comp.par.sy = float(s[1])
				comp.par.sz = float(s[2])
		except Exception as e:
			self._status('set_object_trs fail: ' + str(e)[:60])

	def _expand_render_par(self, par):
		"""Resolve a Render TOP OP/list/* parameter into a list of OPs."""
		if par is None:
			return []
		try:
			val = par.eval()
		except Exception:
			return []
		if val is None:
			return []
		if isinstance(val, (list, tuple)):
			return [x for x in val if x is not None]
		# Single OP
		if hasattr(val, 'path'):
			return [val]
		return []

	def _classify_render_op(self, o):
		try:
			if isinstance(o, cameraCOMP):
				return 'camera'
			if isinstance(o, geometryCOMP):
				return 'geo'
			if isinstance(o, lightCOMP):
				return 'light'
		except Exception:
			pass
		opt = (getattr(o, 'OPType', '') or type(o).__name__ or '').lower()
		if 'environment' in opt and 'light' in opt:
			return 'env_light'
		if 'camera' in opt:
			return 'camera'
		if 'light' in opt:
			return 'light'
		if 'geometry' in opt or opt.endswith('geo'):
			return 'geo'
		return None

	def _read_object_trs(self, comp):
		def f(name, default):
			p = getattr(comp.par, name, None)
			if p is None:
				return default
			try:
				return float(p.eval())
			except Exception:
				return default
		return {
			't': [f('tx', 0.0), f('ty', 0.0), f('tz', 0.0)],
			'r': [f('rx', 0.0), f('ry', 0.0), f('rz', 0.0)],
			's': [f('sx', 1.0), f('sy', 1.0), f('sz', 1.0)],
		}

	def _read_light_cue(self, o, kind):
		"""Return (light_type, cone_angle) for plate icons."""
		if kind == 'env_light':
			return 'env', 30.0
		lt = 'point'
		ang = 30.0
		p = getattr(o.par, 'lighttype', None)
		if p is not None:
			try:
				lt = str(p.eval() or 'point').strip().lower()
			except Exception:
				lt = 'point'
		if lt not in ('point', 'cone', 'distant'):
			lt = 'point'
		cp = getattr(o.par, 'coneangle', None)
		if cp is not None:
			try:
				ang = float(cp.eval())
			except Exception:
				ang = 30.0
		return lt, ang

	def _find_geo_tip_pop(self, geo):
		"""Prefer outPOP tip inside a Geometry COMP; else deepest POP-like child."""
		if geo is None:
			return None
		try:
			outs = []
			pops = []
			for c in geo.findChildren(maxDepth=8):
				ot = (getattr(c, 'OPType', '') or type(c).__name__ or '').lower()
				if 'pop' not in ot:
					continue
				pops.append(c)
				if ot.startswith('out') or ot == 'outpop':
					outs.append(c)
			if outs:
				return outs[-1]
			if pops:
				return pops[-1]
		except Exception:
			pass
		# Direct child out1
		try:
			direct = geo.op('out1')
			if direct is not None:
				return direct
		except Exception:
			pass
		return None

	def _load_proxy_mesh_module(self):
		import importlib.util
		candidates = []
		try:
			candidates.append(os.path.join(project.folder, '4designer', 'td', 'proxy_mesh.py'))
		except Exception:
			pass
		try:
			dd = str(self.ownerComp.par.Daemondir.eval() or '')
			if dd:
				daemon_dir = dd if os.path.isabs(dd) else os.path.join(project.folder, dd)
				candidates.append(os.path.normpath(os.path.join(daemon_dir, '..', 'td', 'proxy_mesh.py')))
		except Exception:
			pass
		for path in candidates:
			if not os.path.isfile(path):
				continue
			try:
				spec = importlib.util.spec_from_file_location('fd_proxy_mesh_hub', path)
				if spec is None or spec.loader is None:
					continue
				mod = importlib.util.module_from_spec(spec)
				spec.loader.exec_module(mod)
				return mod
			except Exception:
				continue
		return None

	def CookRenderProxiesBatch(self, ids=None):
		"""Opt-in beauty GLB for render geos — sequential, capped, never on Refresh."""
		pm = self._load_proxy_mesh_module()
		if pm is None:
			self._status('render proxy: no proxy_mesh')
			return
		# Pull current render scene
		try:
			with self._http('/api/render/state', timeout=2.0) as r:
				scene = json.loads(r.read().decode())
		except Exception as e:
			self._status('render proxy state fail: ' + str(e)[:50])
			return
		objs = scene.get('objects') or {}
		if not isinstance(objs, dict):
			return
		max_n = self.MaxMeshProxies()
		# Count existing mesh proxies
		have = 0
		for o in objs.values():
			if isinstance(o, dict) and o.get('proxy_mode') == 'mesh' and o.get('proxy'):
				have += 1
		want_ids = None
		if isinstance(ids, list) and ids:
			want_ids = set(str(i) for i in ids)
		geos = []
		for oid, o in objs.items():
			if not isinstance(o, dict):
				continue
			if o.get('kind') != 'geo':
				continue
			if want_ids is not None and str(oid) not in want_ids:
				continue
			geos.append((str(oid), o))
		cooked = 0
		skipped = 0
		capped = 0
		for oid, o in geos:
			already = bool(o.get('proxy_mode') == 'mesh' and o.get('proxy'))
			if not already and have >= max_n:
				capped += 1
				continue
			ok = self.CookRenderProxy(oid, str(o.get('td_path') or ''), pm, o)
			if ok:
				cooked += 1
				if not already:
					have += 1
			else:
				skipped += 1
		msg = 'meshes: %d ok' % cooked
		if capped:
			msg += ', %d capped' % capped
		if skipped:
			msg += ', %d skip' % skipped
		self._status(msg)
		# Push status onto render store
		try:
			body = json.dumps({'status': msg}).encode('utf-8')
			req = urllib.request.Request(
				self.BaseUrl + '/api/render/status',
				data=body,
				headers={'X-Workspace-Id': self.WorkspaceId, 'Content-Type': 'application/json'},
				method='POST',
			)
			with urllib.request.urlopen(req, timeout=2.0) as r:
				r.read()
		except Exception:
			pass

	def CookRenderProxy(self, oid, td_path, pm=None, obj_meta=None):
		"""Extract tip POP → GLB → PUT /api/render/objects/{id}/proxy."""
		if pm is None:
			pm = self._load_proxy_mesh_module()
		if pm is None or not td_path:
			return False
		geo = op(td_path)
		if geo is None:
			return False
		tip = self._find_geo_tip_pop(geo)
		if tip is None:
			return False
		result = pm.extract_pop_triangles(tip)
		if result is None:
			return False
		points, tris, status = result
		if status != 'ok' or not points or not tris:
			return False
		try:
			glb = pm.write_glb(points, tris)
		except Exception:
			return False
		bounds = (obj_meta or {}).get('bounds') or self._compute_geo_bounds(geo)
		n_pts = len(points)
		n_tris = len(tris)
		fp = pm.bounds_fingerprint(bounds, n_pts, n_tris)
		# Skip upload if fingerprint matches existing
		prev_fp = ''
		try:
			prev = (obj_meta or {}).get('proxy') or {}
			prev_fp = str(prev.get('fingerprint') or '')
		except Exception:
			pass
		if prev_fp and prev_fp == fp:
			return True
		try:
			self.UploadRenderProxy(oid, glb, fp, n_pts, n_tris)
			return True
		except Exception as e:
			self._status('render upload fail: ' + str(e)[:50])
			return False

	def UploadRenderProxy(self, oid, glb_bytes, fingerprint='', verts=0, tris=0):
		boundary = '----fdrenderproxy' + str(int(time.time() * 1000))
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
			self.BaseUrl + '/api/render/objects/' + oid + '/proxy',
			data=body,
			headers={'X-Workspace-Id': self.WorkspaceId, 'Content-Type': f'multipart/form-data; boundary={boundary}'},
			method='PUT',
		)
		with urllib.request.urlopen(req, timeout=15.0) as r:
			return json.loads(r.read().decode())

	def _compute_geo_bounds(self, geo):
		"""Local-space AABB (pre-transform). UI applies Object COMP TRS once.

		`computeBounds` returns world-space corners; without an inverse, Refresh
		after a move double-applies translation (gizmo/box sit at 2× offset).
		"""
		try:
			b = geo.computeBounds(display=True, render=True, recurse=True)
			mn = getattr(b, 'min', None)
			mx = getattr(b, 'max', None)
			if mn is None or mx is None:
				raise ValueError('empty bounds')
			inv = geo.worldTransform.copy()
			inv.invert()
			xs = (float(mn.x), float(mx.x))
			ys = (float(mn.y), float(mx.y))
			zs = (float(mn.z), float(mx.z))
			lmin = [1e30, 1e30, 1e30]
			lmax = [-1e30, -1e30, -1e30]
			for x in xs:
				for y in ys:
					for z in zs:
						p = inv * tdu.Position(x, y, z)
						px, py, pz = float(p.x), float(p.y), float(p.z)
						if px < lmin[0]:
							lmin[0] = px
						if py < lmin[1]:
							lmin[1] = py
						if pz < lmin[2]:
							lmin[2] = pz
						if px > lmax[0]:
							lmax[0] = px
						if py > lmax[1]:
							lmax[1] = py
						if pz > lmax[2]:
							lmax[2] = pz
			return {'min': lmin, 'max': lmax}
		except Exception:
			pass
		return {'min': [-0.5, -0.5, -0.5], 'max': [0.5, 0.5, 0.5]}
