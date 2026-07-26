"""WebSocket /ws endpoint."""

from __future__ import annotations

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from ..runtime import (
    _emit_set_object_trs,
    _emit_set_trs,
    _ensure_shm,
    hub,
    log,
    registry,
)


def register_ws(app: FastAPI) -> None:
    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        hub.clients.add(ws)
        hub.roles[ws] = "unknown"
        try:
            await ws.send_json({"type": "workspace_list", "workspaces": registry.list_meta()})
            while True:
                msg = await ws.receive_json()
                mtype = msg.get("type")
                if mtype == "hello":
                    role = str(msg.get("role") or "unknown")
                    hub.roles[ws] = role
                    if role == "td":
                        w, rekey = registry.bind_td(
                            ws,
                            str(msg.get("workspace_id") or ""),
                            project_name=str(msg.get("project_name") or ""),
                            project_folder=str(msg.get("project_folder") or ""),
                        )
                        _ensure_shm(w)
                        if rekey:
                            await ws.send_json(
                                {
                                    "type": "workspace_rekey",
                                    "workspace_id": rekey,
                                    "reason": "id_in_use" if msg.get("workspace_id") else "missing_id",
                                }
                            )
                        await hub.broadcast_workspace_list()
                        await hub.broadcast_msg(
                            {
                                "type": "project_patch",
                                "workspace_id": w.id,
                                "td_connected": True,
                            },
                            to_role="ui",
                        )
                    elif role == "ui":
                        await hub.broadcast_workspace_list()
                elif mtype == "ping":
                    await ws.send_json({"type": "pong"})
                elif mtype in (
                    "transform_delta",
                    "transform_commit",
                    "select",
                    "render_transform_delta",
                    "render_select",
                ):
                    wid = str(msg.get("workspace_id") or "").strip()
                    if not wid:
                        await ws.send_json({"type": "error", "error": "workspace_id required"})
                        continue
                    w = registry.get(wid)
                    if w is None:
                        await ws.send_json({"type": "error", "error": f"unknown workspace {wid}"})
                        continue
                    if mtype == "transform_delta":
                        oid = str(msg.get("id") or "")
                        trs = msg.get("trs") or {}
                        obj = w.store.apply_trs_delta(oid, trs)
                        if obj is None:
                            await ws.send_json({"type": "error", "error": f"unknown object {oid}"})
                            continue
                        await _emit_set_trs(w, oid, obj)
                        await hub.broadcast_msg(
                            {
                                "type": "project_patch",
                                "workspace_id": w.id,
                                "objects": {oid: obj},
                            },
                            to_role="ui",
                        )
                    elif mtype == "transform_commit":
                        oid = str(msg.get("id") or "")
                        try:
                            obj = w.store.patch_object(oid, {"trs": msg.get("trs")}, undoable=True)
                        except KeyError:
                            await ws.send_json({"type": "error", "error": f"unknown object {oid}"})
                            continue
                        await _emit_set_trs(w, oid, obj)
                        await hub.broadcast_workspace_state(w)
                    elif mtype == "select":
                        ids = msg.get("ids") or []
                        if isinstance(ids, list):
                            w.store.set_selection([str(i) for i in ids])
                            await hub.broadcast_msg(
                                {
                                    "type": "project_patch",
                                    "workspace_id": w.id,
                                    "selection": w.store.state["selection"],
                                },
                                to_role="ui",
                            )
                    elif mtype == "render_transform_delta":
                        oid = str(msg.get("id") or "")
                        trs = msg.get("trs") or {}
                        obj = w.render_store.apply_trs_delta(oid, trs)
                        if obj is None:
                            await ws.send_json(
                                {"type": "error", "error": f"unknown render object {oid}"}
                            )
                            continue
                        await _emit_set_object_trs(w, oid, obj)
                        await hub.broadcast_msg(
                            {
                                "type": "render_patch",
                                "workspace_id": w.id,
                                "objects": {oid: obj},
                            },
                            to_role="ui",
                        )
                    elif mtype == "render_select":
                        ids = msg.get("ids") or []
                        if isinstance(ids, list):
                            w.render_store.set_selection([str(i) for i in ids])
                            await hub.broadcast_msg(
                                {
                                    "type": "render_patch",
                                    "workspace_id": w.id,
                                    "selection": w.render_store.state["selection"],
                                },
                                to_role="ui",
                            )
        except WebSocketDisconnect:
            pass
        except Exception:
            log.exception("ws client error")
        finally:
            hub.clients.discard(ws)
            role = hub.roles.pop(ws, None)
            if role == "td":
                w = registry.unbind_td(ws)
                if w is not None:
                    await hub.broadcast_workspace_list()
                    hub.broadcast_from_anywhere(
                        {
                            "type": "project_patch",
                            "workspace_id": w.id,
                            "td_connected": False,
                        }
                    )
