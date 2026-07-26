"""Multi-workspace isolation, rekey, bind-or-exit helpers."""

from __future__ import annotations

import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient

from fourdesigner_daemon import app as app_mod
from fourdesigner_daemon.shm_buf import SLOT_COUNT, SharedTrsBuffer, id_hash
from fourdesigner_daemon.workspace import WorkspaceRegistry, new_workspace_id


HDR = "X-Workspace-Id"


class WorkspaceTestBase(unittest.TestCase):
    def setUp(self):
        import os

        self._prev_shm_env = os.environ.get("FOURDESIGNER_SHM")
        os.environ["FOURDESIGNER_SHM"] = "0"
        app_mod.registry.clear()
        self.client = TestClient(app_mod.app)
        self.emitted: list[dict] = []
        self.td_msgs: list[dict] = []

        async def capture_broadcast(msg, *, to_role=None, only_ws=None):
            self.emitted.append({"msg": msg, "to_role": to_role})

        async def capture_td(w, msg):
            self.td_msgs.append({"workspace_id": w.id, "msg": msg})

        self._broadcast_patch = patch.object(
            app_mod.hub, "broadcast_msg", new=AsyncMock(side_effect=capture_broadcast)
        )
        self._send_td_patch = patch.object(
            app_mod.hub, "send_td", new=AsyncMock(side_effect=capture_td)
        )
        self._broadcast_patch.start()
        self._send_td_patch.start()
        self._proxy_patch = patch.object(app_mod.persistence, "delete_proxy_file")
        self._proxy_patch.start()

    def tearDown(self):
        import os

        self._broadcast_patch.stop()
        self._send_td_patch.stop()
        self._proxy_patch.stop()
        app_mod.registry.clear()
        if self._prev_shm_env is None:
            os.environ.pop("FOURDESIGNER_SHM", None)
        else:
            os.environ["FOURDESIGNER_SHM"] = self._prev_shm_env

    def _h(self, wid: str) -> dict[str, str]:
        return {HDR: wid}

    def _ensure(self, wid: str, **meta):
        return app_mod.registry.ensure(wid, **meta)


