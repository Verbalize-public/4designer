"""Re-export shared SHM module for TD Text DAT / disk import.

SoT: shm/fourdesigner_shm/shm_buf.py
When embedded as a hub Text DAT, build_hub copies the shared source verbatim.
When imported from disk (tests), this file bootstraps sys.path.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SHARED_ROOT = Path(__file__).resolve().parent.parent / "shm"
if _SHARED_ROOT.is_dir() and str(_SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(_SHARED_ROOT))

try:
    from fourdesigner_shm.shm_buf import *  # noqa: F403
    from fourdesigner_shm.shm_buf import (  # noqa: F401
        CMD_COOK_PROXIES,
        CMD_DESTROY,
        CMD_LIST_TOPS,
        CMD_PREVIEW,
        CMD_REFRESH_PROXY,
        CMD_SNAPSHOT,
        MAGIC,
        SharedTrsBuffer,
        TOTAL_SIZE,
        VERSION,
        parse_destroy,
        payload_destroy,
        shm_name,
    )
except ImportError:
    # Fallback: load shared file by path (TD Text DAT without package install).
    import importlib.util

    _src = _SHARED_ROOT / "fourdesigner_shm" / "shm_buf.py"
    _spec = importlib.util.spec_from_file_location("fourdesigner_shm_buf", _src)
    if _spec is None or _spec.loader is None:
        raise
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})
