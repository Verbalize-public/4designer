"""Per-TD workspace: isolated SOT, render store, SHM, and pending queues."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import WebSocket

from .render_store import RenderStore
from .shm_buf import SharedTrsBuffer
from .state import StateStore


def new_workspace_id() -> str:
    return str(uuid.uuid4())


@dataclass
class Workspace:
    id: str
    project_name: str = ""
    project_folder: str = ""
    connected: bool = False
    td_ws: Optional[WebSocket] = None
    store: StateStore = field(default_factory=StateStore)
    render_store: RenderStore = field(default_factory=RenderStore)
    shm: Optional[SharedTrsBuffer] = None
    pending_destroys: list[dict[str, str]] = field(default_factory=list)
    pending_proxy_cmds: list[dict[str, Any]] = field(default_factory=list)
    pending_render_cmds: list[dict[str, Any]] = field(default_factory=list)
    shm_seeded_ws: set[str] = field(default_factory=set)
    td_seen_at: float = 0.0
    # When True, meta reports connected without a live TD WebSocket (e2e fixtures).
    fixture: bool = False

    def __post_init__(self) -> None:
        self.store.slug = self.id

    def meta(self) -> dict[str, Any]:
        live = self.td_ws is not None or self.fixture
        return {
            "id": self.id,
            "project_name": self.project_name,
            "project_folder": self.project_folder,
            "connected": bool(self.connected and live),
        }

    def mark_fixture_connected(self) -> None:
        """Simulate a live TD hub for daemon+frontend e2e (no TouchDesigner)."""
        self.fixture = True
        self.connected = True
        self.store.td_connected = True
        self.mark_td_seen()

    def mark_td_seen(self) -> None:
        self.td_seen_at = time.time()
        self.store.td_seen_at = self.td_seen_at

    def sync_td_connected(self, *, http_fresh: bool) -> bool:
        alive = (self.td_ws is not None) or http_fresh or self.fixture
        self.connected = alive
        if self.store.td_connected == alive:
            return False
        self.store.td_connected = alive
        return True

    def close_shm(self, *, unlink: bool = False) -> None:
        if self.shm is None:
            return
        try:
            self.shm.close(unlink=unlink)
        except Exception:
            pass
        self.shm = None


class WorkspaceRegistry:
    def __init__(self) -> None:
        self._by_id: dict[str, Workspace] = {}
        self._td_ws: dict[WebSocket, str] = {}

    def get(self, workspace_id: str) -> Optional[Workspace]:
        return self._by_id.get(workspace_id)

    def all(self) -> list[Workspace]:
        return list(self._by_id.values())

    def list_meta(self) -> list[dict[str, Any]]:
        return [w.meta() for w in self._by_id.values()]

    def any_td_connected(self) -> bool:
        return any(w.connected for w in self._by_id.values())

    def workspace_for_td_ws(self, ws: WebSocket) -> Optional[Workspace]:
        wid = self._td_ws.get(ws)
        return self._by_id.get(wid) if wid else None

    def ensure(self, workspace_id: str, *, project_name: str = "", project_folder: str = "") -> Workspace:
        w = self._by_id.get(workspace_id)
        if w is None:
            w = Workspace(
                id=workspace_id,
                project_name=project_name,
                project_folder=project_folder,
            )
            self._by_id[workspace_id] = w
        else:
            if project_name:
                w.project_name = project_name
            if project_folder:
                w.project_folder = project_folder
        return w

    def bind_td(
        self,
        ws: WebSocket,
        workspace_id: str,
        *,
        project_name: str = "",
        project_folder: str = "",
    ) -> tuple[Workspace, Optional[str]]:
        """Bind a TD WebSocket to a workspace.

        Returns (workspace, rekey_id). rekey_id is set when the client must
        adopt a new id (empty/missing id, or live collision).
        """
        requested = (workspace_id or "").strip()
        rekey: Optional[str] = None

        if not requested:
            rekey = new_workspace_id()
            requested = rekey
        else:
            existing = self._by_id.get(requested)
            if (
                existing is not None
                and existing.td_ws is not None
                and existing.td_ws is not ws
            ):
                rekey = new_workspace_id()
                requested = rekey

        # Drop previous binding for this socket.
        prev_id = self._td_ws.pop(ws, None)
        if prev_id and prev_id != requested:
            prev = self._by_id.get(prev_id)
            if prev is not None and prev.td_ws is ws:
                prev.td_ws = None
                prev.connected = False
                prev.store.td_connected = False

        w = self.ensure(requested, project_name=project_name, project_folder=project_folder)
        if project_name:
            w.project_name = project_name
        if project_folder:
            w.project_folder = project_folder
        w.td_ws = ws
        w.connected = True
        w.store.td_connected = True
        w.mark_td_seen()
        self._td_ws[ws] = w.id
        return w, rekey

    def unbind_td(self, ws: WebSocket) -> Optional[Workspace]:
        wid = self._td_ws.pop(ws, None)
        if not wid:
            return None
        w = self._by_id.get(wid)
        if w is None:
            return None
        if w.td_ws is ws:
            w.td_ws = None
            w.connected = False
            w.store.td_connected = False
        return w

    def close_all_shm(self, *, unlink: bool = False) -> None:
        for w in self._by_id.values():
            w.close_shm(unlink=unlink)

    def clear(self) -> None:
        """Test helper: drop all workspaces."""
        self.close_all_shm(unlink=False)
        self._by_id.clear()
        self._td_ws.clear()
