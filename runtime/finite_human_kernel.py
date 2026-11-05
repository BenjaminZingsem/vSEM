"""Finite numerical startup;original physical actor and all kernel methods reused."""
from collections import deque
import multiprocessing as mp
import os
from pathlib import Path
import secrets
import time
from engine import human_episode_types as t
from .grounded_mailbox import ScalarMailbox,CELL_BYTES
from .human_reserved_mailbox import ReservedMailbox
from .interactive_stage_verifier import PacedCausalVerifier
from .hierarchical_human_kernel import (LiveRealtimeKernel as BaseKernel,LiveKernelConfiguration,
    Wire,RetainedSpool,available_memory,emergency_cells,owner_worker,TICK_CELLS)
from .finite_launch_spec import FrozenFiniteLaunch
from .finite_human_numerics import numerical_worker


class FiniteLiveRealtimeKernel(BaseKernel):
    def __init__(self,directory,initial_settings,configuration,*,finite_catalogue,seed=None):
        t.exact(finite_catalogue,FrozenFiniteLaunch)
        finite_catalogue.__post_init__()  # Revalidate frozen header at startup.
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
            os.getpid(),cap.graph_binding_slots,configuration.image_period_s,finite_catalogue))
        self.owner = None; self.numeric.start()
        try:
            deadline = time.perf_counter()+600.
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
