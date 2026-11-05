"""Primary Gaussian interception by a finite grounded specimen,not an image mask.

Use the frozen correlated-Gaussian rectangle primitive. Positive exterior
pieces preserve tiny escaped mass. Whole-beam underflow guards avoid all world
queries in remote vacuum. No optical field,generator,ledger or operator access.
"""
from dataclasses import dataclass
import math
from .beam_profile import Covariance2D
from .human_episode_types import real
from .primary_fluence import rectangle_probability

GLOBAL_BOUND=.055


def bounds_rectangle(value):
    if type(value) is not tuple or len(value)!=4:raise ValueError('exact immutable specimen rectangle required')
    result=tuple(real(n,-.05,.05) for n in value)
    if result[0]>=result[1] or result[2]>=result[3]:raise ValueError('positive finite specimen rectangle required')
    return result


@dataclass(frozen=True)
class FiniteAbsorption:
    center_x_m:float
    center_y_m:float
    covariance:Covariance2D
    bounds_m:tuple
    absorbed_probability:float
    escaped_probability:float
    raw_absorbed_probability:float
    raw_escaped_probability:float
    raw_closure_residual:float

    def __post_init__(self):
        if type(self.covariance) is not Covariance2D:raise ValueError('exact primary covariance required')
        bounds_rectangle(self.bounds_m)
        real(self.center_x_m,-GLOBAL_BOUND,GLOBAL_BOUND);real(self.center_y_m,-GLOBAL_BOUND,GLOBAL_BOUND)
        for value in (self.absorbed_probability,self.escaped_probability,self.raw_absorbed_probability,self.raw_escaped_probability):
            if type(value) is not float or not math.isfinite(value) or not 0<=value<=1:
                raise ValueError('finite nonnegative physical probabilities required')
        if (abs(math.fsum((self.absorbed_probability,self.escaped_probability,-1.)))>8*math.ulp(1.) or
            type(self.raw_closure_residual) is not float or not math.isfinite(self.raw_closure_residual) or
            abs(self.raw_closure_residual)>8e-15):raise ValueError('absorption/escape closure failed')


def finite_absorption(covariance,center_x_m,center_y_m,bounds_m):
    bounds=bounds_rectangle(bounds_m);cx=real(center_x_m,-GLOBAL_BOUND,GLOBAL_BOUND);cy=real(center_y_m,-GLOBAL_BOUND,GLOBAL_BOUND)
    # Public frozen validation also enforces5..200nm principal RMS. Its zero-area
    # case does no integration and does not bypass any physical type/domain gate.
    rectangle_probability(covariance,cx,cy,0.,0.,0.,0.)
    sx,sy=math.sqrt(covariance.xx_m2),math.sqrt(covariance.yy_m2)
    x0,x1,y0,y1=bounds
    outside_x=max(x0-cx,cx-x1,0.);outside_y=max(y0-cy,cy-y1,0.)
    def zero_tail(distance,sigma):return .5*math.erfc(distance/(math.sqrt(2)*sigma))==0.
    if (outside_x>0 and zero_tail(outside_x,sx)) or (outside_y>0 and zero_tail(outside_y,sy)):
        inside,outside=0.,1.
    elif (x0<=cx<=x1 and y0<=cy<=y1 and all((zero_tail(cx-x0,sx),zero_tail(x1-cx,sx),
            zero_tail(cy-y0,sy),zero_tail(y1-cy,sy)))):
        inside,outside=1.,0.
    else:
        distances=(cx-x0,x1-cx,cy-y0,y1-cy);sigmas=(sx,sx,sy,sy)
        relevant=[i for i,(distance,sigma) in enumerate(zip(distances,sigmas)) if not zero_tail(distance,sigma)]
        if len(relevant)==1:
            # One finite face;all other positive tails provably underflow.
            # A marginal Gaussian is exact even for correlated primary rays.
            i=relevant[0];t=distances[i]/(math.sqrt(2)*sigmas[i])
            inside,outside=.5*math.erfc(-t),.5*math.erfc(t)
            residual=math.fsum((inside,outside,-1.))
            absorbed,escaped=(inside,1.-inside) if inside<=outside else (1.-outside,outside)
            return FiniteAbsorption(cx,cy,covariance,bounds,float(absorbed),float(escaped),float(inside),float(outside),float(residual))
        inside=rectangle_probability(covariance,cx,cy,x0,x1,y0,y1)
        # The sample is inside+-50mm. Every beam capable of intersecting it is
        # over5mm from the+-55mm global boundary,>25,000 maximum RMS. Probability
        # beyond that outer box underflows IEEE64;remote rays took the guard above.
        pieces=((-GLOBAL_BOUND,x0,-GLOBAL_BOUND,GLOBAL_BOUND),(x1,GLOBAL_BOUND,-GLOBAL_BOUND,GLOBAL_BOUND),
            (x0,x1,-GLOBAL_BOUND,y0),(x0,x1,y1,GLOBAL_BOUND))
        outside=math.fsum(rectangle_probability(covariance,cx,cy,*piece) for piece in pieces)
    residual=math.fsum((inside,outside,-1.))
    if abs(residual)>8e-15:raise ValueError('independent inside/outside Gaussian closure failed')
    # Preserve the positively computed smaller probability,especially tiny
    # escaped tails. This balances numerical complement error;it never rescales
    # the intercepted beam to unit mass or invents signal in vacuum.
    if inside<=outside:absorbed,escaped=inside,1.-inside
    else:absorbed,escaped=1.-outside,outside
    return FiniteAbsorption(cx,cy,covariance,bounds,float(absorbed),float(escaped),float(inside),float(outside),float(residual))


def split_incident_charge(charge_C,absorption):
    if type(absorption) is not FiniteAbsorption:raise ValueError('exact finite absorption required')
    return split_probability_charge(charge_C,absorption.absorbed_probability,absorption.escaped_probability)


def split_probability_charge(charge_C,absorbed_probability,escaped_probability):
    q=real(charge_C,0.,float('inf'))
    for value in (absorbed_probability,escaped_probability):
        if type(value) is not float or not math.isfinite(value) or not 0<=value<=1.:
            raise ValueError('exact finite physical probabilities required')
    if abs(math.fsum((absorbed_probability,escaped_probability,-1.)))>8*math.ulp(1.):
        raise ValueError('closed finite physical probabilities required')
    if absorbed_probability<=escaped_probability:
        absorbed=q*absorbed_probability;escaped=math.fsum((q,-absorbed))
    else:
        escaped=q*escaped_probability;absorbed=math.fsum((q,-escaped))
    if (not math.isfinite(absorbed) or not math.isfinite(escaped) or min(absorbed,escaped)<0 or
        abs(math.fsum((absorbed,escaped,-q)))>8*math.ulp(q)+1e-30):
        raise ValueError('finite incident/absorbed/escaped charge closure failed')
    return absorbed,escaped
