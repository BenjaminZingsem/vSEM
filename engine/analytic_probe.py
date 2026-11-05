"""Experimental sparse physical-probe expectation over the fixed analytic world.

Positive Gaussian quadrature samples the actual probe,not the raster pixel area.
This is an identified new continuous analytic variant,not a native-grid claim.
Only immutable expected responses can be cached by its caller;fresh acquired
noise,dose,charge and material state are outside this mathematical builder.
The order schedule requires independent convergence before runtime selection.
"""
from dataclasses import dataclass,field
import hashlib
import json
import math
from pathlib import Path
import time
import numpy as np
from .human_episode_types import EpisodeGeometry,EpisodeSettings,exact
from .human_mapped_probe import (MappedProbeBank,HumanMappedProfile,effective_settings,HEIGHT_STEP_M)
from .human_specimen_map import available_memory_bytes
from .hierarchical_specimen import ANCHOR_RADIUS


@dataclass(frozen=True)
class AnalyticProbeBank(MappedProbeBank):
    protocol:str=field(default='vsem.private.analytic-gaussian-probe.v1',init=False)


def axis_rule(order):
    # Independent Golub-Welsch normal-distribution Jacobi matrix. This avoids
    # high-order polynomial overflow and uses only positive squared eigenvectors.
    from scipy.linalg import eigh_tridiagonal
    if type(order) is not int or order<3:raise ValueError('positive quadrature order required')
    nodes,vectors=eigh_tridiagonal(np.zeros(order),np.sqrt(np.arange(1,order,dtype=np.float64)))
    weights=vectors[0]**2
    if not np.isfinite(nodes).all() or not np.isfinite(weights).all() or weights.sum()<=0:
        raise ValueError('invalid Gaussian quadrature construction')
    return nodes,weights/weights.sum()


def quadrature_order(covariances):
    # The construction's narrowest nonzero analytic edge is8nm. This deliberately
    # generous empirical schedule is a qualification subject,not a calibrated
    # physical law or a precision fallback. High orders may take longer than SEM
    # acquisition and are permitted. No raster pitch enters this choice.
    sigma=max(math.sqrt(c.principal_variances_m2()[1]) for c in covariances)
    intervals=1<<max(5,math.ceil(math.log2(2*sigma/1e-9)))
    return intervals+1


