"""Private actual processes with complete causal certificates before numerics.
No actor ACK/continuous credit reuse/public listener is enabled by this class.
The original accepted private runtime and all frozen inputs remain unchanged.
"""
from collections import deque
import multiprocessing as mp
import os
from pathlib import Path
import secrets
import time
from engine import human_episode_types as t
from engine.human_episode_facts import EpisodeFact
from runtime.human_realtime_records import TickBegin,TickEnd
from runtime.human_realtime_kernel import (PrivateRealtimeKernel,PrivateKernelConfiguration,
    _Wire,_numerical,RetainedCells,lifetime_packet_bound,MAX_TICK_CELLS)
from runtime.grounded_mailbox import ScalarMailbox
from runtime.human_causal_verifier import HumanCausalVerifier


def _checked_owner(science, initial_settings, namespace, capacity, nonce, links, parent_pid,
           period_ns, origin_ns, packet_allowance):
    # Spawned owner imports this module's scalar closure, never NumPy or a source
    # graph. No filesystem writes, Pipe.send, multiprocessing.Queue or feeders.
    from engine.human_verified_episode import GroundedEpisode
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



class CheckedRealtimeKernel(PrivateRealtimeKernel):
    """Retains a whole actual tick before verification/numerical forwarding.

    causal_cut is the only verified physical view. Inherited state is private
    unverified forensic data and must never become a public projection. No ACK
    is generated here; later continuous credit/spool reuse is a separate gate.
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
            self.verifier = HumanCausalVerifier(self.science, initial_settings,
                episode_namespace=self.namespace, capacity=configuration.capacity)
            self.causal_cut = None; self.causal_error = None
            self._candidate_begin = None; self._candidate_facts = []
            self.origin_ns = time.perf_counter_ns()
            self.owner = self.context.Process(target=_checked_owner, name='vsem-private-physical-owner',
                args=(self.science, initial_settings, self.namespace, configuration.capacity, self.nonce,
                    (authority, normal, safety, ready, health, output), os.getpid(), configuration.period_ns,
                    self.origin_ns, self.packet_bound))
            self.owner.start()
        except BaseException:
            self.close(); raise

    def _retain(self, value, cell):
        # Retain exact bytes before checking/forwarding;remove speculative
        # forwards before refresh can service the numerical mailbox.
        super()._retain(value, cell)
        if type(value) is TickBegin:
            self._candidate_begin = value; self._candidate_facts = []
        elif type(value) is EpisodeFact:
            if self._numeric_pending.pop() is not value:
                raise RuntimeError('Speculative numerical forwarding order changed')
            self._candidate_facts.append(value)
        elif type(value) is TickEnd:
            if value.bank_dispatch is not None:
                if self._jobs_pending.pop() is not value.bank_dispatch:
                    raise RuntimeError('Speculative source forwarding order changed')
            if self.causal_error is not None: return
            try:
                cut = self.verifier.verify(self._candidate_begin, tuple(self._candidate_facts), value)
            except Exception as exc:
                self.causal_error = type(exc).__name__+': '+str(exc)
                self.fault('CAUSAL_FAILURE')
                return
            self.causal_cut = cut
            self._numeric_pending.extend(self._candidate_facts)
            if value.bank_dispatch is not None: self._jobs_pending.append(value.bank_dispatch)

