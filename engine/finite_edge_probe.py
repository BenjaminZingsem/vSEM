"""Positive Gaussian integration over only the stored specimen at a hard edge.

Conditional-normal coordinates keep anisotropic/correlated beams resolved.
Unit-standard-deviation panels resolve the density;increasing positive GL order
resolves the fixed material field. There is no truncated-beam renormalization.
The40-sigma extent drops only tails that underflow binary64. Unresolved primary
dose remains governed by the separate full frozen rectangle-CDF partition.
"""
import math
import numpy as np
from .primary_fluence import rectangle_probability
from .finite_absorption import bounds_rectangle
from .human_specimen_map import available_memory_bytes


def _normal_panels(low,high,order):
    nodes,weights=np.polynomial.legendre.leggauss(order)
    low=np.asarray(low,dtype=np.float64);high=np.asarray(high,dtype=np.float64)
    panels=np.arange(-40,40,dtype=np.float64)
    left=np.maximum(low[...,None],panels);right=np.minimum(high[...,None],panels+1)
    half=np.maximum(0.,right-left)/2;mid=left+half
    points=mid[...,None]+half[...,None]*nodes
    probability=half[...,None]*weights*np.exp(-.5*points*points)/math.sqrt(2*math.pi)
    count=80*order
    return points.reshape(*low.shape,count),probability.reshape(*low.shape,count)


def conditional_material_rule(covariance,cx,cy,bounds,order):
    if type(order) is not int or not 4<=order<=2048:raise ValueError('explicit positive GL refinement order required')
    bounds=bounds_rectangle(bounds);rectangle_probability(covariance,cx,cy,0.,0.,0.,0.)
    sx=math.sqrt(covariance.xx_m2);conditional=math.sqrt((covariance.xx_m2*covariance.yy_m2-covariance.xy_m2**2)/covariance.xx_m2)
    slope=covariance.xy_m2/sx;x0,x1,y0,y1=bounds
    u,wu=_normal_panels((x0-cx)/sx,(x1-cx)/sx,order)
    active=wu>0;u=u[active];wu=wu[active]
    shift=cy+slope*u
    v,wv=_normal_panels((y0-shift)/conditional,(y1-shift)/conditional,order)
    probability=wu[:,None]*wv;active=probability>0
    x=np.broadcast_to((cx+sx*u)[:,None],v.shape)[active]
    y=(shift[:,None]+conditional*v)[active];p=probability[active]
    if (not np.isfinite(p).all() or np.any(p<=0) or np.any(x<x0) or np.any(x>x1) or
            np.any(y<y0) or np.any(y>y1)):raise ValueError('positive rule must query existing material only')
    return x,y,p


class FiniteEdgeProbe:
    def __init__(self,world):
        from .finite_gpu_world import GpuFiniteWorld
        if type(world) is not GpuFiniteWorld:raise ValueError('exact stored finite world required')
        self.world=world;self.field_points=0;self.refinements=0

    def _integrate(self,covariance,cx,cy,order):
        import torch
        x,y,weights=conditional_material_rule(covariance,cx,cy,self.world.catalog.header.bounds_m,order)
        if 160*len(x)>available_memory_bytes()*.8:raise MemoryError('actual RAM cannot admit clipped Gaussian rule')
        free,_=torch.cuda.mem_get_info();free+=torch.cuda.memory_reserved()-torch.cuda.memory_allocated()
        batch=int(min(free,available_memory_bytes())*.6//2048)
        if batch<1:raise MemoryError('actual GPU/RAM cannot admit stored edge fields')
        terms=[]
        for start in range(0,len(x),batch):
            tx=torch.tensor(x[start:start+batch].copy(),dtype=torch.float64,device=self.world.device)
            ty=torch.tensor(y[start:start+batch].copy(),dtype=torch.float64,device=self.world.device)
            w=torch.tensor(weights[start:start+batch].copy(),dtype=torch.float64,device=self.world.device)
            fields=self.world.fields(tx,ty);normal=torch.sqrt(1+fields[1]**2+fields[2]**2)
            emitted=fields[3]*normal;collected=emitted*.35*(1-.2*fields[1]/normal)
            terms.append(((emitted*w).sum().item(),(collected*w).sum().item()))
        self.field_points+=len(x)
        return np.array([math.fsum(t[i] for t in terms) for i in range(2)])

    def integrate(self,covariance,cx,cy):
        old=self._integrate(covariance,cx,cy,8)
        for order in (16,32,64,128,256,512,1024,2048):
            new=self._integrate(covariance,cx,cy,order);self.refinements+=1
            if np.all(np.abs(new-old)<=np.maximum(5e-13,2e-6*np.abs(new))):return new
            old=new
        raise ValueError('positive material-edge expectation did not converge;no approximate fallback')
