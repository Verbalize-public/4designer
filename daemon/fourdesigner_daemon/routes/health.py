"""Health check route."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .. import __version__
from ..runtime import _shm_ok, _sync_workspace_td, registry

router = APIRouter()


@router.get("/health")
def health() -> dict[str, Any]:
    for w in registry.all():
        _sync_workspace_td(w, broadcast=False)
    workspaces = registry.list_meta()
    any_td = registry.any_td_connected()
    shm_ok = any(_shm_ok(w) for w in registry.all())
    return {
        "status": "ok",
        "app": "4designer",
        "version": __version__,
        "td_connected": any_td,
        "workspaces": workspaces,
        "shm_ok": shm_ok,
    }
