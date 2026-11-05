"""One ordered OFF-ACTOR numerical lineage across all raster geometries.

Actual unchanged B1 charge projection;exact dyadic sealed/open accumulation;
paired deterministic count prefixes. No authority or independent clock owner.
"""
from dataclasses import dataclass
from fractions import Fraction
import math
import struct

from .human_episode_types import (EpisodeSettings, ScienceIdentity, exact, identity, same_settings)
from .human_episode_facts import EpisodeFact
from .episode_raster import (RasterPlan, TimelinePrefix, BlankHold, AppliedSegment, incident_charge_C)
from .human_mapped_charge_projection import exposure_for_charge, ElapsedCellCharge
from .episode_detector_counts import CountProcess
from packages.acquisition.paged_counts import zero_plane


class DyadicAccumulator:
    def __init__(self):
        self.sealed = self.open = 0

    @staticmethod
    def units(value):
        if type(value) is not float or not math.isfinite(value):
            raise ValueError('finite exact dyadic value required')
        n, d = value.as_integer_ratio()
        return n << (1074-(d.bit_length()-1))

    def rounded(self):
        n = self.sealed+self.open
        if n == 0:
            return 0.0
        result = float(Fraction(n, 1 << 1074))
        if not math.isfinite(result):
            raise ValueError('finite dyadic projection required')
        return result


