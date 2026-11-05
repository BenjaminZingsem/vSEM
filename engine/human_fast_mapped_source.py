"""Explicit new count protocol with unchanged mapped beam/primary physics."""
import hashlib
import json
from pathlib import Path
from .human_mapped_response_source import MappedResponseRegistry
from .human_episode_types import ScienceIdentity
from .human_photon_prefix import PROTOCOL

def fast_pins():
    folder=Path(__file__).resolve().parent
    return {name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in
        ('human_photon_prefix.py','human_fast_mapped_source.py','human_fast_mapped_ledger.py')}

class FastMappedResponseRegistry(MappedResponseRegistry):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.count_pins=fast_pins()
        digest=hashlib.sha256(json.dumps({'unchanged_physics':self.pins,'count_variant':self.count_pins},
            sort_keys=True,separators=(',',':')).encode()).hexdigest()
        old=self.science
        self.science=ScienceIdentity(old.profile_id,old.specimen_digest,old.grid_digest,
            old.vector_mode,digest,PROTOCOL)
    def prepare(self,ticket):
        if fast_pins()!=self.count_pins:raise ValueError('New photon source changed before preparation')
        return super().prepare(ticket)
