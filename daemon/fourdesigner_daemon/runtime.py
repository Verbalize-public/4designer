"""Shared daemon runtime: registry, WS hub, SHM helpers, workspace deps."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import Header, HTTPException, Query, WebSocket

from . import persistence
from .shm_buf import (
    CMD_COOK_PROXIES,
    CMD_DESTROY,
    CMD_LIST_TOPS,
    CMD_PREVIEW,
    CMD_REFRESH_PROXY,
    CMD_SNAPSHOT,
    SharedTrsBuffer,
    payload_destroy,
)
from .workspace import Workspace, WorkspaceRegistry

log = logging.getLogger("fourdesigner.app")

TD_HTTP_STALE_S = 60.0
HEADER_WORKSPACE = "X-Workspace-Id"
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

registry = WorkspaceRegistry()


def _http_fresh(w: Workspace) -> bool:
    seen = float(w.td_seen_at or 0.0)
    return seen > 0.0 and (time.time() - seen) < TD_HTTP_STALE_S


class WsHub:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self.roles: dict[WebSocket, str] = {}
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def broadcast_from_anywhere(self, msg: dict[str, Any]) -> None:
        if self.loop is None:
            return
        self.loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(self.broadcast_msg(msg))
        )

    async def broadcast_msg(
        self,
        msg: dict[str, Any],
        *,
        to_role: Optional[str] = None,
        only_ws: Optional[WebSocket] = None,
    ) -> None:
        if not self.clients:
            return
        dead: list[WebSocket] = []
        for client in list(self.clients):
            if only_ws is not None and client is not only_ws:
                continue
            if to_role is not None and self.roles.get(client) != to_role:
                continue
            try:
                await client.send_json(msg)
            except Exception:
                dead.append(client)
        for client in dead:
            self.clients.discard(client)
            self.roles.pop(client, None)

    async def send_td(self, w: Workspace, msg: dict[str, Any]) -> None:
        if w.td_ws is None:
            return
        try:
            await w.td_ws.send_json(msg)
        except Exception:
            log.exception("send_td failed workspace=%s", w.id)

    async def broadcast_workspace_state(self, w: Workspace) -> None:
        await self.broadcast_msg(
            {"type": "state", "workspace_id": w.id, **w.store.snapshot()},
            to_role="ui",
        )

    async def broadcast_workspace_list(self) -> None:
        await self.broadcast_msg(
            {"type": "workspace_list", "workspaces": registry.list_meta()},
            to_role="ui",
        )


hub = WsHub()


def _sync_workspace_td(w: Workspace, *, broadcast: bool = True) -> bool:
    changed = w.sync_td_connected(http_fresh=_http_fresh(w))
    if changed and broadcast:
        hub.broadcast_from_anywhere(
            {
                "type": "project_patch",
                "workspace_id": w.id,
                "td_connected": w.store.td_connected,
            }
        )
        hub.broadcast_from_anywhere({"type": "workspace_list", "workspaces": registry.list_meta()})
    return changed


def mark_td_seen(w: Workspace) -> None:
    w.mark_td_seen()
    _sync_workspace_td(w, broadcast=True)


def _ensure_shm(w: Workspace) -> SharedTrsBuffer | None:
    if w.shm is not None and w.shm.ok:
        return w.shm
    w.shm = SharedTrsBuffer.create(w.id)
    if w.shm:
        log.info("SHM ready workspace=%s name=%s", w.id, w.shm.name)
    else:
        log.warning("SHM unavailable workspace=%s — WS set_trs fallback", w.id)
    return w.shm


def _shm_ok(w: Workspace) -> bool:
    return w.shm is not None and w.shm.ok


def _shm_write_obj(w: Workspace, oid: str, obj: dict[str, Any]) -> bool:
    buf = _ensure_shm(w)
    if not buf:
        return False
    try:
        buf.write_trs_dict(oid, obj.get("trs") or {})
        return True
    except Exception:
        log.exception("shm write_trs failed workspace=%s id=%s", w.id, oid)
        return False


def _shm_push_cmd(w: Workspace, cmd_type: int, payload: bytes = b"") -> None:
    buf = _ensure_shm(w)
    if not buf:
        return
    if not buf.push_cmd(cmd_type, payload):
        log.warning("SHM cmd ring full workspace=%s type=%s", w.id, cmd_type)


def require_workspace(
    x_workspace_id: Optional[str] = Header(None, alias=HEADER_WORKSPACE),
    workspace: Optional[str] = Query(None, description="Alt to X-Workspace-Id (GLB/loaders)"),
) -> Workspace:
    """Resolve workspace from header or ?workspace= (binary asset loads via GLTFLoader)."""
    wid = (x_workspace_id or workspace or "").strip()
    if not wid:
        raise HTTPException(400, "X-Workspace-Id required")
    w = registry.get(wid)
    if w is None:
        raise HTTPException(404, f"workspace {wid} not found")
    return w


def _proxy_url(oid: str, workspace_id: str) -> str:
    return f"/api/objects/{oid}/proxy.glb?workspace={workspace_id}"


def _render_proxy_url(oid: str, workspace_id: str) -> str:
    return f"/api/render/objects/{oid}/proxy.glb?workspace={workspace_id}"


def _set_trs_msg(oid: str, obj: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "set_trs",
        "id": oid,
        "trs": obj["trs"],
        "td_path": obj.get("td_path") or "",
    }


def _set_layer_msg(oid: str, obj: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "set_layer",
        "id": oid,
        "layer": obj["layer"],
        "td_path": obj.get("td_path") or "",
    }


async def _emit_set_trs(w: Workspace, oid: str, obj: dict[str, Any]) -> None:
    if _shm_write_obj(w, oid, obj):
        return
    await hub.send_td(w, _set_trs_msg(oid, obj))


async def _emit_set_object_trs(w: Workspace, oid: str, obj: dict[str, Any]) -> None:
    wrote = _shm_write_obj(w, oid, obj)
    if wrote and oid in w.shm_seeded_ws:
        return
    await hub.send_td(
        w,
        {
            "type": "set_object_trs",
            "id": oid,
            "trs": obj["trs"],
            "td_path": obj.get("td_path") or "",
        },
    )
    if wrote:
        w.shm_seeded_ws.add(oid)


async def _emit_set_layer(w: Workspace, oid: str, obj: dict[str, Any]) -> None:
    await hub.send_td(w, _set_layer_msg(oid, obj))


async def _emit_set_proxy_mode(w: Workspace, oid: str, obj: dict[str, Any]) -> None:
    await hub.send_td(
        w,
        {
            "type": "set_proxy_mode",
            "id": oid,
            "proxy_mode": obj.get("proxy_mode") or "mask",
            "td_path": obj.get("td_path") or "",
        },
    )


async def _emit_refresh_proxy(w: Workspace, oid: str, obj: dict[str, Any]) -> None:
    td_path = str(obj.get("td_path") or "")
    msg = {"type": "refresh_proxy", "id": oid, "td_path": td_path}
    w.pending_proxy_cmds.append(msg)
    _shm_push_cmd(w, CMD_REFRESH_PROXY, payload_destroy(oid, td_path))
    await hub.send_td(w, msg)


async def _broadcast_render_state(w: Workspace) -> None:
    await hub.broadcast_msg(
        {"type": "render_state", "workspace_id": w.id, **w.render_store.snapshot()},
        to_role="ui",
    )


__all__ = [
    "CMD_COOK_PROXIES",
    "CMD_DESTROY",
    "CMD_LIST_TOPS",
    "CMD_PREVIEW",
    "CMD_REFRESH_PROXY",
    "CMD_SNAPSHOT",
    "FRONTEND_DIST",
    "HEADER_WORKSPACE",
    "SharedTrsBuffer",
    "Workspace",
    "WsHub",
    "_broadcast_render_state",
    "_emit_refresh_proxy",
    "_emit_set_layer",
    "_emit_set_object_trs",
    "_emit_set_proxy_mode",
    "_emit_set_trs",
    "_ensure_shm",
    "_http_fresh",
    "_proxy_url",
    "_render_proxy_url",
    "_shm_ok",
    "_shm_push_cmd",
    "_shm_write_obj",
    "_sync_workspace_td",
    "hub",
    "log",
    "mark_td_seen",
    "payload_destroy",
    "persistence",
    "registry",
    "require_workspace",
]
