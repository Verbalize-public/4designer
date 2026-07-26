"""HTTP helpers to seed marshal/render state without TouchDesigner (e2e + smoke)."""

from __future__ import annotations

from typing import Any, Optional

DEFAULT_WS = "e2e-ws"
BASE = "http://127.0.0.1:9983"


def workspace_headers(workspace_id: str = DEFAULT_WS) -> dict[str, str]:
    return {"X-Workspace-Id": workspace_id}


def ensure_workspace(
    client,
    workspace_id: str = DEFAULT_WS,
    *,
    project_name: str = "e2e.toe",
    project_folder: str = "",
    fixture: bool = True,
) -> dict[str, Any]:
    r = client.post(
        f"{BASE}/api/workspaces",
        json={
            "id": workspace_id,
            "project_name": project_name,
            "project_folder": project_folder,
            "fixture": fixture,
            "td_connected": fixture,
        },
    )
    r.raise_for_status()
    return r.json()


def seed_marshal(
    client,
    *,
    workspace_id: str = DEFAULT_WS,
    oid: str = "e2e-seed",
    name: str = "seed_marshal",
    td_path: str = "/project1/seed",
    trs: Optional[dict] = None,
) -> dict[str, Any]:
    ensure_workspace(client, workspace_id)
    body: dict[str, Any] = {
        "id": oid,
        "name": name,
        "layer": 0,
        "td_path": td_path,
    }
    if trs is not None:
        body["trs"] = trs
    r = client.post(
        f"{BASE}/api/objects/register",
        headers=workspace_headers(workspace_id),
        json=body,
    )
    r.raise_for_status()
    return r.json()


def seed_render_scene(
    client,
    *,
    workspace_id: str = DEFAULT_WS,
    render_path: str = "/project1/render1",
    objects: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    ensure_workspace(client, workspace_id)
    if objects is None:
        objects = [
            {
                "id": "geo-seed",
                "td_path": "/project1/geo1",
                "name": "geo1",
                "kind": "geo",
                "trs": {"t": [0, 0, 0], "r": [0, 0, 0], "s": [1, 1, 1]},
                "bounds": {"min": [-0.5, -0.5, -0.5], "max": [0.5, 0.5, 0.5]},
            },
            {
                "id": "light-seed",
                "td_path": "/project1/light1",
                "name": "light1",
                "kind": "light",
                "light_type": "point",
                "trs": {"t": [0, 2, 0], "r": [0, 0, 0], "s": [1, 1, 1]},
            },
            {
                "id": "cam-seed",
                "td_path": "/project1/cam1",
                "name": "cam1",
                "kind": "camera",
            },
        ]
    r = client.put(
        f"{BASE}/api/render/scene",
        headers=workspace_headers(workspace_id),
        json={"render_path": render_path, "objects": objects},
    )
    r.raise_for_status()
    client.put(
        f"{BASE}/api/render/tops",
        headers=workspace_headers(workspace_id),
        json={"tops": [{"path": render_path, "name": render_path.rsplit("/", 1)[-1]}]},
    )
    return r.json()
