"""Actual cached preparation for the fixed grounded human image/tape source."""
import hashlib
from pathlib import Path
from .human_cached_probe import CachedProbeBuilder
from .human_live_mapped_source import LiveMappedResponseRegistry,projection_pin
from .human_fast_mapped_source import fast_pins
from .human_mapped_response_source import source_identity,ResolvedMappedSource,_digest
from .human_episode_types import ScienceIdentity,BankTicket,ScalarBankHandle,BankReady,exact

def cache_pins():
    folder=Path(__file__).resolve().parent
    return {name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in
            ('human_cached_probe.py','human_cached_source.py')}

class CachedResponseRegistry(LiveMappedResponseRegistry):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.builder=CachedProbeBuilder(self.world);self.cache_source_pins=cache_pins()
        old=self.science
        digest=_digest({'previous_source':old.solver_source_digest,'cached_variant':self.cache_source_pins})
        self.science=ScienceIdentity(old.profile_id,old.specimen_digest,old.grid_digest,
            old.vector_mode,digest,old.count_model_id)

    def prepare(self,ticket):
        exact(ticket,BankTicket)
        if (ticket.science!=self.science or ticket.custodian_generation!=self.generation or
                source_identity()!=self.pins or fast_pins()!=self.count_pins or
                projection_pin()!=self.image_projection_pin or cache_pins()!=self.cache_source_pins):
            raise ValueError('Foreign/changed cached scientific source or generation')
        old=self._tickets.get(ticket.job_id)
        if old is not None:
            if old[0]!=ticket:raise ValueError('Owned cached job identity rebound')
            return BankReady(ticket,old[1])
        if len(self._bindings)>=self.capacity:raise ValueError('Trusted cached binding allowance exhausted')
        bank=self.builder.build(ticket.configuration.geometry,ticket.settings)
        descriptor=_digest({'bank':bank.source_identity,'science':self.science.solver_source_digest,
                            'dwell_ns':ticket.configuration.dwell_ns})
        handle=ScalarBankHandle('cached-'+str(len(self._bindings)+1),self.generation,descriptor,
            self.science.solver_source_digest,ticket.configuration.geometry,ticket.settings)
        self._bindings[handle.handle_id]=ResolvedMappedSource(handle,bank,self.cell_size_m)
        self._tickets[ticket.job_id]=(ticket,handle)
        return BankReady(ticket,handle)
