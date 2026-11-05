"""Numerical fields of one existing finite specimen;no world-generation path.

World coordinates and stored features are frozen. Outside points return material
absence. Only the causal beam integrator may determine an edge-overlap signal;
this module never edits an acquired frame or activates damage/charging codes.
"""
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import torch
from .finite_gpu_catalog import GpuFiniteCatalog
from .finite_gpu_fields import raw_catalog_fields
from .hierarchical_gpu_world import _rectangle
from .hierarchical_specimen import ANCHOR_RADIUS,RELIEF
from .human_alignment_specimen import HOLES,EDGE_M,RELIEF_M
from .procedural_specimen import RELIEF_LIMIT_M,BASE_YIELD,YIELD_SPAN
from .prepared_specimen_map import _coordinates
from .human_specimen_map import available_memory_bytes

def _anchor_fields(feature_sum,features,x,y):
    raw=feature_sum(x,y,features)
    t=torch.tanh(raw[0]/RELIEF_LIMIT_M)
    height=RELIEF_LIMIT_M*t;sx=(1-t*t)*raw[1];sy=(1-t*t)*raw[2]
    se=BASE_YIELD+YIELD_SPAN*torch.tanh(raw[3]);material=torch.zeros_like(x)
    for rect in ((-.75e-6,-.61e-6,-.65e-6,.62e-6),(-.75e-6,.56e-6,-.65e-6,-.51e-6)):
        value,dx,dy=_rectangle(x,y,*rect)
        height=height+12e-9*value;sx=sx+12e-9*dx;sy=sy+12e-9*dy;material=material+.8*value
    value,dx,dy=_rectangle(x,y,-.48e-6,.32e-6,-.30e-6,.28e-6)
    k=2*math.pi/.12e-6;angle=k*(x-.035e-6);wave=torch.tanh(torch.sin(angle)/.45)
    pattern=(1+wave)/2;derivative=(1-wave*wave)*torch.cos(angle)*k/(2*.45)
    shape=value*pattern;gx=dx*pattern+value*derivative;gy=dy*pattern
    height=height+8e-9*shape;sx=sx+8e-9*gx;sy=sy+8e-9*gy;material=material+.75*shape
    for cx,cy,radius in HOLES:
        dx,dy=x-cx*1e-6,y-cy*1e-6;r=radius*1e-6
        t=torch.tanh((dx*dx+dy*dy-r*r)/(2*r*EDGE_M));value=(1-t)/2
        gx=-(1-t*t)*dx/(2*r*EDGE_M);gy=-(1-t*t)*dy/(2*r*EDGE_M)
        height=height-8e-9*value;sx=sx-8e-9*gx;sy=sy-8e-9*gy;material=material-.9*value
    t=torch.tanh(height/RELIEF_M)
    phase=torch.atanh(((se-.22)/.10).clamp(-1+2**-52,1-2**-52))
    return RELIEF_M*t,(1-t*t)*sx,(1-t*t)*sy,.22+.10*torch.tanh(phase+material)


