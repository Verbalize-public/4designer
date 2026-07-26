"""Unit tests for DELETE destroy_td + POST /api/objects/prune (TestClient)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient

from fourdesigner_daemon import app as app_mod

HDR = {"X-Workspace-Id": "ws-test"}


class TestDeletePrune(unittest.TestCase):
    def setUp(self):
        import os

        self._prev_shm_env = os.environ.get("FOURDESIGNER_SHM")
        os.environ["FOURDESIGNER_SHM"] = "0"
        app_mod.registry.clear()
        self.w = app_mod.registry.ensure("ws-test")
        self.client = TestClient(app_mod.app)
        self.td_msgs: list[dict] = []

        async def capture_td(w, msg):
            self.td_msgs.append({"msg": msg, "workspace_id": w.id})

        self._send_td_patch = patch.object(
            app_mod.hub, "send_td", new=AsyncMock(side_effect=capture_td)
        )
        self._send_td_patch.start()
        self._proxy_patch = patch.object(app_mod.persistence, "delete_proxy_file")
        self._proxy_patch.start()

    def tearDown(self):
        import os

        self._send_td_patch.stop()
        self._proxy_patch.stop()
        app_mod.registry.clear()
        if self._prev_shm_env is None:
            os.environ.pop("FOURDESIGNER_SHM", None)
        else:
            os.environ["FOURDESIGNER_SHM"] = self._prev_shm_env

    def test_delete_destroy_td_emits_before_gone(self):
        self.client.post(
            "/api/objects/register",
            json={"id": "x", "name": "m", "td_path": "/project1/marshal1"},
            headers=HDR,
        )
        self.w.pending_destroys.clear()
        self.td_msgs.clear()
        r = self.client.delete("/api/objects/x?destroy_td=true", headers=HDR)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body.get("destroyed_td"))
        self.assertNotIn("x", self.w.store.state["objects"])
        destroy_msgs = [
            e for e in self.td_msgs if e["msg"].get("type") == "destroy_marshal"
        ]
        self.assertEqual(len(destroy_msgs), 1)
        self.assertEqual(destroy_msgs[0]["msg"]["td_path"], "/project1/marshal1")
        pending = self.client.get("/api/pending_destroys", headers=HDR).json()
        self.assertEqual(pending["items"], [{"id": "x", "td_path": "/project1/marshal1"}])
        self.assertEqual(
            self.client.get("/api/pending_destroys", headers=HDR).json()["items"], []
        )

    def test_delete_without_flag_no_destroy(self):
        self.client.post(
            "/api/objects/register",
            json={"id": "y", "name": "m", "td_path": "/project1/marshal2"},
            headers=HDR,
        )
        self.td_msgs.clear()
        r = self.client.delete("/api/objects/y", headers=HDR)
        self.assertEqual(r.status_code, 200)
        destroy_msgs = [
            e for e in self.td_msgs if e["msg"].get("type") == "destroy_marshal"
        ]
        self.assertEqual(destroy_msgs, [])

    def test_second_delete_404(self):
        self.client.post(
            "/api/objects/register",
            json={"id": "z", "name": "m", "td_path": "/p"},
            headers=HDR,
        )
        self.assertEqual(self.client.delete("/api/objects/z", headers=HDR).status_code, 200)
        self.assertEqual(self.client.delete("/api/objects/z", headers=HDR).status_code, 404)

    def test_prune_removes_listed(self):
        self.client.post(
            "/api/objects/register",
            json={"id": "a", "name": "a", "td_path": "/gone"},
            headers=HDR,
        )
        self.client.post(
            "/api/objects/register",
            json={"id": "b", "name": "b", "td_path": "/ok"},
            headers=HDR,
        )
        r = self.client.post(
            "/api/objects/prune", json={"ids": ["a", "missing"]}, headers=HDR
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["removed"], ["a"])
        self.assertNotIn("a", self.w.store.state["objects"])
        self.assertIn("b", self.w.store.state["objects"])


if __name__ == "__main__":
    unittest.main()
