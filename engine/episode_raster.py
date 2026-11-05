"""Pure integer raster/prefix exposure; no clock, scheduler or instrument route."""
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
import re

SAFE_INTEGER = 2**53-1
SOLVER_ID = 'vsem.causal-episode-raster.v1'
_IDENTITY = re.compile(r'[A-Za-z0-9._:-]{1,128}\Z')


def _integer(value, low=0, high=SAFE_INTEGER, name='integer'):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(name+' outside exact integer envelope')
    return value


def _identity(value):
    if type(value) is not str or _IDENTITY.fullmatch(value) is None:
        raise ValueError('exact applied setting identity required')


def _objects(value, cls, name):
    if type(value) is not tuple or any(type(item) is not cls for item in value):
        raise ValueError('immutable exact '+name+' tuple required')


@dataclass(frozen=True)
class RasterPlan:
    width_px: int
    height_px: int
    dwell_ns: int
    protocol: str = field(default='vsem.causal-episode-raster-plan.v1', init=False)
    settling_ns: int = field(default=20000000, init=False)
    line_flyback_ns: int = field(default=100000, init=False)
    frame_overhead_ns: int = field(default=10000000, init=False)

    def __post_init__(self):
        _integer(self.width_px, 1, 4096, 'width')
        _integer(self.height_px, 1, 4096, 'height')
        _integer(self.dwell_ns, 10, 10000000, 'dwell ns')

    @property
    def pixel_count(self):
        return self.width_px*self.height_px

    @property
    def raster_end_ns(self):
        return (self.settling_ns+self.pixel_count*self.dwell_ns
                +(self.height_px-1)*self.line_flyback_ns)

    @property
    def program_end_ns(self):
        return self.raster_end_ns+self.frame_overhead_ns

    def pixel_interval(self, pixel_index):
        _integer(pixel_index, 0, self.pixel_count-1, 'pixel index')
        row, column = divmod(pixel_index, self.width_px)
        start = (self.settling_ns+row*(self.width_px*self.dwell_ns+self.line_flyback_ns)
                 +column*self.dwell_ns)
        return start, start+self.dwell_ns


@dataclass(frozen=True)
class BlankHold:
    start_elapsed_ns: int
    end_elapsed_ns: int
    nominal_cursor_ns: int
    status: str = 'CLOSED'
    reason: str = field(default='response_preparing', init=False)

    def __post_init__(self):
        _integer(self.start_elapsed_ns, name='hold start')
        _integer(self.end_elapsed_ns, self.start_elapsed_ns+1, name='hold end')
        _integer(self.nominal_cursor_ns, name='hold cursor')
        if type(self.status) is not str or self.status not in ('CLOSED', 'OPEN'):
            raise ValueError('exact observed hold status required')


@dataclass(frozen=True)
class TimelinePrefix:
    plan: RasterPlan
    capture_elapsed_ns: int
    blank_holds: tuple = ()

    def __post_init__(self):
        if type(self.plan) is not RasterPlan:
            raise ValueError('exact raster plan required')
        _integer(self.capture_elapsed_ns, name='capture cut')
        _objects(self.blank_holds, BlankHold, 'blank hold')
        preceding, previous_end = 0, 0
        for index, hold in enumerate(self.blank_holds):
            if (hold.start_elapsed_ns < previous_end
                    or hold.end_elapsed_ns > self.capture_elapsed_ns
                    or hold.nominal_cursor_ns != hold.start_elapsed_ns-preceding
                    or hold.nominal_cursor_ns >= self.plan.program_end_ns):
                raise ValueError('inconsistent hold/cursor prefix')
            if hold.status == 'OPEN' and (index != len(self.blank_holds)-1
                    or hold.end_elapsed_ns != self.capture_elapsed_ns):
                raise ValueError('open hold must end at observed prefix cut')
            preceding += hold.end_elapsed_ns-hold.start_elapsed_ns
            previous_end = hold.end_elapsed_ns
        _integer(self.nominal_cursor_ns, 0, self.plan.program_end_ns, 'nominal cursor')

    @property
    def nominal_cursor_ns(self):
        return self.capture_elapsed_ns-sum(h.end_elapsed_ns-h.start_elapsed_ns for h in self.blank_holds)

    @property
    def open_hold(self):
        return bool(self.blank_holds and self.blank_holds[-1].status == 'OPEN')


@dataclass(frozen=True)
class AppliedSegment:
    start_elapsed_ns: int
    end_elapsed_ns: int
    current_pA: int
    setting_id: str

    def __post_init__(self):
        _integer(self.start_elapsed_ns, name='segment start')
        _integer(self.end_elapsed_ns, self.start_elapsed_ns+1, name='segment end')
        _integer(self.current_pA, 1, 1000, 'applied pA')
        _identity(self.setting_id)


