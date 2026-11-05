"""Single-owner four-lane reservations and O(1) tagged-prefix acknowledgements.

No clock, exposure, bank graph, filesystem, transport or numerical calculation.
"""
from dataclasses import dataclass
from .episode_types import integer, exact, choice

LANES = ('R', 'T', 'A', 'C')
REGULAR_PHYSICAL_RESERVE = 6
TERMINAL_PHYSICAL_RESERVE = 7
APPLICATION_RESERVE = 1
REGULAR_CONTROL_RESERVE = 10
EMERGENCY_CONTROL_RESERVE = 8

# Normative complete emission inventory, frozen before state-machine source.
CONTROL_SITES = (
    ('lease_changed', 2, 1),
    ('disposition', 3, 3),
    ('target_retired', 1, 1),
    ('session_ended', 1, 1),
    ('geometry_configured', 1, 0),
    ('interlock_latched', 1, 1),
)


@dataclass(frozen=True)
class EpisodeCapacity:
    regular_slots: int
    terminal_slots: int
    application_slots: int
    control_slots: int
    admission_record_slots: int
    graph_binding_slots: int

    def __post_init__(self):
        for value, minimum in ((self.regular_slots, REGULAR_PHYSICAL_RESERVE),
                (self.terminal_slots, TERMINAL_PHYSICAL_RESERVE),
                (self.application_slots, APPLICATION_RESERVE),
                (self.control_slots, REGULAR_CONTROL_RESERVE+EMERGENCY_CONTROL_RESERVE),
                (self.admission_record_slots, 3), (self.graph_binding_slots, 1)):
            integer(value, minimum)


class _Reservation:
    __slots__ = ('lane', 'remaining', 'serial')

    def __init__(self, lane, count, serial):
        self.lane, self.remaining, self.serial = lane, count, serial


class _Lane:
    __slots__ = ('capacity', 'reserved', 'emitted', 'acknowledged')

    def __init__(self, capacity):
        self.capacity = capacity
        self.reserved = self.emitted = self.acknowledged = 0

    @property
    def free(self):
        return self.capacity-self.reserved-(self.emitted-self.acknowledged)


class EpisodeCredits:
    """Actor-private credits; reservations cannot be supplied by an operator."""
    def __init__(self, capacity):
        exact(capacity, EpisodeCapacity)
        self._lanes = {key: _Lane(value) for key, value in zip(LANES, (
            capacity.regular_slots, capacity.terminal_slots,
            capacity.application_slots, capacity.control_slots))}
        size = sum(lane.capacity for lane in self._lanes.values())+1
        self._checkpoints = [None]*size
        self._reservations = {}
        self._serial = self.ordinal = self.acknowledged_ordinal = 0

    def free(self, lane):
        choice(lane, LANES)
        return self._lanes[lane].free

    def reserve(self, lane, count):
        choice(lane, LANES); integer(count, 1)
        state = self._lanes[lane]
        if count > state.free:
            return None
        self._serial += 1
        reservation = _Reservation(lane, count, self._serial)
        self._reservations[reservation.serial] = reservation
        state.reserved += count
        return reservation

    def _owned(self, reservation):
        if (type(reservation) is not _Reservation or
                self._reservations.get(reservation.serial) is not reservation):
            raise ValueError('exact live owned reservation required')
        return self._lanes[reservation.lane]

    def release(self, reservation):
        state = self._owned(reservation)
        state.reserved -= reservation.remaining
        reservation.remaining = 0
        del self._reservations[reservation.serial]

    def emit(self, reservation):
        state = self._owned(reservation)
        if reservation.remaining <= 0:
            raise ValueError('unreserved emission is forbidden')
        integer(self.ordinal+1, 1)
        reservation.remaining -= 1
        state.reserved -= 1
        state.emitted += 1
        self.ordinal += 1
        self._checkpoints[self.ordinal % len(self._checkpoints)] = (
            self.ordinal, *(self._lanes[name].emitted for name in LANES))
        return self.ordinal

    def acknowledge(self, ordinal):
        integer(ordinal)
        if ordinal > self.ordinal:
            raise ValueError('future verification acknowledgement is forbidden')
        if ordinal <= self.acknowledged_ordinal:
            return False
        checkpoint = self._checkpoints[ordinal % len(self._checkpoints)]
        if checkpoint is None or checkpoint[0] != ordinal:
            raise RuntimeError('retained advancing checkpoint was overwritten')
        for lane, count in zip(LANES, checkpoint[1:]):
            self._lanes[lane].acknowledged = count
        self.acknowledged_ordinal = ordinal
        return True

    def snapshot(self):
        return tuple((name, self._lanes[name].capacity, self._lanes[name].reserved,
            self._lanes[name].emitted, self._lanes[name].acknowledged,
            self._lanes[name].free) for name in LANES)
