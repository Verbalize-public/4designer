"""Workspace list / seed routes."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter

from ..runtime import _sync_workspace_td, registry

router = APIRouter()


@router.get("/api/workspaces")
def list_workspaces() -> dict[str, Any]:
    for w in registry.all():
        _sync_workspace_td(w, broadcast=False)
    return {"workspaces": registry.list_meta()}


@router.post("/api/workspaces")
def create_workspace(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Seed a workspace without TD (e2e / fixtures).

    Pass ``fixture: true`` (or ``td_connected: true``) to mark the workspace
    connected so the UI enables mutations without a live hub WebSocket.
    """
    data = body if isinstance(body, dict) else {}
    wid = str(data.get("id") or "").strip() or str(uuid.uuid4())
    w = registry.ensure(
        wid,
        project_name=str(data.get("project_name") or ""),
        project_folder=str(data.get("project_folder") or ""),
    )
    if data.get("fixture") or data.get("td_connected"):
        w.mark_fixture_connected()
    return w.meta()
