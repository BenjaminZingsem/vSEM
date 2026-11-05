"""Bounded fixed-lattice chunks of the analytic hierarchy;private new variant.

Batch construction is independent of camera magnification. Immutable32-cell
tiles overlap by one native node,so arbitrary query order/eviction cannot redraw
the specimen. Cache residency/batches follow caller admission and actual memory.
"""
from collections import OrderedDict
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from .hierarchical_specimen import _admit
from .human_specimen_map import available_memory_bytes

CELLS=32


class HierarchicalNativeMap:
    def __init__(self,world,*,spacing_m,cache_bytes):
        from .hierarchical_gpu_world import GpuHierarchicalWorld
        if type(world) is not GpuHierarchicalWorld:raise ValueError('exact analytic GPU world required')
        if type(spacing_m) is not float or spacing_m not in (.625e-9,1.25e-9):raise ValueError('declared native spacing required')
        self.tile_bytes=4*(CELLS+1)**2*8
        if type(cache_bytes) is not int or cache_bytes<self.tile_bytes:raise ValueError('measured tile cache allowance required')
        self.world=world;self.specimen=world.specimen;self.spacing=spacing_m;self.budget=cache_bytes
        self.cache=OrderedDict();self.resident_bytes=0;self.generated_tiles=0;self.loaded_tiles=0
        self.max_grid_index=math.floor(math.nextafter(.055,0.)/spacing_m)
        self.identity={'protocol':'vsem.private.hierarchical-native-chunks.v1','analytic_world':world.identity_digest,
            'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'spacing_hex':spacing_m.hex(),'tile_cells':CELLS,'interpolation':'positive-bilinear-global-lattice',
            'noise_dose_or_live_state_cached':False}
        self.identity_digest=hashlib.sha256(json.dumps(self.identity,sort_keys=True,separators=(',',':')).encode()).hexdigest()

    def _remember(self,key,tile):
        if tile.shape!=(4,CELLS+1,CELLS+1) or not np.isfinite(tile).all():raise ValueError('complete finite native tile required')
        if np.any(np.abs(tile[0])>.55e-6) or np.any(tile[3]<.12) or np.any(tile[3]>.32):raise ValueError('native field physical bounds')
        tile.setflags(write=False)
        if key in self.cache:self.cache.pop(key);self.resident_bytes-=self.tile_bytes
        while self.resident_bytes+self.tile_bytes>self.budget:
            self.cache.popitem(last=False);self.resident_bytes-=self.tile_bytes
        self.cache[key]=tile;self.resident_bytes+=self.tile_bytes

    def _tiles(self,keys):
        import torch
        pending=[]
        for key in keys:
            if key in self.cache:
                tile=self.cache.pop(key);self.cache[key]=tile;self.loaded_tiles+=1
                yield key,tile
            else:pending.append(key)
        while pending:
            free,_=torch.cuda.mem_get_info()
            batch=int(min(free,available_memory_bytes())*.6//((CELLS+1)**2*2048))
            if batch<1:raise MemoryError('actual GPU/RAM cannot admit one native chunk')
            take=pending[:batch];del pending[:batch]
            kx=np.array([k[0] for k in take],dtype=np.int64)
            ky=np.array([k[1] for k in take],dtype=np.int64)
            axis=np.arange(CELLS+1,dtype=np.int64)
            ix=kx[:,None,None]*CELLS+axis[None,None,:]
            iy=ky[:,None,None]*CELLS+axis[None,:,None]
            # Only outer incomplete tiles get filled. Both real interpolation
            # neighbours were admitted before any tile generation,and never use
            # these out-of-domain fills. No ray/support is clipped into validity.
            ix=np.clip(ix,-self.max_grid_index,self.max_grid_index)
            iy=np.clip(iy,-self.max_grid_index,self.max_grid_index)
            fields=np.stack(self.world.surface_arrays(ix*self.spacing,iy*self.spacing))
            for index,key in enumerate(take):
                tile=fields[:,index].copy();self.generated_tiles+=1;self._remember(key,tile)
                yield key,tile

    def surface_arrays(self,x_m,y_m):
        from packages.specimens.tile_groups import group_pairs
        x,y=_admit(x_m,y_m);gx,gy=x/self.spacing,y/self.spacing
        ix,iy=np.floor(gx),np.floor(gy)
        if (np.any(ix<-self.max_grid_index) or np.any(iy<-self.max_grid_index) or
                np.any(ix+1>self.max_grid_index) or np.any(iy+1>self.max_grid_index)):
            raise ValueError('both native interpolation neighbours required')
        ix,iy=ix.astype(np.int64),iy.astype(np.int64)
        fx,fy=(gx-ix).ravel(),(gy-iy).ravel();a,b=(ix%CELLS).ravel(),(iy%CELLS).ravel()
        order,starts,keys=group_pairs((ix//CELLS).ravel(),(iy//CELLS).ravel())
        positions={(int(k[0]),int(k[1])):i for i,k in enumerate(keys)}
        if 4*x.size*8>available_memory_bytes()*.8:raise MemoryError('actual RAM cannot admit native field result')
        result=np.empty((4,x.size),dtype=np.float64)
        for key,tile in self._tiles(tuple(positions)):
            number=positions[key];ids=order[starts[number]:starts[number+1]]
            aa,bb,u,v=a[ids],b[ids],fx[ids],fy[ids]
            result[:,ids]=((1-u)*(1-v)*tile[:,bb,aa]+u*(1-v)*tile[:,bb,aa+1]+
                (1-u)*v*tile[:,bb+1,aa]+u*v*tile[:,bb+1,aa+1])
        return tuple(row.reshape(x.shape) for row in result)

    def surface(self,x_m,y_m):
        return tuple(float(v) for v in self.surface_arrays(x_m,y_m))
