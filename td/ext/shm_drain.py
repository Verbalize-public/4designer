"""ShmDrainMixin — shared-memory TRS/cmd drain."""


class ShmDrainMixin:
	def _shm_mod(self):
		dat = self.ownerComp.op('shm_buf')
		if dat is None:
			return None
		try:
			return dat.module
		except Exception:
			return None

	def _shm_ok(self):
		return self._shm is not None and getattr(self._shm, 'ok', False)

	def _try_open_shm(self):
		mod = self._shm_mod()
		if mod is None:
			return
		slug = self.WorkspaceId or str(self.State.get('workspace_id') or '')
		if not slug:
			return
		# Re-open on slug/epoch change
		if self._shm is not None and self._shm_slug == slug:
			try:
				ep = int(self._shm.epoch)
				if ep == self._shm_epoch:
					return
			except Exception:
				pass
			try:
				self._shm.close(unlink=False)
			except Exception:
				pass
			self._shm = None
		try:
			buf = mod.SharedTrsBuffer.open(slug)
		except Exception:
			buf = None
		if buf is None:
			self._shm_open_fails += 1
			return
		self._shm = buf
		self._shm_slug = slug
		self._shm_epoch = int(buf.epoch)
		self._shm_last_trs_seq = -1
		self._shm_last_cmd_seq = -1
		self._shm_last_gen = [0] * 512
		self._shm_trs_pending = False
		self._shm_open_fails = 0

	def DrainShm(self):
		"""Per-frame: apply dirty TRS slots + drain cmd ring. Early-out when idle.

		SHM must not depend on WS ``Connected`` — that flag is only for hello/role.
		"""
		# Self-heal sticky "Waiting for TouchDesigner" after ext reinit.
		if not self.Connected and (int(absTime.frame) % 90) == 0:
			self._recover_ws_hello()
		if not self._shm_ok():
			# Retry open occasionally (daemon may have started after hub).
			if self._shm_open_fails < 30 or (int(absTime.frame) % 120) == 0:
				self._try_open_shm()
			if not self._shm_ok():
				return
		buf = self._shm
		mod = self._shm_mod()
		try:
			ep = int(buf.epoch)
		except Exception:
			self._shm = None
			return
		if ep != self._shm_epoch:
			self._shm_epoch = ep
			self._shm_last_trs_seq = -1
			self._shm_last_cmd_seq = -1
			self._shm_last_gen = [0] * 512
			self._shm_trs_pending = False
		try:
			seq_trs = int(buf.seq_trs)
			seq_cmd = int(buf.seq_cmd)
		except Exception:
			return
		need_trs = seq_trs != self._shm_last_trs_seq or self._shm_trs_pending
		need_cmd = seq_cmd != self._shm_last_cmd_seq
		if not need_trs and not need_cmd:
			return
		if need_trs:
			try:
				dirty = buf.collect_dirty(self._shm_last_gen, max_n=64)
			except Exception:
				dirty = []
			for d in dirty:
				path = self._path_by_hash.get(d.id_hash)
				if not path:
					continue
				self._apply_trs_vectors(path, d.t, d.r, d.s)
			self._shm_trs_pending = len(dirty) >= 64
			if not self._shm_trs_pending:
				self._shm_last_trs_seq = seq_trs
		if need_cmd and mod is not None:
			try:
				cmds = buf.pop_cmds(max_n=16)
			except Exception:
				cmds = []
			for c in cmds:
				self._apply_shm_cmd(mod, c)
			self._shm_last_cmd_seq = int(buf.seq_cmd)

	def _apply_trs_vectors(self, path, t, r, s):
		comp = op(path)
		if comp is None:
			return
		# Marshal: chop_trs Constant CHOP; render Object COMP: direct pars.
		chop = comp.op('chop_trs') if hasattr(comp, 'op') else None
		if chop is not None:
			self._set_const_channels(chop, {
				'tx': float(t[0]), 'ty': float(t[1]), 'tz': float(t[2]),
				'rx': float(r[0]), 'ry': float(r[1]), 'rz': float(r[2]),
				'sx': float(s[0]), 'sy': float(s[1]), 'sz': float(s[2]),
			})
			return
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
			self._status('shm trs fail: ' + str(e)[:60])

	def _apply_shm_cmd(self, mod, c):
		ctype = int(getattr(c, 'type', 0) or 0)
		payload = getattr(c, 'payload', b'') or b''
		if ctype == mod.CMD_DESTROY:
			oid, path = mod.parse_destroy(payload)
			self.ApplyDestroyMarshal({'id': oid, 'td_path': path})
		elif ctype == mod.CMD_LIST_TOPS:
			self.ListRenderTops()
		elif ctype == mod.CMD_SNAPSHOT:
			path = payload.decode('utf-8', errors='replace')
			self.SnapshotRender(path)
		elif ctype == getattr(mod, 'CMD_PREVIEW', 6):
			path = payload.decode('utf-8', errors='replace')
			self.CaptureRenderPreview(path)
		elif ctype == mod.CMD_COOK_PROXIES:
			ids = None
			if payload:
				ids = [p.decode('utf-8', errors='replace') for p in payload.split(b'\0') if p]
			self.CookRenderProxiesBatch(ids)
		elif ctype == mod.CMD_REFRESH_PROXY:
			oid, path = mod.parse_destroy(payload)
			self.ApplyRefreshProxy({'id': oid, 'td_path': path})
