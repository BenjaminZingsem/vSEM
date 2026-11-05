"""Fixed patterned conductive coupon with sharp,asymmetric SEM alignment detail.

New generic analytic specimen. All patterns live in specimen coordinates and
have finite smooth edge scales. No focus,view,acquisition or random frame input.
"""
import math
import numpy as np
from .fine_practice_specimen import FinePracticeSpecimen

EDGE_M=8e-9
RELIEF_M=.55e-6
HOLES=((.68,-.17,.105),(.76,.28,.075),(.35,.65,.11),(-.24,.68,.065),(.15,-.85,.13))

def _scalar_rectangle(x,y,a,b,c,d):
    txa,txb=math.tanh((x-a)/EDGE_M),math.tanh((b-x)/EDGE_M)
    tyc,tyd=math.tanh((y-c)/EDGE_M),math.tanh((d-y)/EDGE_M)
    ax,bx,cy,dy=(1+txa)/2,(1+txb)/2,(1+tyc)/2,(1+tyd)/2
    sx,sy=ax*bx,cy*dy
    dsx=((1-txa*txa)*bx-ax*(1-txb*txb))/(2*EDGE_M)
    dsy=((1-tyc*tyc)*dy-cy*(1-tyd*tyd))/(2*EDGE_M)
    return sx*sy,dsx*sy,sx*dsy

def _array_rectangle(x,y,a,b,c,d):
    txa,txb=np.tanh((x-a)/EDGE_M),np.tanh((b-x)/EDGE_M)
    tyc,tyd=np.tanh((y-c)/EDGE_M),np.tanh((d-y)/EDGE_M)
    ax,bx,cy,dy=(1+txa)/2,(1+txb)/2,(1+tyc)/2,(1+tyd)/2
    sx,sy=ax*bx,cy*dy
    dsx=((1-txa*txa)*bx-ax*(1-txb*txb))/(2*EDGE_M)
    dsy=((1-tyc*tyc)*dy-cy*(1-tyd*tyd))/(2*EDGE_M)
    return sx*sy,dsx*sy,sx*dsy

class HumanAlignmentSpecimen(FinePracticeSpecimen):
    def surface(self,x_m,y_m):
        x,y=float(x_m),float(y_m)
        if not math.isfinite(x) or not math.isfinite(y):raise ValueError('Finite specimen coordinate required')
        height,sx,sy,se=super().surface(x,y)
        material=0.
        for rect in ((-.75e-6,-.61e-6,-.65e-6,.62e-6),(-.75e-6,.56e-6,-.65e-6,-.51e-6)):
            value,dx,dy=_scalar_rectangle(x,y,*rect)
            height+=12e-9*value;sx+=12e-9*dx;sy+=12e-9*dy;material+=.8*value
        value,dx,dy=_scalar_rectangle(x,y,-.48e-6,.32e-6,-.30e-6,.28e-6)
        k=2*math.pi/.12e-6;angle=k*(x-.035e-6);wave=math.tanh(math.sin(angle)/.45)
        pattern=(1+wave)/2;derivative=(1-wave*wave)*math.cos(angle)*k/(2*.45)
        shape=value*pattern;gx=dx*pattern+value*derivative;gy=dy*pattern
        height+=8e-9*shape;sx+=8e-9*gx;sy+=8e-9*gy;material+=.75*shape
        for cx,cy,radius in HOLES:
            dx,dy=x-cx*1e-6,y-cy*1e-6;r=radius*1e-6
            t=math.tanh((dx*dx+dy*dy-r*r)/(2*r*EDGE_M));value=(1-t)/2
            gx=-(1-t*t)*dx/(2*r*EDGE_M);gy=-(1-t*t)*dy/(2*r*EDGE_M)
            height-=8e-9*value;sx-=8e-9*gx;sy-=8e-9*gy;material-=.9*value
        t=math.tanh(height/RELIEF_M)
        phase=math.atanh(max(-1+2**-52,min(1-2**-52,(se-.22)/.10)))
        return RELIEF_M*t,(1-t*t)*sx,(1-t*t)*sy,.22+.10*math.tanh(phase+material)

    def surface_arrays(self,x_m,y_m):
        x,y=np.broadcast_arrays(np.asarray(x_m,dtype=np.float64),np.asarray(y_m,dtype=np.float64))
        if not np.isfinite(x).all() or not np.isfinite(y).all():raise ValueError('Finite specimen coordinate required')
        height,sx,sy,se=(np.array(a,copy=True) for a in super().surface_arrays(x,y))
        material=np.zeros_like(x)
        for rect in ((-.75e-6,-.61e-6,-.65e-6,.62e-6),(-.75e-6,.56e-6,-.65e-6,-.51e-6)):
            value,dx,dy=_array_rectangle(x,y,*rect)
            height+=12e-9*value;sx+=12e-9*dx;sy+=12e-9*dy;material+=.8*value
        value,dx,dy=_array_rectangle(x,y,-.48e-6,.32e-6,-.30e-6,.28e-6)
        k=2*math.pi/.12e-6;angle=k*(x-.035e-6);wave=np.tanh(np.sin(angle)/.45)
        pattern=(1+wave)/2;derivative=(1-wave*wave)*np.cos(angle)*k/(2*.45)
        shape=value*pattern;gx=dx*pattern+value*derivative;gy=dy*pattern
        height+=8e-9*shape;sx+=8e-9*gx;sy+=8e-9*gy;material+=.75*shape
        for cx,cy,radius in HOLES:
            dx,dy=x-cx*1e-6,y-cy*1e-6;r=radius*1e-6
            t=np.tanh((dx*dx+dy*dy-r*r)/(2*r*EDGE_M));value=(1-t)/2
            gx=-(1-t*t)*dx/(2*r*EDGE_M);gy=-(1-t*t)*dy/(2*r*EDGE_M)
            height-=8e-9*value;sx-=8e-9*gx;sy-=8e-9*gy;material-=.9*value
        t=np.tanh(height/RELIEF_M)
        phase=np.arctanh(np.clip((se-.22)/.10,-1+2**-52,1-2**-52))
        return RELIEF_M*t,(1-t*t)*sx,(1-t*t)*sy,.22+.10*np.tanh(phase+material)
