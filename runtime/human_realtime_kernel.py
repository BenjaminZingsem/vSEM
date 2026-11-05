"""Owned realtime physical/numerical processes, PRIVATE integration kernel.

No public listener or causal-verification claim. Every ingress/tick/fact is
retained; actor credits are deliberately NEVER acknowledged here. The full
semantic verifier must be connected before continuous/public operation. Bounded
qualification exhaustion therefore physically interlocks, rather than silently
recycling unverified credits. The numerical cut is not a causal ACK.
"""
from collections import deque
from dataclasses import dataclass
import hashlib
import multiprocessing as mp
import os
from pathlib import Path
import secrets
import time

from engine import human_episode_types as t
from engine.human_episode_facts import EpisodeFact
from engine.episode_credits import EpisodeCapacity
from .grounded_mailbox import ScalarMailbox, CELL_BYTES
from .human_realtime_codec import encode_cell, decode_cell
from .human_realtime_records import TickBegin, TickEnd, NumericalCut

# All simultaneously held source reservations: R6/T7/A1/C10+C8, plus two
# witnesses. This conservative bound covers mixed regular/emergency service.
MAX_TICK_CELLS = 34


def lifetime_packet_bound(capacity):
    """Finite private episode reservation, including preparation-only witnesses.

    Source credits bound facts. This deliberately generous packet allowance also
    covers input/job witnesses. BEFORE each physical service, the owner reserves
    MAX_TICK_CELLS plus an additional full terminal service. It interlocks at the
    actual service time if that lifetime allowance would be exhausted. The guard
    does not rely on a speculative job-count bound or on the parent draining IO.
    ACK reuse/continuous operation requires a separately verified protocol.
    """
    t.exact(capacity, EpisodeCapacity)
    return 3*sum((capacity.regular_slots, capacity.terminal_slots,
                  capacity.application_slots, capacity.control_slots))+4*capacity.admission_record_slots+32


class _Wire:
    def __init__(self, mailbox, nonce):
        self.mailbox, self.nonce = mailbox, nonce
        self.sent = self.received = 0

    def put(self, value):
        cell = encode_cell(value, self.nonce, self.sent+1)
        if not self.mailbox.try_put(cell): return False
        self.sent += 1
        return True

    def get(self):
        cell = self.mailbox.try_get()
        if cell is None: return None
        value = decode_cell(cell, self.nonce, self.received+1)
        self.received += 1
        return value, cell


def _owner(science, initial_settings, namespace, capacity, nonce, links, parent_pid,
           period_ns, origin_ns, packet_allowance):
    # Spawned owner imports this module's scalar closure, never NumPy or a source
    # graph. No filesystem writes, Pipe.send, multiprocessing.Queue or feeders.
    from engine.human_grounded_episode import GroundedEpisode
    owner = GroundedEpisode(science, initial_settings, episode_namespace=namespace, capacity=capacity)
    authority, normal, safety, ready, health, output = (_Wire(link, nonce) for link in links)
    tick_id = 0
    next_service = time.perf_counter_ns()
    while True:
        current = time.perf_counter_ns()
        if current < next_service:
            time.sleep(min((next_service-current)/1e9, .001))
            continue
        next_service = current+period_ns
        if owner.interlock is not None:
            # A parent may tear down the already blanked process. No abandoned
            # semaphore or unverified physical credit is reopened here.
            if os.getppid() != parent_pid: return
            time.sleep(.001)
            continue
        values = [wire.get() for wire in (authority, normal, safety, ready, health)]
        auth, command, stop, bank, fault = [item[0] if item else None for item in values]
        if os.getppid() != parent_pid:
            fault = t.EpisodeFault(namespace, 'PROCESS_FAILURE')
        if packet_allowance-output.sent < 2*MAX_TICK_CELLS:
            fault = t.EpisodeFault(namespace, 'SPOOL_CAPACITY')
        for value, field in ((auth, 'authority'), (command, 'normal'), (stop, 'stop')):
            if value is not None:
                t.exact(value, t.EpisodeInputs)
                if getattr(value, field) is None or any(getattr(value, name) is not None for name in
                       ('authority', 'normal', 'stop', 'bank_result', 'verified_ack', 'fault') if name != field):
                    raise ValueError('Cross-lane owner ingress')
        inputs = t.EpisodeInputs(authority=auth.authority if auth else None,
            normal=command.normal if command else None, stop=stop.stop if stop else None,
            bank_result=bank, fault=fault)
        at = time.perf_counter_ns()-origin_ns
        result = owner.tick(at, inputs)
        meaningful = bool(result.facts or result.bank_dispatch or any(item is not None for item in values) or fault)
        if not meaningful: continue
        tick_id += 1
        records = (TickBegin(tick_id, at, inputs), *result.facts,
            TickEnd(tick_id, result.state, result.bank_dispatch, result.started_raster_ids, result.ended_raster_ids))
        if len(records) > MAX_TICK_CELLS:
            raise RuntimeError('Frozen source reservation envelope violated')
        for value in records:
            if not output.put(value):
                # The prior lifetime reservation guarantees this cannot happen
                # for valid traces, even with a stopped parent.
                # Never continue an exposing loop after a violated proof.
                owner.tick(time.perf_counter_ns()-origin_ns,
                    t.EpisodeInputs(fault=t.EpisodeFault(namespace, 'SPOOL_CAPACITY')))
                raise RuntimeError('No-ACK lifetime mailbox bound violated')


