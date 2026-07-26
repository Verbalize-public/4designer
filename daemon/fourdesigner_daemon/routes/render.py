"""Render-view API routes."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response

from .. import persistence
from ..runtime import (
    CMD_COOK_PROXIES,
    CMD_LIST_TOPS,
    CMD_PREVIEW,
    CMD_SNAPSHOT,
    Workspace,
    _broadcast_render_state,
    _emit_set_object_trs,
    _render_proxy_url,
    _shm_push_cmd,
    hub,
    mark_td_seen,
    require_workspace,
)

router = APIRouter()


@router.get("/api/render/state")
def get_render_state(w: Workspace = Depends(require_workspace)) -> dict[str, Any]:
    snap = w.render_store.snapshot()
    snap["workspace_id"] = w.id
    return snap


@router.get("/api/render/tops")
def get_render_tops(w: Workspace = Depends(require_workspace)) -> dict[str, Any]:
    return {"tops": w.render_store.state.get("tops") or []}


@router.post("/api/render/tops/request")
async def request_render_tops(w: Workspace = Depends(require_workspace)) -> dict[str, Any]:
    w.pending_render_cmds.append({"type": "list_render_tops"})
    _shm_push_cmd(w, CMD_LIST_TOPS)
    await hub.send_td(w, {"type": "list_render_tops"})
    return {"ok": True}


@router.get("/api/render/pending")
def get_render_pending(w: Workspace = Depends(require_workspace)) -> dict[str, Any]:
    mark_td_seen(w)
    items = list(w.pending_render_cmds)
    w.pending_render_cmds.clear()
    return {"items": items}


@router.put("/api/render/tops")
async def put_render_tops(
    body: dict[str, Any], w: Workspace = Depends(require_workspace)
) -> dict[str, Any]:
    mark_td_seen(w)
    tops = body.get("tops") if isinstance(body, dict) else None
    if not isinstance(tops, list):
        raise HTTPException(400, "tops must be a list")
    snap = w.render_store.set_tops(tops)
    await hub.broadcast_msg(
        {"type": "render_patch", "workspace_id": w.id, "tops": snap["tops"]},
        to_role="ui",
    )
    return snap


@router.post("/api/render/refresh")
async def refresh_render(
    body: dict[str, Any], w: Workspace = Depends(require_workspace)
) -> dict[str, Any]:
    path = str((body or {}).get("path") or (body or {}).get("render_path") or "")
    if not path:
        raise HTTPException(400, "path required")
    w.render_store.state["render_path"] = path
    msg = {"type": "render_snapshot", "path": path}
    w.pending_render_cmds.append(msg)
    _shm_push_cmd(w, CMD_SNAPSHOT, path.encode("utf-8"))
    await hub.send_td(w, msg)
    return {"ok": True, "path": path}


@router.post("/api/render/preview/request")
async def request_render_preview(
    body: dict[str, Any], w: Workspace = Depends(require_workspace)
) -> dict[str, Any]:
    path = str((body or {}).get("path") or (body or {}).get("render_path") or "")
    if not path:
        path = str(w.render_store.state.get("render_path") or "")
    if not path:
        raise HTTPException(400, "path required")
    kicked = w.render_store.request_preview(path)
    if kicked:
        msg = {"type": "render_preview", "path": path}
        w.pending_render_cmds.append(msg)
        _shm_push_cmd(w, CMD_PREVIEW, path.encode("utf-8"))
        await hub.send_td(w, msg)
    return {"ok": True, "path": path, "kicked": kicked, **w.render_store.preview_meta()}


@router.put("/api/render/preview")
async def put_render_preview(
    request: Request,
    w: Workspace = Depends(require_workspace),
    path: str = Query(""),
    x_render_path: Optional[str] = Header(None, alias="X-Render-Path"),
) -> dict[str, Any]:
    mark_td_seen(w)
    jpeg = await request.body()
    if not jpeg:
        raise HTTPException(400, "empty body")
    rpath = str(x_render_path or path or w.render_store.preview_path or "")
    return w.render_store.put_preview(jpeg, rpath)


@router.get("/api/render/preview")
def get_render_preview(
    w: Workspace = Depends(require_workspace),
    if_none_match: Optional[str] = Header(None, alias="If-None-Match"),
) -> Response:
    store = w.render_store
    raw = store.preview_jpeg
    if not raw:
        return Response(status_code=204)
    etag = store.preview_etag or ""
    inm = (if_none_match or "").strip().strip('"')
    if etag and inm and inm == etag:
        return Response(status_code=304, headers={"ETag": f'"{etag}"'})
    return Response(
        content=raw,
        media_type="image/jpeg",
        headers={
            "ETag": f'"{etag}"',
            "Cache-Control": "no-store",
            "X-Render-Path": store.preview_path or "",
        },
    )


@router.put("/api/render/scene")
async def put_render_scene(
    body: dict[str, Any], w: Workspace = Depends(require_workspace)
) -> dict[str, Any]:
    mark_td_seen(w)
    snap = w.render_store.set_scene(body if isinstance(body, dict) else {})
    # Skip UI broadcast when Auto-refresh / Refresh produced an identical plate —
    # avoids selection flicker and Three remounts.
    if not w.render_store.last_scene_noop:
        await _broadcast_render_state(w)
    return snap


@router.patch("/api/render/objects/{oid}")
async def patch_render_object(
    oid: str, body: dict[str, Any], w: Workspace = Depends(require_workspace)
) -> dict[str, Any]:
    if "trs" not in (body or {}):
        raise HTTPException(400, "trs required")
    try:
        obj = w.render_store.patch_trs(oid, body["trs"], undoable=True)
    except KeyError:
        raise HTTPException(404, f"render object {oid} not found") from None
    await _emit_set_object_trs(w, oid, obj)
    await hub.broadcast_msg(
        {
            "type": "render_patch",
            "workspace_id": w.id,
            "objects": {oid: obj},
            "selection": w.render_store.state["selection"],
        },
        to_role="ui",
    )
    return obj


@router.post("/api/render/selection")
async def set_render_selection(
    body: dict[str, Any], w: Workspace = Depends(require_workspace)
) -> dict[str, Any]:
    ids = body.get("ids") or []
    if not isinstance(ids, list):
        raise HTTPException(400, "ids must be a list")
    w.render_store.set_selection([str(i) for i in ids])
    await hub.broadcast_msg(
        {
            "type": "render_patch",
            "workspace_id": w.id,
            "selection": w.render_store.state["selection"],
        },
        to_role="ui",
    )
    return {"selection": w.render_store.state["selection"]}


@router.post("/api/render/undo")
async def render_undo(w: Workspace = Depends(require_workspace)) -> dict[str, Any]:
    if not w.render_store.undo():
        return {"ok": False, "reason": "empty", **w.render_store.snapshot()}
    for oid, obj in w.render_store.state["objects"].items():
        await _emit_set_object_trs(w, oid, obj)
    await _broadcast_render_state(w)
    return {"ok": True, **w.render_store.snapshot()}


@router.post("/api/render/redo")
async def render_redo(w: Workspace = Depends(require_workspace)) -> dict[str, Any]:
    if not w.render_store.redo():
        return {"ok": False, "reason": "empty", **w.render_store.snapshot()}
    for oid, obj in w.render_store.state["objects"].items():
        await _emit_set_object_trs(w, oid, obj)
    await _broadcast_render_state(w)
    return {"ok": True, **w.render_store.snapshot()}


@router.post("/api/render/status")
async def post_render_status(
    body: dict[str, Any], w: Workspace = Depends(require_workspace)
) -> dict[str, Any]:
    mark_td_seen(w)
    status = str((body or {}).get("status") or "")
    snap = w.render_store.set_status(status)
    await hub.broadcast_msg(
        {"type": "render_patch", "workspace_id": w.id, "status": snap["status"]},
        to_role="ui",
    )
    return snap


@router.post("/api/render/proxies/request")
async def request_render_proxies(
    body: dict[str, Any] | None = None, w: Workspace = Depends(require_workspace)
) -> dict[str, Any]:
    ids = (body or {}).get("ids") if isinstance(body, dict) else None
    msg: dict[str, Any] = {"type": "render_cook_proxies"}
    payload = b""
    if isinstance(ids, list):
        msg["ids"] = [str(i) for i in ids]
        payload = "\0".join(msg["ids"]).encode("utf-8")
    w.pending_render_cmds.append(msg)
    _shm_push_cmd(w, CMD_COOK_PROXIES, payload)
    await hub.send_td(w, msg)
    return {"ok": True}


@router.put("/api/render/objects/{oid}/proxy")
async def put_render_proxy(
    oid: str,
    file: UploadFile = File(...),
    fingerprint: str = Form(""),
    verts: int = Form(0),
    tris: int = Form(0),
    w: Workspace = Depends(require_workspace),
) -> dict[str, Any]:
    mark_td_seen(w)
    obj = w.render_store.state["objects"].get(oid)
    if obj is None:
        raise HTTPException(404, f"render object {oid} not found")
    if obj.get("kind") != "geo":
        raise HTTPException(400, "proxy only for geo")
    data = await file.read()
    if len(data) < 12 or data[:4] != b"glTF":
        raise HTTPException(400, "not a GLB (missing glTF magic)")
    prev = obj.get("proxy") or {}
    rev = int(prev.get("rev") or 0) + 1
    persistence.write_render_proxy_bytes(w.id, oid, data)
    meta = {
        "format": "glb",
        "url": _render_proxy_url(oid, w.id),
        "fingerprint": fingerprint or str(prev.get("fingerprint") or ""),
        "verts": int(verts),
        "tris": int(tris),
        "rev": rev,
    }
    updated = w.render_store.set_proxy_meta(oid, meta)
    await hub.broadcast_msg(
        {
            "type": "render_patch",
            "workspace_id": w.id,
            "objects": {oid: updated},
            "selection": w.render_store.state["selection"],
            "status": w.render_store.state.get("status") or "",
        },
        to_role="ui",
    )
    return updated or {}


@router.get("/api/render/objects/{oid}/proxy.glb")
def get_render_proxy_glb(oid: str, w: Workspace = Depends(require_workspace)) -> Response:
    obj = w.render_store.state["objects"].get(oid)
    if obj is None:
        raise HTTPException(404, f"render object {oid} not found")
    raw = persistence.read_render_proxy_bytes(w.id, oid)
    if raw is None:
        raise HTTPException(404, "proxy file missing")
    return Response(content=raw, media_type="model/gltf-binary")


@router.delete("/api/render/objects/{oid}/proxy")
async def delete_render_proxy(
    oid: str, w: Workspace = Depends(require_workspace)
) -> dict[str, Any]:
    obj = w.render_store.state["objects"].get(oid)
    if obj is None:
        raise HTTPException(404, f"render object {oid} not found")
    persistence.delete_render_proxy_file(w.id, oid)
    updated = w.render_store.set_proxy_meta(oid, None)
    await hub.broadcast_msg(
        {
            "type": "render_patch",
            "workspace_id": w.id,
            "objects": {oid: updated},
            "selection": w.render_store.state["selection"],
        },
        to_role="ui",
    )
    return {"ok": True, "id": oid}