def _segments(prefix, segments):
    _objects(segments, AppliedSegment, 'applied segment')
    previous, end = None, 0
    for segment in segments:
        if segment.start_elapsed_ns != end:
            raise ValueError('applied segments must exactly partition capture prefix')
        if previous is not None and (previous.setting_id, previous.current_pA) == (
                segment.setting_id, segment.current_pA):
            raise ValueError('nonsemantic observer/chunk segment split')
        end, previous = segment.end_elapsed_ns, segment
    if end != prefix.capture_elapsed_ns:
        raise ValueError('applied segments must end at capture cut')


@dataclass(frozen=True)
class RasterCursor:
    nominal_cursor_ns: int
    phase: str
    pixel_index: object
    used_dwell_ns: int
    completed_pixels: int
    open_hold: bool

    def __post_init__(self):
        _integer(self.nominal_cursor_ns)
        _integer(self.used_dwell_ns, 0, 10000000)
        _integer(self.completed_pixels, 0, 16777216)
        if type(self.open_hold) is not bool or type(self.phase) is not str or self.phase not in (
                'SETTLING', 'PIXEL', 'LINE_FLYBACK', 'FRAME_OVERHEAD', 'COMPLETE'):
            raise ValueError('exact cursor phase/hold required')
        if self.phase == 'PIXEL':
            _integer(self.pixel_index, 0, 16777215)
        elif self.pixel_index is not None or self.used_dwell_ns != 0:
            raise ValueError('blank/completed cursor has no active pixel')


def cursor_at(prefix):
    if type(prefix) is not TimelinePrefix:
        raise ValueError('exact timeline prefix required')
    plan, cursor = prefix.plan, prefix.nominal_cursor_ns
    if cursor < plan.settling_ns:
        return RasterCursor(cursor, 'SETTLING', None, 0, 0, prefix.open_hold)
    if cursor >= plan.raster_end_ns:
        phase = 'COMPLETE' if cursor == plan.program_end_ns else 'FRAME_OVERHEAD'
        return RasterCursor(cursor, phase, None, 0, plan.pixel_count, prefix.open_hold)
    row, offset = divmod(cursor-plan.settling_ns, plan.width_px*plan.dwell_ns+plan.line_flyback_ns)
    if offset >= plan.width_px*plan.dwell_ns:
        return RasterCursor(cursor, 'LINE_FLYBACK', None, 0, (row+1)*plan.width_px, prefix.open_hold)
    column, used = divmod(offset, plan.dwell_ns)
    index = row*plan.width_px+column
    return RasterCursor(cursor, 'PIXEL', index, used, index, prefix.open_hold)


def _hold_coordinates(prefix):
    cursors, cumulative = [], [0]
    for hold in prefix.blank_holds:
        cursors.append(hold.nominal_cursor_ns)
        cumulative.append(cumulative[-1]+hold.end_elapsed_ns-hold.start_elapsed_ns)
    return cursors, cumulative


@dataclass(frozen=True)
class RasterFragment:
    pixel_index: int
    setting_id: str
    current_pA: int
    start_elapsed_ns: int
    end_elapsed_ns: int
    start_nominal_ns: int
    end_nominal_ns: int

    def __post_init__(self):
        _integer(self.pixel_index, 0, 16777215, 'pixel index')
        _identity(self.setting_id)
        _integer(self.current_pA, 1, 1000, 'applied pA')
        _integer(self.start_elapsed_ns)
        _integer(self.end_elapsed_ns, self.start_elapsed_ns+1)
        _integer(self.start_nominal_ns)
        _integer(self.end_nominal_ns, self.start_nominal_ns+1)
        if self.end_elapsed_ns-self.start_elapsed_ns != self.end_nominal_ns-self.start_nominal_ns:
            raise ValueError('active fragment elapsed/nominal durations differ')
        _integer(self.incident_pA_ns, name='fragment charge numerator')

    @property
    def incident_pA_ns(self):
        return self.current_pA*(self.end_nominal_ns-self.start_nominal_ns)


@dataclass(frozen=True)
class PixelExposure:
    pixel_index: int
    fragments: tuple

    def __post_init__(self):
        _integer(self.pixel_index, 0, 16777215)
        _objects(self.fragments, RasterFragment, 'raster fragment')
        if not self.fragments or any(f.pixel_index != self.pixel_index for f in self.fragments):
            raise ValueError('nonempty matching pixel fragments required')
        for before, after in zip(self.fragments, self.fragments[1:]):
            if before.end_nominal_ns != after.start_nominal_ns or before.end_elapsed_ns > after.start_elapsed_ns:
                raise ValueError('pixel fragments must preserve contiguous nominal exposure')
            if before.end_elapsed_ns == after.start_elapsed_ns and (
                    before.setting_id, before.current_pA) == (after.setting_id, after.current_pA):
                raise ValueError('nonsemantic active fragment split')
        _integer(self.used_ns, 1, 10000000, 'used pixel dwell')
        _integer(self.incident_pA_ns, name='pixel charge numerator')

    @property
    def used_ns(self):
        return sum(f.end_nominal_ns-f.start_nominal_ns for f in self.fragments)

    @property
    def incident_pA_ns(self):
        return sum(f.incident_pA_ns for f in self.fragments)


