"""Single-producer reservations over the qualified OS-semaphore fixed ring.

Reservations never advance write position before complete cells are committed.
Process death loses abandoned credits;no recovery/reclamation is attempted.
"""
from .grounded_mailbox import ScalarMailbox, CELL_BYTES


class ReservedMailbox(ScalarMailbox):
    def reserve(self, count):
        if type(count) is not int or not 1 <= count <= self.slots: raise ValueError('Bounded exact reservation count')
        acquired = 0
        for _ in range(count):
            if not self._free.acquire(False):
                for _ in range(acquired): self._free.release()
                return None
            acquired += 1
        return _Reservation(self, count)


class _Reservation:
    def __init__(self, mailbox, count):
        self.mailbox, self.remaining, self.closed = mailbox, count, False

    def commit(self, cell):
        if self.closed or not self.remaining or type(cell) is not bytes or len(cell) != CELL_BYTES:
            raise ValueError('Live reserved complete fixed cell required')
        mailbox = self.mailbox
        start = mailbox._write*CELL_BYTES
        memoryview(mailbox._storage).cast('B')[start:start+CELL_BYTES] = cell
        mailbox._write = (mailbox._write+1) % mailbox.slots
        self.remaining -= 1
        mailbox._committed.release()

    def close(self):
        if self.closed: raise ValueError('Reservation already closed')
        for _ in range(self.remaining): self.mailbox._free.release()
        self.remaining = 0; self.closed = True
