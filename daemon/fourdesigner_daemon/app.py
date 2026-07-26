"""4designer FastAPI app factory: CORS, lifecycle, routers, static UI."""

from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from . import persistence
from .routes import include_routers
from .runtime import (
    CMD_COOK_PROXIES,
    CMD_DESTROY,
    CMD_LIST_TOPS,
    CMD_PREVIEW,
    CMD_REFRESH_PROXY,
    CMD_SNAPSHOT,
    FRONTEND_DIST,
    HEADER_WORKSPACE,
    SharedTrsBuffer,
    Workspace,
    WsHub,
    _broadcast_render_state,
    _emit_refresh_proxy,
    _emit_set_layer,
    _emit_set_object_trs,
    _emit_set_proxy_mode,
    _emit_set_trs,
    _ensure_shm,
    _http_fresh,
    _proxy_url,
    _render_proxy_url,
    _shm_ok,
    _shm_push_cmd,
    _shm_write_obj,
    _sync_workspace_td,
    hub,
    log,
    mark_td_seen,
    payload_destroy,
    registry,
    require_workspace,
)

app = FastAPI(title="4designer", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup() -> None:
    hub.loop = asyncio.get_running_loop()
    persistence.ensure_dirs()
    log.info("4designer multi-workspace daemon ready (memory SOT)")


@app.on_event("shutdown")
async def _shutdown() -> None:
    registry.close_all_shm(unlink=True)


include_routers(app)

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
    "app",
    "hub",
    "log",
    "mark_td_seen",
    "payload_destroy",
    "persistence",
    "registry",
    "require_workspace",
]
