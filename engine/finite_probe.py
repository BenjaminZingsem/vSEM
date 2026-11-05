"""Explicit finite stored-world source:existing material,physical edges,vacuum.

No runtime counter generation or seed-based world exists in this graph. Native
and sparse interior mathematics retain the original qualified optics. Positive
conditional quadrature handles the finite hard edge. Only immutable expected
responses are memoized;counts,exposure,dose and time remain causal and fresh.
"""
from collections import OrderedDict
from dataclasses import dataclass,field,replace
import hashlib
import json
import math
from pathlib import Path
import time
import numpy as np
from .human_episode_types import EpisodeGeometry,EpisodeSettings,exact
from .human_mapped_probe import MappedProbeBank,HumanMappedProfile,effective_settings,HEIGHT_STEP_M
from .human_specimen_map import available_memory_bytes
from .beam_profile import HEIGHT_BOUND_M
from .analytic_probe import AnalyticProbeBuilder,axis_rule,quadrature_order
from .hierarchical_specimen import ANCHOR_RADIUS
from .finite_gpu_world import GpuFiniteWorld
from .finite_native_map import FiniteNativeMap
from .finite_chunked_probe import FiniteChunkedProbeBuilder,CHUNK_CELLS,_bucket
from .finite_edge_probe import FiniteEdgeProbe
from .finite_absorption import finite_absorption


from .finite_probe_types import FiniteProfile,FiniteProbeBank

class _FiniteSparse(AnalyticProbeBuilder):
    def __init__(self,world):
        if type(world) is not GpuFiniteWorld:raise ValueError('exact stored finite world required')
        self.world=world;self.calls=0;self.field_points=0;self.maximum_batch_points=0;self.order_counts={}


def finite_probe_pins():
    root=Path(__file__).resolve().parent
    names=('finite_probe.py','finite_probe_types.py','finite_edge_probe.py','finite_absorption.py','finite_fluence.py',
        'finite_native_map.py','finite_chunked_probe.py','finite_gpu_world.py','finite_gpu_fields.py',
        'finite_gpu_catalog.py','finite_catalog_format.py','analytic_probe.py','human_mapped_probe.py',
        'beam_profile.py','hierarchical_native_map.py')
    result={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in names}
    for name in ('compact_valid_convolution.py','compact_feature_cuda_runtime.py','gaussian_tensor_grid.py'):
        result['packages/numerics/'+name]=hashlib.sha256((root.parent/'packages/numerics'/name).read_bytes()).hexdigest()
    return result


