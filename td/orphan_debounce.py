"""Pure helper: debounce orphan prune when COMP.destroy() skips onExit.

COMP.destroy() in TouchDesigner may not run Execute onExit; a mid-destroy path
can look missing for a few frames. Only treat as orphan after dwell_s.
"""

from __future__ import annotations

from typing import Optional


def orphan_ready_to_prune(
    suspects: dict[str, float],
    oid: str,
    *,
    missing: bool,
    now: float,
    dwell_s: float = 0.75,
) -> bool:
    """Update suspects for oid; return True if it should be pruned now.

    - missing=False → clear suspect, return False
    - missing=True → record first_seen; return True only after dwell_s
    """
    if not missing:
        suspects.pop(oid, None)
        return False
    first = suspects.get(oid)
    if first is None:
        suspects[oid] = now
        return False
    return (now - first) >= dwell_s


def clear_orphan_suspect(suspects: dict[str, float], oid: str) -> None:
    suspects.pop(oid, None)
