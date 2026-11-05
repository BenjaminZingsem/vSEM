"""Bounded immutable beam-bank reuse for the fixed grounded core human scenario.

No counts,noise,dose,physical time or acquired images are cached. Keys include
every physical geometry/setting plus the immutable registry/world identity.
"""
from collections import OrderedDict
from dataclasses import replace
import hashlib
from pathlib import Path
import time
from .human_cached_source import CachedResponseRegistry
from .human_specimen_map import available_memory_bytes
from .human_episode_types import ScienceIdentity
from .human_mapped_response_source import _digest

def core_pin():return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

class MemoizedBuilder:
    def __init__(self,builder,identity,*,budget=None):
        self.builder=builder;self.identity=identity;self.budget=available_memory_bytes()//4 if budget is None else budget
        if type(self.budget) is not int or self.budget<1:raise ValueError('positive measured cache allowance required')
        self.cache=OrderedDict();self.resident=0;self.hits=0;self.misses=0
    def build(self,geometry,settings):
        start=time.perf_counter();key=(self.identity,geometry._key(),settings._key())
        if key in self.cache:
            bank=self.cache.pop(key);self.cache[key]=bank;self.hits+=1
            return replace(bank,construction_s=time.perf_counter()-start)
        bank=self.builder.build(geometry,settings);self.misses+=1
        size=sum(value.nbytes for value in (bank.se_emitted_per_incident,bank.se_collected_per_incident,bank.surface_height_m))
        if size<=self.budget:
            while self.resident+size>self.budget:
                _,old=self.cache.popitem(last=False)
                self.resident-=sum(v.nbytes for v in (old.se_emitted_per_incident,old.se_collected_per_incident,old.surface_height_m))
            self.cache[key]=bank;self.resident+=size
        return bank

class CoreCachedRegistry(CachedResponseRegistry):
    def __init__(self,**kwargs):
        super().__init__(**kwargs);self.core_source_pin=core_pin();old=self.science
        self.science=ScienceIdentity(old.profile_id,old.specimen_digest,old.grid_digest,old.vector_mode,
            _digest({'previous_source':old.solver_source_digest,'immutable_bank_reuse':self.core_source_pin}),old.count_model_id)
        self.builder=MemoizedBuilder(self.builder,self.science)
    def prepare(self,ticket):
        if core_pin()!=self.core_source_pin:raise ValueError('changed immutable bank cache source')
        return super().prepare(ticket)
