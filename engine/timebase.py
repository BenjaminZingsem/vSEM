"""Private engine clock foundation. No operator transport or clock-control route."""
from dataclasses import dataclass
import math
import time


def finite_nonnegative(value, name):
    if type(value) not in (int, float):
        raise ValueError(name + ' must be a finite nonboolean nonnegative number')
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(name + ' exceeds reference numeric range') from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(name + ' must be a finite nonboolean nonnegative number')
    return number


@dataclass(frozen=True)
class ClockStamp:
    mode: str
    simulation_s: float
    wall_elapsed_s: float
    rate: float


class SimulationClock:
    """Realtime evolves during operator/renderer waiting, without observation ticks.

    The default uses a high-resolution monotonic performance counter; Windows
    Python 3.10 time.monotonic has a 15.625 ms tick and cannot resolve 2 ms dwell.
    Decision stepping is an internal evaluator capability. The authoritative actor
    owns the clock; renderers receive immutable stamps/jobs. No public DTO grants
    authority to change its mode or advance a decision.
    """
    def __init__(self, mode='realtime', rate=1.0, initial_simulation_s=0.0, monotonic=time.perf_counter):
        if mode not in ('realtime', 'accelerated', 'decision_stepped'):
            raise ValueError('unknown clock mode')
        rate = finite_nonnegative(rate, 'rate')
        if rate == 0 or (mode != 'accelerated' and rate != 1):
            raise ValueError('only accelerated mode accepts a nonunit positive rate')
        self._mode, self._rate = mode, rate
        self._origin_simulation = finite_nonnegative(initial_simulation_s, 'initial simulation time')
        self._stepped = self._origin_simulation
        self._monotonic = monotonic
        self._origin_wall = finite_nonnegative(monotonic(), 'monotonic origin')
        self._last_wall = self._origin_wall

    def stamp(self):
        now = finite_nonnegative(self._monotonic(), 'monotonic time')
        if now < self._last_wall:
            raise RuntimeError('monotonic clock moved backwards')
        self._last_wall = now
        elapsed = now - self._origin_wall
        simulation = self._stepped if self._mode == 'decision_stepped' else self._origin_simulation + elapsed * self._rate
        if not math.isfinite(simulation):
            raise ValueError('clock overflow')
        return ClockStamp(self._mode, simulation, elapsed, self._rate)

    def advance_decision(self, delta_s):
        if self._mode != 'decision_stepped':
            raise ValueError('decision advance requires explicitly stepped mode')
        delta = finite_nonnegative(delta_s, 'decision interval')
        result = self._stepped + delta
        if not math.isfinite(result):
            raise ValueError('clock overflow')
        # Validate the wall clock before committing a decision. Rejection must
        # leave physical time unchanged, including backwards/invalid readings.
        previous = self.stamp()
        self._stepped = result
        return ClockStamp(self._mode, result, previous.wall_elapsed_s, self._rate)
