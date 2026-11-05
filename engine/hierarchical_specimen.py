"""Private analytic low-relief specimen throughout the admitted stage domain.

Generic constructed morphology,not a measured material atlas. Fixed coordinate
hashes define overlapping C2 grains,pores and fibres on six physical scales.
No camera,zoom,raster,exposure,clock,frame noise or scenario answer is an input.
Material susceptibility/conduction codes are private expansion data,NOT activated
damage/charging physics. The source is not yet selected by a human runtime.
"""
from dataclasses import dataclass,field
import hashlib
import math
import numpy as np
from .human_alignment_specimen import HumanAlignmentSpecimen
from .prepared_specimen_map import _coordinates

P=2147483647
PITCHES=(80e-9,800e-9,8e-6,80e-6,800e-6,.008)
HEIGHTS=(.8e-9,3e-9,14e-9,35e-9,55e-9,60e-9)
CONTRAST=(.4,.45,.5,.65,.6,.45)
REGION_PITCH=80e-6
RELIEF=.55e-6
ANCHOR_RADIUS=2e-6


def _admit(x_m,y_m):
    x,y=np.broadcast_arrays(_coordinates(x_m),_coordinates(y_m))
    if np.any(np.abs(x)>.055) or np.any(np.abs(y)>.055):raise ValueError('specimen coordinate outside fixed domain')
    return x,y


def _hash_scalar(ix,iy,level,seeds):
    h=(((ix%P)^seeds[0])*104729+((iy%P)^seeds[1])*130363+(level+1)*155921+seeds[2])%P
    return (h*h+48271*h+seeds[2])%P


def _hash_array(ix,iy,level,seeds):
    # Every intermediate fits signed int64. This is a deterministic coordinate
    # mixer,not a cryptographic privacy claim. Private seed values stay private.
    h=(((ix%P)^seeds[0])*104729+((iy%P)^seeds[1])*130363+(level+1)*155921+seeds[2])%P
    return (h*h+48271*h+seeds[2])%P


def _parameters_scalar(ix,iy,level,seeds):
    h=_hash_scalar(ix,iy,level,seeds);values=[]
    for k in range(9):
        h=(h*48271+(k+1)*1031)%P;h=((h^(h>>13))*69621)%P
        values.append((h+.5)/P)
    return values


def _parameters_array(ix,iy,level,seeds):
    h=_hash_array(ix,iy,level,seeds);values=[]
    for k in range(9):
        h=(h*48271+(k+1)*1031)%P;h=((h^(h>>13))*69621)%P
        values.append((h.astype(np.float64)+.5)/P)
    return values