def _numerical(initial_settings, namespace, nonce, links, seed, directory,
               delay_per_fact_s, parent_pid, binding_allowance):
    # All large/solver imports are in this owned process only.
    from engine.human_cached_source import CachedResponseRegistry
    from engine.human_specimen_map import NativeWorldMap
    from engine.human_alignment_specimen import HumanAlignmentSpecimen
    from engine.human_live_image_ledger import EpisodeExposureLedger
    registry = CachedResponseRegistry(world=NativeWorldMap(specimen=HumanAlignmentSpecimen(), spacing_m=1.25e-9),
                                     binding_capacity=binding_allowance)
    startup, jobs, facts, bank_output, cuts = (_Wire(link, nonce) for link in links)
    if not startup.put(registry.science): raise RuntimeError('Owned science startup lane exhausted')
    ledger = EpisodeExposureLedger(registry.science, initial_settings,
        episode_namespace=namespace, seed=seed, bank_resolver=registry.resolve)
    directory = Path(directory)
    pending_banks, pending_cuts = deque(), deque()
    while True:
        if os.getppid() != parent_pid: return
        if pending_banks and bank_output.put(pending_banks[0]): pending_banks.popleft()
        if pending_cuts and cuts.put(pending_cuts[0]): pending_cuts.popleft()
        item = jobs.get()
        if item is not None:
            ticket, _ = item
            t.exact(ticket, t.BankTicket)
            try: result = registry.prepare(ticket)
            except Exception: result = t.BankFailed(ticket)
            pending_banks.append(result)
        item = facts.get()
        if item is None:
            time.sleep(.001)
            continue
        fact, _ = item
        t.exact(fact, EpisodeFact)
        if delay_per_fact_s: time.sleep(delay_per_fact_s)
        receipt = ledger.ingest((fact,))
        if receipt.status != 'COMMITTED': raise RuntimeError('Actual numerical follower rejected retained trace: '+receipt.reason)
        raster = None
        if fact.kind in ('RASTER_START', 'PREFIX', 'HOLD_START', 'HOLD_END', 'RASTER_END'):
            raster = fact.body[0]
        elif fact.kind == 'SETTINGS_APPLIED': raster = fact.body[5]
        if raster is None:
            pending_cuts.append(NumericalCut(ledger.last, ledger.physical, ledger.total))
            continue
        # A numerical watermark is scalar. capture_prefix constructs full-size
        # incident/mean tuples and must not be materialized for every 5ms fact.
        # Read the actual committed private capture here; detector page bytes
        # remain immutable at their publication cut and are read only at end.
        capture = ledger.captures[raster]
        se_hash = bse_hash = None
        if fact.kind == 'RASTER_END':
            # Native original counts; no resizing, display refocus or new noise.
            se, bse = capture.counts.read(0, capture.config.geometry.pixel_count)
            se_hash, bse_hash = hashlib.sha256(se).hexdigest(), hashlib.sha256(bse).hexdigest()
            for channel, raw in (('SE', se), ('BSE', bse)):
                target = directory/(raster+'.'+channel+'.uint32')
                with target.open('xb') as stream: stream.write(raw)
        g = capture.config.geometry
        pending_cuts.append(NumericalCut(ledger.last, ledger.physical, ledger.total,
            raster, capture.outcome, g.width_px, g.height_px, capture.total, se_hash, bse_hash))


