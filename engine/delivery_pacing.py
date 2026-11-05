"""Internal pacing gate: renderer completion cannot fabricate fast acquisitions."""
from dataclasses import dataclass
import math
from .timebase import finite_nonnegative


@dataclass(frozen=True)
class DeliveryTiming:
    eligible: bool
    mode: str
    capture_start_simulation_s: float
    capture_end_simulation_s: float
    modeled_wall_duration_s: float | None
    render_ready_wall_elapsed_s: float | None
    earliest_delivery_wall_elapsed_s: float | None
    rendering_latency_s: float | None


def delivery_timing(*, mode, clock_rate, capture_start_simulation_s,
                    capture_end_simulation_s, capture_start_wall_elapsed_s,
                    now_wall_elapsed_s, now_simulation_s, render_ready_wall_elapsed_s):
    start=finite_nonnegative(capture_start_simulation_s,'capture start')
    end=finite_nonnegative(capture_end_simulation_s,'capture end')
    origin=finite_nonnegative(capture_start_wall_elapsed_s,'capture wall origin')
    now=finite_nonnegative(now_wall_elapsed_s,'current wall time')
    sim=finite_nonnegative(now_simulation_s,'current simulation time')
    rate=finite_nonnegative(clock_rate,'clock rate')
    if mode not in ('realtime','accelerated','decision_stepped') or rate == 0 or (mode!='accelerated' and rate!=1):
        raise ValueError('invalid declared clock mode/rate')
    if end < start or now < origin or sim < start:
        raise ValueError('invalid capture/current interval')
    ready=None if render_ready_wall_elapsed_s is None else finite_nonnegative(render_ready_wall_elapsed_s,'render readiness')
    if ready is not None and not origin <= ready <= now:
        raise ValueError('readiness must be an actually observed time after capture start')
    duration=None if mode=='decision_stepped' else (end-start)/rate
    floor=None if duration is None else origin+duration
    if floor is not None and not math.isfinite(floor):
        raise ValueError('delivery deadline overflow')
    earliest=None if ready is None else ready if floor is None else max(floor,ready)
    eligible=ready is not None and sim>=end and (floor is None or now>=floor)
    latency=None if ready is None or floor is None else max(0.0,ready-floor)
    return DeliveryTiming(eligible,mode,start,end,duration,ready,earliest,latency)
