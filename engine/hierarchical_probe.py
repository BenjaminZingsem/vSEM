"""Private hybrid work selection over one fixed specimen;not runtime-selected.

Both numerical methods are independently identified expectations of the same
physical beam/analytic specimen. Dense native meshes and sparse positive normal
quadrature require cross-method convergence before human selection. No live
counts,dose,charge or damaged fields are retained in these intrinsic caches.
"""
import hashlib
import json
from pathlib import Path
from .hierarchical_gpu_world import GpuHierarchicalWorld
from .hierarchical_native_map import HierarchicalNativeMap
from .chunked_probe import ChunkedProbeBuilder,CHUNK_CELLS
from .analytic_probe import AnalyticProbeBuilder
from .core_cached_source import MemoizedBuilder
from .human_specimen_map import available_memory_bytes


class _HybridMath:
    def __init__(self,native,sparse):self.native,self.sparse=native,sparse
    def build(self,geometry,settings):
        # This is work selection,not a beam diameter or specimen-pixel average.
        # Full response/source hashes retain which quadrature actually ran.
        if geometry.pixel_size_m<=2*self.native.world.spacing*CHUNK_CELLS:
            return self.native.build(geometry,settings)
        return self.sparse.build(geometry,settings)


class HierarchicalProbeBuilder:
    def __init__(self,*,specimen=None,spacing_m=.625e-9):
        self.world=GpuHierarchicalWorld(specimen=specimen)
        free=available_memory_bytes()
        self.native_world=HierarchicalNativeMap(self.world,spacing_m=spacing_m,cache_bytes=int(free*.35))
        self.native=ChunkedProbeBuilder(self.native_world,cache_bytes=int(free*.35),device='cuda:0')
        self.sparse=AnalyticProbeBuilder(self.world)
        folder=Path(__file__).resolve().parent
        self.identity=hashlib.sha256(json.dumps({'world':self.world.identity_digest,
            'native':self.native_world.identity_digest,'native_source':self.native.pins,'sparse_source':self.sparse.pins,
            'selection_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'memoizer_sha256':hashlib.sha256((folder/'core_cached_source.py').read_bytes()).hexdigest()},
            sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.memo=MemoizedBuilder(_HybridMath(self.native,self.sparse),self.identity,budget=int(free*.15))

    def build(self,geometry,settings):return self.memo.build(geometry,settings)

    def close(self):
        self.memo.cache.clear();self.memo.resident=0
        self.native.close();self.native_world.cache.clear();self.native_world.resident_bytes=0
