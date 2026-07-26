"""MarshalExt — hub discovery, register, bounds probe, gated mesh proxy cook."""

from __future__ import annotations

import time
import uuid


class MarshalExt:
	def __init__(self, ownerComp):
		self.ownerComp = ownerComp
		self._last_auto_cook = 0.0
		self._last_fp = ''

	def ResolveHub(self):
		hub = getattr(op, 'fourdesigner', None)
		if hub is None:
			hub = getattr(op, '4designer', None)
		if hub is None and hasattr(self.ownerComp.par, 'Hub') and self.ownerComp.par.Hub:
			try:
				hub = op(self.ownerComp.par.Hub)
			except Exception:
				hub = None
		return hub

	def EnsureObjectId(self):
		oid = str(self.ownerComp.par.Objectid.eval() or '')
		if not oid:
			oid = str(uuid.uuid4())
			self.ownerComp.par.Objectid.val = oid
		return oid

	def ProxyMode(self) -> str:
		if not hasattr(self.ownerComp.par, 'Proxymode'):
			return 'mask'
		try:
			v = str(self.ownerComp.par.Proxymode.eval() or 'mask').strip().lower()
		except Exception:
			v = 'mask'
		return 'mesh' if v == 'mesh' else 'mask'

	def RestPop(self):
		return self.ownerComp.op('null_rest') or self.ownerComp.op('in1')

	def _load_proxy_mesh(self):
		"""Load proxy_mesh helpers from sibling DAT or tools path."""
		dat = self.ownerComp.op('proxy_mesh')
		if dat is not None and getattr(dat, 'module', None) is not None:
			try:
				return dat.module
			except Exception:
				pass
		hub = self.ResolveHub()
		# File path next to fourdesigner tools
		import importlib.util
		import os
		candidates = []
		try:
			candidates.append(os.path.join(project.folder, '4designer', 'td', 'proxy_mesh.py'))
		except Exception:
			pass
		if hub is not None:
			try:
				dd = str(hub.par.Daemondir.eval() or '')
				daemon_dir = dd if os.path.isabs(dd) else os.path.join(project.folder, dd)
				candidates.append(os.path.normpath(os.path.join(daemon_dir, '..', 'td', 'proxy_mesh.py')))
			except Exception:
				pass
		for path in candidates:
			if os.path.isfile(path):
				spec = importlib.util.spec_from_file_location('fd_proxy_mesh', path)
				if spec and spec.loader:
					mod = importlib.util.module_from_spec(spec)
					spec.loader.exec_module(mod)
					return mod
		return None

	def ProbeBounds(self):
		pm = self._load_proxy_mesh()
		rest = self.RestPop()
		if pm is None:
			return {
				'min': [-0.5, -0.5, -0.5],
				'max': [0.5, 0.5, 0.5],
			}, 'bounds_fallback'
		bounds, hint = pm.probe_pop_bounds(rest)
		return bounds, hint

	def CookProxyMesh(self):
		"""Returns (glb_bytes, verts, tris, status) or (None,0,0,status). Mask mode must not call."""
		if self.ProxyMode() != 'mesh':
			return None, 0, 0, 'mask'
		pm = self._load_proxy_mesh()
		if pm is None:
			return None, 0, 0, 'proxy_fallback'
		rest = self.RestPop()
		result = pm.extract_pop_triangles(rest)
		if result is None:
			return None, 0, 0, 'proxy_timeout'
		points, tris, status = result
		if status != 'ok' or not points or not tris:
			return None, 0, 0, status if status != 'ok' else 'proxy_fallback'
		try:
			glb = pm.write_glb(points, tris)
		except Exception:
			return None, 0, 0, 'proxy_fallback'
		return glb, len(points), len(tris), 'ok'

	def OnActiveChanged(self):
		active = bool(self.ownerComp.par.Active.eval())
		if active:
			self.Register()
		else:
			self.Unregister()

	def OnProxyModeChanged(self):
		hub = self.ResolveHub()
		if hub is None:
			return
		mode = self.ProxyMode()
		try:
			hub.ext.FourdesignerExt.SetProxyMode(self.ownerComp, mode)
		except Exception as e:
			self._set_proxy_status('mode_fail:' + str(e)[:40])
		if bool(self.ownerComp.par.Active.eval()):
			run('args[0].RefreshProxy()', self, delayFrames=1)

	def Register(self):
		hub = self.ResolveHub()
		if hub is None:
			self.ownerComp.par.Status = 'no_hub'
			return
		self.EnsureObjectId()
		try:
			ex = self.ownerComp.op('execute1')
			if ex is not None:
				ex.store('fd_oid', str(self.ownerComp.par.Objectid.eval() or ''))
		except Exception:
			pass
		try:
			hub.ext.FourdesignerExt.Register(self.ownerComp)
			run('args[0].RefreshProxy()', self, delayFrames=1)
		except Exception as e:
			self.ownerComp.par.Status = 'register_fail:' + str(e)[:80]

	def Unregister(self):
		hub = self.ResolveHub()
		if hub is None:
			self.ownerComp.par.Status = 'no_hub'
			return
		try:
			hub.ext.FourdesignerExt.Unregister(self.ownerComp)
		except Exception as e:
			self.ownerComp.par.Status = 'unregister_fail:' + str(e)[:60]
		try:
			ex = self.ownerComp.op('execute1')
			if ex is not None:
				ex.unstore('fd_oid')
		except Exception:
			pass

	def RefreshProxy(self):
		"""Bounds always; GLB only when Proxymode=mesh (mask short-circuit)."""
		hub = self.ResolveHub()
		if hub is None:
			self.ownerComp.par.Status = 'no_hub'
			return
		if not bool(self.ownerComp.par.Active.eval()):
			return
		bounds, hint = self.ProbeBounds()
		try:
			hub.ext.FourdesignerExt.PatchBoundsQuiet(self.ownerComp, bounds)
		except Exception as e:
			self._set_proxy_status('bounds_fail:' + str(e)[:40])
			return

		mode = self.ProxyMode()
		if mode != 'mesh':
			self._set_proxy_status('bounds_ok' if hint == 'bounds_ok' else hint)
			return

		# Mesh path — Autoproxy cooldown / fingerprint
		pm = self._load_proxy_mesh()
		n_pts = 0
		n_prims = 0
		rest = self.RestPop()
		try:
			n_pts = int(rest.numPoints()) if hasattr(rest, 'numPoints') else 0
		except Exception:
			pass
		fp = pm.bounds_fingerprint(bounds, n_pts, n_prims) if pm else ''
		auto = bool(self.ownerComp.par.Autoproxy.eval()) if hasattr(self.ownerComp.par, 'Autoproxy') else False
		# Always allow explicit Refresh pulse; Autoproxy respects cooldown+fp
		# Caller distinguishes via pulse vs delayed — we always cook on explicit RefreshProxy.
		# Cooldown only when fingerprint unchanged within 1s (skip redundant).
		now = time.time()
		if fp and fp == self._last_fp and (now - self._last_auto_cook) < 1.0:
			self._set_proxy_status('proxy_ok')
			return

		try:
			if hub.ext.FourdesignerExt.MeshProxyCount() >= hub.ext.FourdesignerExt.MaxMeshProxies():
				# Already counted if this object has proxy — allow refresh of existing
				oid = str(self.ownerComp.par.Objectid.eval() or '')
				if not hub.ext.FourdesignerExt.ObjectHasProxy(oid):
					self._set_proxy_status('proxy_cap')
					return
		except Exception:
			pass

		glb, verts, tris, status = self.CookProxyMesh()
		if glb is None:
			self._set_proxy_status(status if status != 'ok' else 'proxy_fallback')
			return
		try:
			hub.ext.FourdesignerExt.UploadProxy(self.ownerComp, glb, fp, verts, tris)
			self._last_fp = fp
			self._last_auto_cook = now
			self._set_proxy_status('proxy_ok')
		except Exception as e:
			self._set_proxy_status('upload_fail:' + str(e)[:40])

	def MaybeAutoProxy(self):
		"""Fingerprint path — only if Autoproxy on and mesh mode."""
		if self.ProxyMode() != 'mesh':
			return
		if not hasattr(self.ownerComp.par, 'Autoproxy') or not bool(self.ownerComp.par.Autoproxy.eval()):
			return
		now = time.time()
		if now - self._last_auto_cook < 1.0:
			return
		self.RefreshProxy()

	def _set_proxy_status(self, msg: str):
		if hasattr(self.ownerComp.par, 'Proxystatus'):
			try:
				self.ownerComp.par.Proxystatus = str(msg)[:80]
			except Exception:
				pass

	def OnDestroy(self):
		"""Always unregister by Objectid — do not gate on Active (may already be off)."""
		try:
			_ = str(self.ownerComp.par.Objectid.eval() or '')
		except Exception:
			pass
		try:
			self.Unregister()
		except Exception:
			pass
