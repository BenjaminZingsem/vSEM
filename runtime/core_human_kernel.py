"""Continuous private SEM path:retained causal ACK,actual numerics,sweep pacing.

No public listener/authentication is provided here. Journal writes are buffered
development retention,not fsync/crash-durable replay. One owner clock remains
independent of launcher IO and image processing. No science graph enters it.
"""
from collections import deque
from dataclasses import dataclass
import ctypes
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import secrets
import time

from engine import human_episode_types as t
from engine.human_episode_facts import EpisodeFact
from engine.episode_credits import EpisodeCapacity
from .grounded_mailbox import ScalarMailbox,CELL_BYTES
from .human_reserved_mailbox import ReservedMailbox
from .human_live_codec import encode_cell,decode_cell
from .human_live_records import LiveTickBegin,SweepDelivery,NativeImageReady
from .human_realtime_records import TickEnd,NumericalCut
from .human_paced_verifier import PacedCausalVerifier
from .core_human_numerics import numerical_worker

TICK_CELLS = 34


class Wire:
    def __init__(self,mailbox,nonce):
        self.mailbox,self.nonce = mailbox,nonce
        self.sent = self.received = 0
    def put(self,value):
        if not self.mailbox.try_put(encode_cell(value,self.nonce,self.sent+1)): return False
        self.sent += 1; return True
    def get(self):
        cell = self.mailbox.try_get()
        if cell is None: return None
        value = decode_cell(cell,self.nonce,self.received+1)
        self.received += 1; return value,cell
    def commit(self,reservation,values):
        if len(values) > reservation.remaining: raise ValueError('Unreserved live output batch')
        for value in values:
            reservation.commit(encode_cell(value,self.nonce,self.sent+1)); self.sent += 1
        reservation.close()


def owner_worker(science,settings,namespace,capacity,nonce,links,parent_pid,period_ns,origin_ns):
    from engine.human_paced_episode import GroundedEpisode
    owner = GroundedEpisode(science,settings,episode_namespace=namespace,capacity=capacity)
    authority,normal,safety,ready,health,ack,delivery,output = (Wire(link,nonce) for link in links)
    terminal = output.mailbox.reserve(TICK_CELLS)
    if terminal is None: raise RuntimeError('Prior safe output reservation unavailable')
    tick_id = 0; next_service = time.perf_counter_ns()
    while True:
        current = time.perf_counter_ns()
        if current < next_service:
            time.sleep(min((next_service-current)/1e9,.001)); continue
        next_service = current+period_ns
        if owner.interlock is not None:
            if os.getppid() != parent_pid: return
            time.sleep(.001); continue
        values = [wire.get() for wire in (authority,normal,safety,ready,health,ack,delivery)]
        auth,command,stop,bank,fault,acknowledgement,delivered = [item[0] if item else None for item in values]
        reservation = output.mailbox.reserve(TICK_CELLS)
        if reservation is None:
            reservation = terminal; terminal = None
            fault = t.EpisodeFault(namespace,'SPOOL_CAPACITY')
        if os.getppid() != parent_pid: fault = t.EpisodeFault(namespace,'PROCESS_FAILURE')
        for value,field in ((auth,'authority'),(command,'normal'),(stop,'stop')):
            if value is not None:
                t.exact(value,t.EpisodeInputs)
                if getattr(value,field) is None or any(getattr(value,name) is not None for name in
                    ('authority','normal','stop','bank_result','verified_ack','fault') if name != field):
                    raise ValueError('Cross-lane live ingress')
        inputs = t.EpisodeInputs(authority=auth.authority if auth else None,normal=command.normal if command else None,
            stop=stop.stop if stop else None,bank_result=bank,verified_ack=acknowledgement,fault=fault)
        at = time.perf_counter_ns()-origin_ns
        result = owner.tick(at,inputs,delivered)
        if not (result.facts or result.bank_dispatch or any(item is not None for item in values) or fault):
            reservation.close(); continue
        tick_id += 1
        records = (LiveTickBegin(tick_id,at,inputs,delivered),*result.facts,
            TickEnd(tick_id,result.state,result.bank_dispatch,result.started_raster_ids,result.ended_raster_ids))
        if len(records) > TICK_CELLS: raise RuntimeError('Frozen mixed source envelope violated')
        output.commit(reservation,records)


