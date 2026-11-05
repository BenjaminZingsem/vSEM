"""Private original procedural coupon; generic geometry, not measured SEM truth.

A finite C2 scene in specimen metres. No acquisition, clock, renderer, transport
or image assets live here. Surface identity is independent of view and sampling.
"""
from dataclasses import dataclass, field
import hashlib
import math
import random
import numpy as np

RELIEF_LIMIT_M = 0.55e-6
BASE_YIELD = 0.22
YIELD_SPAN = 0.10
MIN_SUPPORT_RADIUS_M = 1.2e-6
MIN_PATTERN_PERIOD_M = 1.8e-6


@dataclass(frozen=True)
class _Feature:
    x: float
    y: float
    rx: float
    ry: float
    angle: float
    height: float
    contrast: float
    kind: str = 'particle'
    period: float = 1.8e-6
    phase: float = 0.0
    step_width: float = 0.8e-6
    c: float = field(init=False, repr=False)
    s: float = field(init=False, repr=False)
    bx: float = field(init=False, repr=False)
    by: float = field(init=False, repr=False)

    def __post_init__(self):
        c, s = math.cos(self.angle), math.sin(self.angle)
        object.__setattr__(self, 'c', c)
        object.__setattr__(self, 's', s)
        object.__setattr__(self, 'bx', math.hypot(self.rx*c, self.ry*s))
        object.__setattr__(self, 'by', math.hypot(self.rx*s, self.ry*c))

    def scalar(self, x, y):
        # Projection bounds skip unrelated features without truncating their
        # actual support. Wendland C2 is already exactly zero at r >= 1.
        if abs(x-self.x) >= self.bx or abs(y-self.y) >= self.by:
            return 0.0, 0.0, 0.0, 0.0
        u = self.c*(x-self.x)+self.s*(y-self.y)
        v = -self.s*(x-self.x)+self.c*(y-self.y)
        r = math.hypot(u/self.rx, v/self.ry)
        if r >= 1:
            return 0.0, 0.0, 0.0, 0.0
        a = 1-r
        bump = a**4*(4*r+1)
        du = -20*a**3*u/self.rx**2
        dv = -20*a**3*v/self.ry**2
        pattern, pu, pv = 1.0, 0.0, 0.0
        if self.kind in ('ridges', 'cross'):
            k = 2*math.pi/self.period
            pattern, pu = math.sin(k*u+self.phase), k*math.cos(k*u+self.phase)
            if self.kind == 'cross':
                sv, cv = math.sin(.73*k*v), math.cos(.73*k*v)
                pv, pattern, pu = -.73*k*pattern*sv, pattern*cv, pu*cv
        elif self.kind == 'terrace':
            t = math.tanh(u/self.step_width)
            pattern, pu = .5*(1+t), .5*(1-t*t)/self.step_width
        bu, bv = du*pattern+bump*pu, dv*pattern+bump*pv
        shape = bump*pattern
        return (self.height*shape, self.height*(self.c*bu-self.s*bv),
                self.height*(self.s*bu+self.c*bv), self.contrast*shape)

    def arrays(self, x, y):
        # Independent float64 formulas; work only on the intersecting support.
        u = self.c*(x-self.x)+self.s*(y-self.y)
        v = -self.s*(x-self.x)+self.c*(y-self.y)
        r = np.hypot(u/self.rx, v/self.ry)
        a = np.maximum(0.0, 1-r)
        bump = a**4*(4*r+1)
        du, dv = -20*a**3*u/self.rx**2, -20*a**3*v/self.ry**2
        pattern, pu, pv = np.ones_like(x), np.zeros_like(x), np.zeros_like(x)
        if self.kind in ('ridges', 'cross'):
            k = 2*math.pi/self.period
            pattern, pu = np.sin(k*u+self.phase), k*np.cos(k*u+self.phase)
            if self.kind == 'cross':
                sv, cv = np.sin(.73*k*v), np.cos(.73*k*v)
                pv, pattern, pu = -.73*k*pattern*sv, pattern*cv, pu*cv
        elif self.kind == 'terrace':
            t = np.tanh(u/self.step_width)
            pattern, pu = .5*(1+t), .5*(1-t*t)/self.step_width
        bu, bv = du*pattern+bump*pu, dv*pattern+bump*pv
        shape = bump*pattern
        return (self.height*shape, self.height*(self.c*bu-self.s*bv),
                self.height*(self.s*bu+self.c*bv), self.contrast*shape)