class GpuFiniteWorld:
    def __init__(self,catalog):
        if type(catalog) is not GpuFiniteCatalog or not catalog.validated:
            raise ValueError('complete verified frozen catalogue required')
        from packages.numerics.compact_feature_cuda_runtime import compact_feature_sum
        self.catalog=catalog;self.feature_sum=compact_feature_sum;self.device=catalog.data.device
        self.field_points_evaluated=0;self.field_batches=0;self.empty_queries=0
        root=Path(__file__).resolve().parent
        names=('finite_gpu_world.py','finite_gpu_fields.py','finite_gpu_catalog.py','finite_catalog_format.py',
            'hierarchical_gpu_world.py','human_alignment_specimen.py','procedural_specimen.py')
        pins={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names}
        pins['compact_feature_cuda_runtime.py']=hashlib.sha256((root.parent/'packages/numerics/compact_feature_cuda_runtime.py').read_bytes()).hexdigest()
        self.identity={'protocol':'vsem.private.finite-stored-world.v1','catalogue':catalog.source_identity,
            'manifest_sha256':catalog.header.manifest_sha256,'source':pins,'generation_allowed':False,
            'frame':'fixed-specimen-metres-y-up','material_codes_activate_feedback':False}
        self.identity_digest=hashlib.sha256(json.dumps(self.identity,sort_keys=True,separators=(',',':')).encode()).hexdigest()

    def fields(self,x,y):
        # Caller selects only already-present material positions. The raw lookup
        # validates that assertion before reading any device table pointer.
        raw=raw_catalog_fields(x,y,self.catalog);z,sx,sy,material=raw.unbind(0)
        p=2*math.pi*(x/136e-9+y/233e-9)
        q=2*math.pi*((x-.3*y)/311e-9)+self.catalog.header.background_phase
        wave=torch.sin(p)+.5*torch.sin(q)
        z=z+.15e-9*wave;material=material+.05*wave
        sx=sx+.15e-9*2*math.pi*(torch.cos(p)/136e-9+.5*torch.cos(q)/311e-9)
        sy=sy+.15e-9*2*math.pi*(torch.cos(p)/233e-9-.15*torch.cos(q)/311e-9)
        r2=(x*x+y*y)/ANCHOR_RADIUS**2;mask=r2<1
        if bool(mask.any()):
            ax,ay=x[mask].contiguous(),y[mask].contiguous()
            a,b,c,se=_anchor_fields(self.feature_sum,self.catalog.anchor,ax,ay);w=(1-r2[mask])**3
            dwx=-6*ax*(1-r2[mask])**2/ANCHOR_RADIUS**2
            dwy=-6*ay*(1-r2[mask])**2/ANCHOR_RADIUS**2
            z[mask]+=w*a;sx[mask]+=w*b+dwx*a;sy[mask]+=w*c+dwy*a
            material[mask]+=w*torch.atanh(((se-.22)/.10).clamp(-1+2**-52,1-2**-52))
        t=torch.tanh(z/RELIEF)
        result=torch.stack((RELIEF*t,(1-t*t)*sx,(1-t*t)*sy,.22+.10*torch.tanh(material)))
        if not bool(torch.isfinite(result).all()):raise ValueError('nonfinite frozen specimen field')
        self.field_points_evaluated+=x.numel();self.field_batches+=1
        return result

    def surface_arrays(self,x_m,y_m):
        x,y=np.broadcast_arrays(_coordinates(x_m),_coordinates(y_m))
        if np.any(np.abs(x)>.055) or np.any(np.abs(y)>.055):raise ValueError('qualified specimen coordinate domain required')
        shape=x.shape;x=x.reshape(-1);y=y.reshape(-1);a,b,c,d=self.catalog.header.bounds_m
        material=(x>=a)&(x<=b)&(y>=c)&(y<=d);indices=np.flatnonzero(material)
        result=np.zeros((4,x.size),dtype=np.float64)
        if not len(indices):self.empty_queries+=1;return tuple(v.reshape(shape) for v in result)
        free,_=torch.cuda.mem_get_info();free+=torch.cuda.memory_reserved()-torch.cuda.memory_allocated()
        batch=max(1,int(min(free,available_memory_bytes())*.6//2048))
        for start in range(0,len(indices),batch):
            selected=indices[start:start+batch]
            tx=torch.tensor(x[selected].copy(),dtype=torch.float64,device=self.device)
            ty=torch.tensor(y[selected].copy(),dtype=torch.float64,device=self.device)
            result[:,selected]=self.fields(tx,ty).cpu().numpy()
        return tuple(v.reshape(shape) for v in result)

    def material_codes(self,x_m,y_m):
        x,y=np.broadcast_arrays(_coordinates(x_m),_coordinates(y_m));a,b,c,d=self.catalog.header.bounds_m
        if np.any(np.abs(x)>.055) or np.any(np.abs(y)>.055):raise ValueError('qualified specimen coordinate domain required')
        inside=(x>=a)&(x<=b)&(y>=c)&(y<=d);values=np.full((3,*x.shape),-1,dtype=np.int8)
        ix=np.floor(x[inside]/self.catalog.header.region_pitch_m).astype(np.int64)-self.catalog.header.region_origin[0]
        iy=np.floor(y[inside]/self.catalog.header.region_pitch_m).astype(np.int64)-self.catalog.header.region_origin[1]
        values[:,inside]=self.catalog.regions[:,iy,ix]
        return tuple(values)