def available_memory():
    if os.name == 'nt':
        class Memory(ctypes.Structure):
            _fields_ = [('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(name,ctypes.c_ulonglong) for name in
                ('total_phys','avail_phys','total_page','avail_page','total_virtual','avail_virtual','avail_extended')]
        value = Memory(); value.length = ctypes.sizeof(value)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)): raise OSError('Actual RAM query failed')
        return int(value.avail_phys)
    rows = dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    return int(rows['MemAvailable'].split()[0])*1024


def emergency_cells(capacity,output_slots):
    """All source credits,witnesses,two in-flight coalesced ACKs and terminal.

    One ACK cell may be read by the actor while another is queued. Each can
    release at most the complete four-lane capacity. Three cells/fact cover
    fact plus both tick witnesses. The physical health lane fences at its next
    service;the conservative allowance does not assume that parent's observation
    and actor service happen on the same tick. Owned bank/ACK-only boundary
    witnesses and the entire output ring are also covered.
    """
    total = sum((capacity.regular_slots,capacity.terminal_slots,capacity.application_slots,capacity.control_slots))
    return output_slots+9*total+128+2*TICK_CELLS


class RetainedSpool:
    def __init__(self,ordinary,reserve):
        self.ordinary,self.reserve = ordinary,reserve
        self.groups = deque(); self.cells = 0; self.pressured = False
    def retain(self,cells,ordinal):
        if self.cells+len(cells) > self.ordinary+self.reserve: raise RuntimeError('Complete emergency spool allowance exhausted')
        self.groups.append((ordinal,tuple(cells))); self.cells += len(cells)
        if self.cells >= self.ordinary: self.pressured = True
    def consume(self,numerical_ordinal):
        while self.groups and self.groups[0][0] <= numerical_ordinal:
            _,cells = self.groups.popleft(); self.cells -= len(cells)


@dataclass(frozen=True)
class LiveKernelConfiguration:
    capacity: EpisodeCapacity
    period_ns: int = 5_000_000
    ordinary_spool_cells: object = None
    delay_per_fact_s: float = 0.
    image_period_s: float = 1.

    def __post_init__(self):
        t.exact(self.capacity,EpisodeCapacity); t.integer(self.period_ns,1_000_000,100_000_000)
        if self.ordinary_spool_cells is not None: t.integer(self.ordinary_spool_cells,1)
        t.real(self.delay_per_fact_s,0.,10.); t.real(self.image_period_s,.05,60.)


