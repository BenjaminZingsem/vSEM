"""Source seal includes the grounded image/tape projection variant."""
import hashlib
from pathlib import Path
from .human_fast_mapped_source import FastMappedResponseRegistry
from .human_episode_types import ScienceIdentity

def projection_pin():
    folder=Path(__file__).resolve().parent
    return hashlib.sha256((folder/'human_live_image_ledger.py').read_bytes()+
        (folder/'human_live_mapped_source.py').read_bytes()).hexdigest()
class LiveMappedResponseRegistry(FastMappedResponseRegistry):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.image_projection_pin=projection_pin();old=self.science
        digest=hashlib.sha256((old.solver_source_digest+self.image_projection_pin).encode()).hexdigest()
        self.science=ScienceIdentity(old.profile_id,old.specimen_digest,old.grid_digest,
            old.vector_mode,digest,old.count_model_id)
    def prepare(self,ticket):
        if projection_pin()!=self.image_projection_pin:raise ValueError('Grounded image/tape source changed')
        return super().prepare(ticket)