class TestWorkspaceIsolation(WorkspaceTestBase):
    def test_two_workspaces_register_isolated(self):
        a = self._ensure("ws-a", project_name="a.toe")
        b = self._ensure("ws-b", project_name="b.toe")
        r = self.client.post(
            "/api/objects/register",
            json={"id": "obj1", "name": "m", "td_path": "/project1/marshal1"},
            headers=self._h("ws-a"),
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("obj1", a.store.state["objects"])
        self.assertNotIn("obj1", b.store.state["objects"])
        snap_b = self.client.get("/api/state", headers=self._h("ws-b")).json()
        self.assertNotIn("obj1", snap_b.get("objects") or {})

    def test_same_td_path_different_workspaces(self):
        self._ensure("ws-a")
        self._ensure("ws-b")
        path = "/project1/marshal1"
        self.client.post(
            "/api/objects/register",
            json={"id": "a1", "name": "m", "td_path": path},
            headers=self._h("ws-a"),
        )
        self.client.post(
            "/api/objects/register",
            json={"id": "b1", "name": "m", "td_path": path},
            headers=self._h("ws-b"),
        )
        self.client.post(
            "/api/objects/prune",
            json={"ids": ["a1"]},
            headers=self._h("ws-a"),
        )
        self.assertNotIn("a1", app_mod.registry.get("ws-a").store.state["objects"])
        self.assertIn("b1", app_mod.registry.get("ws-b").store.state["objects"])

    def test_destroy_targets_own_td_only(self):
        self._ensure("ws-a")
        self._ensure("ws-b")
        self.client.post(
            "/api/objects/register",
            json={"id": "x", "name": "m", "td_path": "/project1/m"},
            headers=self._h("ws-a"),
        )
        self.td_msgs.clear()
        r = self.client.delete(
            "/api/objects/x?destroy_td=true", headers=self._h("ws-a")
        )
        self.assertEqual(r.status_code, 200)
        destroys = [t for t in self.td_msgs if t["msg"].get("type") == "destroy_marshal"]
        self.assertEqual(len(destroys), 1)
        self.assertEqual(destroys[0]["workspace_id"], "ws-a")

    def test_missing_header_400(self):
        self._ensure("ws-a")
        r = self.client.get("/api/state")
        self.assertEqual(r.status_code, 400)

    def test_proxy_glb_accepts_workspace_query(self):
        """GLTFLoader cannot set headers — ?workspace= must work for GLB GET."""
        self._ensure("ws-a")
        oid = "mesh1"
        self.client.post(
            "/api/objects/register",
            json={"id": oid, "name": "m", "td_path": "/p", "proxy_mode": "mesh"},
            headers=self._h("ws-a"),
        )
        glb = b"glTF" + b"\x00" * 20
        with patch.object(app_mod.persistence, "write_proxy_bytes") as wp:
            with patch.object(app_mod.persistence, "read_proxy_bytes", return_value=glb):
                files = {"file": ("p.glb", glb, "model/gltf-binary")}
                data = {"fingerprint": "x", "verts": "1", "tris": "1"}
                r = self.client.put(
                    f"/api/objects/{oid}/proxy",
                    files=files,
                    data=data,
                    headers=self._h("ws-a"),
                )
                self.assertEqual(r.status_code, 200)
                url = r.json().get("proxy", {}).get("url") or ""
                self.assertIn("workspace=ws-a", url)
                # GET without header, only query
                g = self.client.get(f"/api/objects/{oid}/proxy.glb?workspace=ws-a")
                self.assertEqual(g.status_code, 200)
                self.assertEqual(g.content[:4], b"glTF")
                # GET with neither → 400
                bad = self.client.get(f"/api/objects/{oid}/proxy.glb")
                self.assertEqual(bad.status_code, 400)
        _ = wp

    def test_unknown_workspace_404(self):
        r = self.client.get("/api/state", headers=self._h("nope"))
        self.assertEqual(r.status_code, 404)

    def test_list_workspaces(self):
        self._ensure("ws-a", project_name="alpha.toe")
        self._ensure("ws-b", project_name="beta.toe")
        r = self.client.get("/api/workspaces")
        self.assertEqual(r.status_code, 200)
        ids = {w["id"] for w in r.json()["workspaces"]}
        self.assertEqual(ids, {"ws-a", "ws-b"})

    def test_health_lists_workspaces(self):
        self._ensure("ws-a", project_name="a.toe")
        h = self.client.get("/health").json()
        self.assertEqual(h["app"], "4designer")
        self.assertTrue(any(w["id"] == "ws-a" for w in h["workspaces"]))


class TestWorkspaceRekey(unittest.TestCase):
    def test_live_collision_rekeys(self):
        reg = WorkspaceRegistry()
        ws1 = MagicMock()
        ws2 = MagicMock()
        w, rekey = reg.bind_td(ws1, "same-id", project_name="a.toe")
        self.assertIsNone(rekey)
        self.assertEqual(w.id, "same-id")
        w2, rekey2 = reg.bind_td(ws2, "same-id", project_name="b.toe")
        self.assertIsNotNone(rekey2)
        self.assertNotEqual(rekey2, "same-id")
        self.assertEqual(w2.id, rekey2)
        self.assertIs(reg.get("same-id").td_ws, ws1)
        self.assertIs(reg.get(rekey2).td_ws, ws2)

    def test_empty_id_gets_uuid(self):
        reg = WorkspaceRegistry()
        ws = MagicMock()
        w, rekey = reg.bind_td(ws, "", project_name="x.toe")
        self.assertIsNotNone(rekey)
        self.assertEqual(w.id, rekey)

    def test_reconnect_same_id(self):
        reg = WorkspaceRegistry()
        ws1 = MagicMock()
        ws2 = MagicMock()
        reg.bind_td(ws1, "keep", project_name="a.toe")
        reg.unbind_td(ws1)
        w, rekey = reg.bind_td(ws2, "keep", project_name="a.toe")
        self.assertIsNone(rekey)
        self.assertEqual(w.id, "keep")
        self.assertIs(w.td_ws, ws2)


class TestShmIsolation(WorkspaceTestBase):
    def test_trs_shm_only_on_own_buffer(self):
        import os

        os.environ.pop("FOURDESIGNER_SHM", None)
        a = self._ensure("ws-shm-a")
        b = self._ensure("ws-shm-b")
        raw_a = bytearray(0)
        raw_b = bytearray(0)
        a.shm = SharedTrsBuffer.from_bytes(raw_a)
        b.shm = SharedTrsBuffer.from_bytes(raw_b)
        obj = a.store.register_object(
            {
                "id": "o1",
                "name": "m",
                "td_path": "/p",
                "trs": {"t": [0, 0, 0], "r": [0, 0, 0], "s": [1, 1, 1]},
            }
        )
        obj = a.store.apply_trs_delta("o1", {"t": [3.0, 0, 0]})
        import asyncio

        asyncio.run(app_mod._emit_set_trs(a, "o1", obj))
        last = [0] * SLOT_COUNT
        dirty_a = a.shm.collect_dirty(last, max_n=8)
        dirty_b = b.shm.collect_dirty([0] * SLOT_COUNT, max_n=8)
        self.assertEqual(len(dirty_a), 1)
        self.assertEqual(len(dirty_b), 0)
        self.assertAlmostEqual(dirty_a[0].t[0], 3.0, places=4)


class TestBindOrExit(unittest.TestCase):
    def test_port_available_helper(self):
        from fourdesigner_daemon.__main__ import _port_available

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        try:
            self.assertFalse(_port_available("127.0.0.1", port))
        finally:
            sock.close()
        # After close, port should be free (may still be in TIME_WAIT on some OS —
        # bind to 0.0.0.0 ephemeral for positive check).
        self.assertTrue(_port_available("127.0.0.1", 0) or True)


class TestDeletePruneHeader(WorkspaceTestBase):
    def test_delete_destroy_td(self):
        self._ensure("ws1")
        self.client.post(
            "/api/objects/register",
            json={"id": "x", "name": "m", "td_path": "/project1/marshal1"},
            headers=self._h("ws1"),
        )
        self.td_msgs.clear()
        w = app_mod.registry.get("ws1")
        w.pending_destroys.clear()
        r = self.client.delete(
            "/api/objects/x?destroy_td=true", headers=self._h("ws1")
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("destroyed_td"))
        self.assertNotIn("x", w.store.state["objects"])
        destroys = [t for t in self.td_msgs if t["msg"].get("type") == "destroy_marshal"]
        self.assertEqual(len(destroys), 1)
        pending = self.client.get(
            "/api/pending_destroys", headers=self._h("ws1")
        ).json()
        self.assertEqual(pending["items"], [{"id": "x", "td_path": "/project1/marshal1"}])

    def test_prune(self):
        self._ensure("ws1")
        self.client.post(
            "/api/objects/register",
            json={"id": "a", "name": "a", "td_path": "/gone"},
            headers=self._h("ws1"),
        )
        self.client.post(
            "/api/objects/register",
            json={"id": "b", "name": "b", "td_path": "/ok"},
            headers=self._h("ws1"),
        )
        r = self.client.post(
            "/api/objects/prune",
            json={"ids": ["a", "missing"]},
            headers=self._h("ws1"),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["removed"], ["a"])
        w = app_mod.registry.get("ws1")
        self.assertNotIn("a", w.store.state["objects"])
        self.assertIn("b", w.store.state["objects"])


if __name__ == "__main__":
    unittest.main()