class LiveRealtimeKernel:
    """Trusted single-thread service primitive. Public adapters must serialize it.

    causal_cut is verified physical state;numeric progress is independent. A
    trusted service loop must call refresh independently of operator requests.
    No authentication or evaluated-agent confinement claim is made here.
    """
    def __init__(self,directory,initial_settings,configuration,*,seed=None):
        t.exact(initial_settings,t.EpisodeSettings); t.exact(configuration,LiveKernelConfiguration)
        self.directory = Path(directory).resolve(); self.directory.mkdir(parents=True,exist_ok=False)
        self.initial_settings,self.configuration = initial_settings,configuration
        self.namespace = 'live-'+secrets.token_hex(8); self.nonce = secrets.token_bytes(16)
        self.seed = secrets.token_bytes(32) if seed is None else seed
        if type(self.seed) is not bytes or len(self.seed) != 32: raise ValueError('Private32-byte count key required')
        self.context = mp.get_context('spawn'); cap = configuration.capacity
        total = sum((cap.regular_slots,cap.terminal_slots,cap.application_slots,cap.control_slots))
        self.output_slots = max(2*TICK_CELLS,3*total+128)
        reserve = emergency_cells(cap,self.output_slots); free = available_memory()
        ordinary = configuration.ordinary_spool_cells or max(1024,int(free*.05/(2*CELL_BYTES)))
        if 2*CELL_BYTES*(ordinary+reserve+self.output_slots) > free*.5:
            raise MemoryError('Declared complete retention reservation does not fit actual available RAM')
        self.spool = RetainedSpool(ordinary,reserve)
        make = lambda count: ScalarMailbox(self.context,count)
        startup,jobs,facts,banks,cuts,images = make(1),make(2),make(total),make(2),make(total),make(32)
        authority,normal,safety,ready,health,ack,delivery = make(32),make(32),make(32),make(2),make(2),make(1),make(1)
        output = ReservedMailbox(self.context,self.output_slots)
        self._startup,self._jobs,self._facts,self._banks,self._cuts,self._images = (Wire(link,self.nonce) for link in
            (startup,jobs,facts,banks,cuts,images))
        self._authority,self._normal,self._safety,self._ready,self._health,self._ack,self._delivery,self._output = (
            Wire(link,self.nonce) for link in (authority,normal,safety,ready,health,ack,delivery,output))
        self._numeric_pending,self._jobs_pending,self._ready_pending,self._delivery_pending = deque(),deque(),deque(),deque()
        self._ack_pending = None; self._last_ack_sent = 0; self._fault_sent = False
        self._candidate_begin = None; self._candidate_facts,self._candidate_cells = [],[]
        self._last_tick = self._last_ordinal = self._last_physical = 0
        self._last_num_ordinal = self._last_num_physical = self._last_num_total = 0
        self._pending_fact_index = {}; self._capture_ends = {}; self._terminal_cuts = {}; self._images_waiting = deque()
        self.causal_cut = self.causal_error = self.state = self.science = None
        self.numerical_cuts = []; self.native_images = []; self.dispatches = []
        self._journal = (self.directory/'owner.cells').open('xb',buffering=1024*1024)
        self.numeric = self.context.Process(target=numerical_worker,name='vsem-live-numerical',args=(initial_settings,self.namespace,
            self.nonce,(startup,jobs,facts,banks,cuts,images),self.seed,str(self.directory),configuration.delay_per_fact_s,
            os.getpid(),cap.graph_binding_slots,configuration.image_period_s))
        self.owner = None; self.numeric.start()
        try:
            deadline = time.perf_counter()+30.
            while time.perf_counter() < deadline:
                item = self._startup.get()
                if item is not None: self.science = t.exact(item[0],t.ScienceIdentity); break
                if not self.numeric.is_alive(): raise RuntimeError('Actual live numerical startup failed')
                time.sleep(.005)
            if self.science is None: raise TimeoutError('Numerical startup remains unknown')
            self.verifier = PacedCausalVerifier(self.science,initial_settings,episode_namespace=self.namespace,capacity=cap)
            self.origin_ns = time.perf_counter_ns()
            self.owner = self.context.Process(target=owner_worker,name='vsem-live-physical',args=(self.science,initial_settings,
                self.namespace,cap,self.nonce,(authority,normal,safety,ready,health,ack,delivery,output),os.getpid(),
                configuration.period_ns,self.origin_ns))
            self.owner.start()
        except BaseException:
            self.close(); raise

    def elapsed_ns(self): return time.perf_counter_ns()-self.origin_ns

    def submit(self,inputs):
        t.exact(inputs,t.EpisodeInputs)
        present = [name for name in ('authority','normal','stop') if getattr(inputs,name) is not None]
        if len(present) != 1 or any(getattr(inputs,name) is not None for name in ('bank_result','verified_ack','fault')):
            raise ValueError('One closed trusted intent,not private verification/source data')
        wire = {'authority':self._authority,'normal':self._normal,'stop':self._safety}[present[0]]
        if not wire.put(inputs): raise BufferError('Live ingress full;admission remains unknown')

    def fault(self,reason):
        if self._fault_sent: return
        if not self._health.put(t.EpisodeFault(self.namespace,reason)): raise RuntimeError('Reserved health lane unavailable')
        self._fault_sent = True; self._ack_pending = None

    def _retain(self,value,cell):
        self._candidate_cells.append(cell)
        if type(value) is LiveTickBegin:
            if self._candidate_begin is not None or value.tick_id != self._last_tick+1: raise ValueError('Missing/overlapping live tick')
            self._candidate_begin = value; self._candidate_facts = []
        elif type(value) is EpisodeFact:
            if self._candidate_begin is None or value.issued_at_ns != self._candidate_begin.at_ns:
                raise ValueError('Live fact lacks actual input/time witness')
            if value.episode_namespace != self.namespace or value.ordinal != self._last_ordinal+1: raise ValueError('Foreign/missing live fact')
            if value.physical_sequence is not None:
                if value.physical_sequence != self._last_physical+1: raise ValueError('Missing physical live predecessor')
                self._last_physical = value.physical_sequence
            self._last_ordinal = value.ordinal; self._candidate_facts.append(value)
        elif type(value) is TickEnd:
            if self._candidate_begin is None or value.tick_id != self._candidate_begin.tick_id: raise ValueError('Missing live tick closure')
            self.spool.retain(self._candidate_cells,value.state.last_ordinal)
            if self.spool.pressured: self.fault('SPOOL_CAPACITY')
            self._journal.write(b''.join(self._candidate_cells))  # before ANY ACK
            self.state = value.state; self._last_tick = value.tick_id
            if self.causal_error is None:
                try: cut = self.verifier.verify(self._candidate_begin,tuple(self._candidate_facts),value)
                except Exception as exc:
                    self.causal_error = type(exc).__name__+': '+str(exc); self.fault('CAUSAL_FAILURE')
                else:
                    self.causal_cut = cut
                    for fact in self._candidate_facts:
                        self._numeric_pending.append(fact); self._pending_fact_index[fact.ordinal] = fact
                        if fact.kind == 'RASTER_END': self._capture_ends[fact.body[0]] = fact
                    if value.bank_dispatch is not None:
                        self.dispatches.append(value.bank_dispatch); self._jobs_pending.append(value.bank_dispatch)
                    if not self._fault_sent and cut.last_ordinal > self._last_ack_sent:
                        self._ack_pending = t.VerifiedAcknowledgement(self.namespace,cut.last_ordinal)
            self._candidate_begin = None; self._candidate_facts,self._candidate_cells = [],[]
        else: raise ValueError('Unknown live owner record')

    def _numerical_cut(self,cut):
        t.exact(cut,NumericalCut)
        if cut.last_ordinal != self._last_num_ordinal+1 or self.causal_cut is None or cut.last_ordinal > self.causal_cut.last_ordinal:
            raise ValueError('Numerical cut exceeds complete retained causal source')
        fact = self._pending_fact_index.pop(cut.last_ordinal)
        physical = fact.physical_sequence if fact.physical_sequence is not None else self._last_num_physical
        expected_total = self._last_num_total+(fact.body[8] if fact.kind == 'PREFIX' else 0)
        if cut.physical_sequence != physical or cut.episode_incident_pA_ns != expected_total:
            raise ValueError('Numerical cut differs from exact source charge/physical sequence')
        self._last_num_ordinal,self._last_num_physical,self._last_num_total = cut.last_ordinal,physical,expected_total
        self.numerical_cuts.append(cut); self.spool.consume(cut.last_ordinal)
        if cut.se_raw_sha256 is not None:
            if fact.kind != 'RASTER_END' or fact.body[0] != cut.causal_raster_id: raise ValueError('Forged terminal numerical delivery')
            self._terminal_cuts[cut.causal_raster_id] = cut

    def read_image(self,ready):
        t.exact(ready,NativeImageReady)
        if ready.numerical_ordinal > self._last_num_ordinal: raise ValueError('Image is not numerically committed')
        folder = self.directory/ready.image_id
        raw = (folder/'metadata.json').read_bytes()
        if hashlib.sha256(raw).hexdigest() != ready.metadata_sha256: raise ValueError('Immutable image metadata changed')
        metadata = json.loads(raw)
        if (metadata['image_id'],metadata['causal_raster_id'],metadata['numerical_ordinal'],metadata['physical_sequence']) != (
                ready.image_id,ready.causal_raster_id,ready.numerical_ordinal,ready.physical_sequence): raise ValueError('Image cut rebound')
        channels = {}
        size = metadata['configuration']['geometry']['width_px']*metadata['configuration']['geometry']['height_px']*4
        for name in ('SE','BSE'):
            data = (folder/(name+'.uint32')).read_bytes()
            if len(data) != size or hashlib.sha256(data).hexdigest() != metadata['counts_sha256'][name]: raise ValueError('Native count artifact changed')
            channels[name] = data
        return metadata,channels

    def refresh(self):
        if self.owner is None: return
        if not self.owner.is_alive(): raise RuntimeError('Actual live owner died;episode quarantined')
        if not self.numeric.is_alive(): self.fault('PROCESS_FAILURE')
        for _ in range(512):
            item = self._output.get()
            if item is None: break
            self._retain(*item)
        if self.numeric.is_alive():
            for pending,wire in ((self._jobs_pending,self._jobs),(self._numeric_pending,self._facts)):
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
                self._numerical_cut(item[0])
            for _ in range(32):
                item = self._images.get()
                if item is None: break
                self._images_waiting.append(t.exact(item[0],NativeImageReady))
        for pending,wire in ((self._ready_pending,self._ready),(self._delivery_pending,self._delivery)):
            for _ in range(32):
                if not pending or not wire.put(pending[0]): break
                pending.popleft()
        if self._ack_pending is not None and not self._fault_sent and self._ack.put(self._ack_pending):
            self._last_ack_sent = self._ack_pending.last_ordinal; self._ack_pending = None
        while self._images_waiting and self._images_waiting[0].numerical_ordinal <= self._last_num_ordinal:
            ready = self._images_waiting.popleft(); metadata,channels = self.read_image(ready)
            terminal = self._terminal_cuts.get(ready.causal_raster_id)
            if metadata['outcome'] != 'ACQUIRING':
                if (terminal is None or terminal.last_ordinal != ready.numerical_ordinal or
                        metadata['counts_sha256'] != {'SE':terminal.se_raw_sha256,'BSE':terminal.bse_raw_sha256}):
                    raise ValueError('Terminal image lacks actual numerical delivery proof')
                delivery = SweepDelivery(self.namespace,ready.causal_raster_id,ready.numerical_ordinal)
                self.verifier.register_delivery(delivery); self._delivery_pending.append(delivery)
            self.native_images.append(ready)

    def wait(self,predicate,timeout_s=20.):
        deadline = time.perf_counter()+timeout_s
        while time.perf_counter() < deadline:
            self.refresh()
            if predicate(): return
            time.sleep(.005)
        raise TimeoutError('Live observation timeout;physical outcome remains unknown')

    def close(self):
        owner = getattr(self,'owner',None)
        if owner is not None and owner.is_alive():
            try:
                self.fault('PROCESS_FAILURE')
                self.wait(lambda:self.state is not None and self.state.phase == 'INTERLOCKED',2.)
            finally: owner.terminate(); owner.join(5.)
        numeric = getattr(self,'numeric',None)
        if numeric is not None and numeric.is_alive(): numeric.terminate()
        if numeric is not None and numeric.pid is not None:
            numeric.join(2.)
            if numeric.is_alive(): numeric.kill(); numeric.join(5.)
        journal = getattr(self,'_journal',None)
        if journal is not None and not journal.closed:
            if self._candidate_cells: journal.write(b''.join(self._candidate_cells))
            journal.close()

    def __enter__(self): return self
    def __exit__(self,*args): self.close()
