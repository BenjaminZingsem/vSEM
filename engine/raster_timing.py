"""Analytic exposure timing; no renderer, setpoint facade or hidden-truth export."""
from dataclasses import dataclass
import math
from .timebase import finite_nonnegative


@dataclass(frozen=True)
class RasterTiming:
    width_px: int
    height_px: int
    dwell_s: float
    line_flyback_s: float = 0.0
    settling_s: float = 0.0
    frame_overhead_s: float = 0.0

    def __post_init__(self):
        for name in ('width_px', 'height_px'):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= 2048:
                raise ValueError('reference raster dimensions must be integers in 1..2048')
        for name in ('dwell_s','line_flyback_s','settling_s','frame_overhead_s'):
            finite_nonnegative(getattr(self,name),name)
        if self.dwell_s == 0 or not math.isfinite(self.duration_s):
            raise ValueError('positive dwell and finite total duration required')

    @property
    def row_exposure_s(self): return self.width_px * float(self.dwell_s)

    @property
    def duration_s(self):
        return float(self.settling_s) + self.height_px * self.row_exposure_s + (self.height_px-1)*float(self.line_flyback_s) + float(self.frame_overhead_s)

    def row_start_s(self, row):
        if type(row) is not int or not 0 <= row < self.height_px:
            raise ValueError('row index outside raster')
        return self.settling_s + row * (self.row_exposure_s + self.line_flyback_s)

    def completed_rows(self, elapsed_s):
        elapsed = finite_nonnegative(elapsed_s,'elapsed')
        return sum(elapsed >= self.row_start_s(row)+self.row_exposure_s for row in range(self.height_px))

    def beam_on_s(self, start_s, end_s):
        start = finite_nonnegative(start_s,'interval start')
        end = finite_nonnegative(end_s,'interval end')
        if end < start: raise ValueError('reversed exposure interval')
        return math.fsum(max(0.0,min(end,self.row_start_s(row)+self.row_exposure_s)-max(start,self.row_start_s(row))) for row in range(self.height_px))

    def charge_C(self, start_s, end_s, current_A):
        current = finite_nonnegative(current_A,'current')
        result = self.beam_on_s(start_s,end_s) * current
        if not math.isfinite(result): raise ValueError('charge overflow')
        return result


@dataclass(frozen=True)
class CaptureSegment:
    """Internal immutable settings snapshot; caller must supply actual applied state."""
    start_elapsed_s: float
    end_elapsed_s: float
    current_A: float
    settings_revision: int

    def __post_init__(self):
        start=finite_nonnegative(self.start_elapsed_s,'segment start')
        end=finite_nonnegative(self.end_elapsed_s,'segment end')
        finite_nonnegative(self.current_A,'current')
        if end < start or type(self.settings_revision) is not int or self.settings_revision < 0:
            raise ValueError('invalid capture segment')


def segment_charge_C(timing, segments):
    if type(timing) is not RasterTiming or type(segments) is not tuple:
        raise ValueError('immutable capture inputs required')
    previous = 0.0
    charges=[]
    for segment in segments:
        if type(segment) is not CaptureSegment or segment.start_elapsed_s != previous or segment.end_elapsed_s > timing.duration_s:
            raise ValueError('segments must be contiguous from zero within capture')
        charges.append(timing.charge_C(segment.start_elapsed_s,segment.end_elapsed_s,segment.current_A))
        previous=segment.end_elapsed_s
    total=math.fsum(charges)
    if not math.isfinite(total): raise ValueError('charge overflow')
    return total
