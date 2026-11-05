"""Frontier-owned fused FP64 procedural hierarchy,not runtime-selected.

Only fixed world arithmetic runs here. The caller owns the existing GPU1 lease;
there is no device/provider fallback,actor,acquired image,dose or material-state
mutation. CPU reference/anchor/final physical bounds remain independently checked.
Pinned Triton2.3.1 uses triton.language.math for double libdevice functions.
"""
import os
import torch
import triton
import triton.language as tl
import triton.language.math as dm
from .hierarchical_specimen import PITCHES,HEIGHTS,CONTRAST,REGION_PITCH,P

GPU_UUID = os.environ.get('VSEM_GPU_UUID', 'UNCONFIGURED')


@triton.jit
def _d(value:tl.constexpr):
    return tl.full((),value,tl.float64)


@triton.jit
def _hash(ix,iy,level,s0,s1,s2):
    a=ix%2147483647;b=iy%2147483647
    a=tl.where(a<0,a+2147483647,a);b=tl.where(b<0,b+2147483647,b)
    h=((a^s0)*104729+(b^s1)*130363+(level+1)*155921+s2)%2147483647
    return (h*h+48271*h+s2)%2147483647


@triton.jit
def _step(h,k:tl.constexpr):
    h=(h*48271+(k+1)*1031)%2147483647
    h=((h^(h>>13))*69621)%2147483647
    return h,(h.to(tl.float64)+_d(.5))/_d(2147483647.)


@triton.jit
def _raw_kernel(X,Y,PARAMS,OUT,N,s0,s1,s2,BLOCK:tl.constexpr):
    indices=tl.program_id(0)*BLOCK+tl.arange(0,BLOCK);mask=indices<N
    x=tl.load(X+indices,mask=mask,other=0);y=tl.load(Y+indices,mask=mask,other=0)
    z=tl.full((BLOCK,),0.,tl.float64);sx=z;sy=z;material=z
    pi2=_d(6.283185307179586);region=_d(REGION_PITCH)
    for level in range(6):
        pitch=tl.load(PARAMS+level*3);height=tl.load(PARAMS+level*3+1);contrast=tl.load(PARAMS+level*3+2)
        bx=dm.floor(x/pitch).to(tl.int64);by=dm.floor(y/pitch).to(tl.int64)
        for i in range(3):
            for j in range(3):
                ix=bx+i-1;iy=by+j-1
                h=_hash(ix,iy,level,s0,s1,s2)
                h,q0=_step(h,0);h,q1=_step(h,1);h,q2=_step(h,2)
                h,q3=_step(h,3);h,q4=_step(h,4);h,q5=_step(h,5)
                h,q6=_step(h,6);h,q7=_step(h,7);h,q8=_step(h,8)
                region_x=dm.floor(((ix.to(tl.float64)+_d(.5))*pitch)/region).to(tl.int64)
                region_y=dm.floor(((iy.to(tl.float64)+_d(.5))*pitch)/region).to(tl.int64)
                rh=_hash(region_x,region_y,8,s0,s1,s2);family=rh%3
                angle=tl.where(family==2,pi2*rh.to(tl.float64)/_d(2147483647.)+_d(.4)*(q2-_d(.5)),pi2*q2)
                ca=dm.cos(angle);sa=dm.sin(angle)
                cx=(ix.to(tl.float64)+_d(.2)+_d(.6)*q0)*pitch
                cy=(iy.to(tl.float64)+_d(.2)+_d(.6)*q1)*pitch
                rx=tl.where(family==2,_d(.96),_d(.62)+_d(.30)*q3)*pitch
                ry=tl.where(family==2,_d(.14)+_d(.12)*q4,_d(.42)+_d(.36)*q4)*pitch
                u=ca*(x-cx)+sa*(y-cy);v=-sa*(x-cx)+ca*(y-cy)
                r=dm.sqrt((u/rx)*(u/rx)+(v/ry)*(v/ry));a=tl.maximum(_d(0.),_d(1.)-r)
                a3=a*a*a;bump=a3*a*(_d(4.)*r+_d(1.))
                du=-_d(20.)*a3*u/(rx*rx);dv=-_d(20.)*a3*v/(ry*ry)
                k=pi2/(_d(.28)*pitch);phase=k*v+pi2*q7
                pattern=tl.where(family==2,_d(.7)+_d(.3)*dm.cos(phase),_d(1.))
                pv=tl.where(family==2,-_d(.3)*k*dm.sin(phase),_d(0.))
                value=bump*pattern;bu=du*pattern;bv=dv*pattern+bump*pv
                amplitude=height*(_d(.3)+_d(.7)*q5)*tl.where(family==1,-_d(1.),_d(1.))
                m=contrast*tl.where(family==1,-_d(.3)-_d(.7)*q6,_d(.15)+_d(.85)*q6)
                z+=amplitude*value;sx+=amplitude*(ca*bu-sa*bv);sy+=amplitude*(sa*bu+ca*bv);material+=m*value
    tl.store(OUT+indices,z,mask=mask);tl.store(OUT+N+indices,sx,mask=mask)
    tl.store(OUT+2*N+indices,sy,mask=mask);tl.store(OUT+3*N+indices,material,mask=mask)


def raw_hierarchy(x,y,seeds):
    if torch.__version__!='2.3.1+cu121' or triton.__version__!='2.3.1':raise ValueError('pinned Torch/Triton required')
    if os.environ.get('CUDA_VISIBLE_DEVICES')!=GPU_UUID or torch.cuda.device_count()!=1:
        raise ValueError('explicit exclusively leased GPU1 required')
    if (type(x) is not torch.Tensor or type(y) is not torch.Tensor or x.device.type!='cuda' or x.device!=y.device or
        x.dtype!=torch.float64 or y.dtype!=torch.float64 or x.layout!=torch.strided or y.layout!=torch.strided or
        x.ndim!=1 or y.shape!=x.shape or not x.is_contiguous() or not y.is_contiguous() or x.requires_grad or y.requires_grad):
        raise ValueError('same-device contiguous FP64 coordinate vectors required')
    if type(seeds) is not tuple or len(seeds)!=3 or any(type(v) is not int or not 0<=v<P for v in seeds):
        raise ValueError('exact private coordinate-mixer tuple required')
    if (not bool(torch.isfinite(x).all()) or not bool(torch.isfinite(y).all()) or
        bool((x.abs()>.055).any()) or bool((y.abs()>.055).any())):raise ValueError('fixed coordinate domain required')
    out=torch.empty((4,x.numel()),dtype=torch.float64,device=x.device)
    if x.numel():
        parameters=torch.tensor(tuple(v for row in zip(PITCHES,HEIGHTS,CONTRAST) for v in row),dtype=torch.float64,device=x.device)
        _raw_kernel[(triton.cdiv(x.numel(),128),)](x,y,parameters,out,x.numel(),*seeds,BLOCK=128,num_warps=4,enable_fp_fusion=False)
    return out