@dataclass(frozen=True)
class HierarchicalSpecimen:
    seed:bytes=field(default=b'vesm-hierarchical-low-relief-v1',repr=False)
    _seeds:tuple=field(init=False,repr=False)
    _anchor:object=field(init=False,repr=False,compare=False)

    def __post_init__(self):
        if type(self.seed) is not bytes or not 1<=len(self.seed)<=128:raise ValueError('private bounded seed required')
        raw=hashlib.blake2b(b'vesm-hierarchical-fields-v1:'+self.seed,digest_size=24).digest()
        object.__setattr__(self,'_seeds',tuple(int.from_bytes(raw[i:i+8],'little')%P for i in (0,8,16)))
        object.__setattr__(self,'_anchor',HumanAlignmentSpecimen(seed=self.seed))

    def material_codes(self,x_m,y_m):
        x,y=_admit(x_m,y_m)
        ix=np.floor(x/REGION_PITCH).astype(np.int64);iy=np.floor(y/REGION_PITCH).astype(np.int64)
        return tuple((_hash_array(ix,iy,level,self._seeds)%3).astype(np.int8) for level in (8,13,21))

    def surface(self,x_m,y_m):
        # Independent scalar implementation,using Python integer and libm ops.
        ax,ay=_admit(x_m,y_m)
        if ax.ndim!=0 or ay.ndim!=0:raise ValueError('scalar specimen coordinates required')
        x,y=float(ax),float(ay)
        z=sx=sy=material=0.
        for level,(pitch,height,contrast) in enumerate(zip(PITCHES,HEIGHTS,CONTRAST)):
            bx,by=math.floor(x/pitch),math.floor(y/pitch)
            for di in (-1,0,1):
                for dj in (-1,0,1):
                    ix,iy=bx+di,by+dj;q=_parameters_scalar(ix,iy,level,self._seeds)
                    region_x=math.floor(((ix+.5)*pitch)/REGION_PITCH)
                    region_y=math.floor(((iy+.5)*pitch)/REGION_PITCH)
                    rh=_hash_scalar(region_x,region_y,8,self._seeds);family=rh%3
                    angle=(2*math.pi*rh/P+.4*(q[2]-.5)) if family==2 else 2*math.pi*q[2]
                    ca,sa=math.cos(angle),math.sin(angle)
                    cx=(ix+.2+.6*q[0])*pitch;cy=(iy+.2+.6*q[1])*pitch
                    rx=(.96 if family==2 else .62+.30*q[3])*pitch
                    ry=(.14+.12*q[4] if family==2 else .42+.36*q[4])*pitch
                    u=ca*(x-cx)+sa*(y-cy);v=-sa*(x-cx)+ca*(y-cy)
                    r=math.hypot(u/rx,v/ry)
                    if r>=1:continue
                    a=1-r;bump=a**4*(4*r+1);du=-20*a**3*u/(rx*rx);dv=-20*a**3*v/(ry*ry)
                    pattern,pv=1.,0.
                    if family==2:
                        k=2*math.pi/(.28*pitch);phase=k*v+2*math.pi*q[7]
                        pattern=.7+.3*math.cos(phase);pv=-.3*k*math.sin(phase)
                    value=bump*pattern;bu=du*pattern;bv=dv*pattern+bump*pv
                    h=height*(.3+.7*q[5])*(-1 if family==1 else 1)
                    m=contrast*((-.3-.7*q[6]) if family==1 else .15+.85*q[6])
                    z+=h*value;sx+=h*(ca*bu-sa*bv);sy+=h*(sa*bu+ca*bv);material+=m*value
        p=2*math.pi*(x/136e-9+y/233e-9);q=2*math.pi*((x-.3*y)/311e-9)+self._seeds[0]/P
        wave=math.sin(p)+.5*math.sin(q)
        z+=.15e-9*wave;material+=.05*wave
        sx+=.15e-9*2*math.pi*(math.cos(p)/136e-9+.5*math.cos(q)/311e-9)
        sy+=.15e-9*2*math.pi*(math.cos(p)/233e-9-.15*math.cos(q)/311e-9)
        r2=(x*x+y*y)/ANCHOR_RADIUS**2
        if r2<1:
            a,b,c,se=self._anchor.surface(x,y);w=(1-r2)**3
            dwx=-6*x*(1-r2)**2/ANCHOR_RADIUS**2;dwy=-6*y*(1-r2)**2/ANCHOR_RADIUS**2
            z+=w*a;sx+=w*b+dwx*a;sy+=w*c+dwy*a
            material+=w*math.atanh(max(-1+2**-52,min(1-2**-52,(se-.22)/.10)))
        t=math.tanh(z/RELIEF)
        return RELIEF*t,(1-t*t)*sx,(1-t*t)*sy,.22+.10*math.tanh(material)

    def _raw_arrays(self,x_m,y_m):
        x,y=_admit(x_m,y_m)
        z,sx,sy,material=(np.zeros_like(x) for _ in range(4))
        for level,(pitch,height,contrast) in enumerate(zip(PITCHES,HEIGHTS,CONTRAST)):
            bx,by=np.floor(x/pitch).astype(np.int64),np.floor(y/pitch).astype(np.int64)
            for di in (-1,0,1):
                for dj in (-1,0,1):
                    ix,iy=bx+di,by+dj;q=_parameters_array(ix,iy,level,self._seeds)
                    region_x=np.floor(((ix+.5)*pitch)/REGION_PITCH).astype(np.int64)
                    region_y=np.floor(((iy+.5)*pitch)/REGION_PITCH).astype(np.int64)
                    rh=_hash_array(region_x,region_y,8,self._seeds);family=rh%3
                    angle=np.where(family==2,2*math.pi*rh/P+.4*(q[2]-.5),2*math.pi*q[2])
                    ca,sa=np.cos(angle),np.sin(angle)
                    cx=(ix+.2+.6*q[0])*pitch;cy=(iy+.2+.6*q[1])*pitch
                    rx=np.where(family==2,.96,.62+.30*q[3])*pitch
                    ry=np.where(family==2,.14+.12*q[4],.42+.36*q[4])*pitch
                    u=ca*(x-cx)+sa*(y-cy);v=-sa*(x-cx)+ca*(y-cy)
                    r=np.hypot(u/rx,v/ry);a=np.maximum(0.,1-r)
                    bump=a**4*(4*r+1);du=-20*a**3*u/(rx*rx);dv=-20*a**3*v/(ry*ry)
                    k=2*math.pi/(.28*pitch);phase=k*v+2*math.pi*q[7]
                    pattern=np.where(family==2,.7+.3*np.cos(phase),1.)
                    pv=np.where(family==2,-.3*k*np.sin(phase),0.)
                    value=bump*pattern;bu=du*pattern;bv=dv*pattern+bump*pv
                    h=height*(.3+.7*q[5])*np.where(family==1,-1.,1.)
                    m=contrast*np.where(family==1,-.3-.7*q[6],.15+.85*q[6])
                    z+=h*value;sx+=h*(ca*bu-sa*bv);sy+=h*(sa*bu+ca*bv);material+=m*value
        return z,sx,sy,material

    def surface_arrays(self,x_m,y_m):
        x,y=_admit(x_m,y_m)
        z,sx,sy,material=self._raw_arrays(x,y)
        p=2*math.pi*(x/136e-9+y/233e-9);q=2*math.pi*((x-.3*y)/311e-9)+self._seeds[0]/P
        wave=np.sin(p)+.5*np.sin(q)
        z+=.15e-9*wave;material+=.05*wave
        sx+=.15e-9*2*math.pi*(np.cos(p)/136e-9+.5*np.cos(q)/311e-9)
        sy+=.15e-9*2*math.pi*(np.cos(p)/233e-9-.15*np.cos(q)/311e-9)
        r2=(x*x+y*y)/ANCHOR_RADIUS**2;mask=r2<1
        if np.any(mask):
            a,b,c,se=self._anchor.surface_arrays(x[mask],y[mask]);w=(1-r2[mask])**3
            dwx=-6*x[mask]*(1-r2[mask])**2/ANCHOR_RADIUS**2;dwy=-6*y[mask]*(1-r2[mask])**2/ANCHOR_RADIUS**2
            z[mask]+=w*a;sx[mask]+=w*b+dwx*a;sy[mask]+=w*c+dwy*a
            material[mask]+=w*np.arctanh(np.clip((se-.22)/.10,-1+2**-52,1-2**-52))
        t=np.tanh(z/RELIEF)
        return RELIEF*t,(1-t*t)*sx,(1-t*t)*sy,.22+.10*np.tanh(material)
