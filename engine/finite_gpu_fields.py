"""FP64 fields from already stored finite elements;no seed/hash/generation path.

All coefficients are read from one validated immutable GPU catalogue. This is
numerical field evaluation,not acquisition or activation of material feedback.
"""
import os
import torch
import triton
import triton.language as tl
import triton.language.math as dm

GPU_UUID = os.environ.get('VSEM_GPU_UUID', 'UNCONFIGURED')

@triton.jit
def _d(value:tl.constexpr):
    return tl.full((),value,tl.float64)

@triton.jit(do_not_specialize=[6])
def _catalog_kernel(X,Y,PARAMS,META,TABLE,OUT,N,BLOCK:tl.constexpr):
    indices=tl.program_id(0).to(tl.int64)*BLOCK+tl.arange(0,BLOCK).to(tl.int64);N=N.to(tl.int64);mask=indices<N
    x=tl.load(X+indices,mask=mask,other=0);y=tl.load(Y+indices,mask=mask,other=0)
    z=tl.full((BLOCK,),0.,tl.float64);sx=z;sy=z;material=z
    pi2=_d(6.283185307179586)
    for level in range(6):
        pitch=tl.load(PARAMS+level*3);height=tl.load(PARAMS+level*3+1);contrast=tl.load(PARAMS+level*3+2)
        bx=dm.floor(x/pitch).to(tl.int64);by=dm.floor(y/pitch).to(tl.int64)
        ox=tl.load(META+level*5);oy=tl.load(META+level*5+1)
        nx=tl.load(META+level*5+2);ny=tl.load(META+level*5+3);base=tl.load(META+level*5+4)
        area=nx*ny
        for i in range(3):
            for j in range(3):
                ix=bx+i-1;iy=by+j-1
                cell=(iy-oy)*nx+ix-ox
                q0=(tl.load(TABLE+base+0*area+cell,mask=mask,other=0).to(tl.float64)+_d(.5))/_d(2147483647.)
                q1=(tl.load(TABLE+base+1*area+cell,mask=mask,other=0).to(tl.float64)+_d(.5))/_d(2147483647.)
                q2=(tl.load(TABLE+base+2*area+cell,mask=mask,other=0).to(tl.float64)+_d(.5))/_d(2147483647.)
                q3=(tl.load(TABLE+base+3*area+cell,mask=mask,other=0).to(tl.float64)+_d(.5))/_d(2147483647.)
                q4=(tl.load(TABLE+base+4*area+cell,mask=mask,other=0).to(tl.float64)+_d(.5))/_d(2147483647.)
                q5=(tl.load(TABLE+base+5*area+cell,mask=mask,other=0).to(tl.float64)+_d(.5))/_d(2147483647.)
                q6=(tl.load(TABLE+base+6*area+cell,mask=mask,other=0).to(tl.float64)+_d(.5))/_d(2147483647.)
                q7=(tl.load(TABLE+base+7*area+cell,mask=mask,other=0).to(tl.float64)+_d(.5))/_d(2147483647.)
                rh=tl.load(TABLE+base+8*area+cell,mask=mask,other=0).to(tl.int64);family=rh%3
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


def raw_catalog_fields(x,y,catalog):
    from .finite_gpu_catalog import GpuFiniteCatalog
    if type(catalog) is not GpuFiniteCatalog or not catalog.validated:
        raise ValueError('fully validated frozen GPU catalogue required')
    if torch.__version__!='2.3.1+cu121' or triton.__version__!='2.3.1':raise ValueError('pinned Torch/Triton required')
    if os.environ.get('CUDA_VISIBLE_DEVICES')!=GPU_UUID or torch.cuda.device_count()!=1:
        raise ValueError('exclusively leased physical GPU1 required')
    for value in (x,y):
        if (type(value) is not torch.Tensor or value.layout!=torch.strided or value.dtype!=torch.float64 or
            value.device!=catalog.data.device or value.ndim!=1 or not value.is_contiguous() or value.requires_grad):
            raise ValueError('same-device contiguous FP64 position vectors required')
    if y.shape!=x.shape or not bool(torch.isfinite(x).all()) or not bool(torch.isfinite(y).all()):
        raise ValueError('equal finite positions required')
    a,b,c,d=catalog.header.bounds_m
    if bool(((x<a)|(x>b)|(y<c)|(y>d)).any()):raise ValueError('only existing in-sample positions may query stored elements')
    result=torch.empty((4,x.numel()),dtype=torch.float64,device=x.device)
    if x.numel():_catalog_kernel[(triton.cdiv(x.numel(),256),)](x,y,catalog.parameters,catalog.metadata,catalog.data,result,x.numel(),
        BLOCK=256,enable_fp_fusion=False)
    return result