class RetainedCells:
    """Parent-private exact witnesses; ordinary pressure cannot erase history.

    Reserve covers ALL possible actor packets, not merely a current tick. A
    numerical cut never acknowledges physical owner credits. Full witnesses
    remain resident for the private audit even after numerical consumption.
    """
    def __init__(self, ordinary_cells, emergency_cells):
        t.integer(ordinary_cells, 1); t.integer(emergency_cells, 1)
        self.ordinary_cells, self.emergency_cells = ordinary_cells, emergency_cells
        self.cells = []
        self.pressured = False

    def append(self, cell):
        if type(cell) is not bytes or len(cell) != CELL_BYTES: raise ValueError('Exact retained wire cell required')
        if len(self.cells) >= self.ordinary_cells+self.emergency_cells:
            raise RuntimeError('Complete emergency retention reservation exhausted')
        self.cells.append(cell)
        self.pressured = len(self.cells) >= self.ordinary_cells


@dataclass(frozen=True)
class PrivateKernelConfiguration:
    capacity: EpisodeCapacity
    period_ns: int = 5_000_000
    ordinary_retained_cells: int = 65536
    delay_per_fact_s: float = 0.0
    packet_allowance_cells: object = None  # fault-injection qualification only

    def __post_init__(self):
        t.exact(self.capacity, EpisodeCapacity)
        t.integer(self.period_ns, 1_000_000, 100_000_000)
        t.integer(self.ordinary_retained_cells, 1)
        t.real(self.delay_per_fact_s, 0., 10.)
        if self.packet_allowance_cells is not None:
            t.integer(self.packet_allowance_cells, 2*MAX_TICK_CELLS, lifetime_packet_bound(self.capacity))


