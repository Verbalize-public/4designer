"""Unit tests for SharedTrsBuffer (in-process bytearray, no OS SHM required)."""

from __future__ import annotations

import unittest

from fourdesigner_daemon.shm_buf import (
    CMD_DESTROY,
    CMD_LIST_TOPS,
    CMD_PREVIEW,
    CMD_SNAPSHOT,
    FLAG_OCCUPIED,
    FLAG_TOMBSTONE,
    MAGIC,
    SLOT_COUNT,
    TOTAL_SIZE,
    VERSION,
    SharedTrsBuffer,
    id_hash,
    parse_destroy,
    payload_destroy,
)


class ShmBufTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = bytearray(TOTAL_SIZE)
        self.buf = SharedTrsBuffer.from_bytes(self.raw)

    def test_header_magic(self) -> None:
        self.assertEqual(bytes(self.buf._buf[0:4]), MAGIC)
        self.assertEqual(self.buf._buf[4], VERSION)
        self.assertEqual(self.buf.seq_trs, 0)

    def test_id_hash_stable(self) -> None:
        self.assertEqual(id_hash("abc"), id_hash("abc"))
        self.assertNotEqual(id_hash("a"), id_hash("b"))

    def test_write_read_trs(self) -> None:
        slot = self.buf.write_trs("obj1", [1, 2, 3], [0, 90, 0], [1, 1, 1])
        self.assertGreaterEqual(slot, 0)
        self.assertEqual(self.buf.seq_trs, 1)
        last = [0] * SLOT_COUNT
        dirty = self.buf.collect_dirty(last, max_n=64)
        self.assertEqual(len(dirty), 1)
        d = dirty[0]
        self.assertEqual(d.id_hash, id_hash("obj1"))
        self.assertEqual(d.t, (1.0, 2.0, 3.0))
        self.assertEqual(d.r, (0.0, 90.0, 0.0))
        self.assertTrue(d.flags & FLAG_OCCUPIED)
        # Second collect: same gen → empty
        dirty2 = self.buf.collect_dirty(last, max_n=64)
        self.assertEqual(dirty2, [])

    def test_many_slots(self) -> None:
        for i in range(200):
            self.buf.write_trs(f"o{i}", [i, 0, 0], [0, 0, 0], [1, 1, 1])
        last = [0] * SLOT_COUNT
        got = 0
        while True:
            batch = self.buf.collect_dirty(last, max_n=64)
            if not batch:
                break
            got += len(batch)
        self.assertEqual(got, 200)

    def test_tombstone(self) -> None:
        self.buf.write_trs("x", [0, 0, 0], [0, 0, 0], [1, 1, 1])
        self.buf.release_slot("x")
        last = [0] * SLOT_COUNT
        dirty = self.buf.collect_dirty(last, max_n=64)
        self.assertEqual(dirty, [])
        found = False
        for i in range(SLOT_COUNT):
            ds = self.buf.read_slot(i)
            assert ds is not None
            if ds.flags & FLAG_TOMBSTONE:
                found = True
                break
        self.assertTrue(found)

    def test_cmd_ring(self) -> None:
        self.assertTrue(self.buf.push_cmd_str(CMD_LIST_TOPS, ""))
        self.assertTrue(self.buf.push_cmd(CMD_DESTROY, payload_destroy("a", "/p/a")))
        self.assertTrue(self.buf.push_cmd_str(CMD_SNAPSHOT, "/project1/r1"))
        self.assertTrue(self.buf.push_cmd_str(CMD_PREVIEW, "/project1/r1"))
        self.assertEqual(self.buf.seq_cmd, 4)
        cmds = self.buf.pop_cmds(max_n=16)
        self.assertEqual(len(cmds), 4)
        self.assertEqual(cmds[0].type, CMD_LIST_TOPS)
        self.assertEqual(cmds[1].type, CMD_DESTROY)
        oid, path = parse_destroy(cmds[1].payload)
        self.assertEqual(oid, "a")
        self.assertEqual(path, "/p/a")
        self.assertEqual(cmds[2].payload.decode(), "/project1/r1")
        self.assertEqual(cmds[3].type, CMD_PREVIEW)
        self.assertEqual(cmds[3].payload.decode(), "/project1/r1")
        self.assertEqual(self.buf.pop_cmds(), [])

    def test_cmd_ring_wrap(self) -> None:
        from fourdesigner_daemon.shm_buf import CMD_CAPACITY

        for i in range(CMD_CAPACITY - 1):
            self.assertTrue(self.buf.push_cmd_str(CMD_LIST_TOPS, str(i)))
        self.assertFalse(self.buf.push_cmd_str(CMD_LIST_TOPS, "full"))
        n = len(self.buf.pop_cmds(max_n=CMD_CAPACITY))
        self.assertEqual(n, CMD_CAPACITY - 1)

    def test_reject_bad_magic_open_path(self) -> None:
        # from_bytes with garbage still re-inits if magic wrong
        bad = bytearray(TOTAL_SIZE)
        bad[0:4] = b"XXXX"
        b2 = SharedTrsBuffer.from_bytes(bad)
        self.assertEqual(bytes(b2._buf[0:4]), MAGIC)


if __name__ == "__main__":
    unittest.main()
