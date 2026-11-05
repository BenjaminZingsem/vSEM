"""Private exact analytic world fields on explicitly leased GPU1.

Frontier composition of the qualified hierarchy and finite basis port. No pixel
pitch,zoom,noise,dose,clock or live material state is an input. A GPU compiler or
allocation failure is fatal;there is no device/precision/provider fallback.
This source is not selected by the human service before its own acceptance.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import numpy as np
import torch
import triton
from .hierarchical_specimen import HierarchicalSpecimen,RELIEF,ANCHOR_RADIUS
from .hierarchical_gpu_fields import raw_hierarchy,GPU_UUID
from .human_alignment_specimen import EDGE_M,HOLES,RELIEF_M
from .procedural_specimen import RELIEF_LIMIT_M,BASE_YIELD,YIELD_SPAN


def _sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def _rectangle(x,y,a,b,c,d):
    ta,tb=torch.tanh((x-a)/EDGE_M),torch.tanh((b-x)/EDGE_M)
    tc,td=torch.tanh((y-c)/EDGE_M),torch.tanh((d-y)/EDGE_M)
    ax,bx,cy,dy=(1+ta)/2,(1+tb)/2,(1+tc)/2,(1+td)/2
    sx,sy=ax*bx,cy*dy
    dsx=((1-ta*ta)*bx-ax*(1-tb*tb))/(2*EDGE_M)
    dsy=((1-tc*tc)*dy-cy*(1-td*td))/(2*EDGE_M)
    return sx*sy,dsx*sy,sx*dsy


class GpuHierarchicalWorld:
    def __init__(self,*,specimen=None):
        if (torch.__version__!='2.3.1+cu121' or triton.__version__!='2.3.1' or
                os.environ.get('CUDA_VISIBLE_DEVICES')!=GPU_UUID or torch.cuda.device_count()!=1):
            raise ValueError('pinned runtime and explicit exclusively leased GPU1 required')
        self.specimen=HierarchicalSpecimen() if specimen is None else specimen
        if type(self.specimen) is not HierarchicalSpecimen:raise ValueError('exact fixed hierarchical specimen required')
        # The only finite-feature implementation admitted here must have passed
        # the separate terminal source review/direct GPU acceptance,not merely a
        # local cross-family reviewer. Release selection remains external.
        from packages.numerics.compact_feature_cuda_runtime import compact_feature_sum
        self.feature_sum=compact_feature_sum
        self.device=torch.device('cuda:0')
        kinds={'particle':0.,'ridges':1.,'cross':2.,'terrace':3.}
        # _anchor is evaluated ONLY inside the fixed2um disk. A rotated ellipse
        # lies within radius rx+ry in either axis. Beyond that conservative box
        # its compact basis and derivatives are identically zero. Preserve input
        # row order,and include an eight-ULP outward margin;this is exact support
        # elimination,not a smaller halo or an approximation to the specimen.
        features=[]
        for f in self.specimen._anchor._features:
            radius=f.rx+f.ry
            margin=8*math.ulp(max(abs(f.x),abs(f.y),radius,ANCHOR_RADIUS))
            if abs(f.x)>ANCHOR_RADIUS+radius+margin or abs(f.y)>ANCHOR_RADIUS+radius+margin:continue
            features.append(f)
        rows=[(f.x,f.y,f.rx,f.ry,f.angle,f.height,f.contrast,kinds[f.kind],f.period,f.phase,f.step_width)
            for f in features]
        self.total_finite_features=len(self.specimen._anchor._features)
        self.retained_finite_features=len(features)
        self.features=torch.tensor(rows,dtype=torch.float64,device=self.device)
        folder=Path(__file__).resolve().parent
        names=('hierarchical_gpu_world.py','hierarchical_gpu_fields.py','hierarchical_specimen.py',
            'human_alignment_specimen.py','fine_practice_specimen.py','procedural_specimen.py')
        pins={n:_sha(folder/n) for n in names}
        pins['compact_feature_cuda_runtime.py']=_sha(folder.parent/'packages/numerics/compact_feature_cuda_runtime.py')
        self.identity={'protocol':'vsem.private.hierarchical-analytic-gpu.v1','source':pins,
            'private_seed_sha256':hashlib.sha256(self.specimen.seed).hexdigest(),
            'frame':'fixed-specimen-metres-y-up','torch':torch.__version__,'triton':triton.__version__,
            'python':sys.version,'numpy':np.__version__,'byteorder':sys.byteorder,
            'zoom_pixel_clock_dose_independent':True,'material_codes_activate_feedback':False}
        self.identity_digest=hashlib.sha256(json.dumps(self.identity,sort_keys=True,separators=(',',':')).encode()).hexdigest()

    def _anchor(self,x,y):
        raw=self.feature_sum(x,y,self.features)
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

    def fields(self,x,y):
        raw=raw_hierarchy(x,y,self.specimen._seeds)
        z,sx,sy,material=raw.unbind(0)
        p=2*math.pi*(x/136e-9+y/233e-9);q=2*math.pi*((x-.3*y)/311e-9)+self.specimen._seeds[0]/2147483647
        wave=torch.sin(p)+.5*torch.sin(q)
        z=z+.15e-9*wave;material=material+.05*wave
        sx=sx+.15e-9*2*math.pi*(torch.cos(p)/136e-9+.5*torch.cos(q)/311e-9)
        sy=sy+.15e-9*2*math.pi*(torch.cos(p)/233e-9-.15*torch.cos(q)/311e-9)
        r2=(x*x+y*y)/ANCHOR_RADIUS**2;mask=r2<1
        if bool(mask.any()):
            ax,ay=x[mask].contiguous(),y[mask].contiguous()
            a,b,c,se=self._anchor(ax,ay);w=(1-r2[mask])**3
            dwx=-6*ax*(1-r2[mask])**2/ANCHOR_RADIUS**2
            dwy=-6*ay*(1-r2[mask])**2/ANCHOR_RADIUS**2
            z[mask]+=w*a;sx[mask]+=w*b+dwx*a;sy[mask]+=w*c+dwy*a
            material[mask]+=w*torch.atanh(((se-.22)/.10).clamp(-1+2**-52,1-2**-52))
        t=torch.tanh(z/RELIEF)
        result=torch.stack((RELIEF*t,(1-t*t)*sx,(1-t*t)*sy,.22+.10*torch.tanh(material)))
        if not bool(torch.isfinite(result).all()):raise ValueError('nonfinite physical field')
        return result

    def surface_arrays(self,x_m,y_m):
        from .hierarchical_specimen import _admit
        from .human_specimen_map import available_memory_bytes
        x,y=_admit(x_m,y_m);n=x.size
        free,_=torch.cuda.mem_get_info()
        # Ample measured workspace per point for hierarchy,anchor and transfers.
        # This is memory-derived batch sizing,not a fixed compute ceiling.
        batch=max(1,int(min(free,available_memory_bytes())*.6//2048))
        if 4*n*8>available_memory_bytes()*.8:raise MemoryError('actual RAM cannot admit field result')
        result=np.empty((4,n),dtype=np.float64);x=x.reshape(-1);y=y.reshape(-1)
        for start in range(0,n,batch):
            stop=min(n,start+batch)
            tx=torch.tensor(x[start:stop].copy(),dtype=torch.float64,device=self.device)
            ty=torch.tensor(y[start:stop].copy(),dtype=torch.float64,device=self.device)
            result[:,start:stop]=self.fields(tx,ty).cpu().numpy()
        shape=np.broadcast_shapes(np.shape(x_m),np.shape(y_m))
        return tuple(a.reshape(shape) for a in result)
