"""HTTP / WebSocket route modules for the 4designer daemon."""

from __future__ import annotations

from fastapi import FastAPI

from . import health, objects, render, workspaces
from .static_ui import mount_static
from .ws import register_ws


def include_routers(app: FastAPI) -> None:
    app.include_router(health.router)
    app.include_router(workspaces.router)
    app.include_router(objects.router)
    app.include_router(render.router)
    register_ws(app)
    mount_static(app)


__all__ = ["include_routers"]
