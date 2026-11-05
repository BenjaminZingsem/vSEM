"""New identified stage-aware grounded ledger,unchanged intrinsic probe physics."""
import hashlib
from pathlib import Path
from .core_cached_source import CoreCachedRegistry
from .human_episode_types import ScienceIdentity
from .human_mapped_response_source import _digest


def pins():
    root=Path(__file__).resolve().parent
    return {name:hashlib.sha256((root/name).read_bytes()).hexdigest()
        for name in ('interactive_stage_source.py','interactive_stage_ledger.py')}


class StageResponseRegistry(CoreCachedRegistry):
    def __init__(self,**kwargs):
        super().__init__(**kwargs);self.stage_source_pins=pins();old=self.science
        digest=_digest({'unchanged_intrinsic_source':old.solver_source_digest,'stage_ledger':self.stage_source_pins})
        self.science=ScienceIdentity(old.profile_id,old.specimen_digest,old.grid_digest,old.vector_mode,digest,old.count_model_id)
        self.builder.identity=self.science

    def prepare(self,ticket):
        if pins()!=self.stage_source_pins:raise ValueError('actual-pose ledger source changed')
        return super().prepare(ticket)