class _Transaction:
    def __init__(self):
        self.undo = []

    def attr(self, obj, name, value):
        self.undo.append(('attr', obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def item(self, obj, key, value):
        self.undo.append(('item', obj, key, (key in obj, obj.get(key))))
        obj[key] = value

    def append(self, obj, value):
        self.undo.append(('append', obj, None, None))
        obj.append(value)

    def rollback(self):
        for kind, obj, key, value in reversed(self.undo):
            if kind == 'attr':
                setattr(obj, key, value)
            elif kind == 'append':
                obj.pop()
            elif value[0]:
                obj[key] = value[1]
            else:
                del obj[key]


@dataclass(frozen=True)
class NumericalReceipt:
    last_ordinal: int
    physical_sequence: int
    status: str
    reason: str


@dataclass(frozen=True)
class EpisodeCapturePrefix:
    causal_raster_id: str
    session_generation: int
    sweep_index: int
    mode: str
    operation_id: str
    live_view_id: object
    origin_ns: int
    numerical_ordinal: int
    physical_sequence: int
    configuration: object
    settings: EpisodeSettings
    setting_id: str
    state_start_elapsed_ns: int
    prefix: TimelinePrefix
    applied_segments: tuple
    incident_pA_ns: tuple
    counts: object
    se_means: tuple
    bse_means: tuple
    incident_total_pA_ns: int
    outcome: str
    terminal_reason: object


@dataclass(frozen=True)
class EpisodeDoseSnapshot:
    cells: tuple
    tail_charge_C: float
    ground_charge_C: float
    incident_total_pA_ns: int
    numerical_ordinal: int
    physical_sequence: int


class _Capture:
    def __init__(self, fact):
        identifier, session, sweep, mode, op, view, config, handle, label = fact.body
        self.identity, self.session, self.sweep = identifier, session, sweep
        self.mode, self.op, self.view, self.config = mode, op, view, config
        self.origin = fact.event_at_ns
        self.plan = RasterPlan(config.geometry.width_px, config.geometry.height_px, config.dwell_ns)
        self.binding, self.label = handle, label
        self.settings = handle.settings
        self.elapsed = self.nominal = self.total = self.segment_start = self.state_start = 0
        self.hold = self.hold_cursor = None
        self.ordinal, self.physical = fact.ordinal, fact.physical_sequence
        self.holds, self.segments = [], []
        self.incident, self.se, self.bse = {}, {}, {}
        self.labels = {label: handle}
        self.counts = zero_plane(self.plan.pixel_count)
        self.outcome, self.reason = 'ACQUIRING', None


def _active_prefix(plan, cursor):
    # Independent arithmetic of cumulative beam-on ns;no owner import.
    duration = plan.width_px*plan.dwell_ns
    t = max(0, min(cursor, plan.raster_end_ns)-plan.settling_ns)
    complete_lines, remaining = divmod(t, duration+plan.line_flyback_ns)
    return min(plan.pixel_count*plan.dwell_ns, complete_lines*duration+min(remaining, duration))


class EpisodeExposureLedger:
    def __init__(self, science, initial_settings, *, episode_namespace, seed, bank_resolver):
        exact(science, ScienceIdentity); exact(initial_settings, EpisodeSettings); identity(episode_namespace)
        if type(seed) is not bytes or len(seed) != 32 or not callable(bank_resolver):
            raise ValueError('trusted resolver and private32-byte seed required')
        self.science, self.actual, self.episode, self.seed = science, initial_settings, episode_namespace, seed
        self.resolve = bank_resolver
        self.last = self.physical = self.last_issued = self.total = self.applied_generation = 0
        self.active = self.poison = self.open_fragment = None
        self.facts, self.captures, self.cells = {}, {}, {}
        self.tail, self.ground, self.se_emitted, self.bse_emitted = (DyadicAccumulator() for _ in range(4))

    def _source(self, handle, configuration=None, settings=None):
        source = self.resolve(handle)
        if source.handle != handle or handle.source_binding_digest != self.science.solver_source_digest:
            raise ValueError('source resolver returned a foreign/rebound descriptor')
        if configuration is not None and handle.geometry != configuration.geometry:
            raise ValueError('captured source geometry rebound')
        if settings is not None and handle.settings != settings:
            raise ValueError('captured source settings rebound')
        return source

    @staticmethod
    def _seal(accumulator, transaction):
        transaction.attr(accumulator, 'sealed', accumulator.sealed+accumulator.open)
        transaction.attr(accumulator, 'open', 0)

    def _seal_fragment(self, transaction):
        old = self.open_fragment
        if old is None:
            return
        capture = self.captures[old['raster']]
        for accumulator in (capture.se[old['pixel']], capture.bse[old['pixel']],
                            self.tail, self.ground, self.se_emitted, self.bse_emitted):
            self._seal(accumulator, transaction)
        for key in old['cells']:
            self._seal(self.cells[key], transaction)
        transaction.attr(self, 'open_fragment', None)

    def _project(self, capture, index, start, end, transaction):
        handle = capture.binding
        key = (capture.identity, index, capture.label, handle.descriptor_digest)
        old = self.open_fragment
        if old is None or old['key'] != key or old['end'] != start:
            self._seal_fragment(transaction)
            origin = start
        else:
            origin = old['start']
        source = self._source(handle, capture.config, capture.settings)
        response = source.response(index)
        current = capture.settings.current_pA
        exposure = exposure_for_charge(response, current_pA=current, incident_pA_ns=(end-origin)*current)
        for table in (capture.se, capture.bse):
            if index not in table:
                transaction.item(table, index, DyadicAccumulator())
        cell_keys = []
        for cell in exposure.cell_charges:
            cell_key = (cell.index_x, cell.index_y)
            cell_keys.append(cell_key)
            if cell_key not in self.cells:
                transaction.item(self.cells, cell_key, DyadicAccumulator())
            transaction.attr(self.cells[cell_key], 'open', DyadicAccumulator.units(cell.charge_C))
        for accumulator, value in ((capture.se[index], exposure.se_mean), (capture.bse[index], exposure.bse_mean),
            (self.tail, exposure.tail_charge_C), (self.ground, exposure.ground_charge_C),
            (self.se_emitted, exposure.se_emitted_charge_C), (self.bse_emitted, exposure.bse_emitted_charge_C)):
            transaction.attr(accumulator, 'open', DyadicAccumulator.units(value))
        transaction.attr(self, 'open_fragment', {'key': key, 'raster': capture.identity,
            'pixel': index, 'start': origin, 'end': end, 'cells': tuple(cell_keys)})
        transaction.item(capture.incident, index, capture.incident.get(index, 0)+(end-start)*current)

    def _interval(self, capture, body, transaction):
        _, from_elapsed, to_elapsed, from_nominal, to_nominal, held, _, _, _, _ = body
        if held:
            if to_elapsed > from_elapsed:
                self._seal_fragment(transaction)
            return
        plan = capture.plan
        start, end = max(from_nominal, plan.settling_ns), min(to_nominal, plan.raster_end_ns)
        if end <= start:
            return
        row, within = divmod(start-plan.settling_ns, plan.width_px*plan.dwell_ns+plan.line_flyback_ns)
        index = row*plan.width_px+min(within//plan.dwell_ns, plan.width_px)
        changed = []
        while index < plan.pixel_count:
            a, b = plan.pixel_interval(index)
            if a >= end:
                break
            left, right = max(a, start), min(b, end)
            if right > left:
                e0 = from_elapsed+left-from_nominal
                e1 = from_elapsed+right-from_nominal
                self._project(capture, index, e0, e1, transaction)
                changed.append(index)
            index += 1
        if not changed:
            return
        # Both channels are computed before an immutable paired plane can commit.
        packed_se, packed_bse = [], []
        for index in changed:
            frame_key = self.episode+':'+capture.identity
            se = CountProcess(self.seed, frame_key, index, 'SE').count(capture.se[index].rounded())
            bse = CountProcess(self.seed, frame_key, index, 'BSE').count(capture.bse[index].rounded())
            packed_se.append(struct.pack('<I', se)); packed_bse.append(struct.pack('<I', bse))
        if changed != list(range(changed[0], changed[-1]+1)):
            raise ValueError('raster interval does not follow contiguous original pixels')
        plane = capture.counts.write(changed[0], b''.join(packed_se), b''.join(packed_bse))
        transaction.attr(capture, 'counts', plane)

    def _process(self, fact, transaction):
        if fact.episode_namespace != self.episode or fact.issued_at_ns < self.last_issued:
            raise ValueError('foreign/backward numerical trace')
        if fact.physical_sequence is not None and (fact.physical_sequence != self.physical+1 or fact.physical_predecessor != self.physical):
            raise ValueError('missing original physical predecessor')
        body, kind = fact.body, fact.kind
        if kind == 'RASTER_START':
            identifier, _, _, _, _, _, configuration, handle, _ = body
            self._source(handle, configuration, self.actual)
            if self.active is not None or identifier in self.captures or fact.event_at_ns != fact.issued_at_ns:
                raise ValueError('concurrent/duplicate/backdated raster')
            capture = _Capture(fact)
            transaction.item(self.captures, identifier, capture)
            transaction.attr(self, 'active', identifier)
        elif kind == 'SETTINGS_APPLIED':
            op, previous, settings, generation, handle, identifier, elapsed = body
            self._source(handle, settings=settings)
            if previous != self.actual or generation != self.applied_generation+1:
                raise ValueError('global optics predecessor mismatch')
            if identifier is None:
                if self.active is not None or elapsed is not None:
                    raise ValueError('blanked application fabricated a capture')
            else:
                if identifier != self.active:
                    raise ValueError('application targets wrong raster')
                capture = self.captures[identifier]
                self._source(handle, capture.config, settings)
                if capture.hold is not None or elapsed != capture.elapsed or fact.event_at_ns != capture.origin+elapsed or op in capture.labels:
                    raise ValueError('held/backdated/rebound optics application')
                self._seal_fragment(transaction)
                if capture.elapsed > capture.segment_start:
                    transaction.append(capture.segments, AppliedSegment(capture.segment_start, capture.elapsed,
                        capture.settings.current_pA, capture.label))
                transaction.item(capture.labels, op, handle)
                transaction.attr(capture, 'segment_start', elapsed)
                transaction.attr(capture, 'state_start', elapsed)
                transaction.attr(capture, 'binding', handle)
                transaction.attr(capture, 'settings', settings)
                transaction.attr(capture, 'label', op)
                transaction.attr(capture, 'ordinal', fact.ordinal)
                transaction.attr(capture, 'physical', fact.physical_sequence)
            transaction.attr(self, 'actual', settings)
            transaction.attr(self, 'applied_generation', generation)
        elif kind in ('PREFIX', 'HOLD_START', 'HOLD_END', 'RASTER_END'):
            identifier = body[0]
            if identifier != self.active or identifier not in self.captures:
                raise ValueError('no active original raster for prefix')
            capture = self.captures[identifier]
            if kind == 'PREFIX':
                _, a, b, u, v, held, handle, label, delta, total = body
                if (a, u, held, handle, label) != (capture.elapsed, capture.nominal, capture.hold is not None,
                        capture.binding, capture.label) or b < a or v < u or v > capture.plan.program_end_ns:
                    raise ValueError('noncontiguous/rebound exposure prefix')
                if v-u != (0 if held else b-a) or fact.event_at_ns != capture.origin+b:
                    raise ValueError('prefix elapsed/blank timing mismatch')
                expected = (_active_prefix(capture.plan, v)-_active_prefix(capture.plan, u))*capture.settings.current_pA
                if delta != expected or total != capture.total+delta:
                    raise ValueError('integer incident closure mismatch')
                self._interval(capture, body, transaction)
                transaction.attr(capture, 'elapsed', b); transaction.attr(capture, 'nominal', v)
                transaction.attr(capture, 'total', total); transaction.attr(self, 'total', self.total+delta)
            elif kind == 'HOLD_START':
                _, elapsed, nominal, label = body
                if capture.hold is not None or (elapsed, nominal, label) != (capture.elapsed, capture.nominal, capture.label):
                    raise ValueError('hold start lineage mismatch')
                transaction.attr(capture, 'hold', elapsed); transaction.attr(capture, 'hold_cursor', nominal)
            elif kind == 'HOLD_END':
                _, start, end, nominal, label = body
                if (start, end, nominal, label) != (capture.hold, capture.elapsed, capture.hold_cursor, capture.label):
                    raise ValueError('hold end lineage mismatch')
                if end > start:
                    transaction.append(capture.holds, BlankHold(start, end, nominal))
                transaction.attr(capture, 'hold', None); transaction.attr(capture, 'hold_cursor', None)
            else:
                _, elapsed, nominal, total, reason = body
                if capture.hold is not None or (elapsed, nominal, total) != (capture.elapsed, capture.nominal, capture.total):
                    raise ValueError('terminal prefix lineage mismatch')
                if fact.event_at_ns != capture.origin+elapsed or (reason == 'COMPLETED' and nominal != capture.plan.program_end_ns):
                    raise ValueError('terminal capture time/completion mismatch')
                self._seal_fragment(transaction)
                transaction.attr(capture, 'outcome', 'COMPLETED' if reason == 'COMPLETED' else 'CANCELLED')
                transaction.attr(capture, 'reason', reason); transaction.attr(self, 'active', None)
            transaction.attr(capture, 'ordinal', fact.ordinal)
            transaction.attr(capture, 'physical', fact.physical_sequence)
        # Stage/control facts share ordering but create no detector sample/dose.
        if fact.physical_sequence is not None:
            transaction.attr(self, 'physical', fact.physical_sequence)
        transaction.attr(self, 'last_issued', fact.issued_at_ns)

    def ingest(self, facts):
        if type(facts) is not tuple or any(type(fact) is not EpisodeFact for fact in facts):
            raise ValueError('closed immutable complete trace batch required')
        if self.poison is not None:
            return NumericalReceipt(self.last, self.physical, 'POISONED', self.poison)
        for fact in facts:
            if fact.ordinal <= self.last:
                if self.facts.get(fact.ordinal) != fact:
                    self.poison = 'CONFLICTING_DUPLICATE'
                    return NumericalReceipt(self.last, self.physical, 'POISONED', self.poison)
                continue
            if fact.ordinal != self.last+1 or fact.predecessor != self.last:
                return NumericalReceipt(self.last, self.physical, 'BLOCKED', 'MISSING_PREDECESSOR')
            transaction = _Transaction()
            try:
                self._process(fact, transaction)
            except Exception:
                transaction.rollback()
                self.poison = 'NUMERIC_FAILURE'
                return NumericalReceipt(self.last, self.physical, 'POISONED', self.poison)
            self.facts[fact.ordinal] = fact
            self.last = fact.ordinal
        return NumericalReceipt(self.last, self.physical, 'COMMITTED', 'OK')

    def capture_prefix(self, identifier):
        identity(identifier)
        if identifier not in self.captures:
            raise ValueError('unknown original numerical capture')
        capture = self.captures[identifier]
        holds, segments = list(capture.holds), list(capture.segments)
        if capture.hold is not None and capture.elapsed > capture.hold:
            holds.append(BlankHold(capture.hold, capture.elapsed, capture.hold_cursor, 'OPEN'))
        if capture.elapsed > capture.segment_start:
            segments.append(AppliedSegment(capture.segment_start, capture.elapsed, capture.settings.current_pA, capture.label))
        count = capture.plan.pixel_count
        return EpisodeCapturePrefix(capture.identity, capture.session, capture.sweep, capture.mode,
            capture.op, capture.view, capture.origin, capture.ordinal, capture.physical, capture.config,
            capture.settings, capture.label, capture.state_start,
            TimelinePrefix(capture.plan, capture.elapsed, tuple(holds)), tuple(segments),
            tuple(capture.incident.get(i, 0) for i in range(count)), capture.counts,
            tuple(capture.se[i].rounded() if i in capture.se else 0. for i in range(count)),
            tuple(capture.bse[i].rounded() if i in capture.bse else 0. for i in range(count)),
            capture.total, capture.outcome, capture.reason)

    def dose_snapshot(self):
        cells = tuple(ElapsedCellCharge(x, y, value.rounded()) for (x, y), value in
                      sorted(self.cells.items(), key=lambda item: (item[0][1], item[0][0])))
        q = incident_charge_C(self.total)
        tail, ground = self.tail.rounded(), self.ground.rounded()
        deposited = math.fsum([cell.charge_C for cell in cells]+[tail])
        imbalance = math.fsum((-q, self.se_emitted.rounded(), self.bse_emitted.rounded(), ground))
        if abs(deposited-q) > 8*math.ulp(q) or abs(imbalance) > 8*math.ulp(q):
            raise ValueError('persistent canonical incident/8ULP closure failed')
        return EpisodeDoseSnapshot(cells, tail, ground, self.total, self.last, self.physical)
