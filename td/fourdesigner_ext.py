"""FourdesignerExt — hub extension: daemon lifecycle + WS set_trs fan-in."""

import importlib.util
import os
import uuid
from pathlib import Path

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000


def _mixin_bases():
	names = [
		('hub_lifecycle', 'HubLifecycleMixin'),
		('shm_drain', 'ShmDrainMixin'),
		('render_snapshot', 'RenderSnapshotMixin'),
		('marshal_registry', 'MarshalRegistryMixin'),
	]
	bases = []
	# TD embedded path: sibling Text DATs next to fourdesigner_ext
	try:
		parent = me.parent()  # type: ignore[name-defined]
		for dat_name, cls_name in names:
			dat = parent.op(dat_name)
			if dat is not None:
				bases.append(getattr(dat.module, cls_name))
		if len(bases) == 4:
			return tuple(bases)
	except Exception:
		pass
	# Disk path (td/ext/*.py)
	bases = []
	ext_dir = Path(__file__).resolve().parent / 'ext'
	for dat_name, cls_name in names:
		path = ext_dir / f'{dat_name}.py'
		spec = importlib.util.spec_from_file_location(f'fd_ext_{dat_name}', path)
		if spec is None or spec.loader is None:
			raise ImportError(f'missing mixin: {path}')
		mod = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(mod)
		bases.append(getattr(mod, cls_name))
	return tuple(bases)


_BASES = _mixin_bases()


class FourdesignerExt(*_BASES):
	SPAWN_COOLDOWN_S = 30
	PRUNE_GROUP = 'fourdesigner_prune'
	PRUNE_PERIOD_FRAMES = 1800  # ~30s at 60fps — orphan sweep only
	PRUNE_PERIOD_SHM_DOWN = 300  # fallback pending poll when SHM unavailable

	def __init__(self, ownerComp):
		self.ownerComp = ownerComp
		self.State = {}
		self.Connected = False
		self._retry_fails = 0
		self._last_spawn = 0.0
		self._path_by_id = {}
		self._path_by_hash = {}
		self._shm = None
		self._shm_slug = ''
		self._shm_epoch = -1
		self._shm_last_trs_seq = -1
		self._shm_last_cmd_seq = -1
		self._shm_last_gen = [0] * 512
		self._shm_trs_pending = False
		self._shm_open_fails = 0
		self._prune_ticks = 0
		self._pending_http_count = 0  # exit-criteria counter (idle should stay 0 when SHM ok)
		self._orphan_suspects = {}  # oid → first_seen time for PruneOrphans debounce
		self._ensure_workspace_id()
		# Ext reinit resets Connected while the Websocket DAT can stay peer-live.
		run("args[0]._recover_ws_hello()", self, delayFrames=2)
		run("args[0]._recover_ws_hello()", self, delayFrames=45)

	def _ensure_workspace_id(self):
		par = getattr(self.ownerComp.par, 'Workspaceid', None)
		if par is None:
			return
		cur = str(par.eval() or '').strip()
		if not cur:
			par.val = str(uuid.uuid4())

	@property
	def WorkspaceId(self):
		par = getattr(self.ownerComp.par, 'Workspaceid', None)
		if par is None:
			return ''
		wid = str(par.eval() or '').strip()
		if not wid:
			self._ensure_workspace_id()
			wid = str(par.eval() or '').strip()
		return wid

	@property
	def BaseUrl(self):
		return self.ownerComp.par.Daemonurl.eval().rstrip('/')

	@property
	def DaemonDir(self):
		d = self.ownerComp.par.Daemondir.eval()
		if os.path.isabs(d):
			return d
		return os.path.join(project.folder, d)