class FiniteProbeBuilder:
    def __init__(self,world,*,spacing_m=.625e-9):
        if type(world) is not GpuFiniteWorld:raise ValueError('exact frozen finite GPU world required')
        self.world=world;free=available_memory_bytes()
        self.native_world=FiniteNativeMap(world,spacing_m=spacing_m,cache_bytes=int(free*.35))
        self.native=FiniteChunkedProbeBuilder(self.native_world,cache_bytes=int(free*.35),device='cuda:0')
        self.sparse=_FiniteSparse(world);self.edge=FiniteEdgeProbe(world)
        self.pins=finite_probe_pins();self.identity=hashlib.sha256(json.dumps(
            {'world':world.identity_digest,'native':self.native_world.identity_digest,'pins':self.pins},
            sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.cache=OrderedDict();self.resident=0;self.budget=int(free*.15);self.hits=self.misses=0

    @staticmethod
    def _size(bank):
        return sum(v.nbytes for v in (bank.se_emitted_per_incident,bank.se_collected_per_incident,
            bank.surface_height_m,bank.absorbed_probability,bank.escaped_probability))

    def build(self,geometry,settings):
        exact(geometry,EpisodeGeometry);exact(settings,EpisodeSettings)
        if self.pins!=finite_probe_pins():raise ValueError('changed frozen finite scientific graph')
        key=(self.identity,geometry._key(),settings._key());start=time.perf_counter()
        if key in self.cache:
            bank=self.cache.pop(key);self.cache[key]=bank;self.hits+=1
            return replace(bank,construction_s=time.perf_counter()-start)
        bank=self._build(geometry,settings);self.misses+=1;size=self._size(bank)
        if size<=self.budget:
            while self.resident+size>self.budget:
                _,old=self.cache.popitem(last=False);self.resident-=self._size(old)
            self.cache[key]=bank;self.resident+=size
        return bank

    def _sparse(self,x,y,heights,settings,geometry,indices):
        result=np.zeros((2,len(x)),dtype=np.float64);lower=np.floor(heights/HEIGHT_STEP_M).astype(np.int64)
        fraction=heights/HEIGHT_STEP_M-lower;mask=np.zeros(len(x),dtype=bool);mask[indices]=True;used=0
        beam=effective_settings(settings,geometry);profile=FiniteProfile()
        for level in np.unique(np.concatenate((lower[indices],lower[indices]+1))):
            blend=np.where(mask,np.where(lower==level,1-fraction,np.where(lower+1==level,fraction,0.)),0.)
            if not blend.any():continue
            cov=profile.covariance(beam,int(level)*HEIGHT_STEP_M);base=quadrature_order((cov,));used+=1
            sigma=math.sqrt(cov.principal_variances_m2()[1]);near=np.hypot(x,y)<=ANCHOR_RADIUS+9*sigma
            for anchor in (False,True):
                active=np.flatnonzero((blend!=0)&(near==anchor))
                if not len(active):continue
                order=2*(base-1)+1 if anchor else base;nodes,weights=axis_rule(order)
                a,b,c,d=self.world.catalog.header.bounds_m;extent=float(np.max(np.abs(nodes)))
                if (np.any(x[active]-math.sqrt(cov.xx_m2)*extent<a) or np.any(x[active]+math.sqrt(cov.xx_m2)*extent>b) or
                        np.any(y[active]-math.sqrt(cov.yy_m2)*extent<c) or np.any(y[active]+math.sqrt(cov.yy_m2)*extent>d)):
                    raise ValueError('finite sparse query lacks existing complete quadrature support')
                result[:,active]+=self.sparse._integrate(x[active],y[active],cov,nodes,weights)*blend[active]
        return result,used

    def _build(self,geometry,settings):
        start=time.perf_counter();count=geometry.pixel_count
        if count*512>available_memory_bytes()*.8:raise MemoryError('actual RAM cannot admit requested finite response indexing')
        px=geometry.center_x_m+(np.arange(geometry.width_px)+.5-geometry.width_px/2)*geometry.pixel_size_m
        py=geometry.center_y_m+(geometry.height_px/2-np.arange(geometry.height_px)-.5)*geometry.pixel_size_m
        x,y=np.meshgrid(px,py);x=x.ravel();y=y.ravel()
        if np.any(np.abs(x)>.055) or np.any(np.abs(y)>.055):raise ValueError('finite coordinates exceed scientific envelope')
        profile=FiniteProfile();beam=effective_settings(settings,geometry)
        widest=[profile.covariance(beam,h) for h in (-HEIGHT_BOUND_M,HEIGHT_BOUND_M)]
        sx=max(math.sqrt(c.xx_m2) for c in widest);sy=max(math.sqrt(c.yy_m2) for c in widest)
        a,b,c,d=self.world.catalog.header.bounds_m
        # Forty marginal sigmas underflow erfc in binary64. Only these proven
        # zero rays skip all material,field,tile,FFT and edge-quadrature work.
        empty=(x<a-40*sx)|(x>b+40*sx)|(y<c-40*sy)|(y>d+40*sy)
        heights=np.zeros(count,dtype=np.float64);present=np.flatnonzero(~empty)
        if len(present):heights[present]=self.world.surface_arrays(x[present],y[present])[0]
        deep=(x>a+40*sx)&(x<b-40*sx)&(y>c+40*sy)&(y<d-40*sy)
        absorbed=np.where(deep,1.,0.).astype(np.float64);escaped=np.where(deep,0.,1.).astype(np.float64)
        for i in np.flatnonzero(~empty&~deep):
            mass=finite_absorption(profile.covariance(beam,float(heights[i])),float(x[i]),float(y[i]),(a,b,c,d))
            absorbed[i]=mass.absorbed_probability;escaped[i]=mass.escaped_probability
        result=np.zeros((2,count),dtype=np.float64);used=0
        native=geometry.pixel_size_m<=2*self.native_world.spacing*CHUNK_CELLS
        if native:
            margin_x=(_bucket(math.ceil(9*sx/self.native_world.spacing))+2*CHUNK_CELLS+2)*self.native_world.spacing
            margin_y=(_bucket(math.ceil(9*sy/self.native_world.spacing))+2*CHUNK_CELLS+2)*self.native_world.spacing
        else:
            order=2*(quadrature_order(widest)-1)+1;nodes,_=axis_rule(order);extent=float(np.max(np.abs(nodes)))
            margin_x,margin_y=extent*sx,extent*sy
        interior=(absorbed>0)&(x>a+margin_x)&(x<b-margin_x)&(y>c+margin_y)&(y<d-margin_y)
        indices=np.flatnonzero(interior)
        if len(indices):
            if native:
                bank=self.native.build(geometry,settings,active_indices=indices)
                result[0]=bank.se_emitted_per_incident.copy();result[1]=bank.se_collected_per_incident.copy()
                heights[indices]=bank.surface_height_m[indices];used=bank.height_layers
                # Primary interception belongs to the same centre height that
                # the native bank retains,including tiny positive escape tails.
                for i in indices[~deep[indices]]:
                    mass=finite_absorption(profile.covariance(beam,float(heights[i])),float(x[i]),float(y[i]),(a,b,c,d))
                    absorbed[i]=mass.absorbed_probability;escaped[i]=mass.escaped_probability
            else:result,used=self._sparse(x,y,heights,settings,geometry,indices)
        for i in np.flatnonzero((absorbed>0)&~interior):
            lower=math.floor(heights[i]/HEIGHT_STEP_M);fraction=heights[i]/HEIGHT_STEP_M-lower
            for level,blend in ((lower,1-fraction),(lower+1,fraction)):
                if blend:
                    cov=profile.covariance(beam,level*HEIGHT_STEP_M)
                    result[:,i]+=blend*self.edge.integrate(cov,float(x[i]),float(y[i]))
        source=hashlib.sha256(json.dumps({'variant':'finite-stored-native-sparse-conditional-edge-v1',
            'builder':self.identity,'geometry':geometry._key(),'settings':settings._key(),
            'coefficients_sha256':hashlib.sha256(result.tobytes()+heights.tobytes()+absorbed.tobytes()+escaped.tobytes()).hexdigest()},
            sort_keys=True,separators=(',',':')).encode()).hexdigest()
        return FiniteProbeBank(geometry,settings,source,result[0].copy(),result[1].copy(),heights,
            time.perf_counter()-start,self.native_world.spacing if native else 0.,used,absorbed,escaped)

    def close(self):
        self.cache.clear();self.resident=0;self.native.close();self.native_world.cache.clear();self.native_world.resident_bytes=0
