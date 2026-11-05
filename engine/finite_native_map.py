"""Fixed lattice evaluation of stored finite shapes;empty tiles share zero data.

These are derived field caches. They contain no newly generated specimen
elements and never change the immutable catalogue or its physical bounds.
"""
from collections import OrderedDict
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from .hierarchical_native_map import HierarchicalNativeMap,CELLS
from .finite_gpu_world import GpuFiniteWorld


class FiniteNativeMap(HierarchicalNativeMap):
    def __init__(self,world,*,spacing_m,cache_bytes):
        if type(world) is not GpuFiniteWorld:raise ValueError('exact immutable finite GPU world required')
        if type(spacing_m) is not float or spacing_m not in (.625e-9,1.25e-9):raise ValueError('qualified native spacing required')
        self.tile_bytes=4*(CELLS+1)**2*8
        if type(cache_bytes) is not int or cache_bytes<self.tile_bytes:raise ValueError('actual measured cache allowance required')
        self.world=world;self.specimen=world;self.spacing=spacing_m;self.budget=cache_bytes
        self.cache=OrderedDict();self.resident_bytes=0;self.generated_tiles=0;self.loaded_tiles=0;self.empty_tiles=0
        self.max_grid_index=math.floor(math.nextafter(.055,0.)/spacing_m)
        self.zero_tile=np.zeros((4,CELLS+1,CELLS+1),dtype=np.float64);self.zero_tile.setflags(write=False)
        self.identity={'protocol':'vsem.private.finite-native-chunks.v1','finite_world':world.identity_digest,
            'spacing_hex':spacing_m.hex(),'tile_cells':CELLS,'interpolation':'positive-bilinear-global-lattice',
            'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'inherited_source_sha256':hashlib.sha256((Path(__file__).parent/'hierarchical_native_map.py').read_bytes()).hexdigest(),
            'new_specimen_elements':False,'counts_dose_or_live_state_cached':False}
        self.identity_digest=hashlib.sha256(json.dumps(self.identity,sort_keys=True,separators=(',',':')).encode()).hexdigest()

    def _remember(self,key,tile):
        if tile.shape!=(4,CELLS+1,CELLS+1) or not np.isfinite(tile).all():raise ValueError('complete finite field tile required')
        if np.any(np.abs(tile[0])>.55e-6) or np.any(tile[3]<0.) or np.any(tile[3]>.32):raise ValueError('finite material field bounds')
        tile.setflags(write=False)
        if key in self.cache:self.cache.pop(key);self.resident_bytes-=self.tile_bytes
        while self.resident_bytes+self.tile_bytes>self.budget:
            self.cache.popitem(last=False);self.resident_bytes-=self.tile_bytes
        self.cache[key]=tile;self.resident_bytes+=self.tile_bytes

    def _tiles(self,keys):
        a,b,c,d=self.world.catalog.header.bounds_m;pending=[];span=CELLS*self.spacing
        for key in keys:
            x,y=key[0]*span,key[1]*span
            if x>b or x+span<a or y>d or y+span<c:
                self.empty_tiles+=1;yield key,self.zero_tile
            else:pending.append(key)
        yield from super()._tiles(pending)
