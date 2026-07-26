"""Re-export shared SHM module (SoT: shm/fourdesigner_shm)."""

from __future__ import annotations

import sys
from pathlib import Path

_SHARED_ROOT = Path(__file__).resolve().parents[2] / "shm"
if str(_SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(_SHARED_ROOT))

from fourdesigner_shm.shm_buf import *  # noqa: F403, E402
from fourdesigner_shm.shm_buf import (  # noqa: F401, E402
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
