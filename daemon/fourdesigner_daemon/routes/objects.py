"""Marshal object / project SOT routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from .. import persistence
from ..runtime import (
    CMD_DESTROY,
    Workspace,
    _emit_refresh_proxy,
    _emit_set_layer,
    _emit_set_proxy_mode,
    _emit_set_trs,
    _proxy_url,
    _shm_push_cmd,
    hub,
    mark_td_seen,
    payload_destroy,
    require_workspace,
)

router = APIRouter()


@router.get("/api/state")
def get_state(w: Workspace = Depends(require_workspace)) -> dict[str, Any]:
    snap = w.store.snapshot()
    snap["workspace_id"] = w.id
    snap["project_name"] = w.project_name
    snap["project_folder"] = w.project_folder
    return snap


@router.post("/api/objects/register")
async def register_object(
    body: dict[str, Any], w: Workspace = Depends(require_workspace)
) -> dict[str, Any]:
    mark_td_seen(w)
    obj = w.store.register_object(body)
    await hub.broadcast_workspace_state(w)
    await _emit_set_trs(w, obj["id"], obj)
    return obj


@router.delete("/api/objects/{oid}")
async def delete_object(
    oid: str, destroy_td: bool = False, w: Workspace = Depends(require_workspace)
) -> dict[str, Any]:
    prev = w.store.state["objects"].get(oid)
    if prev is None:
        raise HTTPException(404, f"object {oid} not found")
    td_path = str(prev.get("td_path") or "")
    if destroy_td:
        msg = {"type": "destroy_marshal", "id": oid, "td_path": td_path}
        if not any(d.get("id") == oid for d in w.pending_destroys):
            w.pending_destroys.append({"id": oid, "td_path": td_path})
        _shm_push_cmd(w, CMD_DESTROY, payload_destroy(oid, td_path))
        if w.shm is not None and w.shm.ok:
            try:
                w.shm.release_slot(oid)
            except Exception:
                pass
        await hub.send_td(w, msg)
    w.store.unregister_object(oid)
    persistence.delete_proxy_file(w.id, oid)
    await hub.broadcast_workspace_state(w)
    return {"ok": True, "id": oid, "destroyed_td": bool(destroy_td)}


@router.get("/api/pending_destroys")
def pending_destroys(w: Workspace = Depends(require_workspace)) -> dict[str, Any]:
    mark_td_seen(w)
    items = list(w.pending_destroys)
    w.pending_destroys.clear()
    return {"items": items}


@router.post("/api/objects/prune")
async def prune_objects(
    body: dict[str, Any], w: Workspace = Depends(require_workspace)
) -> dict[str, Any]:
    mark_td_seen(w)
    raw = body.get("ids") if isinstance(body, dict) else None
    if not isinstance(raw, list):
        raise HTTPException(400, "ids must be a list")
    removed: list[str] = []
    for item in raw:
        oid = str(item)
        if w.store.unregister_object(oid):
            persistence.delete_proxy_file(w.id, oid)
            removed.append(oid)
    if removed:
        await hub.broadcast_workspace_state(w)
    return {"ok": True, "removed": removed}


@router.patch("/api/objects/{oid}")
async def patch_object(
    oid: str, body: dict[str, Any], w: Workspace = Depends(require_workspace)
) -> dict[str, Any]:
    prev = w.store.state["objects"].get(oid)
    prev_mode = (prev or {}).get("proxy_mode", "mask")
    quiet = bool(body.pop("_quiet", False)) if isinstance(body, dict) else False
    if quiet and set(body.keys()) <= {"bounds", "proxy_mode"}:
        mark_td_seen(w)
        obj = None
        if "bounds" in body:
            obj = w.store.set_bounds_quiet(oid, body["bounds"])
        if "proxy_mode" in body:
            obj = w.store.set_proxy_mode_quiet(oid, body["proxy_mode"])
        if obj is None:
            raise HTTPException(404, f"object {oid} not found")
        if prev_mode == "mesh" and obj.get("proxy_mode") == "mask":
            persistence.delete_proxy_file(w.id, oid)
        await hub.broadcast_msg(
            {
                "type": "project_patch",
                "workspace_id": w.id,
                "objects": {oid: obj},
                "selection": w.store.state["selection"],
            },
            to_role="ui",
        )
        return obj
    try:
        obj = w.store.patch_object(oid, body, undoable=True)
    except KeyError:
        raise HTTPException(404, f"object {oid} not found") from None
    if prev_mode == "mesh" and obj.get("proxy_mode") == "mask":
        persistence.delete_proxy_file(w.id, oid)
        obj = w.store.set_proxy_meta(oid, None) or obj
    if "trs" in body:
        await _emit_set_trs(w, oid, obj)
    if "layer" in body:
        await _emit_set_layer(w, oid, obj)
    if "proxy_mode" in body:
        await _emit_set_proxy_mode(w, oid, obj)
        if obj.get("proxy_mode") == "mesh":
            await _emit_refresh_proxy(w, oid, obj)
    await hub.broadcast_workspace_state(w)
    return obj


@router.post("/api/objects/proxies/request")
async def request_object_proxies(
    body: dict[str, Any] | None = None, w: Workspace = Depends(require_workspace)
) -> dict[str, Any]:
    raw = (body or {}).get("ids") if isinstance(body, dict) else None
    ids: list[str]
    if isinstance(raw, list) and raw:
        ids = [str(i) for i in raw]
    else:
        ids = [
            oid
            for oid, o in w.store.state["objects"].items()
            if isinstance(o, dict) and o.get("proxy_mode") == "mesh"
        ]
    n = 0
    for oid in ids:
        obj = w.store.state["objects"].get(oid)
        if not isinstance(obj, dict):
            continue
        if obj.get("proxy_mode") != "mesh":
            obj = w.store.set_proxy_mode_quiet(oid, "mesh") or obj
            await _emit_set_proxy_mode(w, oid, obj)
        await _emit_refresh_proxy(w, oid, obj)
        n += 1
    if n:
        await hub.broadcast_workspace_state(w)
    return {"ok": True, "count": n}


@router.get("/api/objects/proxies/pending")
def pending_object_proxies(w: Workspace = Depends(require_workspace)) -> dict[str, Any]:
    mark_td_seen(w)
    items = list(w.pending_proxy_cmds)
    w.pending_proxy_cmds.clear()
    return {"items": items}


@router.put("/api/objects/{oid}/proxy")
async def put_proxy(
    oid: str,
    file: UploadFile = File(...),
    fingerprint: str = Form(""),
    verts: int = Form(0),
    tris: int = Form(0),
    w: Workspace = Depends(require_workspace),
) -> dict[str, Any]:
    mark_td_seen(w)
    obj = w.store.state["objects"].get(oid)
    if obj is None:
        raise HTTPException(404, f"object {oid} not found")
    if obj.get("proxy_mode") != "mesh":
        raise HTTPException(400, "proxy upload rejected: proxy_mode is mask")
    data = await file.read()
    if len(data) < 12 or data[:4] != b"glTF":
        raise HTTPException(400, "not a GLB (missing glTF magic)")
    prev = obj.get("proxy") or {}
    rev = int(prev.get("rev") or 0) + 1
    persistence.write_proxy_bytes(w.id, oid, data)
    meta = {
        "format": "glb",
        "url": _proxy_url(oid, w.id),
        "fingerprint": fingerprint or str(prev.get("fingerprint") or ""),
        "verts": int(verts),
        "tris": int(tris),
        "rev": rev,
    }
    updated = w.store.set_proxy_meta(oid, meta)
    await hub.broadcast_msg(
        {
            "type": "project_patch",
            "workspace_id": w.id,
            "objects": {oid: updated},
            "selection": w.store.state["selection"],
        },
        to_role="ui",
    )
    return updated or {}


@router.get("/api/objects/{oid}/proxy.glb")
def get_proxy_glb(oid: str, w: Workspace = Depends(require_workspace)) -> Response:
    obj = w.store.state["objects"].get(oid)
    if obj is None:
        raise HTTPException(404, f"object {oid} not found")
    raw = persistence.read_proxy_bytes(w.id, oid)
    if raw is None:
        raise HTTPException(404, "proxy file missing")
    return Response(content=raw, media_type="model/gltf-binary")


@router.delete("/api/objects/{oid}/proxy")
async def delete_proxy(oid: str, w: Workspace = Depends(require_workspace)) -> dict[str, Any]:
    obj = w.store.state["objects"].get(oid)
    if obj is None:
        raise HTTPException(404, f"object {oid} not found")
    persistence.delete_proxy_file(w.id, oid)
    updated = w.store.set_proxy_meta(oid, None)
    await hub.broadcast_msg(
        {
            "type": "project_patch",
            "workspace_id": w.id,
            "objects": {oid: updated},
            "selection": w.store.state["selection"],
        },
        to_role="ui",
    )
    return {"ok": True, "id": oid}


@router.post("/api/undo")
async def undo(w: Workspace = Depends(require_workspace)) -> dict[str, Any]:
    if not w.store.undo():
        return {"ok": False, "reason": "empty"}
    for oid, obj in w.store.state["objects"].items():
        await _emit_set_trs(w, oid, obj)
    await hub.broadcast_workspace_state(w)
    return {"ok": True, "workspace_id": w.id, **w.store.snapshot()}


@router.post("/api/redo")
async def redo(w: Workspace = Depends(require_workspace)) -> dict[str, Any]:
    if not w.store.redo():
        return {"ok": False, "reason": "empty"}
    for oid, obj in w.store.state["objects"].items():
        await _emit_set_trs(w, oid, obj)
    await hub.broadcast_workspace_state(w)
    return {"ok": True, "workspace_id": w.id, **w.store.snapshot()}


@router.post("/api/clear")
async def clear_state(w: Workspace = Depends(require_workspace)) -> dict[str, Any]:
    for oid in list(w.store.state["objects"].keys()):
        persistence.delete_proxy_file(w.id, oid)
    w.store.clear()
    await hub.broadcast_workspace_state(w)
    snap = w.store.snapshot()
    snap["workspace_id"] = w.id
    return snap


@router.patch("/api/layers/{layer_id}")
async def patch_layer(
    layer_id: str, body: dict[str, Any], w: Workspace = Depends(require_workspace)
) -> dict[str, Any]:
    try:
        layer = int(layer_id)
    except ValueError as e:
        raise HTTPException(400, "layer id must be int") from e
    layer_obj = w.store.set_layer_meta(
        layer,
        name=body.get("name"),
        visible=body.get("visible"),
    )
    await hub.broadcast_workspace_state(w)
    return layer_obj


@router.post("/api/selection")
async def set_selection(
    body: dict[str, Any], w: Workspace = Depends(require_workspace)
) -> dict[str, Any]:
    ids = body.get("ids") or []
    if not isinstance(ids, list):
        raise HTTPException(400, "ids must be a list")
    w.store.set_selection([str(i) for i in ids])
    await hub.broadcast_msg(
        {
            "type": "project_patch",
            "workspace_id": w.id,
            "selection": w.store.state["selection"],
        },
        to_role="ui",
    )
    return {"selection": w.store.state["selection"]}