class AnalyticProbeBuilder:
    def __init__(self,world):
        from .hierarchical_gpu_world import GpuHierarchicalWorld
        if type(world) is not GpuHierarchicalWorld:raise ValueError('exact qualified analytic world implementation required')
        self.world=world;self.calls=0;self.field_points=0;self.maximum_batch_points=0;self.order_counts={}
        folder=Path(__file__).resolve().parent
        self.pins={n:hashlib.sha256((folder/n).read_bytes()).hexdigest()
            for n in ('analytic_probe.py','beam_profile.py','human_mapped_probe.py')}
        self.pins['gaussian_tensor_grid.py']=hashlib.sha256((folder.parent/'packages/numerics/gaussian_tensor_grid.py').read_bytes()).hexdigest()

    def _integrate(self,x,y,covariance,nodes,weights):
        import torch
        from packages.numerics.gaussian_tensor_grid import gaussian_grid
        n=len(x);q=len(nodes)**2
        free,_=torch.cuda.mem_get_info()
        # Account for coordinate/result/anchor scratch,using current actual
        # resources. There is no task-count,point-count or compute budget here.
        bytes_per_point=q*1536
        batch=int(min(free,available_memory_bytes())*.6//bytes_per_point)
        if batch<1:raise MemoryError('actual GPU/RAM cannot admit one quadrature point')
        tn=torch.tensor(nodes.copy(),dtype=torch.float64,device=self.world.device)
        tw=torch.tensor(weights.copy(),dtype=torch.float64,device=self.world.device)
        result=np.empty((2,n),dtype=np.float64)
        for start in range(0,n,batch):
            stop=min(n,start+batch);size=stop-start
            tx=torch.tensor(x[start:stop].copy(),dtype=torch.float64,device=self.world.device)
            ty=torch.tensor(y[start:stop].copy(),dtype=torch.float64,device=self.world.device)
            xx=torch.full_like(tx,covariance.xx_m2);xy=torch.full_like(tx,covariance.xy_m2);yy=torch.full_like(tx,covariance.yy_m2)
            coords,probability=gaussian_grid(tx,ty,xx,xy,yy,tn,tw)
            flat=coords.reshape(-1,2)
            fields=self.world.fields(flat[:,0].contiguous(),flat[:,1].contiguous())
            normal=torch.sqrt(1+fields[1]*fields[1]+fields[2]*fields[2])
            emitted=fields[3]*normal;collected=emitted*.35*(1-.2*fields[1]/normal)
            values=torch.stack(((emitted.reshape(size,q)*probability).sum(1),
                (collected.reshape(size,q)*probability).sum(1)))
            result[:,start:stop]=values.cpu().numpy()
            self.field_points+=size*q;self.maximum_batch_points=max(self.maximum_batch_points,size*q)
        return result

    def build(self,geometry,settings):
        exact(geometry,EpisodeGeometry);exact(settings,EpisodeSettings)
        started=time.perf_counter();beam=effective_settings(settings,geometry);profile=HumanMappedProfile()
        columns=np.arange(geometry.width_px,dtype=np.float64)
        rows=np.arange(geometry.height_px,dtype=np.float64)
        px=geometry.center_x_m+(columns+.5-geometry.width_px/2)*geometry.pixel_size_m
        py=geometry.center_y_m+(geometry.height_px/2-rows-.5)*geometry.pixel_size_m
        x,y=np.meshgrid(px,py);x=x.ravel();y=y.ravel()
        heights=np.array(self.world.surface_arrays(x,y)[0],copy=True)
        lower=np.floor(heights/HEIGHT_STEP_M).astype(np.int64);fraction=heights/HEIGHT_STEP_M-lower
        levels=np.unique(np.concatenate((lower,lower+1)))
        covariances={int(level):profile.covariance(beam,int(level)*HEIGHT_STEP_M) for level in levels}
        result=np.zeros((2,geometry.pixel_count),dtype=np.float64);used=0;orders=set()
        for level in levels:
            blend=np.where(lower==level,1-fraction,np.where(lower+1==level,fraction,0.))
            mask=blend!=0
            if not mask.any():continue
            covariance=covariances[int(level)];base_order=quadrature_order((covariance,))
            # The finite alignment anchor has8nm analytic edges. A physical
            # footprint intersecting it gets twice the quadrature intervals.
            # This choice uses only specimen coordinates and covariance,never
            # camera pitch/query grouping. Outer morphology need not pay for
            # a distant anchor. Actual convergence remains independently tested.
            sigma=math.sqrt(covariance.principal_variances_m2()[1])
            anchor=np.hypot(x,y)<=ANCHOR_RADIUS+9*sigma
            for near in (False,True):
                active=mask&(anchor==near)
                if not active.any():continue
                order=2*(base_order-1)+1 if near else base_order
                nodes,weights=axis_rule(order);orders.add(order)
                extent=float(np.max(np.abs(nodes)))
                # Full actual quadrature support is admitted before field work;
                # no source or probe is clipped into validity at an outer edge.
                if (np.any(np.abs(x[active])+math.sqrt(covariance.xx_m2)*extent>.055) or
                        np.any(np.abs(y[active])+math.sqrt(covariance.yy_m2)*extent>.055)):
                    raise ValueError('complete analytic physical-probe support outside world')
                result[:,active]+=self._integrate(x[active],y[active],covariance,nodes,weights)*blend[active]
                self.order_counts[order]=self.order_counts.get(order,0)+int(active.sum())
            used+=1
        self.calls+=1
        identity={'variant':'continuous-analytic-positive-Gaussian+50nm-height-v1',
            'world':self.world.identity_digest,'geometry':geometry._key(),'settings':settings._key(),
            'source':self.pins,'orders':sorted(orders),'axis_rule':'FP64-normal-Jacobi-eigenvectors',
            'coefficient_sha256':hashlib.sha256(result.tobytes()+heights.tobytes()).hexdigest()}
        source=hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        return AnalyticProbeBank(geometry,settings,source,result[0].copy(),result[1].copy(),
            heights,time.perf_counter()-started,0.,used)

    def close(self):pass
