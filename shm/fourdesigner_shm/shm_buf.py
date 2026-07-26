"""Fixed-layout shared-memory buffer for 4designer hot-path TRS + cmd doorbell.

SPSC: daemon writes, TD reads. No locks — publish via generation + seq counters.

Layout (little-endian):
  Header 256 B
  TRS slots: SLOT_COUNT × 64 B
  CMD region: 8 B (head, tail) + CMD_CAPACITY × 128 B
"""

from __future__ import annotations

import hashlib
import os
import struct
import time
from dataclasses import dataclass
from typing import Any, Iterable, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAGIC = b"FDSH"
VERSION = 1
HEADER_SIZE = 256
SLOT_COUNT = 512
SLOT_SIZE = 64
DIRTY_BYTES = SLOT_COUNT // 8  # 64
CMD_CAPACITY = 64
CMD_SLOT_SIZE = 128
CMD_HEADER_SIZE = 8  # head u32, tail u32

TRS_TABLE_OFF = HEADER_SIZE
CMD_REGION_OFF = HEADER_SIZE + SLOT_COUNT * SLOT_SIZE
TOTAL_SIZE = CMD_REGION_OFF + CMD_HEADER_SIZE + CMD_CAPACITY * CMD_SLOT_SIZE

# Header offsets
OFF_MAGIC = 0
OFF_VERSION = 4
OFF_SLOT_COUNT = 8
OFF_CMD_CAP = 12
OFF_SEQ_TRS = 16
OFF_SEQ_CMD = 24
OFF_EPOCH = 32
OFF_DIRTY = 48  # 64 bytes

# Slot offsets within each 64 B
S_ID = 0
S_GEN = 8
S_FLAGS = 12
S_T = 16
S_R = 28
S_S = 40

FLAG_OCCUPIED = 1
FLAG_TOMBSTONE = 2

CMD_DESTROY = 1
CMD_LIST_TOPS = 2
CMD_SNAPSHOT = 3
CMD_COOK_PROXIES = 4
CMD_REFRESH_PROXY = 5  # marshal GLB cook (id\0path)
CMD_PREVIEW = 6  # render TOP JPEG preview (path)

_U64 = struct.Struct("<Q")
_U32 = struct.Struct("<I")
_U16 = struct.Struct("<H")
_F3 = struct.Struct("<fff")


def shm_name(slug: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (slug or "default"))[:48]
    # Windows: Local\ prefix is session-local; multiprocessing adds its own naming.
    return f"fourdesigner_v1_{safe}"


def id_hash(oid: str) -> int:
    digest = hashlib.blake2b(oid.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "little")


def _env_shm_disabled() -> bool:
    return os.environ.get("FOURDESIGNER_SHM", "1").strip() in ("0", "false", "False", "no", "off")


@dataclass
class DirtySlot:
    slot: int
    id_hash: int
    gen: int
    flags: int
    t: tuple[float, float, float]
    r: tuple[float, float, float]
    s: tuple[float, float, float]


@dataclass
class CmdItem:
    type: int
    payload: bytes