@dataclass(frozen=True)
class RasterExposure:
    prefix: TimelinePrefix
    applied_segments: tuple
    pixels: tuple
    protocol: str = field(default='vsem.causal-episode-raster-exposure.v1', init=False)
    solver_id: str = field(default=SOLVER_ID, init=False)

    def __post_init__(self):
        if type(self.prefix) is not TimelinePrefix:
            raise ValueError('exact timeline prefix required')
        _segments(self.prefix, self.applied_segments)
        _objects(self.pixels, PixelExposure, 'pixel exposure')
        state = cursor_at(self.prefix)
        nominal_cursor = state.nominal_cursor_ns
        count = state.completed_pixels+int(state.phase == 'PIXEL' and state.used_dwell_ns > 0)
        if len(self.pixels) != count:
            raise ValueError('acquired pixel count differs from exact cursor')
        hold_cursors, hold_sums = _hold_coordinates(self.prefix)
        segment_starts = tuple(s.start_elapsed_ns for s in self.applied_segments)
        for index, pixel in enumerate(self.pixels):
            a, b = self.prefix.plan.pixel_interval(index)
            used = min(b, nominal_cursor)-a
            if pixel.pixel_index != index or pixel.used_ns != used or (
                    pixel.fragments[0].start_nominal_ns != a
                    or pixel.fragments[-1].end_nominal_ns != a+used):
                raise ValueError('pixel nominal exposure differs from raster prefix')
            for fragment in pixel.fragments:
                lo = bisect_right(hold_cursors, fragment.start_nominal_ns)
                hi = bisect_left(hold_cursors, fragment.end_nominal_ns)
                if (lo != hi or fragment.start_elapsed_ns != fragment.start_nominal_ns+hold_sums[lo]
                        or fragment.end_elapsed_ns != fragment.end_nominal_ns+hold_sums[hi]):
                    raise ValueError('active fragment intersects or misplaces blank hold')
                segment_index = bisect_right(segment_starts, fragment.start_elapsed_ns)-1
                if segment_index < 0:
                    raise ValueError('active fragment lacks applied segment')
                segment = self.applied_segments[segment_index]
                if fragment.end_elapsed_ns > segment.end_elapsed_ns or (
                        fragment.setting_id, fragment.current_pA) != (segment.setting_id, segment.current_pA):
                    raise ValueError('active fragment differs from actual applied settings')
        _integer(self.incident_pA_ns, high=2**64-1, name='frame charge numerator')

    @property
    def completed_pixels(self):
        return sum(pixel.used_ns == self.prefix.plan.dwell_ns for pixel in self.pixels)

    @property
    def incident_pA_ns(self):
        return sum(pixel.incident_pA_ns for pixel in self.pixels)

    @property
    def raster_complete(self):
        return self.prefix.nominal_cursor_ns >= self.prefix.plan.raster_end_ns

    @property
    def program_complete(self):
        return self.prefix.nominal_cursor_ns == self.prefix.plan.program_end_ns and not self.prefix.open_hold


def integrate_raster(prefix, segments):
    if type(prefix) is not TimelinePrefix:
        raise ValueError('exact timeline prefix required')
    _segments(prefix, segments)
    hold_cursors, hold_sums = _hold_coordinates(prefix)
    nominal_cursor = prefix.nominal_cursor_ns
    pixels, segment_index = [], 0
    for index in range(prefix.plan.pixel_count):
        start, nominal_end = prefix.plan.pixel_interval(index)
        end = min(nominal_end, nominal_cursor)
        if start >= end:
            break
        inside_lo = bisect_right(hold_cursors, start)
        inside_hi = bisect_left(hold_cursors, end)
        cuts = (start,)+tuple(sorted(set(hold_cursors[inside_lo:inside_hi])))+(end,)
        fragments = []
        for a, b in zip(cuts, cuts[1:]):
            actual_a = a+hold_sums[bisect_right(hold_cursors, a)]
            actual_b = b+hold_sums[bisect_left(hold_cursors, b)]
            while segment_index < len(segments) and segments[segment_index].end_elapsed_ns <= actual_a:
                segment_index += 1
            next_segment = segment_index
            while next_segment < len(segments) and segments[next_segment].start_elapsed_ns < actual_b:
                segment = segments[next_segment]
                lo, hi = max(actual_a, segment.start_elapsed_ns), min(actual_b, segment.end_elapsed_ns)
                if lo < hi:
                    fragments.append(RasterFragment(index, segment.setting_id, segment.current_pA,
                        lo, hi, a+(lo-actual_a), a+(hi-actual_a)))
                if segment.end_elapsed_ns >= actual_b:
                    break
                next_segment += 1
            segment_index = next_segment
        pixels.append(PixelExposure(index, tuple(fragments)))
    return RasterExposure(prefix, segments, tuple(pixels))


def incident_charge_C(incident_pA_ns):
    _integer(incident_pA_ns, high=2**64-1, name='incident pA ns')
    return incident_pA_ns/10**21
