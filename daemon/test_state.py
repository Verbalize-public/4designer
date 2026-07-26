"""Unit tests for 4designer StateStore (no server required)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fourdesigner_daemon.state import StateStore, normalize_trs


def test_register_and_patch():
    s = StateStore()
    obj = s.register_object(
        {
            "id": "abc",
            "name": "m1",
            "layer": 0,
            "td_path": "/project1/marshal1",
        }
    )
    assert obj["id"] == "abc"
    assert "abc" in s.state["objects"]
    patched = s.patch_object("abc", {"trs": {"t": [1, 0, 0], "r": [0, 0, 0], "s": [1, 1, 1]}})
    assert patched["trs"]["t"] == [1.0, 0.0, 0.0]


def test_undo_redo():
    s = StateStore()
    s.register_object({"id": "a", "name": "a", "td_path": "/x"})
    s.patch_object("a", {"trs": {"t": [2, 0, 0], "r": [0, 0, 0], "s": [1, 1, 1]}})
    assert s.state["objects"]["a"]["trs"]["t"][0] == 2.0
    assert s.undo()
    assert s.state["objects"]["a"]["trs"]["t"][0] == 0.0
    assert s.redo()
    assert s.state["objects"]["a"]["trs"]["t"][0] == 2.0


def test_delta_not_undoable():
    s = StateStore()
    s.register_object({"id": "a", "name": "a", "td_path": "/x"})
    s.apply_trs_delta("a", {"t": [3, 0, 0], "r": [0, 0, 0], "s": [1, 1, 1]})
    assert s.state["objects"]["a"]["trs"]["t"][0] == 3.0
    assert not s.undo()  # no undo entry from delta


def test_layer_visibility():
    s = StateStore()
    s.register_object({"id": "a", "name": "a", "layer": 1, "td_path": "/x"})
    assert "1" in s.state["layers"]
    s.set_layer_visible(1, False)
    assert s.state["layers"]["1"]["visible"] is False


def test_normalize_trs():
    trs = normalize_trs({"t": [1, 2], "r": None})
    assert trs["t"] == [0.0, 0.0, 0.0]  # invalid length → default
    trs2 = normalize_trs({"t": [1, 2, 3]})
    assert trs2["t"] == [1.0, 2.0, 3.0]


def test_unregister():
    s = StateStore()
    s.register_object({"id": "a", "name": "a", "td_path": "/x"})
    s.set_selection(["a"])
    assert s.unregister_object("a")
    assert "a" not in s.state["objects"]
    assert s.state["selection"] == []


if __name__ == "__main__":
    test_register_and_patch()
    test_undo_redo()
    test_delta_not_undoable()
    test_layer_visibility()
    test_normalize_trs()
    test_unregister()
    print("ok")