class PrivateRealtimeKernel:
    """Trusted private harness. No HTTP, actor ACK or release authority.

    refresh() services launcher-owned liveness/retention. A later trusted service
    must own this continuously; operator requests must never drive the clock.
    """
    def __init__(self, directory, initial_settings, configuration, *, seed=None):
        t.exact(initial_settings, t.EpisodeSettings)
        t.exact(configuration, PrivateKernelConfiguration)
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=False)
        self.configuration, self.initial_settings = configuration, initial_settings
        self.namespace = 'rt-'+secrets.token_hex(8)
        self.nonce = secrets.token_bytes(16)
        self.seed = secrets.token_bytes(32) if seed is None else seed
        if type(self.seed) is not bytes or len(self.seed) != 32: raise ValueError('Private32-byte count key required')
        self.context = mp.get_context('spawn')
        self.packet_bound = configuration.packet_allowance_cells or lifetime_packet_bound(configuration.capacity)
        make = lambda slots: ScalarMailbox(self.context, slots)
        # Exact finite qualification envelope; budgets account for the complete
        # no-ACK episode, not an arbitrary image-size or GPU/RAM restriction.
        fact_bound = sum((configuration.capacity.regular_slots, configuration.capacity.terminal_slots,
            configuration.capacity.application_slots, configuration.capacity.control_slots))
        job_bound = 2*configuration.capacity.admission_record_slots+2
        startup, jobs, numeric_facts, banks, cuts = (make(1), make(job_bound),
            make(fact_bound), make(job_bound), make(fact_bound))
        authority, normal, safety, ready, health, output = (make(32), make(32), make(32),
            make(job_bound), make(32), make(self.packet_bound))
        self._startup, self._jobs, self._numeric_facts, self._banks, self._cuts = (
            _Wire(link, self.nonce) for link in (startup, jobs, numeric_facts, banks, cuts))
        self._authority, self._normal, self._safety, self._ready, self._health, self._output = (
            _Wire(link, self.nonce) for link in (authority, normal, safety, ready, health, output))
        self.retained = RetainedCells(configuration.ordinary_retained_cells, self.packet_bound)
        self.records, self.facts, self.numerical_cuts, self.dispatches = [], [], [], []
        self.state = self.science = None
        self._fault_sent = False
        self._numeric_pending, self._jobs_pending, self._ready_pending = deque(), deque(), deque()
        self._active_tick = None
        self._last_tick = self._last_ordinal = self._last_physical = 0
        self._last_num_ordinal = self._last_num_physical = self._last_num_total = 0
        self.numeric = self.context.Process(target=_numerical, name='vsem-private-numerical',
            args=(initial_settings, self.namespace, self.nonce,
                (startup, jobs, numeric_facts, banks, cuts), self.seed, str(self.directory),
                configuration.delay_per_fact_s, os.getpid(), configuration.capacity.graph_binding_slots))
        self.owner = None
        self.numeric.start()
        try:
            deadline = time.perf_counter()+30.
            while time.perf_counter() < deadline:
                item = self._startup.get()
                if item is not None:
                    self.science = t.exact(item[0], t.ScienceIdentity); break
                if not self.numeric.is_alive(): raise RuntimeError('Actual numerical startup failed')
                time.sleep(.005)
            if self.science is None: raise TimeoutError('Owned numerical science startup remains unknown')
            self.origin_ns = time.perf_counter_ns()
            self.owner = self.context.Process(target=_owner, name='vsem-private-physical-owner',
                args=(self.science, initial_settings, self.namespace, configuration.capacity, self.nonce,
                    (authority, normal, safety, ready, health, output), os.getpid(), configuration.period_ns,
                    self.origin_ns, self.packet_bound))
            self.owner.start()
        except BaseException:
            self.close(); raise

    def elapsed_ns(self): return time.perf_counter_ns()-self.origin_ns

    def submit(self, inputs):
        t.exact(inputs, t.EpisodeInputs)
        present = [name for name in ('authority', 'normal', 'stop') if getattr(inputs, name) is not None]
        if len(present) != 1 or any(getattr(inputs, name) is not None for name in ('bank_result', 'verified_ack', 'fault')):
            raise ValueError('One closed intent on its dedicated trusted lane required')
        wire = {'authority': self._authority, 'normal': self._normal, 'stop': self._safety}[present[0]]
        if not wire.put(inputs): raise BufferError('Ingress lane full; admission is unknown')

    def fault(self, reason):
        if self._fault_sent: return
        if not self._health.put(t.EpisodeFault(self.namespace, reason)):
            raise RuntimeError('Reserved private health lane unavailable')
        self._fault_sent = True

    def _retain(self, value, cell):
        self.retained.append(cell)  # exact bytes BEFORE any forwarding
        self.records.append(value)
        if isinstance(value, TickBegin):
            if self._active_tick is not None or value.tick_id != self._last_tick+1:
                raise ValueError('Missing/overlapping private tick witness')
            self._active_tick = value
        elif isinstance(value, EpisodeFact):
            if self._active_tick is None or value.issued_at_ns != self._active_tick.at_ns:
                raise ValueError('Fact lacks actual input/time witness')
            if value.episode_namespace != self.namespace or value.ordinal != self._last_ordinal+1:
                raise ValueError('Foreign/missing retained fact')
            if value.physical_sequence is not None:
                if value.physical_sequence != self._last_physical+1: raise ValueError('Missing physical exposure predecessor')
                self._last_physical = value.physical_sequence
            self._last_ordinal = value.ordinal
            self.facts.append(value); self._numeric_pending.append(value)
        elif isinstance(value, TickEnd):
            if (self._active_tick is None or value.tick_id != self._active_tick.tick_id or
                    value.state.now_ns != self._active_tick.at_ns or value.state.last_ordinal != self._last_ordinal or
                    value.state.physical_sequence != self._last_physical or value.state.verified_ordinal != 0):
                raise ValueError('Unretained/mislabeled private tick cut')
            self._last_tick = value.tick_id; self._active_tick = None
            self.state = value.state
            if value.bank_dispatch is not None:
                self.dispatches.append(value.bank_dispatch); self._jobs_pending.append(value.bank_dispatch)
        else: raise ValueError('Unknown owner output record')

    def refresh(self):
        if self.owner is None: return
        if not self.owner.is_alive(): raise RuntimeError('Actual physical owner died; private episode must close')
        if not self.numeric.is_alive(): self.fault('PROCESS_FAILURE')
        # Bounded launcher service; large native numerical work is never here.
        for _ in range(512):
            item = self._output.get()
            if item is None: break
            self._retain(*item)
        if self.retained.pressured: self.fault('SPOOL_CAPACITY')
        if self.numeric.is_alive():
            for pending, wire in ((self._jobs_pending, self._jobs), (self._numeric_pending, self._numeric_facts)):
                for _ in range(512):
                    if not pending or not wire.put(pending[0]): break
                    pending.popleft()
            for _ in range(512):
                item = self._banks.get()
                if item is None: break
                self._ready_pending.append(item[0])
            for _ in range(512):
                item = self._cuts.get()
                if item is None: break
                cut = t.exact(item[0], NumericalCut)
                if (cut.last_ordinal != self._last_num_ordinal+1 or cut.last_ordinal > self._last_ordinal or
                        cut.physical_sequence < self._last_num_physical or cut.physical_sequence > self._last_physical or
                        cut.episode_incident_pA_ns < self._last_num_total):
                    raise ValueError('Invalid actual numerical cut')
                fact = self.facts[cut.last_ordinal-1]
                expected_physical = fact.physical_sequence if fact.physical_sequence is not None else self._last_num_physical
                if cut.physical_sequence != expected_physical: raise ValueError('Numerical cut differs from its retained physical source')
                self._last_num_ordinal, self._last_num_physical, self._last_num_total = (
                    cut.last_ordinal, cut.physical_sequence, cut.episode_incident_pA_ns)
                self.numerical_cuts.append(cut)
        for _ in range(512):
            if not self._ready_pending or not self._ready.put(self._ready_pending[0]): break
            self._ready_pending.popleft()

    def wait(self, predicate, timeout_s=15.):
        deadline = time.perf_counter()+timeout_s
        while time.perf_counter() < deadline:
            self.refresh()
            if predicate(): return
            time.sleep(.005)
        raise TimeoutError('Private runtime observation timed out; physical outcome remains unknown')

    def close(self):
        owner = getattr(self, 'owner', None)
        if owner is not None and owner.is_alive():
            try:
                self.fault('PROCESS_FAILURE')
                self.wait(lambda: self.state is not None and self.state.phase == 'INTERLOCKED', 2.)
            finally:
                owner.terminate(); owner.join(5.)
        numeric = getattr(self, 'numeric', None)
        if numeric is not None and numeric.is_alive(): numeric.terminate()
        if numeric is not None and numeric.pid is not None:
            numeric.join(2.)
            if numeric.is_alive(): numeric.kill(); numeric.join(5.)
        if owner is not None and owner.pid is not None: owner.join(5.)

    def __enter__(self): return self
    def __exit__(self, *args): self.close()
