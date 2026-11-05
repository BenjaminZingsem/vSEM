"""Launcher-owned SPSC fixed cells,using actual OS semaphore visibility edges.

No bare shared flags,pickle bodies,queue feeder thread or blocking actor IO.
Each endpoint must have exactly one producer and one consumer. Role ownership
and process-death interlocks are supplied by the trusted launcher.
"""
import ctypes

CELL_BYTES = 4096


class ScalarMailbox:
    def __init__(self, context, slots):
        if type(slots) is not int or slots < 1:
            raise ValueError('positive trusted mailbox slot count required')
        self.slots = slots
        self._storage = context.RawArray(ctypes.c_ubyte, slots*CELL_BYTES)
        self._free = context.Semaphore(slots)
        self._committed = context.Semaphore(0)
        # These are endpoint-local indices,not shared visibility/credit flags.
        self._write = self._read = 0

    def try_put(self, cell):
        if type(cell) is not bytes or len(cell) != CELL_BYTES:
            raise ValueError('one exact complete fixed byte cell required')
        if not self._free.acquire(False):
            return False
        start = self._write*CELL_BYTES
        memoryview(self._storage).cast('B')[start:start+CELL_BYTES] = cell
        self._write = (self._write+1) % self.slots
        self._committed.release()
        return True

    def try_get(self):
        if not self._committed.acquire(False):
            return None
        start = self._read*CELL_BYTES
        cell = bytes(memoryview(self._storage).cast('B')[start:start+CELL_BYTES])
        self._read = (self._read+1) % self.slots
        self._free.release()
        return cell