def _scene(seed):
    um = 1e-6
    def f(x, y, rx, ry, angle, height, contrast, kind='particle', period=1.8, phase=0.0):
        return _Feature(x*um,y*um,rx*um,ry*um,math.radians(angle),height*um,
                        contrast,kind,period*um,phase)
    features = [
        # Multiscale substrate relief and broad asymmetric terraces.
        f(-17,-13,65,48,23,.06,-.18,'terrace'),
        f(16,24,43,29,-31,.08,.12),
        f(0,-12,18,8,14,.19,.22,'terrace'),
        # Upper-left L-shaped pair, with one offset small satellite.
        f(-12,10,1.7,5.0,-10,.31,.60),
        f(-9.2,7.1,4.8,1.7,-10,.26,.48),
        f(-10.1,15.2,1.3,1.6,35,.20,.35),
        # Notched oval annulus, made from bounded smooth relief contributions.
        f(11,-8,4.2,3.5,24,.36,.55),
        f(11,-8,2.1,1.8,24,-.31,-.48),
        f(13.5,-6.1,1.7,1.3,24,-.17,-.27),
        # Separate, differently oriented patterned islands; no global tiling.
        f(10,10,7.5,6.0,27,.12,.24),
        f(10,10,6.5,5.0,27,.035,.10,'ridges',1.8,.3),
        f(-1,-2,6.3,5.0,-18,.030,.12,'cross',2.1,.7),
        f(-18,-5,5.0,2.0,61,.14,-.28),
        f(20,0,1.5,3.3,-38,.23,.42),
    ]
    rng = random.Random(int.from_bytes(hashlib.blake2b(seed,digest_size=32).digest(),'big'))
    # Fixed finite particle locations with private deterministic variation.
    # Neither a lattice repeat nor view-dependent noise is generated.
    places = ((-20,18),(-21,5),(-19,-16),(-9,-18),(-4,17),(4,18),(19,19),
              (22,-15),(3,-21),(-4,5),(4,2),(-16,-24),(29,8),(-32,-2),
              (34,-28),(-42,30),(55,17),(-58,-34),(7,60),(28,74))
    for x,y in places:
        features.append(f(x+rng.uniform(-1.3,1.3),y+rng.uniform(-1.3,1.3),
                          rng.uniform(1.2,2.8),rng.uniform(1.2,3.5),rng.uniform(-90,90),
                          rng.uniform(.07,.24),rng.uniform(-.30,.65)))
    return tuple(features)


@dataclass(frozen=True)
class ProceduralSpecimen:
    seed: bytes = field(default=b'vesm-procedural-coupon-v1', repr=False)
    _features: tuple = field(init=False, repr=False)

    def __post_init__(self):
        if type(self.seed) is not bytes or not 1 <= len(self.seed) <= 128:
            raise ValueError('private procedural seed must be 1..128 bytes')
        object.__setattr__(self,'_features',_scene(self.seed))

    def surface(self, x_m, y_m):
        if not math.isfinite(x_m) or not math.isfinite(y_m):
            raise ValueError('finite specimen coordinates required')
        z = dx = dy = material = 0.0
        for feature in self._features:
            a,b,c,d = feature.scalar(x_m,y_m)
            z += a; dx += b; dy += c; material += d
        t = math.tanh(z/RELIEF_LIMIT_M)
        return (RELIEF_LIMIT_M*t, (1-t*t)*dx, (1-t*t)*dy,
                BASE_YIELD+YIELD_SPAN*math.tanh(material))

    def surface_arrays(self, x_m, y_m):
        x,y = np.broadcast_arrays(np.asarray(x_m,dtype=np.float64),np.asarray(y_m,dtype=np.float64))
        if not np.isfinite(x).all() or not np.isfinite(y).all():
            raise ValueError('finite specimen coordinates required')
        z,dx,dy,material = (np.zeros_like(x) for _ in range(4))
        if x.size:
            xmin,xmax,ymin,ymax = float(x.min()),float(x.max()),float(y.min()),float(y.max())
            for f in self._features:
                # Coarse disjointness avoids allocating an array per distant
                # feature for each immutable quadrature response.
                if xmax < f.x-f.bx or xmin > f.x+f.bx or ymax < f.y-f.by or ymin > f.y+f.by:
                    continue
                mask = (np.abs(x-f.x)<f.bx)&(np.abs(y-f.y)<f.by)
                if not mask.any():
                    continue
                a,b,c,d = f.arrays(x[mask],y[mask])
                z[mask] += a; dx[mask] += b; dy[mask] += c; material[mask] += d
        t = np.tanh(z/RELIEF_LIMIT_M)
        return RELIEF_LIMIT_M*t,(1-t*t)*dx,(1-t*t)*dy,BASE_YIELD+YIELD_SPAN*np.tanh(material)
