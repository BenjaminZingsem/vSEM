"""Private hierarchy/actual-pose registry;not selected by a human service yet.

Only immutable intrinsic response preparation changes. Original photon-prefix,
actual-pose ledger,primary fluence,ordered timing and separate transports remain
qualified independently. This reference is explicitly IDEAL_GROUNDED;private
material codes do not become activated charging or damage by being present.
"""
import hashlib
from pathlib import Path
from .interactive_stage_source import StageResponseRegistry
from .human_episode_types import ScienceIdentity
from .human_mapped_response_source import _digest


def hierarchy_source_pins():
    root=Path(__file__).resolve().parent
    names=('hierarchical_source.py','hierarchical_image_ledger.py','hierarchical_probe.py','hierarchical_gpu_world.py',
        'hierarchical_gpu_fields.py','hierarchical_native_map.py','hierarchical_specimen.py',
        'analytic_probe.py','chunked_probe.py')
    pins={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names}
    for name in ('batched_valid_convolution.py','compact_feature_cuda_runtime.py','gaussian_tensor_grid.py'):
        pins['packages/numerics/'+name]=hashlib.sha256((root.parent/'packages/numerics'/name).read_bytes()).hexdigest()
    return pins


class HierarchicalResponseRegistry(StageResponseRegistry):
    def __init__(self,*,spacing_m=.625e-9,**kwargs):
        from .hierarchical_probe import HierarchicalProbeBuilder
        super().__init__(**kwargs)
        self.builder=HierarchicalProbeBuilder(spacing_m=spacing_m)
        self.world=self.builder.world
        self.hierarchy_pins=hierarchy_source_pins();old=self.science
        self.science=ScienceIdentity(old.profile_id,self.builder.world.identity_digest,
            _digest({'primary_cell_size_hex':self.cell_size_m.hex(),
                'immutable_hybrid_identity':self.builder.identity,'frame':'fixed-specimen-metres-y-up'}),
            old.vector_mode,_digest({'existing_ledger_count_and_stage':old.solver_source_digest,
                'hierarchy':self.hierarchy_pins,'hybrid_identity':self.builder.identity}),old.count_model_id)
        self.builder.memo.identity=self.science

    def prepare(self,ticket):
        if hierarchy_source_pins()!=self.hierarchy_pins:raise ValueError('hierarchical source changed after science binding')
        return super().prepare(ticket)

    def close(self):self.builder.close()