class SharedTrsBuffer:
    """Create (daemon) or open (TD) the named shared buffer."""

    def __init__(self, buf: memoryview, *, owns_shm: Any = None, name: str = "") -> None:
        self._buf = buf
        self._owns = owns_shm
        self.name = name
        self.ok = True
        # Daemon-only free list / id map (process-local)
        self._id_to_slot: dict[str, int] = {}
        self._free: list[int] = []
        self._init_free_if_empty()

    def _init_free_if_empty(self) -> None:
        if self._id_to_slot:
            return
        # Scan occupied slots to rebuild map is TD's job; daemon starts empty free list
        # and allocates on first write. On create we zero everything so all free.
        occupied = 0
        for i in range(SLOT_COUNT):
            flags = self._read_u32(TRS_TABLE_OFF + i * SLOT_SIZE + S_FLAGS)
            if flags & FLAG_OCCUPIED and not (flags & FLAG_TOMBSTONE):
                occupied += 1
            else:
                self._free.append(i)
        if occupied == 0 and not self._free:
            self._free = list(range(SLOT_COUNT))

    # -- lifecycle ---------------------------------------------------------

    @classmethod
    def create(cls, slug: str = "default") -> Optional["SharedTrsBuffer"]:
        if _env_shm_disabled():
            return None
        try:
            from multiprocessing import shared_memory
        except ImportError:
            return None
        name = shm_name(slug)
        # Unlink stale
        try:
            old = shared_memory.SharedMemory(name=name)
            old.close()
            old.unlink()
        except FileNotFoundError:
            pass
        except Exception:
            pass
        try:
            shm = shared_memory.SharedMemory(name=name, create=True, size=TOTAL_SIZE)
        except Exception:
            # Previous daemon died without unlink, or TD still holds the name.
            # Attach and reset header (new epoch) so we remain the writer.
            try:
                existing = shared_memory.SharedMemory(name=name, create=False)
            except Exception:
                return None
            if existing.size < TOTAL_SIZE:
                existing.close()
                return None
            mv = memoryview(existing.buf)[:TOTAL_SIZE]
            mv[:] = b"\x00" * TOTAL_SIZE
            self = cls(mv, owns_shm=existing, name=name)
            self._write_header_fresh()
            self._free = list(range(SLOT_COUNT))
            self._id_to_slot.clear()
            return self
        mv = memoryview(shm.buf)[:TOTAL_SIZE]
        mv[:] = b"\x00" * TOTAL_SIZE
        self = cls(mv, owns_shm=shm, name=name)
        self._write_header_fresh()
        self._free = list(range(SLOT_COUNT))
        self._id_to_slot.clear()
        return self

    @classmethod
    def open(cls, slug: str = "default") -> Optional["SharedTrsBuffer"]:
        if _env_shm_disabled():
            return None
        try:
            from multiprocessing import shared_memory
        except ImportError:
            return None
        name = shm_name(slug)
        try:
            shm = shared_memory.SharedMemory(name=name, create=False)
        except FileNotFoundError:
            return None
        except Exception:
            return None
        if shm.size < TOTAL_SIZE:
            shm.close()
            return None
        mv = memoryview(shm.buf)[:TOTAL_SIZE]
        if bytes(mv[OFF_MAGIC : OFF_MAGIC + 4]) != MAGIC:
            shm.close()
            return None
        if mv[OFF_VERSION] != VERSION:
            shm.close()
            return None
        return cls(mv, owns_shm=shm, name=name)

    @classmethod
    def from_bytes(cls, raw: bytearray | memoryview) -> "SharedTrsBuffer":
        """In-process buffer for unit tests (no OS SHM)."""
        if isinstance(raw, bytearray):
            if len(raw) < TOTAL_SIZE:
                raw.extend(b"\x00" * (TOTAL_SIZE - len(raw)))
            mv = memoryview(raw)[:TOTAL_SIZE]
        else:
            mv = raw[:TOTAL_SIZE]
        self = cls(mv, owns_shm=None, name="test")
        if bytes(mv[OFF_MAGIC : OFF_MAGIC + 4]) != MAGIC:
            self._write_header_fresh()
            self._free = list(range(SLOT_COUNT))
        return self

    def close(self, *, unlink: bool = False) -> None:
        self.ok = False
        try:
            self._buf.release()
        except Exception:
            pass
        if self._owns is not None:
            try:
                self._owns.close()
            except Exception:
                pass
            if unlink:
                try:
                    self._owns.unlink()
                except Exception:
                    pass
            self._owns = None

    def _write_header_fresh(self) -> None:
        b = self._buf
        b[OFF_MAGIC : OFF_MAGIC + 4] = MAGIC
        b[OFF_VERSION] = VERSION
        _U32.pack_into(b, OFF_SLOT_COUNT, SLOT_COUNT)
        _U32.pack_into(b, OFF_CMD_CAP, CMD_CAPACITY)
        _U64.pack_into(b, OFF_SEQ_TRS, 0)
        _U64.pack_into(b, OFF_SEQ_CMD, 0)
        _U64.pack_into(b, OFF_EPOCH, int(time.time()) & 0xFFFFFFFFFFFFFFFF)
        b[OFF_DIRTY : OFF_DIRTY + DIRTY_BYTES] = b"\x00" * DIRTY_BYTES
        _U32.pack_into(b, CMD_REGION_OFF, 0)  # head
        _U32.pack_into(b, CMD_REGION_OFF + 4, 0)  # tail

    # -- raw helpers -------------------------------------------------------

    def _read_u32(self, off: int) -> int:
        return _U32.unpack_from(self._buf, off)[0]

    def _read_u64(self, off: int) -> int:
        return _U64.unpack_from(self._buf, off)[0]

    def _write_u32(self, off: int, v: int) -> None:
        _U32.pack_into(self._buf, off, v & 0xFFFFFFFF)

    def _write_u64(self, off: int, v: int) -> None:
        _U64.pack_into(self._buf, off, v & 0xFFFFFFFFFFFFFFFF)

    @property
    def epoch(self) -> int:
        return self._read_u64(OFF_EPOCH)

    @property
    def seq_trs(self) -> int:
        return self._read_u64(OFF_SEQ_TRS)

    @property
    def seq_cmd(self) -> int:
        return self._read_u64(OFF_SEQ_CMD)

    def _set_dirty(self, slot: int) -> None:
        byte_i = OFF_DIRTY + (slot >> 3)
        bit = 1 << (slot & 7)
        self._buf[byte_i] = self._buf[byte_i] | bit

    def _dirty_slots(self) -> list[int]:
        out: list[int] = []
        base = OFF_DIRTY
        for byte_i in range(DIRTY_BYTES):
            v = self._buf[base + byte_i]
            if not v:
                continue
            for bit in range(8):
                if v & (1 << bit):
                    out.append(byte_i * 8 + bit)
        return out

    # -- TRS write (daemon) ------------------------------------------------

    def alloc_slot(self, oid: str) -> int:
        if oid in self._id_to_slot:
            return self._id_to_slot[oid]
        if not self._free:
            raise RuntimeError("SharedTrsBuffer: no free slots")
        slot = self._free.pop()
        self._id_to_slot[oid] = slot
        return slot

    def release_slot(self, oid: str) -> None:
        slot = self._id_to_slot.pop(oid, None)
        if slot is None:
            return
        off = TRS_TABLE_OFF + slot * SLOT_SIZE
        gen = self._read_u32(off + S_GEN) + 1
        self._write_u64(off + S_ID, 0)
        self._write_u32(off + S_GEN, gen)
        self._write_u32(off + S_FLAGS, FLAG_TOMBSTONE)
        self._set_dirty(slot)
        self._write_u64(OFF_SEQ_TRS, self.seq_trs + 1)
        self._free.append(slot)

    def write_trs(
        self,
        oid: str,
        t: Iterable[float],
        r: Iterable[float],
        s: Iterable[float],
    ) -> int:
        """Write TRS for object id; returns slot index."""
        slot = self.alloc_slot(oid)
        off = TRS_TABLE_OFF + slot * SLOT_SIZE
        tt = tuple(float(x) for x in t)
        rr = tuple(float(x) for x in r)
        ss = tuple(float(x) for x in s)
        if len(tt) < 3 or len(rr) < 3 or len(ss) < 3:
            raise ValueError("trs vectors need 3 components")
        h = id_hash(oid)
        gen = self._read_u32(off + S_GEN) + 1
        if gen == 0:
            gen = 1
        self._write_u64(off + S_ID, h)
        self._write_u32(off + S_FLAGS, FLAG_OCCUPIED)
        _F3.pack_into(self._buf, off + S_T, tt[0], tt[1], tt[2])
        _F3.pack_into(self._buf, off + S_R, rr[0], rr[1], rr[2])
        _F3.pack_into(self._buf, off + S_S, ss[0], ss[1], ss[2])
        self._write_u32(off + S_GEN, gen)  # gen last as publish
        self._set_dirty(slot)
        self._write_u64(OFF_SEQ_TRS, self.seq_trs + 1)
        return slot

    def write_trs_dict(self, oid: str, trs: dict[str, Any]) -> int:
        t = trs.get("t") or [0, 0, 0]
        r = trs.get("r") or [0, 0, 0]
        s = trs.get("s") or [1, 1, 1]
        return self.write_trs(oid, t, r, s)

    # -- TRS read (TD) -----------------------------------------------------

    def read_slot(self, slot: int) -> Optional[DirtySlot]:
        if slot < 0 or slot >= SLOT_COUNT:
            return None
        off = TRS_TABLE_OFF + slot * SLOT_SIZE
        flags = self._read_u32(off + S_FLAGS)
        gen = self._read_u32(off + S_GEN)
        h = self._read_u64(off + S_ID)
        t = _F3.unpack_from(self._buf, off + S_T)
        r = _F3.unpack_from(self._buf, off + S_R)
        s = _F3.unpack_from(self._buf, off + S_S)
        return DirtySlot(slot=slot, id_hash=h, gen=gen, flags=flags, t=t, r=r, s=s)

    def collect_dirty(self, last_gen: list[int], *, max_n: int = 64) -> list[DirtySlot]:
        """Return slots whose gen > last_gen[slot], up to max_n.

        TD-local last_gen watermarks — does not clear SHM. Scans all slots
        (512 × cheap u32 compare); seq_trs doorbell avoids calling this when idle.
        """
        if len(last_gen) < SLOT_COUNT:
            last_gen.extend([0] * (SLOT_COUNT - len(last_gen)))
        out: list[DirtySlot] = []
        for slot in range(SLOT_COUNT):
            if len(out) >= max_n:
                break
            off = TRS_TABLE_OFF + slot * SLOT_SIZE
            gen = self._read_u32(off + S_GEN)
            if gen == 0 or gen == last_gen[slot]:
                continue
            flags = self._read_u32(off + S_FLAGS)
            if flags & FLAG_TOMBSTONE or not (flags & FLAG_OCCUPIED):
                last_gen[slot] = gen
                continue
            h = self._read_u64(off + S_ID)
            t = _F3.unpack_from(self._buf, off + S_T)
            r = _F3.unpack_from(self._buf, off + S_R)
            s = _F3.unpack_from(self._buf, off + S_S)
            out.append(DirtySlot(slot=slot, id_hash=h, gen=gen, flags=flags, t=t, r=r, s=s))
            last_gen[slot] = gen
        return out

    # -- CMD ring ----------------------------------------------------------

    def _cmd_head_tail(self) -> tuple[int, int]:
        return self._read_u32(CMD_REGION_OFF), self._read_u32(CMD_REGION_OFF + 4)

    def push_cmd(self, cmd_type: int, payload: bytes = b"") -> bool:
        """Enqueue command; returns False if ring full."""
        head, tail = self._cmd_head_tail()
        next_tail = (tail + 1) % CMD_CAPACITY
        if next_tail == head:
            return False
        off = CMD_REGION_OFF + CMD_HEADER_SIZE + tail * CMD_SLOT_SIZE
        raw = payload[: CMD_SLOT_SIZE - 4]
        _U16.pack_into(self._buf, off, cmd_type & 0xFFFF)
        _U16.pack_into(self._buf, off + 2, len(raw) & 0xFFFF)
        self._buf[off + 4 : off + 4 + len(raw)] = raw
        if len(raw) < CMD_SLOT_SIZE - 4:
            # zero rest optional
            pass
        self._write_u32(CMD_REGION_OFF + 4, next_tail)
        self._write_u64(OFF_SEQ_CMD, self.seq_cmd + 1)
        return True

    def push_cmd_str(self, cmd_type: int, text: str = "") -> bool:
        return self.push_cmd(cmd_type, text.encode("utf-8"))

    def pop_cmds(self, *, max_n: int = 16) -> list[CmdItem]:
        out: list[CmdItem] = []
        for _ in range(max_n):
            head, tail = self._cmd_head_tail()
            if head == tail:
                break
            off = CMD_REGION_OFF + CMD_HEADER_SIZE + head * CMD_SLOT_SIZE
            ctype = _U16.unpack_from(self._buf, off)[0]
            plen = _U16.unpack_from(self._buf, off + 2)[0]
            plen = min(plen, CMD_SLOT_SIZE - 4)
            payload = bytes(self._buf[off + 4 : off + 4 + plen])
            out.append(CmdItem(type=ctype, payload=payload))
            self._write_u32(CMD_REGION_OFF, (head + 1) % CMD_CAPACITY)
        return out


def payload_destroy(oid: str, td_path: str) -> bytes:
    # "id\0path"
    return f"{oid}\0{td_path}".encode("utf-8")


def parse_destroy(payload: bytes) -> tuple[str, str]:
    parts = payload.split(b"\0", 1)
    oid = parts[0].decode("utf-8", errors="replace")
    path = parts[1].decode("utf-8", errors="replace") if len(parts) > 1 else ""
    return oid, path
